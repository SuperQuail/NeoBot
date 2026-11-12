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
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_adapter.model import response
from neobot_adapter.official.auth import OfficialAuthError
from neobot_adapter.official.identity import IdentityMap, MessageIdMap, resolve_openid
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
#: Markdown 段里允许出现的内嵌 @：id 可以是 openid（直通），也可以是迁移期的
#: 13 位合成号（发送前按只读映射表换成 member_openid）。
_AT_USER_TAG = re.compile(r'<qqbot-at-user\s+id="([^"]+)"\s*/?>')
_AT_USER_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_VALID_AT_USER_TAG = re.compile(r'<qqbot-at-user\s+id="[A-Za-z0-9_-]{1,128}"\s*/?>')
_AT_EVERYONE_TAG = re.compile(r"<qqbot-at-everyone\s*/?>")
_VALID_CMD_TAG = re.compile(
    r'<qqbot-cmd-(?:enter|input)\s+text="[^"\s]+"(?:\s+(?:show|reference)="[^"\s]*")*\s*/>'
)
#: 官方协议标签形态：<qqbot-...>、</qqbot-...> 与 <@openid>；只有白名单里的
#: 那几个能原样上线，其余必须降级成普通文字，否则会被客户端真的执行。
_OFFICIAL_TAG = re.compile(r"</?qqbot-[^>]*>|<@!?[^>]*>")


