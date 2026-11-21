"""机器人是否被 @ 的唯一判定入口。

官方通道由适配器按官方 API 契约给出权威结论（消息模型 mentioned_self：
True/False），app 侧不再按通道名、uin、at 段 qq=0 等方式猜；None 表示
非官方/旧路径，回退 OneBot 的 at 段判定。
"""

from __future__ import annotations

from typing import Any

from neobot_app.bot_accounts import bot_account_for_message


def is_addressed_to_bot(message: Any, config: Any = None) -> bool:
    """这条消息是否明确 @ 了机器人。

    官方消息优先读 mentioned_self（True/False 权威，不再看 at 段/通道/self_id）；
    None 表示非官方/未知，回退 OneBot 的 at 段逻辑。
    """
    mentioned_self = getattr(message, "mentioned_self", None)
    if mentioned_self is not None:
        return bool(mentioned_self)
    return _onebot_at_addressed(message, config)


def _onebot_at_addressed(message: Any, config: Any = None) -> bool:
    """OneBot 语义：at 段 qq 等于消息级 self_id（缺省回退通道账号）。"""
    target = str(bot_account_for_message(message, config))
    if not target or target == "0":
        return False
    for segment in getattr(message, "message", None) or ():
        # 命令入口的 message 可能是模型段，也可能是插件/测试传的 dict 段
        if isinstance(segment, dict):
            segment_type = segment.get("type")
            data = segment.get("data") or {}
        else:
            segment_type = getattr(segment, "type", None)
            raw_data = getattr(segment, "data", None)
            data = (
                raw_data
                if isinstance(raw_data, dict)
                else (raw_data.model_dump(exclude_none=True) if hasattr(raw_data, "model_dump") else {})
            )
        if hasattr(segment_type, "value"):
            segment_type = segment_type.value
        if str(segment_type) != "at":
            continue
        if isinstance(data, dict) and str(data.get("qq") or "") == target:
            return True
    raw_message = str(getattr(message, "raw_message", "") or "")
    return f"[CQ:at,qq={target}" in raw_message
