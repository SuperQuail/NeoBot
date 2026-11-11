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
#: 非消息事件：映射成 OneBot notice/request，供插件与通知层消费。
NOTICE_EVENTS = frozenset(
    {
        "GROUP_MEMBER_ADD",
        "GROUP_MEMBER_REMOVE",
        "GROUP_JOIN_REQUEST",
        "FRIEND_ADD",
        "FRIEND_DEL",
        "GROUP_ADD_ROBOT",
        "GROUP_DEL_ROBOT",
        "GROUP_MSG_RECEIVE",
        "GROUP_MSG_REJECT",
        "C2C_MSG_RECEIVE",
        "C2C_MSG_REJECT",
        "SUBSCRIBE_MESSAGE_STATUS",
    }
)

_QUOTED_MESSAGE_TYPE = 103
_QUOTE_PREFIX = "[引用] "
_QUOTE_ATTACHMENT = "[附件]"
_VOICE_PLACEHOLDER = "[语音消息]"
#: 官方文本里 @ 机器人的标记：<@!openid> 或 <qqbot-at-user id="openid" />。
_MENTION_MARKUP = re.compile(r'(?:<qqbot-at-user\s+id="([^"]*)"\s*/>|<@!?([^>\s]+)>)')
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
        #: 机器人自己的 openid；READY 由适配器写入，用于从 mentions 里认出 @bot。
        self.bot_openid = ""

    def from_dispatch(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """完整 op0 载荷 → OneBot 事件；非消息事件/重复投递返回 None。"""
        if not isinstance(payload, dict):
            return None
        event_type = str(payload.get("t") or "")
        if event_type not in MESSAGE_EVENTS and event_type not in NOTICE_EVENTS:
            return None
        data = payload.get("d")
        if not isinstance(data, dict):
            return None
        event_id = str(payload.get("id") or "")
        if event_id and self._dedupe.is_duplicate(event_id):
            self._logger.debug("官方重复事件已跳过", event=event_type, event_id=event_id)
            return None
        if event_type in NOTICE_EVENTS:
            return self.map_notice(event_type, data)
        return self.map_message(event_type, data)

    def map_message(self, event_type: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """单个官方消息事件 d 段 → OneBot 事件 dict。"""
        if event_type not in MESSAGE_EVENTS or not isinstance(data, dict):
            return None
        official_id = str(data.get("id") or "").strip()
        created_at = _epoch_seconds(data.get("timestamp"))
        kind, context_openid = _conversation_context(event_type, data)
        try:
            message_id = (
                self._message_ids.next(
                    official_id,
                    context={"kind": kind, "openid": context_openid, "at": created_at},
                )
                if official_id
                else 0
            )
        except ValueError:
            message_id = 0
        event: dict[str, Any] = {
            "time": created_at,
            "self_id": self.self_id,
            "post_type": "message",
            "message_id": message_id,
            "font": 0,
        }
        if official_id:
            # 被动回复要用官方 msg_id；OneBot 命令方只看到合成 int。
            event["_official_message_id"] = official_id
        # 本条消息自身的引用索引：之后引用回复它时 message_reference 要填这个。
        ref_idx = _own_ref_idx(data)
        if ref_idx and message_id:
            self._message_ids.remember_reference(message_id, ref_idx)
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

    def map_notice(self, event_type: str, data: dict[str, Any]) -> dict[str, Any]:
        """官方非消息事件 → OneBot notice/request；缺少 openid 时返回 None。"""
        timestamp = _epoch_seconds(data.get("timestamp"))
        if event_type in {"GROUP_MEMBER_ADD", "GROUP_MEMBER_REMOVE"}:
            group_openid = str(data.get("group_openid") or "").strip()
            member_openid = str(data.get("member_openid") or "").strip()
            if not group_openid or not member_openid:
                return None
            group_id = self._identity.group_id(group_openid)
            user_id = self._identity.user_id(member_openid)
            return {
                "time": timestamp,
                "self_id": self.self_id,
                "post_type": "notice",
                "notice_type": "group_increase" if event_type.endswith("ADD") else "group_decrease",
                "sub_type": "approve" if event_type.endswith("ADD") else "leave",
                "group_id": group_id,
                "user_id": user_id,
                "operator_id": 0,
            }
        if event_type == "GROUP_JOIN_REQUEST":
            group_openid = str(data.get("group_openid") or "").strip()
            member_openid = str(data.get("member_openid") or "").strip()
            if not group_openid or not member_openid:
                return None
            verify = data.get("verify_info") if isinstance(data.get("verify_info"), dict) else {}
            comment = str(verify.get("verify_message") or data.get("username") or "").strip()
            return {
                "time": _epoch_seconds(data.get("apply_at")),
                "self_id": self.self_id,
                "post_type": "request",
                "request_type": "group",
                "sub_type": "add",
                "group_id": self._identity.group_id(group_openid),
                "user_id": self._identity.user_id(member_openid),
                "comment": comment,
                "flag": str(data.get("join_request_id") or ""),
                "_official_member_openid": member_openid,
            }
        if event_type in {"FRIEND_ADD", "FRIEND_DEL"}:
            openid = str(data.get("openid") or "").strip()
            if not openid:
                return None
            return {
                "time": timestamp,
                "self_id": self.self_id,
                "post_type": "notice",
                "notice_type": "friend_add" if event_type == "FRIEND_ADD" else "friend_remove",
                "user_id": self._identity.user_id(openid),
            }
        if event_type in {"GROUP_MSG_RECEIVE", "GROUP_MSG_REJECT"}:
            group_openid = str(data.get("group_openid") or "").strip()
            if not group_openid:
                return None
            operator_openid = str(data.get("op_member_openid") or "").strip()
            return {
                "time": timestamp,
                "self_id": self.self_id,
                "post_type": "notice",
                "notice_type": "group_msg_receive" if event_type.endswith("RECEIVE") else "group_msg_reject",
                "group_id": self._identity.group_id(group_openid),
                "operator_id": self._identity.user_id(operator_openid) if operator_openid else 0,
            }
        if event_type in {"C2C_MSG_RECEIVE", "C2C_MSG_REJECT"}:
            openid = str(data.get("openid") or "").strip()
            if not openid:
                return None
            return {
                "time": timestamp,
                "self_id": self.self_id,
                "post_type": "notice",
                "notice_type": "c2c_msg_receive" if event_type.endswith("RECEIVE") else "c2c_msg_reject",
                "user_id": self._identity.user_id(openid),
            }
        if event_type == "SUBSCRIBE_MESSAGE_STATUS":
            group_openid = str(data.get("group_openid") or "").strip()
            user_openid = str(data.get("openid") or "").strip()
            if not group_openid and not user_openid:
                return None
            return {
                "time": timestamp,
                "self_id": self.self_id,
                "post_type": "notice",
                "notice_type": "subscribe_message_status",
                "group_id": self._identity.group_id(group_openid) if group_openid else 0,
                "user_id": self._identity.user_id(user_openid) if user_openid else 0,
                "subscribe_results": data.get("result") if isinstance(data.get("result"), list) else [],
            }
        if event_type in {"GROUP_ADD_ROBOT", "GROUP_DEL_ROBOT"}:
            group_openid = str(data.get("group_openid") or "").strip()
            operator_openid = str(data.get("op_member_openid") or "").strip()
            if not group_openid:
                return None
            return {
                "time": timestamp,
                "self_id": self.self_id,
                "post_type": "notice",
                "notice_type": "group_add_robot" if event_type == "GROUP_ADD_ROBOT" else "group_del_robot",
                "group_id": self._identity.group_id(group_openid),
                "operator_id": self._identity.user_id(operator_openid) if operator_openid else 0,
            }
        return None

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
            message,
            data.get("content"),
            data.get("mentions"),
            self._identity,
            bot_self_id=self.self_id,
            bot_openid=self.bot_openid,
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
            message,
            data.get("content"),
            data.get("mentions"),
            self._identity,
            bot_self_id=self.self_id,
            bot_openid=self.bot_openid,
            unknown_is_bot=True,
        )
        _append_attachments(message, data.get("attachments"))
        role = str(author.get("member_role") or "").strip().casefold()
        if role not in {"owner", "admin", "member"}:
            role = "member"
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
                    "role": role,
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


def _conversation_context(event_type: str, data: dict[str, Any]) -> tuple[str, str]:
    """事件的会话类型与 openid；撤回消息时用它定位官方端点。"""
    if event_type == "C2C_MESSAGE_CREATE":
        author = data.get("author") if isinstance(data.get("author"), dict) else {}
        return "private", str(author.get("user_openid") or author.get("id") or "").strip()
    group_openid = str(data.get("group_openid") or data.get("group_id") or "").strip()
    return "group", group_openid


def _own_ref_idx(data: dict[str, Any]) -> str:
    """message_scene.ext 里的 msg_idx：本条消息的引用索引（REFIDX_...）。"""
    scene = data.get("message_scene")
    if not isinstance(scene, dict):
        return ""
    ext = scene.get("ext")
    if not isinstance(ext, list):
        return ""
    for item in ext:
        text = str(item)
        if text.startswith("msg_idx="):
            return text[len("msg_idx=") :].strip()
    return ""


def _append_text(message: list[dict[str, Any]], text: str) -> None:
    if text:
        message.append({"type": "text", "data": {"text": text}})


def _mention_openid(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("member_openid") or item.get("id") or item.get("user_openid") or "").strip()


def _append_bot_at(message: list[dict[str, Any]], bot_self_id: int) -> None:
    if not bot_self_id:
        return
    if any(
        segment.get("type") == "at" and str(segment.get("data", {}).get("qq")) == str(bot_self_id)
        for segment in message
    ):
        return
    message.append({"type": "at", "data": {"qq": bot_self_id}})


def _append_content_with_mentions(
    message: list[dict[str, Any]],
    content: Any,
    mentions: Any,
    identity: IdentityMap,
    *,
    bot_self_id: int = 0,
    bot_openid: str = "",
    unknown_is_bot: bool = False,
) -> None:
    """按官方 content 里的 @ 标记顺序生成 text/at 段。

    官方 content 已去掉 @机器人前缀，但被 @ 的其他用户仍可能以
    `<@!openid>` / `<qqbot-at-user id="openid">` 形式留在正文里；mentions 列表
    是同一批用户的权威信息。按标记位置切分才能保持「命令在前、@ 在后」的真实顺序。
    没有出现在正文标记里的 mention 追加到末尾（命令层仍能拿到 at_qqs）。
    """
    text = str(content or "")
    bot_openid = str(bot_openid or "").strip()
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
            # 保留原文空格：text 段会被命令解析按空字符串拼接，strip 掉会
            # 把「/linkqq @用户 123」变成「/linkqq123」而无法匹配命令。
            _append_text(message, text[cursor : match.start()])
        openid = str(match.group(1) or match.group(2) or "").strip()
        item = mention_map.get(openid)
        if item is not None and item.get("bot") is True:
            # mentions 不含机器人自己，但全量消息可能仍把它列在 mentions；
            # 只有命中自身 openid 才补 bot at，别的机器人不能冒充。
            if bot_openid and openid == bot_openid:
                _append_bot_at(message, bot_self_id)
            seen.add(openid)
        elif item is not None:
            user_id = identity.user_id(openid)
            name = str(item.get("username") or "").strip()
            message.append({"type": "at", "data": {"qq": str(user_id), "name": name}})
            seen.add(openid)
        elif bot_openid and openid == bot_openid:
            _append_bot_at(message, bot_self_id)
        elif unknown_is_bot and bot_self_id and not bot_openid:
            # 群全量消息（GROUP_MESSAGE_CREATE）的 content 仍带 @机器人 标记，
            # 但 mentions 明确不含机器人；未知标记就是机器人自己，补成 at 段，
            # 否则群命令触发条件「被 @bot」无法满足。
            _append_bot_at(message, bot_self_id)
        # 其余未知标记（非机器人）无法解析出用户，丢弃，不制造假用户。
        cursor = match.end()
    if cursor < len(text):
        _append_text(message, text[cursor:])

    for openid, item in mention_map.items():
        if openid in seen:
            continue
        if item.get("bot") is True:
            if bot_openid and openid == bot_openid:
                _append_bot_at(message, bot_self_id)
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
        content_type = str(attachment.get("content_type") or "").strip().lower()
        filename = str(attachment.get("filename") or attachment.get("name") or "")
        is_voice = content_type.startswith(_VOICE_CONTENT_PREFIXES) or filename.endswith((".silk", ".amr", ".wav"))
        if is_voice:
            # 官方在 voice_wav_url 给出可播放的 WAV；有就发 record 段，ASR 文本另起一段。
            wav_url = str(attachment.get("voice_wav_url") or "").strip()
            if wav_url:
                message.append({"type": "record", "data": {"file": wav_url, "url": wav_url}})
            asr = str(attachment.get("asr_refer_text") or "").strip()
            if asr:
                _append_text(message, asr)
            elif not wav_url:
                message.append({"type": "text", "data": {"text": _VOICE_PLACEHOLDER}})
            continue
        if not url:
            continue
        if content_type.startswith("image"):
            message.append({"type": "image", "data": {"file": url, "url": url}})
        elif content_type.startswith("video") or filename.lower().endswith(_VIDEO_FILE_SUFFIXES):
            message.append({"type": "video", "data": {"file": url, "url": url}})
        else:
            message.append({"type": "file", "data": {"file": url, "url": url, "name": filename}})
