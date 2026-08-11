"""内置命令:/help /reboot /add_admin /del_admin。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from neobot_app.commands.model import (
    PERM_EVERYONE,
    PERM_SUPER_ADMIN,
    Command,
    CommandContext,
)

if TYPE_CHECKING:
    from neobot_app.commands.service import CommandService

_QQ_PATTERN = re.compile(r"^\d{5,15}$")


def build_builtin_commands(service: "CommandService") -> list[Command]:
    return [
        Command(
            name="help",
            description="查看可用命令列表",
            permission=PERM_EVERYONE,
            handler=_handle_help,
        ),
        Command(
            name="reboot",
            description="重启 Bot(超级管理员)",
            permission=PERM_SUPER_ADMIN,
            handler=_handle_reboot,
        ),
        Command(
            name="add_admin",
            description="添加次级管理员,用 QQ 号或 @ 指定(超级管理员)",
            permission=PERM_SUPER_ADMIN,
            usage="<QQ号|@某人>",
            handler=_handle_add_admin,
        ),
        Command(
            name="del_admin",
            description="删除次级管理员,用 QQ 号或 @ 指定(超级管理员)",
            permission=PERM_SUPER_ADMIN,
            usage="<QQ号|@某人>",
            handler=_handle_del_admin,
        ),
    ]


async def _handle_help(ctx: CommandContext) -> str:
    """列出当前用户可见的命令。"""
    lines = ["可用命令:"]
    visible = [
        command
        for command in ctx.service.registry.commands()
        if ctx.service.permissions.can(ctx.user_id, command.permission)
    ]
    visible.sort(key=lambda command: command.name)
    for command in visible:
        lines.append(f"  {command.help_line}")
    lines.append("命令以 / 开头,群聊中需先 @bot。")
    return "\n".join(lines)


async def _handle_reboot(ctx: CommandContext) -> str:
    """重启 Bot(进程内重建应用,cli 主循环支持)。"""
    if not ctx.service.request_restart():
        return "重启功能不可用(当前启动方式不支持)"
    return "正在重启…请稍候"


async def _handle_add_admin(ctx: CommandContext) -> str:
    return await _modify_admin(ctx, add=True)


async def _handle_del_admin(ctx: CommandContext) -> str:
    return await _modify_admin(ctx, add=False)


async def _modify_admin(ctx: CommandContext, *, add: bool) -> str:
    """添加/删除次级管理员:QQ 号参数或 @ 提取。"""
    target_qq = _extract_target_qq(ctx)
    if target_qq is None:
        return (
            "请指定目标: /add_admin <QQ号> 或 /add_admin @某人\n"
            f"当前权限: {ctx.service.permissions.describe()}"
        )

    supers = ctx.service.permissions.super_admins
    if target_qq in supers:
        return f"QQ {target_qq} 是超级管理员,超级管理员只能通过配置增减,不能通过命令修改。"

    current = set(ctx.service.permissions.sub_admins)
    if add:
        if target_qq in current:
            return f"QQ {target_qq} 已是次级管理员。"
        current.add(target_qq)
        action = "添加"
    else:
        if target_qq not in current:
            return f"QQ {target_qq} 不是次级管理员。"
        current.discard(target_qq)
        action = "删除"

    result = await ctx.service.save_sub_admins(sorted(current))
    if result.startswith("错误"):
        return result
    return f"已{action}次级管理员 QQ {target_qq}。\n当前次级管理员: {'、'.join(str(qq) for qq in sorted(current)) or '(无)'}"


def _extract_target_qq(ctx: CommandContext) -> int | None:
    """从参数或 @ 段提取目标 QQ 号(排除 @bot 触发段)。"""
    bot_account = ctx.service._bot_account()
    # 优先 @ 段(排除 bot 自己)
    for qq in sorted(ctx.at_qqs):
        if qq != bot_account:
            return qq
    # 参数中的 QQ 号
    for arg in ctx.args:
        candidate = arg.strip()
        if candidate.startswith("@"):
            candidate = candidate[1:]
        if _QQ_PATTERN.match(candidate):
            return int(candidate)
    return None
