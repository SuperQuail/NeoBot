"""QQ 官方消息发送：Markdown 降级、被动回复限额与多段拆发。

官方 v2 发送接口只收一条消息体，而 OneBot 的 message 是消息段数组；这里按
「文本合并成一条 + 媒体逐条」拆分。被动回复（msg_id + msg_seq）有会话级限额，
超限/过期后降级为主动推送（不带 msg_id），每个会话只告警一次。
"""

from __future__ import annotations

import asyncio
import random
import re
import time
from collections import deque
from typing import Any

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_adapter.model import response
from neobot_adapter.official.auth import OfficialAuthError
from neobot_adapter.official.identity import IdentityMap, MessageIdMap
from neobot_adapter.official.media import MediaFile, MediaUploader, api_data
from neobot_adapter.official.settings import OfficialSettings

#: 群聊被动回复 5 分钟内同一 msg_id 最多 4 条；单聊 60 分钟内最多 3 条。
_PASSIVE_LIMITS = {"group": (4, 300.0), "private": (3, 3600.0)}
#: 每个会话缓存多少个候选 msg_id；最新的优先用。
_PASSIVE_CANDIDATES = 8
_TEXT_LIMIT = 4000
_MSG_SEQ_MAX = 10000
_API_TIMEOUT_SECONDS = 10.0
_MESSAGE_ENDPOINTS = {
    "group": "/v2/groups/{openid}/messages",
    "private": "/v2/users/{openid}/messages",
}
_MEDIA_SEGMENTS = frozenset({"image", "record", "voice", "video", "file"})
#: at 段在合并文本里的占位符；保留顺序，发送时再展开成官方 markdown @ 标记。
_AT_PLACEHOLDER = "\x00AT{}\x00"
_MARKDOWN_REJECTION_HINTS = ("不允许", "not allowed", "forbidden", "unsupported")


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
                payload = await raw.json(content_type=None)
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


def _timeout(seconds: float) -> Any:
    import aiohttp

    return aiohttp.ClientTimeout(total=seconds)


def _error_code(payload: dict[str, Any]) -> int | str | None:
    code = payload.get("code", payload.get("biz_code"))
    if isinstance(code, str):
        return code
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return str(code)


def _error_message(payload: dict[str, Any]) -> str:
    return (
        str(payload.get("message") or payload.get("msg") or payload.get("err_msg") or "").strip() or "官方接口返回失败"
    )


class PassiveReplyCache:
    """每个会话的被动回复候选 msg_id 与限额计数。"""

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

    def remember(self, kind: str, conversation_id: Any, official_msg_id: str) -> None:
        """收到一条用户消息后登记，供后续被动回复使用。"""
        limit, ttl = self._limits.get(kind, _PASSIVE_LIMITS["private"])
        key = f"{kind}:{conversation_id}"
        now = self._clock()
        entries = self._entries.setdefault(key, deque())
        entries.append([str(official_msg_id), now, 0])
        while len(entries) > self._candidates:
            entries.popleft()
        while entries and now - entries[0][1] > ttl:
            entries.popleft()

    def acquire(self, kind: str, conversation_id: Any) -> tuple[str | None, bool]:
        """取一个还能用的被动回复目标。

        返回 (msg_id, degraded)：msg_id 为 None 表示转主动推送；degraded 表示
        本来有候选但全部超限/过期（调用方据此每个会话只告警一次）。
        """
        limit, ttl = self._limits.get(kind, _PASSIVE_LIMITS["private"])
        key = f"{kind}:{conversation_id}"
        entries = self._entries.get(key)
        if not entries:
            return None, False
        now = self._clock()
        while entries and now - entries[0][1] > ttl:
            entries.popleft()
        for entry in reversed(entries):
            if entry[2] < limit:
                entry[2] += 1
                return str(entry[0]), False
        return None, True


