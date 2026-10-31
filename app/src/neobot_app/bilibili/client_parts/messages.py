"""私信：会话与消息读取、发送。"""

from __future__ import annotations

import json
import time
from typing import Any

from ..errors import BilibiliError
from .common import DEFAULT_DEVICE_ID, VC_BASE, _to_int
from .models import BilibiliMessage, BilibiliSession


class _MessageMixin:
    """私信会话读取、去重与发送。"""

    # ── 私信 ──

    def get_sessions(self, count: int = 30) -> list[BilibiliSession]:
        """获取私信会话列表（按最后消息时间倒序）。"""
        params = {
            "session_type": 1,
            "group_fold": 1,
            "unfollow_fold": 0,
            "sort_rule": 2,
            "build": 0,
            "mobi_app": "web",
        }
        try:
            payload = self._fetch("GET", f"{VC_BASE}/session_svr/v1/session_svr/get_sessions", params=params)
        except BilibiliError as exc:
            self._log_read_error("私信会话读取", exc)
            return []
        data = payload.get("data")
        raw_sessions = data.get("session_list") if isinstance(data, dict) else None
        sessions = [
            BilibiliSession.from_api(item)
            for item in raw_sessions or []
            if isinstance(item, dict)
        ]
        sessions.sort(
            key=lambda item: item.last_msg.timestamp if item.last_msg else 0,
            reverse=True,
        )
        return sessions[: max(_to_int(count), 0)]

    def get_messages(self, talker_id: int, size: int = 5) -> list[BilibiliMessage]:
        """获取指定会话的最新消息。"""
        params = {
            "sender_device_id": 1,
            "talker_id": _to_int(talker_id),
            "session_type": 1,
            "size": _to_int(size),
            "build": 0,
            "mobi_app": "web",
        }
        try:
            payload = self._fetch("GET", f"{VC_BASE}/svr_sync/v1/svr_sync/fetch_session_msgs", params=params)
        except BilibiliError as exc:
            self._log_read_error("私信读取", exc)
            return []
        data = payload.get("data")
        raw_messages = data.get("messages") if isinstance(data, dict) else None
        return [
            BilibiliMessage.from_api(item, self._my_uid)
            for item in raw_messages or []
            if isinstance(item, dict)
        ]

    def get_new_messages(self, session: BilibiliSession) -> list[BilibiliMessage]:
        """获取会话里尚未见过、且不是自己发出的新消息。"""
        messages = self.get_messages(session.talker_id, size=3)
        new_messages: list[BilibiliMessage] = []
        for message in messages:
            if not message.msg_key or message.msg_key in self._seen_msg_keys:
                continue
            if self._my_uid and message.sender_uid == self._my_uid:
                continue
            if message.timestamp <= self._last_msg_times.get(session.talker_id, 0):
                continue
            self._seen_msg_keys.add(message.msg_key)
            new_messages.append(message)
        if new_messages:
            self._last_msg_times[session.talker_id] = max(item.timestamp for item in new_messages)
        return new_messages

    def send_message(self, receiver_id: int, text: str) -> bool:
        """发送文本私信。"""
        message = (text or "").strip()
        if not receiver_id or not message:
            self._logger.warning("B站私信参数不完整（receiver_id/text 不能为空）")
            return False
        sender_uid = self.my_uid
        if not sender_uid:
            self._logger.debug("B站私信发送失败：未取到自己的 UID")
            return False
        form: dict[str, Any] = {
            "msg[sender_uid]": sender_uid,
            "msg[receiver_id]": _to_int(receiver_id),
            "msg[receiver_type]": 1,
            "msg[msg_type]": 1,
            "msg[msg_status]": 0,
            "msg[content]": json.dumps({"content": message}, ensure_ascii=False),
            "msg[timestamp]": int(time.time()),
            "msg[new_face_version]": 0,
            "msg[dev_id]": DEFAULT_DEVICE_ID,
            "build": 0,
            "mobi_app": "web",
            "csrf": self._bili_jct,
            "csrf_token": self._bili_jct,
        }
        self._rate_limit_wait()
        try:
            self._fetch(
                "POST",
                f"{VC_BASE}/web_im/v1/web_im/send_msg",
                data=form,
                headers={"Referer": "https://message.bilibili.com/"},
            )
        except BilibiliError as exc:
            self._on_write_error("私信发送", exc)
            return False
        self._logger.info(f"B站私信已发送: receiver={receiver_id}")
        return True
