"""消息段渲染：正文、@提及包装、回复段与 CQ 字符串互转。"""

from __future__ import annotations

from enum import Enum
import re
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional

from .common import QueueMessage
from .helpers import _safe_int


class _QueueSegmentMixin:
    def _render_message_content(
        self,
        message: QueueMessage,
        *,
        replied_messages: Optional[List[QueueMessage]] = None,
        reply_number_resolver: Optional[Callable[[int], int]] = None,
        wrap_at_mention: bool = False,
    ) -> str:
        reply_by_id = {
            reply.message_id: reply
            for reply in (replied_messages or [])
            if reply.message_id is not None
        }
        if message.message:
            parts: list[str] = []
            has_at_bot = False
            for segment in message.message:
                seg_text = self._normalize_inline_text(
                    self._segment_to_text(
                        segment,
                        reply_by_id=reply_by_id,
                        reply_number_resolver=reply_number_resolver,
                    )
                )
                if wrap_at_mention and self._is_at_bot_segment(segment):
                    has_at_bot = True
                    parts.append(
                        f"<这是新的可能要回答的内容>{seg_text}</这是新的可能要回答的内容>"
                    )
                else:
                    parts.append(seg_text)
            if has_at_bot:
                return "".join(parts).strip()
            if wrap_at_mention:
                text = "".join(parts).strip()
                return f"<这是新的可能要回答的内容>{text}</这是新的可能要回答的内容>" if text else "[无消息内容]"
            text = "".join(parts).strip()
            return text or "[无消息内容]"

        if message.raw_message:
            text = self._normalize_inline_text(self._parse_raw_message(message.raw_message))
            if wrap_at_mention:
                text = self._wrap_at_in_raw_message(text, message)
            return text or "[无消息内容]"

        return "[无消息内容]"

    def _is_at_bot_segment(self, segment: object) -> bool:
        if self.bot_account is None:
            return False
        seg_type = getattr(segment, "type", None)
        if isinstance(seg_type, Enum):
            seg_type = seg_type.value
        if str(seg_type) != "at":
            return False
        raw_data = getattr(segment, "data", None)
        data = self._segment_data_to_dict(raw_data)
        qq = str(data.get("qq") or "")
        return qq == str(self.bot_account)

    def _wrap_at_in_raw_message(self, text: str, _message: QueueMessage) -> str:
        if self.bot_account is None:
            return f"<这是新的可能要回答的内容>{text}</这是新的可能要回答的内容>"
        pattern = rf"(@QQ:{self.bot_account}|@[^(\n]*\(QQ:{self.bot_account}\))"
        if re.search(pattern, text):
            return re.sub(
                pattern,
                r"<这是新的可能要回答的内容>\1</这是新的可能要回答的内容>",
                text,
            )
        return f"<这是新的可能要回答的内容>{text}</这是新的可能要回答的内容>"

    def _segment_to_text(
        self,
        segment: object,
        *,
        reply_by_id: Optional[Dict[int, QueueMessage]] = None,
        reply_number_resolver: Optional[Callable[[int], int]] = None,
    ) -> str:
        msg_type = getattr(segment, "type", None)
        if isinstance(msg_type, Enum):
            msg_type = msg_type.value

        raw_data = getattr(segment, "data", None)
        if raw_data is None and isinstance(segment, dict):
            msg_type = msg_type or segment.get("type")
            raw_data = segment.get("data")

        if msg_type is None:
            return "[未知消息]"

        data = self._segment_data_to_dict(raw_data)
        if str(msg_type) == "reply":
            return self._format_reply_segment(
                data,
                reply_by_id or {},
                reply_number_resolver,
            )
        formatter = self._segment_formatters().get(str(msg_type))
        if formatter is not None:
            return formatter(data)

        cq_code = self._segment_to_cq(str(msg_type), data)
        if len(cq_code) > self.cq_fallback_max_length:
            return "未知过长消息"
        return cq_code

    @staticmethod
    def _segment_data_to_dict(raw_data: object) -> Dict[str, object]:
        if raw_data is None:
            return {}
        if isinstance(raw_data, dict):
            return raw_data
        if hasattr(raw_data, "model_dump"):
            return raw_data.model_dump(exclude_none=True)
        return {}

    def _format_reply_segment(
        self,
        data: Dict[str, object],
        reply_by_id: Dict[int, QueueMessage],
        reply_number_resolver: Optional[Callable[[int], int]] = None,
    ) -> str:
        message_id = _safe_int(data.get("id"))
        if message_id is None:
            return "[回复:消息ID=未知]"
        replied_message = reply_by_id.get(message_id)
        if replied_message is None:
            return f"[回复:消息ID={message_id}]"

        number = reply_number_resolver(message_id) if reply_number_resolver is not None else None
        label = f"回复消息{number}" if number is not None else f"回复消息ID={message_id}"
        sender = self._message_sender_name(replied_message)
        content = self._render_message_content(replied_message)
        return f"[{label}: {sender}: {content}]"

    @staticmethod
    def _format_at_segment(data: Dict[str, object]) -> str:
        qq = data.get("qq", "未知")
        if qq == "all":
            return "@全体成员"
        name = data.get("name")
        if name:
            return f"@{name}(QQ:{qq})"
        return f"@QQ:{qq}"

    @staticmethod
    def _normalize_inline_text(text: str) -> str:
        return text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")

    def _parse_raw_message(self, raw_message: str) -> str:
        pattern = r"\[CQ:([^,\]]+)(?:,([^\]]*))?\]"
        result: List[str] = []
        pos = 0

        for match in re.finditer(pattern, raw_message):
            if match.start() > pos:
                result.append(raw_message[pos:match.start()])

            msg_type = match.group(1)
            params = self._parse_cq_params(match.group(2) or "")
            formatter = self._segment_formatters().get(msg_type)
            cq_code = match.group(0)
            if formatter is not None:
                result.append(formatter(params))
            elif len(cq_code) > self.cq_fallback_max_length:
                result.append("未知过长消息")
            else:
                result.append(cq_code)

            pos = match.end()

        if pos < len(raw_message):
            result.append(raw_message[pos:])

        return "".join(result)

    @staticmethod
    def _parse_cq_params(params_str: str) -> Dict[str, str]:
        params: Dict[str, str] = {}
        if not params_str:
            return params
        for item in params_str.split(","):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            params[key] = value
        return params

    @staticmethod
    def _segment_to_cq(msg_type: str, data: Dict[str, object]) -> str:
        if not data:
            return f"[CQ:{msg_type}]"
        parts = []
        for key, value in data.items():
            if value is None:
                continue
            parts.append(f"{key}={value}")
        params = ",".join(parts)
        return f"[CQ:{msg_type},{params}]" if params else f"[CQ:{msg_type}]"
