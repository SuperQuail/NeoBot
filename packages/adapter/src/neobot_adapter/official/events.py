"""QQ 官方 v2 事件 → OneBot v11 事件字典的映射。

官方网关把 op0 dispatch 载荷原样交给适配器（{"t": 事件类型, "d": 数据}），
这里把它落成 OneBot 形状的 dict 交给门面的事件分发器；本模块不持有网络状态，
也不认识 HTTP。官方只给 openid/字符串消息 ID，靠 IdentityMap / MessageIdMap
换成 OneBot 的合成数字。
"""

from __future__ import annotations

import re
import time
from collections import deque
from datetime import datetime
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_adapter.official.identity import IdentityMap, MessageIdMap

#: 需要映射的消息事件；其余 dispatch（READY/RESUMED/互动事件等）由适配器自行处理。
MESSAGE_EVENTS = frozenset({"C2C_MESSAGE_CREATE", "GROUP_AT_MESSAGE_CREATE", "GROUP_MESSAGE_CREATE"})

_QUOTED_MESSAGE_TYPE = 103
_QUOTE_PREFIX = "[引用] "
_QUOTE_ATTACHMENT = "[附件]"
_VOICE_PLACEHOLDER = "[语音消息]"
#: 官方文本里 @ 机器人的标记：<@!openid> 或 <qqbot-at-user id="openid" />。
_MENTION_MARKUP = re.compile(
    r'(?:<qqbot-at-user\s+id="([^"]*)"\s*/>|<@!?([^>\s]+)>)'
)
_DEDUPE_TTL_SECONDS = 300.0
_DEDUPE_MAX_SIZE = 1000
_VOICE_CONTENT_PREFIXES = ("voice", "audio")
_VIDEO_FILE_SUFFIXES = (".mp4", ".mov", ".avi", ".mkv", ".webm")


