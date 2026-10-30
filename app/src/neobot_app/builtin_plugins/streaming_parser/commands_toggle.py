"""推送开关命令：/开播推送、/下播推送（每个直播间单独开关）。"""

from __future__ import annotations

from typing import Any

from . import cards
from .commands import (
    UNNAMED,
    command_args,
    conv_group_id,
    fail,
    parse_switch,
    parse_target,
    shots,
    usage_card,
)
from .subscriptions import SubscriptionService

try:
    from neobot_app.commands.model import PERM_SUB_ADMIN
except Exception:  # pragma: no cover
    PERM_SUB_ADMIN = 1


def register_toggle_commands(registrar: Any, ctx: Any, state: Any) -> list[str]:
    """注册开播/下播推送开关命令。"""
    names: list[str] = []
    _register_one(registrar, ctx, state, names, "开播推送", "live", "开播")
    _register_one(registrar, ctx, state, names, "下播推送", "live_end", "下播")
    return names


def _register_one(
    registrar: Any,
    ctx: Any,
    state: Any,
    names: list[str],
    command_name: str,
    kind: str,
    label: str,
) -> None:
    """注册一条开关命令；用工厂函数避免闭包捕获循环变量。"""
    usage_text = "/" + command_name + " <房间号|短号|链接> <开|关>"

    @registrar.register(
        command_name,
        description="开关某个直播间的" + label + "推送",
        usage="<房间号|短号|链接> <开|关>",
        permission=PERM_SUB_ADMIN,
        params=(("目标", "与 /监听 相同的目标写法"), ("开关", "开 或 关")),
    )
    async def _toggle(command_ctx: Any) -> None:
        group_id = conv_group_id(command_ctx)
        if not group_id:
            await fail(command_ctx, ctx, "只能在群里使用", "这个命令需要在群聊里发送。")
            return
        args = command_args(command_ctx)
        if len(args) < 2:
            await cards.send_card(
                command_ctx,
                usage_card(label + "推送开关", [usage_text]),
                screenshots=shots(ctx),
            )
            return
        switch = parse_switch(args[1])
        if switch is None:
            await fail(
                command_ctx, ctx, "开关只能填 开 或 关", "收到的是：" + str(args[1])
            )
            return
        try:
            target_kind, number = parse_target(args[0])
        except ValueError as exc:
            await fail(command_ctx, ctx, "参数不对", str(exc))
            return
        row = await state.find_subscription(group_id, target_kind, number)
        if row is None:
            await fail(command_ctx, ctx, "没有监听这个直播间", "先用 /监听 添加它。")
            return
        await SubscriptionService(state).toggle(
            group_id,
            row.room_id,
            push_live=switch if kind == "live" else None,
            push_live_end=switch if kind == "live_end" else None,
        )
        await cards.send_card(
            command_ctx,
            cards.kv_card(
                title="已更新推送开关",
                items=[
                    ("主播", row.name or UNNAMED),
                    ("房间号", str(row.room_id)),
                    (label + "推送", "开" if switch else "关"),
                ],
                note="推送卡片后是否再触发一次 AI 回复，用 /config 调整",
            ),
            screenshots=shots(ctx),
        )

    names.append(command_name)
