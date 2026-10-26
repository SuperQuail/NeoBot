"""流水线用到的消息解析小工具。"""

from __future__ import annotations

from neobot_adapter.model.message import GroupMessage
from neobot_adapter.model.message import PrivateMessage


def _build_poke_action_text(
    raw_info: list | None,
    sender_name: str,
    target_name: str,
) -> str:
    """从 raw_info 构建完整的戳一戳动作文本，如 '唐天揉了揉弥音的脸'。

    raw_info 结构示例:
    [
        {"col": "0", ...},
        {"col": "1", ...},
        {"col": "2", "txt": "揉了揉"},   # 动作前缀
        {"col": "3", ...},               # 目标占位
        {"col": "4", "txt": "的脸"},     # 动作后缀
    ]
    """
    if not isinstance(raw_info, list) or not raw_info:
        return ""

    sender = sender_name or "QQ用户"
    target = target_name or "QQ用户"

    try:
        first_txt = ""
        second_txt = ""
        # raw_info[2] 是动作前缀，raw_info[4] 是动作后缀
        if len(raw_info) > 2 and isinstance(raw_info[2], dict):
            first_txt = str(raw_info[2].get("txt", "") or "")
        if len(raw_info) > 4 and isinstance(raw_info[4], dict):
            second_txt = str(raw_info[4].get("txt", "") or "")

        if first_txt:
            return f"{sender}{first_txt}{target}{second_txt}"
    except Exception:
        pass

    return ""

def _extract_reply_message_ids(message: PrivateMessage | GroupMessage) -> list[int]:
    ids: list[int] = []
    for segment in getattr(message, "message", None) or []:
        segment_type = getattr(segment, "type", None)
        if hasattr(segment_type, "value"):
            segment_type = segment_type.value
        if str(segment_type) != "reply":
            continue
        raw_data = getattr(segment, "data", None)
        if isinstance(raw_data, dict):
            data = raw_data
        elif hasattr(raw_data, "model_dump"):
            data = raw_data.model_dump(exclude_none=True)
        else:
            data = {}
        message_id = _safe_int(data.get("id"))
        if message_id is not None and message_id not in ids:
            ids.append(message_id)
    return ids

def _sender_name(message: PrivateMessage | GroupMessage) -> str:
    sender = getattr(message, "sender", None)
    if sender is not None:
        for field in ("card", "nickname"):
            value = getattr(sender, field, None)
            if value:
                return str(value)
    user_id = getattr(message, "user_id", None)
    return f"QQ:{user_id}" if user_id is not None else ""

def _credential_message_text(message: PrivateMessage | GroupMessage) -> str:
    """提取消息的纯文本内容(不含"发送者: "前缀,用于凭据匹配)。

    注意:event_message__to_text 会拼接发送者名前缀,凭据文本匹配必须
    使用纯文本段拼接,否则签发永远无法命中。
    """
    parts: list[str] = []
    segments = getattr(message, "message", None)
    if not segments:
        return ""
    for segment in segments:
        segment_type = getattr(segment, "type", None)
        segment_type = getattr(segment_type, "value", segment_type)
        if str(segment_type or "") != "text":
            continue
        data = getattr(segment, "data", None)
        if isinstance(data, dict):
            text = data.get("text")
        else:
            text = getattr(data, "text", None)
        if text:
            parts.append(str(text))
    return "".join(parts)

def _safe_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None

def _message_has_images(message: PrivateMessage | GroupMessage) -> bool:
    """检查消息是否包含图片段（image 或 cardimage）。"""
    segments = getattr(message, "message", None)
    if not segments:
        return False
    for seg in segments:
        seg_type = getattr(seg, "type", None)
        if hasattr(seg_type, "value"):
            seg_type = seg_type.value
        if str(seg_type or "") in ("image", "cardimage"):
            return True
    return False