class _EventDedupe:
    """官方事件 id 的滑动去重：同一事件重复投递时只放行一次。"""

    def __init__(
        self,
        *,
        ttl_seconds: float = _DEDUPE_TTL_SECONDS,
        max_size: int = _DEDUPE_MAX_SIZE,
        clock: Any = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_size = max(1, int(max_size))
        self._clock = clock
        self._seen: dict[str, float] = {}
        self._order: deque[tuple[str, float]] = deque()

    def is_duplicate(self, event_id: str) -> bool:
        """返回是否已见过；首次见到时登记并返回 False。"""
        key = str(event_id or "").strip()
        if not key:
            return False
        now = self._clock()
        while self._order and now - self._order[0][1] > self._ttl:
            expired, _ = self._order.popleft()
            self._seen.pop(expired, None)
        if key in self._seen:
            return True
        self._seen[key] = now
        self._order.append((key, now))
        while len(self._order) > self._max_size:
            expired, _ = self._order.popleft()
            self._seen.pop(expired, None)
        return False


class EventMapper:
    """把官方消息事件映射成 OneBot 事件；有状态的部分只有去重与 ID 映射。"""

    def __init__(
        self,
        *,
        identity: IdentityMap,
        message_ids: MessageIdMap,
        logger: Logger | None = None,
        self_id: int = 0,
    ) -> None:
        self._identity = identity
        self._message_ids = message_ids
        self._logger = logger if logger is not None else NullLogger()
        self._dedupe = _EventDedupe()
        #: 机器人自己的合成号；登录后由适配器写入（/users/@me 的 robot_uin）。
        self.self_id = int(self_id or 0)

    def from_dispatch(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """完整 op0 载荷 → OneBot 事件；非消息事件/重复投递返回 None。"""
        if not isinstance(payload, dict):
            return None
        event_type = str(payload.get("t") or "")
        if event_type not in MESSAGE_EVENTS:
            return None
        data = payload.get("d")
        if not isinstance(data, dict):
            return None
        event_id = str(payload.get("id") or "")
        if event_id and self._dedupe.is_duplicate(event_id):
            self._logger.debug("官方重复事件已跳过", event=event_type, event_id=event_id)
            return None
        return self.map_message(event_type, data)

    def map_message(self, event_type: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """单个官方消息事件 d 段 → OneBot 事件 dict。"""
        if event_type not in MESSAGE_EVENTS or not isinstance(data, dict):
            return None
        official_id = str(data.get("id") or "").strip()
        try:
            message_id = self._message_ids.next(official_id) if official_id else 0
        except ValueError:
            message_id = 0
        event: dict[str, Any] = {
            "time": _epoch_seconds(data.get("timestamp")),
            "self_id": self.self_id,
            "post_type": "message",
            "message_id": message_id,
            "font": 0,
        }
        if official_id:
            # 被动回复要用官方 msg_id；OneBot 命令方只看到合成 int。
            event["_official_message_id"] = official_id
        message: list[dict[str, Any]] = []
        if event_type == "C2C_MESSAGE_CREATE":
            self._fill_private(event, data, message)
        else:
            self._fill_group(event, data, message, require_at=event_type == "GROUP_AT_MESSAGE_CREATE")
        if event.get("message_type") is None:
            return None
        event["message"] = message
        event["raw_message"] = "".join(
            str(segment.get("data", {}).get("text") or "") for segment in message if segment.get("type") == "text"
        )
        return event

    # ── 私聊 ────────────────────────────────────────────────────────

    def _fill_private(
        self,
        event: dict[str, Any],
        data: dict[str, Any],
        message: list[dict[str, Any]],
    ) -> None:
        author = data.get("author") if isinstance(data.get("author"), dict) else {}
        openid = str(author.get("user_openid") or author.get("id") or "").strip()
        if not openid:
            self._logger.warning("官方私聊事件缺少用户 openid，已跳过")
            return
        user_id = self._identity.user_id(openid)
        _append_quote(message, data)
        _append_content_with_mentions(
            message, data.get("content"), data.get("mentions"), self._identity
        )
        _append_attachments(message, data.get("attachments"))
        event.update(
            {
                "message_type": "private",
                "sub_type": "friend",
                "user_id": user_id,
                "target_id": self.self_id,
                "sender": {
                    "user_id": user_id,
                    "nickname": _nickname(author, user_id),
                },
            }
        )

    # ── 群聊 ────────────────────────────────────────────────────────

    def _fill_group(
        self,
        event: dict[str, Any],
        data: dict[str, Any],
        message: list[dict[str, Any]],
        *,
        require_at: bool,
    ) -> None:
        author = data.get("author") if isinstance(data.get("author"), dict) else {}
        group_openid = str(data.get("group_openid") or data.get("group_id") or "").strip()
        user_openid = str(author.get("member_openid") or author.get("id") or "").strip()
        if not group_openid or not user_openid:
            self._logger.warning("官方群聊事件缺少群或用户 openid，已跳过")
            return
        group_id = self._identity.group_id(group_openid)
        user_id = self._identity.user_id(user_openid)
        if require_at:
            # GROUP_AT_MESSAGE_CREATE 必然 @ 了机器人：OneBot 消费方按 at 段判断。
            message.append({"type": "at", "data": {"qq": self.self_id}})
        _append_quote(message, data)
        _append_content_with_mentions(
            message, data.get("content"), data.get("mentions"), self._identity
        )
        _append_attachments(message, data.get("attachments"))
        event.update(
            {
                "message_type": "group",
                "sub_type": "normal",
                "group_id": group_id,
                "user_id": user_id,
                "sender": {
                    "user_id": user_id,
                    "nickname": _nickname(author, user_id),
                    "card": "",
                    "role": "member",
                },
            }
        )


def _epoch_seconds(value: Any) -> int:
    """RFC3339（官方）→ epoch 秒；解析不了时退回当前时间。"""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    text = str(value or "").strip()
    if text:
        try:
            return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
        except ValueError:
            pass
    return int(time.time())


def _nickname(author: dict[str, Any], user_id: int) -> str:
    name = str(author.get("username") or "").strip()
    return name or f"QQ:{user_id}"


def _append_text(message: list[dict[str, Any]], text: str) -> None:
    if text:
        message.append({"type": "text", "data": {"text": text}})


def _mention_openid(item: Any) -> str:
    if not isinstance(item, dict) or item.get("bot") is True:
        return ""
    return str(
        item.get("member_openid")
        or item.get("id")
        or item.get("user_openid")
        or ""
    ).strip()


def _append_content_with_mentions(
    message: list[dict[str, Any]],
    content: Any,
    mentions: Any,
    identity: IdentityMap,
) -> None:
    """按官方 content 里的 @ 标记顺序生成 text/at 段。

    官方 content 已去掉 @机器人前缀，但被 @ 的其他用户仍可能以
    `<@!openid>` / `<qqbot-at-user id="openid">` 形式留在正文里；mentions 列表
    是同一批用户的权威信息。按标记位置切分才能保持「命令在前、@ 在后」的真实顺序。
    没有出现在正文标记里的 mention 追加到末尾（命令层仍能拿到 at_qqs）。
    """
    text = str(content or "")
    mention_map: dict[str, dict[str, Any]] = {}
    if isinstance(mentions, list):
        for item in mentions:
            openid = _mention_openid(item)
            if openid:
                mention_map[openid] = item

    seen: set[str] = set()
    cursor = 0
    for match in _MENTION_MARKUP.finditer(text):
        if match.start() > cursor:
            _append_text(message, text[cursor : match.start()].strip())
        openid = str(match.group(1) or match.group(2) or "").strip()
        if openid in mention_map:
            item = mention_map[openid]
            user_id = identity.user_id(openid)
            name = str(item.get("username") or "").strip()
            message.append({"type": "at", "data": {"qq": str(user_id), "name": name}})
            seen.add(openid)
        # 未在 mentions 里的标记（例如 @机器人本身）直接丢弃，不制造假用户。
        cursor = match.end()
    if cursor < len(text):
        _append_text(message, text[cursor:].strip())

    for openid, item in mention_map.items():
        if openid in seen:
            continue
        user_id = identity.user_id(openid)
        name = str(item.get("username") or "").strip()
        message.append({"type": "at", "data": {"qq": str(user_id), "name": name}})


def _append_quote(message: list[dict[str, Any]], data: dict[str, Any]) -> None:
    """引用消息前置成文本：OneBot 消费方的引用解析在官方模式里没有 API 可查。"""
    quoted = _quoted_text(data)
    if quoted:
        message.append({"type": "text", "data": {"text": f"{_QUOTE_PREFIX}{quoted}\n"}})


def _quoted_text(data: dict[str, Any]) -> str:
    try:
        if int(data.get("message_type") or 0) != _QUOTED_MESSAGE_TYPE:
            return ""
    except (TypeError, ValueError):
        return ""
    elements = data.get("msg_elements")
    if not isinstance(elements, list) or not elements:
        return ""
    element = elements[0] if isinstance(elements[0], dict) else {}
    text = str(element.get("content") or "").strip()
    if text:
        return text
    attachments = element.get("attachments")
    return _QUOTE_ATTACHMENT if isinstance(attachments, list) and attachments else ""


def _append_attachments(message: list[dict[str, Any]], attachments: Any) -> None:
    if not isinstance(attachments, list):
        return
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        url = str(attachment.get("url") or "").strip()
        if not url:
            continue
        content_type = str(attachment.get("content_type") or "").strip().lower()
        filename = str(attachment.get("filename") or attachment.get("name") or "")
        if content_type.startswith("image"):
            message.append({"type": "image", "data": {"file": url, "url": url}})
        elif content_type.startswith(_VOICE_CONTENT_PREFIXES) or filename.endswith((".silk", ".amr")):
            # 官方语音没有可直接播放的 OneBot record URL：有 ASR 文本就追加文本，
            # 否则放一个占位，避免模型把空消息当成无事发生。
            asr = str(attachment.get("asr_refer_text") or "").strip()
            message.append({"type": "text", "data": {"text": asr or _VOICE_PLACEHOLDER}})
        elif content_type.startswith("video") or filename.lower().endswith(_VIDEO_FILE_SUFFIXES):
            message.append({"type": "video", "data": {"file": url, "url": url}})
        else:
            message.append({"type": "file", "data": {"file": url, "url": url, "name": filename}})