def neutralize_official_tags(
    text: str,
    *,
    allow_at_user: bool = False,
    allow_at_everyone: bool = False,
    allow_commands: bool = False,
) -> tuple[str, int]:
    """把白名单之外的官方标签首尾尖括号换成全角，返回 (文本, 转义个数)。

    官方 Markdown 会执行 <qqbot-at-everyone /> / <qqbot-cmd-*/>；这些标签只能
    由结构化参数生成，用户原话或模型复述里出现的同类标签必须降级成普通文字。
    """
    count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal count
        tag = match.group(0)
        if allow_at_user and _VALID_AT_USER_TAG.fullmatch(tag):
            return tag
        if allow_at_everyone and _AT_EVERYONE_TAG.fullmatch(tag):
            return tag
        if allow_commands and _VALID_CMD_TAG.fullmatch(tag):
            return tag
        count += 1
        return tag.replace("<", "＜").replace(">", "＞")

    return _OFFICIAL_TAG.sub(replace, text), count


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
    #: 结构化参数（工具层校验、这里只负责按协议拼装）；content 里同名标签一律转义。
    at_everyone: bool = False
    commands: list[dict[str, Any]] = field(default_factory=list)
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
            # 纯文本消息（msg_type=0）发不出官方标签；用户原话里的标签一律
            # 全角化，避免「复述标签」在以后某次切换成 Markdown 时被执行。
            text, neutralized = neutralize_official_tags(prepared.text)
            if neutralized:
                self._logger.info(
                    "官方纯文本已把官方标签转义为普通文字",
                    conversation_kind=kind,
                    conversation_id=conversation_id,
                    count=neutralized,
                )
            for chunk in _split_text(text):
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
        # content 来自模型/用户：只放行内嵌 @。@全体与指令按钮只能来自结构化
        # 参数，正文里手写的同名标签一律全角化，避免「复述标签」被真的执行。
        content, neutralized = neutralize_official_tags(content, allow_at_user=True)
        if neutralized:
            self._logger.info(
                "官方 Markdown 已把非结构化官方标签转义为普通文字",
                conversation_kind=kind,
                conversation_id=conversation_id,
                count=neutralized,
            )
        if prepared.at_everyone:
            if kind != "group":
                raise _SendFailure("单聊不支持 @全体成员；请直接写提醒")
            content = f"<qqbot-at-everyone /> {content}"
        for tag in _command_tags(kind, prepared.commands):
            content = f"{content}\n\n{tag}"
        if len(content) > _TEXT_LIMIT:
            raise _SendFailure(
                f"Markdown 消息 {len(content)} 字，超过单条上限 {_TEXT_LIMIT}；请精简或改用 send_long_reply"
            )
        if prepared.at_everyone:
            await self._assert_can_at_everyone(openid)
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
        """把 <qqbot-at-user id="..."> 校验后规整成 member_openid。

        单聊没有真正的 @ 能力：内嵌 @ 全部替换成「@用户」普通文字；群聊里
        openid 格式非法或无法解析时同样替换并记 WARNING——坏 ID 不上线，也
        不把整条消息打回。
        """
        if _AT_USER_TAG.search(content) is None:
            return content

        def replace(match: re.Match[str]) -> str:
            raw = match.group(1).strip()
            if kind != "group" or not _AT_USER_ID.fullmatch(raw):
                self._logger.warning(
                    "官方 Markdown 内嵌 @ 的 ID 不可用，已替换为普通文字",
                    conversation_kind=kind,
                    user_id_length=len(raw),
                )
                return "@用户"
            openid = resolve_openid(self._identity, raw, "user")
            if not openid:
                self._logger.warning(
                    "官方 Markdown 内嵌 @ 的 openid 无法解析，已替换为普通文字",
                    conversation_kind=kind,
                    user_id_length=len(raw),
                )
                return "@用户"
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
        """ConversationRef.id 直接就是 openid；旧合成号走只读迁移表反查。"""
        return resolve_openid(self._identity, conversation.id, conversation.kind)

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
    markdown_at_everyone = False
    markdown_commands: list[dict[str, Any]] = []
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
            markdown_at_everyone = markdown_at_everyone or bool(data.get("at_everyone"))
            raw_commands = data.get("commands")
            if raw_commands is not None:
                if not isinstance(raw_commands, list) or any(
                    not isinstance(item, dict) for item in raw_commands
                ):
                    raise _SendFailure("official_markdown 的 commands 必须是对象数组")
                markdown_commands.extend(dict(item) for item in raw_commands)
        elif segment_type in _MEDIA_SEGMENTS:
            # app 的 file 是文件服务器 URL（可能是 127.0.0.1，QQ 拉不到）；有
            # local_path 时官方优先读本地文件走分片上传，file 只留给 OneBot 兼容。
            local_path = str(data.get("local_path") or "").strip()
            source = local_path or str(data.get("file") or data.get("url") or "").strip()
            if not source:
                raise _SendFailure(f"媒体消息段 {segment_type} 缺少 file/url/local_path")
            file_name = str(data.get("name") or "").strip()
            if not file_name and local_path:
                file_name = Path(local_path).name
            media.append(
                (
                    "record" if segment_type == "voice" else segment_type,
                    source,
                    file_name,
                )
            )
    if markdown_parts:
        if text_parts or media:
            raise _SendFailure("official_markdown 消息段不能与文本/at/富媒体段混用")
        return _Prepared(
            markdown="\n".join(markdown_parts),
            at_everyone=markdown_at_everyone,
            commands=markdown_commands,
            reply=reply,
        )
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


def _command_tags(kind: str, commands: list[dict[str, Any]]) -> list[str]:
    """结构化指令参数 → 官方 <qqbot-cmd-*> 标签；值统一 urlencode。"""
    tags: list[str] = []
    for command in commands:
        text = _encoded_attr(command.get("text"))
        if not text:
            continue
        if command.get("enter"):
            if kind != "private":
                raise _SendFailure("群聊不支持回车指令；请去掉 enter 或改用 send_reply")
            tags.append(f'<qqbot-cmd-enter text="{text}" />')
            continue
        show = _encoded_attr(command.get("show")) or text
        reference = "true" if command.get("reference") else "false"
        tags.append(
            f'<qqbot-cmd-input text="{text}" show="{show}" reference="{reference}" />'
        )
    return tags


def _encoded_attr(value: Any) -> str:
    """urlencode 指令值；先 unquote，已编码的输入不会被二次编码破坏。"""
    text = str(value or "").strip()
    return quote(unquote(text), safe="") if text else ""


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