class MessageSender:
    """把 OneBot 消息段发成官方消息；单实例绑定一次适配器运行期。"""

    def __init__(
        self,
        *,
        api: OfficialApi,
        settings: OfficialSettings,
        identity: IdentityMap,
        message_ids: MessageIdMap,
        passive: PassiveReplyCache,
        media: MediaUploader,
        logger: Logger | None = None,
        markdown: bool | None = None,
    ) -> None:
        self._api = api
        self._settings = settings
        self._identity = identity
        self._message_ids = message_ids
        self._passive = passive
        self._media = media
        self._logger = logger if logger is not None else NullLogger()
        self._markdown = settings.markdown if markdown is None else bool(markdown)
        self._degraded_warned: set[str] = set()

    async def send(
        self,
        conversation: ConversationRef,
        message: str | list[dict[str, Any]],
        timeout: float = _API_TIMEOUT_SECONDS,
    ) -> response.SendMsgResponse:
        """发送一条 OneBot 消息（文本合并一条，媒体逐条）。"""
        kind = str(conversation.kind or "")
        if kind not in _MESSAGE_ENDPOINTS:
            return _failed(f"官方协议不支持发送到该会话类型: {kind}")
        openid = self._openid(conversation)
        if not openid:
            return _failed(f"官方协议无法反查会话 {kind}:{conversation.id} 的 openid（该会话未在官方事件中出现过）")
        try:
            text, media_items, reply_id, at_entries = _prepare(message)
        except ValueError as exc:
            return _failed(str(exc))
        reply_id = self._resolve_reply(reply_id)
        if not text and not media_items:
            return _failed("消息内容为空")

        force_markdown = False
        if at_entries:
            text, force_markdown = self._render_mentions(text, at_entries, kind)
        sent_id: int | None = None
        if text:
            for chunk in _split_text(text):
                try:
                    official_id = await self._send_text(
                        kind,
                        openid,
                        conversation.id,
                        chunk,
                        reply_id,
                        timeout,
                        force_markdown=force_markdown,
                    )
                except (OfficialApiError, OfficialAuthError) as exc:
                    return _failed(f"官方消息发送失败：{exc}")
                sent_id = self._track_sent(official_id) or sent_id
        for segment_type, source, file_name in media_items:
            try:
                official_id = await self._send_media(
                    kind,
                    openid,
                    conversation.id,
                    segment_type,
                    source,
                    file_name,
                    reply_id,
                    timeout,
                )
            except Exception as exc:
                return _failed(f"官方富媒体发送失败：{exc}")
            sent_id = self._track_sent(official_id) or sent_id
        return _ok(sent_id)

    # ── 单条发送 ────────────────────────────────────────────────────

    def _render_mentions(
        self, text: str, at_entries: list[tuple[str, str]], kind: str
    ) -> tuple[str, bool]:
        """把 at 占位符换成官方 markdown @ 标记；返回 (文本, 是否包含可用 @)。"""
        has_embed = False
        for index, (qq, name) in enumerate(at_entries):
            tag = self._mention_tag(kind, qq, name)
            if tag.startswith("<qqbot-at"):
                has_embed = True
            text = text.replace(_AT_PLACEHOLDER.format(index), tag)
        return text, has_embed

    def _mention_tag(self, kind: str, qq: str, name: str) -> str:
        label = f"@{name}" if name else f"@{qq}"
        if kind != "group":
            # 官方只有群聊支持 @ 用户；单聊继续用可读文本。
            return label
        if str(qq).strip().casefold() == "all":
            return "<qqbot-at-everyone />"
        try:
            synthetic = int(qq)
        except (TypeError, ValueError):
            return label
        openid = self._identity.openid(synthetic, "user")
        if not openid:
            return label
        return f'<qqbot-at-user id="{openid}" />'

    async def _send_text(
        self,
        kind: str,
        openid: str,
        conversation_id: Any,
        text: str,
        reply_id: str | None,
        timeout: float,
        *,
        force_markdown: bool = False,
    ) -> str:
        payload = self._message_payload(kind, conversation_id)
        use_markdown = self._markdown or force_markdown
        if use_markdown and text:
            payload["msg_type"] = 2
            payload["markdown"] = {"content": text}
        else:
            payload["msg_type"] = 0
            payload["content"] = text
        if reply_id:
            payload["message_reference"] = {"message_id": reply_id}
        endpoint = _MESSAGE_ENDPOINTS[kind].format(openid=openid)
        try:
            body = await self._api.request("POST", endpoint, body=payload, timeout=timeout)
        except OfficialApiError as exc:
            if not (use_markdown and text and _is_markdown_forbidden(exc)):
                raise
            self._logger.warning("官方 Markdown 发送被拒绝，降级为纯文本重发", error=str(exc))
            fallback = dict(payload)
            fallback.pop("markdown", None)
            fallback["msg_type"] = 0
            # 降级为纯文本时 @ 标记不能再留在 content 里
            fallback["content"] = _strip_mention_tags(text)
            fallback["msg_seq"] = random.randint(1, _MSG_SEQ_MAX)
            body = await self._api.request("POST", endpoint, body=fallback, timeout=timeout)
        return _response_message_id(body)

    async def _send_media(
        self,
        kind: str,
        openid: str,
        conversation_id: Any,
        segment_type: str,
        source: str,
        file_name: str,
        reply_id: str | None,
        timeout: float,
    ) -> str:
        media: MediaFile = await self._media.upload(
            self._api,
            kind=kind,
            openid=openid,
            segment_type=segment_type,
            source=source,
            file_name=file_name,
        )
        payload = self._message_payload(kind, conversation_id)
        payload["msg_type"] = 7
        media_payload = {"file_info": media.file_info}
        if media.file_uuid:
            media_payload["file_uuid"] = media.file_uuid
        payload["media"] = media_payload
        if reply_id:
            payload["message_reference"] = {"message_id": reply_id}
        endpoint = _MESSAGE_ENDPOINTS[kind].format(openid=openid)
        body = await self._api.request("POST", endpoint, body=payload, timeout=timeout)
        return _response_message_id(body)

    def _message_payload(self, kind: str, conversation_id: Any) -> dict[str, Any]:
        """公共字段：被动回复目标与随机 msg_seq。"""
        payload: dict[str, Any] = {"msg_seq": random.randint(1, _MSG_SEQ_MAX)}
        msg_id, degraded = self._passive.acquire(kind, conversation_id)
        if msg_id is not None:
            payload["msg_id"] = msg_id
        elif degraded:
            key = f"{kind}:{conversation_id}"
            if key not in self._degraded_warned:
                self._degraded_warned.add(key)
                self._logger.warning(
                    "官方被动回复额度已用尽或过期，后续消息改为主动推送",
                    conversation_kind=kind,
                    conversation_id=conversation_id,
                )
        return payload

    def _resolve_reply(self, value: str | None) -> str | None:
        """reply 段里的合成 int 反查官方 msg_id；查不到就不填引用。"""
        text = str(value or "").strip()
        if not text:
            return None
        if text.startswith("ROBOT") or not text.isdigit():
            return text
        return self._message_ids.official(int(text))

    def _openid(self, conversation: ConversationRef) -> str | None:
        try:
            synthetic = int(str(conversation.id))
        except (TypeError, ValueError):
            return None
        return self._identity.openid(synthetic, conversation.kind)

    def _track_sent(self, official_id: str) -> int | None:
        if not official_id:
            return None
        try:
            return self._message_ids.next(official_id)
        except ValueError:
            return None


