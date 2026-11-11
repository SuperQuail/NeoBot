"""QQ 官方消息发送：纯文本 / 显式 Markdown / 富媒体的单条发送。

官方 v2 一段消息体只承载一种内容，没有自动降级：Markdown 被拒、被动回复额度
用尽、媒体上传失败都直接返回 failed 并记录 info 日志，不会改写内容或改发主动
消息。被动回复必须带官方 msg_id + 递增 msg_seq，且只在官方时限内可用。
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_adapter.model import response
from neobot_adapter.official.auth import OfficialAuthError
from neobot_adapter.official.identity import IdentityMap, MessageIdMap
from neobot_adapter.official.media import MediaUploader, api_data
from neobot_adapter.official.settings import OfficialSettings

#: 官方被动回复限额：群 5 分钟内同一 msg_id 最多 5 条；单聊 60 分钟内最多 4 条。
_PASSIVE_LIMITS = {"group": (5, 300.0), "private": (4, 3600.0)}
#: 每个会话缓存多少个候选 msg_id；最新的优先用。
_PASSIVE_CANDIDATES = 8
_TEXT_LIMIT = 4000
_API_TIMEOUT_SECONDS = 10.0
_MESSAGE_ENDPOINTS = {
    "group": "/v2/groups/{openid}/messages",
    "private": "/v2/users/{openid}/messages",
}
_MEDIA_SEGMENTS = frozenset({"image", "record", "voice", "video", "file"})
_OFFICIAL_MARKDOWN_SEGMENT = "official_markdown"
#: Markdown 段里允许出现的内嵌 @：id 是 13 位合成号，发送前换成 member_openid。
_AT_USER_TAG = re.compile(r'<qqbot-at-user\s+id="(\d+)"\s*/?>')
_AT_EVERYONE_TAG = re.compile(r"<qqbot-at-everyone\s*/?>")


class OfficialApiError(RuntimeError):
    """官方 HTTP 接口返回的业务/传输错误。"""

    def __init__(
        self,
        message: str,
        *,
        code: int | str | None = None,
        status: int = 0,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.payload = payload or {}


class OfficialApi:
    """官方 HTTP 接口的最小客户端；token 失效（401）时刷新后重试一次。"""

    def __init__(
        self,
        settings: OfficialSettings,
        token_provider: Any,
        logger: Logger | None = None,
        *,
        http: Any | None = None,
    ) -> None:
        self._settings = settings
        self._token_provider = token_provider
        self._logger = logger if logger is not None else NullLogger()
        self._session = http
        self._owns_session = False

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        timeout: float = _API_TIMEOUT_SECONDS,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        """调用官方 HTTP API，返回原始 JSON 对象；失败抛 OfficialApiError。"""
        url = f"{self._settings.base_url.rstrip('/')}{path}"
        token = await self._token_provider.get_token()
        status, payload = await self._send(method, url, body, token, timeout)
        if status == 401 and retry_auth:
            self._logger.info("官方接口 token 失效，刷新后重试一次")
            token = await self._token_provider.get_token(force=True)
            status, payload = await self._send(method, url, body, token, timeout)
        code = _error_code(payload)
        if status >= 400 or code not in (None, 0, "0"):
            raise OfficialApiError(
                _error_message(payload),
                code=code,
                status=status,
                payload=payload,
            )
        return payload

    async def _send(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None,
        token: str,
        timeout: float,
    ) -> tuple[int, dict[str, Any]]:
        session = await self._ensure_session()
        headers = {
            "Authorization": f"QQBot {token}",
            "Accept": "application/json",
        }
        try:
            async with session.request(
                method,
                url,
                json=body,
                headers=headers,
                timeout=_timeout(timeout),
            ) as raw:
                status = int(getattr(raw, "status", 0) or 0)
                payload = await _read_json(raw)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise OfficialApiError(f"请求官方接口失败: {type(exc).__name__}: {exc}") from exc
        if not isinstance(payload, dict):
            raise OfficialApiError(f"官方接口响应格式异常（HTTP {status}）", status=status)
        return status, payload

    async def _ensure_session(self) -> Any:
        if self._session is None:
            import aiohttp

            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        session = self._session
        self._session = None
        if session is not None and self._owns_session:
            await session.close()
        self._owns_session = False


async def _read_json(raw: Any) -> Any:
    """读响应体；204/空响应按空对象处理（删除接口成功时无 body）。"""
    try:
        return await raw.json(content_type=None)
    except asyncio.CancelledError:
        raise
    except Exception:
        pass
    try:
        text = await raw.text()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise OfficialApiError(f"读取官方接口响应失败: {type(exc).__name__}: {exc}") from exc
    if not str(text or "").strip():
        return {}
    import json

    try:
        return json.loads(text)
    except ValueError as exc:
        raise OfficialApiError("官方接口响应不是合法 JSON") from exc


def _timeout(seconds: float) -> Any:
    import aiohttp

    return aiohttp.ClientTimeout(total=seconds)


def _error_code(payload: dict[str, Any]) -> int | str | None:
    """错误码优先取 err_code（官方 OpenAPI），兼容 code/biz_code。"""
    for key in ("err_code", "code", "biz_code"):
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        text = str(value).strip()
        if not text:
            continue
        try:
            return int(text)
        except ValueError:
            return text
    return None


def _error_message(payload: dict[str, Any]) -> str:
    return (
        str(payload.get("err_msg") or payload.get("message") or payload.get("msg") or "").strip() or "官方接口返回失败"
    )


class PassiveReplyCache:
    """每个会话的被动回复候选 msg_id、限额计数与递增 msg_seq。"""

    def __init__(
        self,
        *,
        limits: dict[str, tuple[int, float]] | None = None,
        candidates: int = _PASSIVE_CANDIDATES,
        clock: Any = time.monotonic,
    ) -> None:
        self._limits = limits or _PASSIVE_LIMITS
        self._candidates = max(1, int(candidates))
        self._clock = clock
        #: conversation key -> deque[[msg_id, 收到时间, 已用次数]]
        self._entries: dict[str, deque[list[Any]]] = {}
        #: conversation key -> 已分配的 msg_seq；同一 msg_id 下单调递增即不会撞车。
        self._seq: dict[str, int] = {}

    def remember(self, kind: str, conversation_id: Any, official_msg_id: str) -> None:
        """收到一条用户消息后登记，供后续被动回复使用。"""
        limit, ttl = self._limits.get(kind, _PASSIVE_LIMITS["private"])
        del limit
        key = f"{kind}:{conversation_id}"
        now = self._clock()
        entries = self._entries.setdefault(key, deque())
        entries.append([str(official_msg_id), now, 0])
        while len(entries) > self._candidates:
            entries.popleft()
        while entries and now - entries[0][1] > ttl:
            entries.popleft()

    def acquire(self, kind: str, conversation_id: Any) -> tuple[str | None, str]:
        """取一个还能用的被动回复目标。

        返回 (msg_id, 失败原因)；msg_id 为空表示官方不允许再被动回复，调用方
        必须直接失败——不会转成主动消息。
        """
        limit, ttl = self._limits.get(kind, _PASSIVE_LIMITS["private"])
        key = f"{kind}:{conversation_id}"
        entries = self._entries.get(key)
        if not entries:
            return None, "没有可用的被动回复目标（未收到可回复的官方消息）"
        now = self._clock()
        while entries and now - entries[0][1] > ttl:
            entries.popleft()
        if not entries:
            return None, "被动回复目标已过期（群 5 分钟 / 单聊 60 分钟）"
        for entry in reversed(entries):
            if entry[2] < limit:
                entry[2] += 1
                return str(entry[0]), ""
        return None, "被动回复次数已达官方上限（群 5 次 / 单聊 4 次）"

    def next_seq(self, kind: str, conversation_id: Any) -> int:
        """同一会话内递增的 msg_seq；相同 msg_id + msg_seq 会被官方去重拒绝。"""
        key = f"{kind}:{conversation_id}"
        value = self._seq.get(key, 0) + 1
        self._seq[key] = value
        return value


class _SendFailure(RuntimeError):
    """发送前置条件不满足；消息未发出。"""


@dataclass
class _Prepared:
    text: str = ""
    markdown: str | None = None
    media: list[tuple[str, str, str]] = field(default_factory=list)
    reply: str | None = None


class MessageSender:
    """把 OneBot 消息段发成官方消息；单实例绑定一次适配器运行期。"""

    def __init__(
        self,
        *,
        api: OfficialApi,
        identity: IdentityMap,
        message_ids: MessageIdMap,
        passive: PassiveReplyCache,
        media: MediaUploader,
        logger: Logger | None = None,
    ) -> None:
        self._api = api
        self._identity = identity
        self._message_ids = message_ids
        self._passive = passive
        self._media = media
        self._logger = logger if logger is not None else NullLogger()

    async def send(
        self,
        conversation: ConversationRef,
        message: str | list[dict[str, Any]],
        timeout: float = _API_TIMEOUT_SECONDS,
        *,
        proactive: bool = False,
    ) -> response.SendMsgResponse:
        """发送一条 OneBot 消息；任何失败都返回 failed，不改写内容。"""
        kind = str(conversation.kind or "")
        if kind not in _MESSAGE_ENDPOINTS:
            return self._fail(kind, conversation.id, f"官方协议不支持发送到该会话类型: {kind}")
        openid = self._openid(conversation)
        if not openid:
            return self._fail(
                kind,
                conversation.id,
                f"官方协议无法反查会话 {kind}:{conversation.id} 的 openid（该会话未在官方事件中出现过）",
            )
        try:
            prepared = _prepare(message)
            reference = self._reference_idx(prepared.reply)
            if prepared.markdown is not None:
                return await self._send_markdown(
                    kind, openid, conversation.id, prepared, reference, timeout, proactive
                )
            if not prepared.text and not prepared.media:
                return self._fail(kind, conversation.id, "消息内容为空")
            return await self._send_plain(
                kind, openid, conversation.id, prepared, reference, timeout, proactive
            )
        except _SendFailure as exc:
            return self._fail(kind, conversation.id, str(exc))
        except (OfficialApiError, OfficialAuthError) as exc:
            return self._fail(kind, conversation.id, f"官方消息发送失败：{exc}")
        except Exception as exc:
            return self._fail(
                kind,
                conversation.id,
                f"官方消息发送失败：{type(exc).__name__}: {exc}",
            )

    # ── 纯文本 / 富媒体 ──────────────────────────────────────────────

    async def _send_plain(
        self,
        kind: str,
        openid: str,
        conversation_id: Any,
        prepared: _Prepared,
        reference: str | None,
        timeout: float,
        proactive: bool,
    ) -> response.SendMsgResponse:
        sent_id: int | None = None
        if prepared.text:
            for chunk in _split_text(prepared.text):
                payload = self._message_payload(kind, conversation_id, proactive)
                payload["msg_type"] = 0
                payload["content"] = chunk
                if reference:
                    payload["message_reference"] = {"message_id": reference}
                body = await self._api.request(
                    "POST",
                    _MESSAGE_ENDPOINTS[kind].format(openid=openid),
                    body=payload,
                    timeout=timeout,
                )
                sent_id = self._track_sent(body, kind, openid) or sent_id
        for segment_type, source, file_name in prepared.media:
            media = await self._media.upload(
                self._api,
                kind=kind,
                openid=openid,
                segment_type=segment_type,
                source=source,
                file_name=file_name,
            )
            payload = self._message_payload(kind, conversation_id, proactive)
            payload["msg_type"] = 7
            payload["media"] = {"file_info": media.file_info}
            if reference:
                payload["message_reference"] = {"message_id": reference}
            body = await self._api.request(
                "POST",
                _MESSAGE_ENDPOINTS[kind].format(openid=openid),
                body=payload,
                timeout=timeout,
            )
            sent_id = self._track_sent(body, kind, openid) or sent_id
        return _ok(sent_id)

    # ── 显式 Markdown ───────────────────────────────────────────────

    async def _send_markdown(
        self,
        kind: str,
        openid: str,
        conversation_id: Any,
        prepared: _Prepared,
        reference: str | None,
        timeout: float,
        proactive: bool,
    ) -> response.SendMsgResponse:
        content = self._render_markdown_mentions(str(prepared.markdown or ""), kind)
        if not content.strip():
            raise _SendFailure("Markdown 内容为空")
        if kind == "group" and _AT_EVERYONE_TAG.search(content):
            await self._assert_can_at_everyone(openid)
        if len(content) > _TEXT_LIMIT:
            raise _SendFailure(
                f"Markdown 消息 {len(content)} 字，超过单条上限 {_TEXT_LIMIT}；请精简或改用 send_long_reply"
            )
        payload = self._message_payload(kind, conversation_id, proactive)
        payload["msg_type"] = 2
        payload["markdown"] = {"content": content}
        if reference:
            payload["message_reference"] = {"message_id": reference}
        body = await self._api.request(
            "POST",
            _MESSAGE_ENDPOINTS[kind].format(openid=openid),
            body=payload,
            timeout=timeout,
        )
        return _ok(self._track_sent(body, kind, openid))

    async def _assert_can_at_everyone(self, group_openid: str) -> None:
        """@全体成员要求机器人是群管理员；无法确认时直接失败，不做降级。"""
        try:
            body = await self._api.request("GET", f"/v2/groups/{group_openid}/bot_state")
        except OfficialApiError as exc:
            raise _SendFailure(f"无法确认 @全体成员权限：{exc}") from exc
        data = api_data(body)
        role = str(data.get("member_role") or "").strip().casefold()
        if role not in {"admin", "owner"}:
            raise _SendFailure("@全体成员需要机器人是群管理员；当前角色不支持")

    def _render_markdown_mentions(self, content: str, kind: str) -> str:
        """把 <qqbot-at-user id="合成号"> 换成 member_openid；其余官方标签原样保留。"""
        has_mention = _AT_USER_TAG.search(content) is not None
        if has_mention and kind != "group":
            raise _SendFailure("单聊消息不支持 @ 用户；请直接写昵称")
        if not has_mention:
            return content

        def replace(match: re.Match[str]) -> str:
            synthetic = int(match.group(1))
            openid = self._identity.openid(synthetic, "user")
            if not openid:
                raise _SendFailure(f"Markdown 中的 @ 用户 ID 无法反查 openid：{synthetic}")
            return f'<qqbot-at-user id="{openid}" />'

        return _AT_USER_TAG.sub(replace, content)

    # ── 公共字段 ────────────────────────────────────────────────────

    def _message_payload(
        self, kind: str, conversation_id: Any, proactive: bool
    ) -> dict[str, Any]:
        if proactive:
            return {}
        msg_id, reason = self._passive.acquire(kind, conversation_id)
        if msg_id is None:
            raise _SendFailure(reason)
        return {"msg_id": msg_id, "msg_seq": self._passive.next_seq(kind, conversation_id)}

    def _reference_idx(self, value: str | None) -> str | None:
        """reply 段的合成 id 反查引用索引；没有索引就不填 message_reference。"""
        text = str(value or "").strip()
        if not text:
            return None
        if text.startswith("REFIDX_"):
            return text
        try:
            synthetic = int(text)
        except ValueError:
            return None
        return self._message_ids.reference(synthetic)

    def _openid(self, conversation: ConversationRef) -> str | None:
        try:
            synthetic = int(str(conversation.id))
        except (TypeError, ValueError):
            return None
        return self._identity.openid(synthetic, conversation.kind)

    def _track_sent(self, body: dict[str, Any], kind: str, openid: str) -> int | None:
        official_id = _response_message_id(body)
        if not official_id:
            return None
        try:
            synthetic = self._message_ids.next(
                official_id,
                context={"kind": kind, "openid": openid, "at": time.time()},
            )
        except ValueError:
            return None
        ref_idx = _response_ref_idx(body)
        if ref_idx:
            self._message_ids.remember_reference(synthetic, ref_idx)
        return synthetic

    def _fail(self, kind: str, conversation_id: Any, reason: str) -> response.SendMsgResponse:
        # 发送失败只落 info 日志并返回 failed；绝不把错误文本发进聊天。
        self._logger.info(
            "QQ 官方消息未发送",
            conversation_kind=kind,
            conversation_id=conversation_id,
            reason=reason,
        )
        return _failed(reason)


def _prepare(message: str | list[dict[str, Any]]) -> _Prepared:
    """OneBot 消息 → 待发送内容；显式 markdown 段与其他内容段互斥。"""
    if isinstance(message, str):
        return _Prepared(text=message)
    if not isinstance(message, list):
        raise _SendFailure("消息必须是字符串或 OneBot 消息段数组")
    text_parts: list[str] = []
    markdown_parts: list[str] = []
    media: list[tuple[str, str, str]] = []
    reply: str | None = None
    for segment in message:
        if isinstance(segment, str):
            text_parts.append(segment)
            continue
        if not isinstance(segment, dict):
            raise _SendFailure(f"官方协议不支持该消息段类型：{type(segment).__name__}")
        segment_type = str(segment.get("type") or "")
        data = segment.get("data") if isinstance(segment.get("data"), dict) else {}
        if segment_type not in {"text", "at", "reply", _OFFICIAL_MARKDOWN_SEGMENT, *_MEDIA_SEGMENTS}:
            raise _SendFailure(f"官方协议不支持该消息段类型：{segment_type or 'unknown'}")
        if segment_type == "text":
            text_parts.append(str(data.get("text") or ""))
        elif segment_type == "at":
            # 纯文本消息发不出真正的 @；不制造假 @ 文本，需要 @ 请用 Markdown 卡片。
            continue
        elif segment_type == "reply":
            reply = _reply_id(data, reply)
        elif segment_type == _OFFICIAL_MARKDOWN_SEGMENT:
            markdown_parts.append(str(data.get("content") or ""))
        elif segment_type in _MEDIA_SEGMENTS:
            source = str(data.get("file") or data.get("url") or "").strip()
            if not source:
                raise _SendFailure(f"媒体消息段 {segment_type} 缺少 file/url")
            media.append(
                (
                    "record" if segment_type == "voice" else segment_type,
                    source,
                    str(data.get("name") or ""),
                )
            )
    if markdown_parts:
        if text_parts or media:
            raise _SendFailure("official_markdown 消息段不能与文本/at/富媒体段混用")
        return _Prepared(markdown="\n".join(markdown_parts), reply=reply)
    return _Prepared(text="".join(text_parts), media=media, reply=reply)


def _reply_id(data: dict[str, Any], current: str | None) -> str | None:
    """记录 reply 段的 id（合成 int 或官方 REFIDX 字符串），解析在 MessageSender。"""
    value = data.get("id")
    if value in (None, ""):
        return current
    return str(value).strip()


def _split_text(text: str, limit: int = _TEXT_LIMIT) -> list[str]:
    """按 4000 字安全切分纯文本：优先换行，其次空格，最后硬切。"""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        cut = window.rfind("\n")
        if cut <= 0:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        chunks.append(remaining)
    return chunks


def _response_message_id(body: dict[str, Any]) -> str:
    data = api_data(body)
    return str(data.get("id") or data.get("message_id") or "")


def _response_ref_idx(body: dict[str, Any]) -> str:
    data = api_data(body)
    ext_info = data.get("ext_info")
    if not isinstance(ext_info, dict):
        return ""
    return str(ext_info.get("ref_idx") or "").strip()


def _ok(message_id: int | None) -> response.SendMsgResponse:
    return response.SendMsgResponse(
        status="ok",
        retcode=0,
        message="",
        wording="",
        data=response.SendPrivateMsgData(message_id=message_id),
    )


def _failed(message: str, *, retcode: int = 1404) -> response.SendMsgResponse:
    return response.SendMsgResponse(
        status="failed",
        retcode=retcode,
        message=message,
        wording=message,
        data=None,
    )
