"""旧版依赖真实 QQ/群号的后台目标 → 官方合成会话的迁移解析。

历史定时任务/通知/跨聊天记录里存的是真实 QQ 号/群号；切到 only-official 后
官方协议只认合成 ID。这里做区分：
- 已是合成 ID：原样使用；
- 真实 QQ/群号且有 /linkqq、/linkgroup 映射：自动换成合成 ID；
- 真实 QQ/群号且没有映射：WARNING（每目标仅一次），返回 None 不投递。
不是 only-official 时完全不动。
"""

from __future__ import annotations

from typing import Any

from neobot_app.bot_accounts import (
    is_synthetic_id,
    looks_like_real_group_number,
    looks_like_real_qq,
)
from neobot_app.user_identity import synthetic_for_group, synthetic_for_qq

_WARNED: set[tuple[str, str]] = set()


def resolve_legacy_official_target(
    kind: str,
    conversation_id: Any,
    *,
    adapter: Any,
    logger: Any,
) -> tuple[str, str] | None:
    """返回 (目标 ID, 强制通道) 或 None（缺映射）。"""
    target = str(conversation_id or "").strip()
    if kind not in {"group", "private"} or not target:
        return target, ""
    active = getattr(adapter, "active_channels", None)
    if active is None or tuple(str(item) for item in active) != ("official",):
        return target, ""
    if not target.isdigit():
        return target, ""
    if is_synthetic_id(target):
        return target, "official"
    if kind == "group" and not looks_like_real_group_number(target):
        return target, ""
    if kind == "private" and not looks_like_real_qq(target):
        return target, ""
    mapped = (
        synthetic_for_group(int(target), "official")
        if kind == "group"
        else synthetic_for_qq(int(target), "official")
    )
    if mapped:
        logger.info(
            "旧后台目标已按映射迁移到官方合成 ID",
            conversation_kind=kind,
            legacy_id=target,
            synthetic_id=mapped,
        )
        return str(mapped), "official"
    key = (kind, target)
    if key not in _WARNED:
        _WARNED.add(key)
        logger.warning(
            "官方通道无法解析旧后台目标：缺少真实 QQ/群号到官方合成 ID 的映射",
            conversation_kind=kind,
            legacy_id=target,
            hint="请用 /linkqq 或 /linkgroup 建立映射，或把任务目标改成官方合成 ID",
        )
    return None