def _prepare(
    message: str | list[dict[str, Any]],
) -> tuple[str, list[tuple[str, str, str]], str | None, list[tuple[str, str]]]:
    """OneBot 消息 → (合并文本, 媒体列表, 引用 msg_id, at 列表)。"""
    if isinstance(message, str):
        return message, [], None, []
    if not isinstance(message, list):
        raise ValueError("消息必须是字符串或 OneBot 消息段数组")
    text_parts: list[str] = []
    media: list[tuple[str, str, str]] = []
    at_entries: list[tuple[str, str]] = []
    reply_id: str | None = None
    for segment in message:
        if isinstance(segment, str):
            text_parts.append(segment)
            continue
        if not isinstance(segment, dict):
            continue
        segment_type = str(segment.get("type") or "")
        data = segment.get("data") if isinstance(segment.get("data"), dict) else {}
        if segment_type == "text":
            text_parts.append(str(data.get("text") or ""))
        elif segment_type == "at":
            index = len(at_entries)
            at_entries.append(
                (str(data.get("qq") if data.get("qq") is not None else ""), str(data.get("name") or ""))
            )
            text_parts.append(_AT_PLACEHOLDER.format(index))
        elif segment_type == "reply":
            reply_id = _reply_id(data, reply_id)
        elif segment_type in _MEDIA_SEGMENTS:
            source = str(data.get("file") or data.get("url") or "").strip()
            if source:
                media.append(
                    (
                        "record" if segment_type == "voice" else segment_type,
                        source,
                        str(data.get("name") or ""),
                    )
                )
    return "".join(text_parts), media, reply_id, at_entries


def _strip_mention_tags(text: str) -> str:
    """Markdown 被拒时的纯文本降级：去掉官方 @ 标记，避免原样露出标签。"""
    text = re.sub(r'<qqbot-at-user\s+id="[^"]*"\s*/>', "", text)
    text = text.replace("<qqbot-at-everyone />", "")
    return text


def _reply_id(data: dict[str, Any], current: str | None) -> str | None:
    """记录 reply 段的 id（合成 int 或官方字符串），真实解析在 MessageSender。"""
    value = data.get("id")
    if value in (None, ""):
        return current
    return str(value).strip()


def _split_text(text: str, limit: int = _TEXT_LIMIT) -> list[str]:
    """按 4000 字安全切分：优先换行，其次空格，最后硬切。"""
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


def _is_markdown_forbidden(exc: OfficialApiError) -> bool:
    text = f"{exc.message} {exc.payload.get('message') or ''}".casefold()
    if "markdown" not in text:
        return False
    return any(hint in text for hint in _MARKDOWN_REJECTION_HINTS)


def _response_message_id(body: dict[str, Any]) -> str:
    data = api_data(body)
    return str(data.get("id") or data.get("message_id") or "")


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
