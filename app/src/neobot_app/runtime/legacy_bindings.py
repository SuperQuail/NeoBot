"""旧版依赖真实 QQ/群号的后台目标 → 官方会话 ID 的迁移解析。

历史定时任务/通知/跨聊天记录里存的是真实 QQ 号/群号；切到 only-official 后
官方协议只认本地 ID（openid）。这里做区分：
- 已是本地 ID（openid，或旧版合成号）：旧合成号借 identities.json 反查成 openid，
  查不到就原样使用；
- 真实 QQ/群号且有 /linkqq、/linkgroup 映射：自动换成 openid；
- 真实 QQ/群号且没有映射：WARNING（每目标仅一次），返回 None 不投递。
不是 only-official 时完全不动。
"""

from __future__ import annotations

from typing import Any

from neobot_app.bot_accounts import (
    identity_text,
    looks_like_real_group_number,
    looks_like_real_qq,
)
from neobot_app.user_identity import openid_for_group, openid_for_legacy_id, openid_for_qq

_WARNED: set[tuple[str, str]] = set()


def resolve_legacy_official_target(
    kind: str,
    conversation_id: Any,
    *,
    adapter: Any,
    logger: Any,
) -> tuple[str, str] | None:
    """返回 (目标 ID, 强制通道) 或 None（缺映射）。"""
    target = identity_text(conversation_id)
    if kind not in {"group", "private"} or not target:
        return target, ""
    active = getattr(adapter, "active_channels", None)
    if active is None or tuple(str(item) for item in active) != ("official",):
        return target, ""

    is_real = (
        looks_like_real_group_number(target)
        if kind == "group"
        else looks_like_real_qq(target)
    )
    if not is_real:
        # 已经是 openid：原样；旧版 13 位合成号：借适配器 identities.json 反查成 openid
        converted = openid_for_legacy_id(kind, target) or target
        return converted, "official"

    mapped = (
        openid_for_group(target, "official")
        if kind == "group"
        else openid_for_qq(target, "official")
    )
    if mapped:
        logger.info(
            "旧后台目标已按映射迁移到官方 openid",
            conversation_kind=kind,
            legacy_id=target,
            openid=mapped,
        )
        return mapped, "official"
    key = (kind, target)
    if key not in _WARNED:
        _WARNED.add(key)
        logger.warning(
            "官方通道无法解析旧后台目标：缺少真实 QQ/群号到官方 openid 的映射",
            conversation_kind=kind,
            legacy_id=target,
            hint="请用 /linkqq 或 /linkgroup 建立映射，或把任务目标改成官方会话 ID（openid）",
        )
    return None
