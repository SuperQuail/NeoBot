"""内置命令:/help /reboot /add_admin /del_admin。"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from neobot_app.commands.model import (
    PERM_EVERYONE,
    PERM_SUB_ADMIN,
    PERM_SUPER_ADMIN,
    Command,
    CommandContext,
    permission_name,
)
from neobot_app.runtime.sleep_service import parse_sleep_duration

if TYPE_CHECKING:
    from neobot_app.commands.service import CommandService

_QQ_PATTERN = re.compile(r"^\d{5,15}$")


def build_builtin_commands(service: "CommandService") -> list[Command]:
    return [
        Command(
            name="help",
            description="查看可用命令列表;/help <命令名> 查看单个命令的详细说明与参数",
            permission=PERM_EVERYONE,
            usage="[命令名]",
            params=(
                ("命令名", "可选。查看指定命令的详细说明、参数与权限要求"),
            ),
            handler=_handle_help,
        ),
        Command(
            name="reboot",
            description="重启 Bot(超级管理员)",
            permission=PERM_SUPER_ADMIN,
            params=(),
            handler=_handle_reboot,
        ),
        Command(
            name="add_admin",
            description="添加次级管理员,用 QQ 号或 @ 指定(超级管理员)",
            permission=PERM_SUPER_ADMIN,
            usage="<QQ号|@某人>",
            params=(
                ("QQ号|@某人", "必填。要添加为次级管理员的 QQ 号,或直接 @ 对方"),
            ),
            handler=_handle_add_admin,
        ),
        Command(
            name="del_admin",
            description="删除次级管理员,用 QQ 号或 @ 指定(超级管理员)",
            permission=PERM_SUPER_ADMIN,
            usage="<QQ号|@某人>",
            params=(
                ("QQ号|@某人", "必填。要移除的次级管理员 QQ 号,或直接 @ 对方"),
            ),
            handler=_handle_del_admin,
        ),
        Command(
            name="sleep",
            description="让 Bot 进入睡眠(次级管理员);睡眠期间群聊只接收不回复,被@会叫醒",
            permission=PERM_SUB_ADMIN,
            usage="<时长>",
            params=(
                (
                    "时长",
                    "必填。睡眠时长,支持 30s / 10m / 2h / 1d,裸数字按分钟,最多 12 小时",
                ),
            ),
            handler=_handle_sleep,
        ),
        Command(
            name="awake",
            description="叫醒睡眠中的 Bot(次级管理员)",
            permission=PERM_SUB_ADMIN,
            params=(),
            handler=_handle_awake,
        ),
    ]


def _render_command_list_markdown(commands: list[Command]) -> str:
    """命令列表 markdown(列表)。"""
    lines = ["# 可用命令", ""]
    for command in commands:
        name_part = command.display_name
        if command.usage:
            name_part += f" {command.usage}"
        lines.append(f"- `{name_part}` — {command.description}")
        lines.append(f"  - 权限: **{permission_name(command.permission)}**")
    lines.append("")
    lines.append("> 命令以 `/` 开头,群聊中需先 @bot。")
    return "\n".join(lines)


def _render_command_detail_markdown(command: Command) -> str:
    """单个命令的详细说明 markdown。"""
    lines = [
        f"# `{command.display_name}`",
        "",
        f"{command.description}",
        "",
        "| 项目 | 内容 |",
        "| --- | --- |",
        f"| 权限 | {permission_name(command.permission)} |",
        f"| 用法 | `{command.display_name}{' ' + command.usage if command.usage else ''}` |",
    ]
    if command.aliases:
        lines.append(f"| 别名 | `{'`、`'.join('/' + alias for alias in command.aliases)}` |")
    if command.params:
        lines.extend(
            [
                "",
                "## 参数",
                "",
                "| 参数 | 说明 |",
                "| --- | --- |",
            ]
        )
        for name, description in command.params:
            lines.append(f"| `{name}` | {description} |")
    return "\n".join(lines)


async def _handle_help(ctx: CommandContext) -> str | None:
    """列出当前用户可见的命令;带参数时显示指定命令的详情。

    使用 markdown 渲染器输出为图片发送;渲染失败时降级为纯文本。
    返回 None 表示已自行发送回复。
    """
    visible = [
        command
        for command in ctx.service.registry.commands()
        if ctx.service.permissions.can(ctx.user_id, command.permission)
    ]
    visible.sort(key=lambda command: command.name)

    target = None
    if ctx.args:
        target = ctx.args[0].lstrip("/")

    if target:
        command = ctx.service.registry.get(target)
        if command is None:
            text = (
                f"未找到命令 `/{target}`。\n\n"
                "可用命令:\n" + "\n".join(f"  {item.help_line}" for item in visible)
            )
        elif command not in visible:
            text = f"命令 `/{target}` 存在,但你没有权限查看其详情(需要权限:{permission_name(command.permission)})。"
        else:
            markdown = _render_command_detail_markdown(command)
            if await ctx.service.send_markdown_image(
                ctx.kind, ctx.conv_id, markdown, at_user_id=ctx.user_id
            ):
                return None
            text = (
                f"{command.help_line}\n"
                + ("参数:\n" + "\n".join(f"  {name} — {desc}" for name, desc in command.params))
            )
        if await ctx.service.send_markdown_image(ctx.kind, ctx.conv_id, text, at_user_id=ctx.user_id):
            return None
        return text

    markdown = _render_command_list_markdown(visible)
    if await ctx.service.send_markdown_image(
        ctx.kind, ctx.conv_id, markdown, at_user_id=ctx.user_id
    ):
        return None
    lines = ["可用命令:"]
    for command in visible:
        lines.append(f"  {command.help_line}")
    lines.append("命令以 / 开头,群聊中需先 @bot。")
    return "\n".join(lines)


async def _handle_reboot(ctx: CommandContext) -> str:
    """重启 Bot(进程内重建应用,cli 主循环支持)。"""
    if not ctx.service.request_restart():
        return "重启功能不可用(当前启动方式不支持)"
    return "正在重启…请稍候"


async def _handle_sleep(ctx: CommandContext) -> str:
    """让 Bot 进入睡眠:睡眠期间群聊消息只接收不回复,被@会唤醒;私聊不受影响。"""
    sleep_service = getattr(ctx.service, "sleep_service", None)
    if sleep_service is None:
        return "睡眠功能不可用(未注入睡眠服务)"
    if not ctx.args:
        return (
            "请提供睡眠时长,例如: /sleep 2h"
            "(支持 30s / 10m / 2h / 1d,裸数字按分钟,最多 12 小时)"
        )
    seconds, error = parse_sleep_duration(ctx.args[0])
    if error is not None:
        return error
    _ok, message = sleep_service.sleep(seconds)
    return message


async def _handle_awake(ctx: CommandContext) -> str:
    """叫醒睡眠中的 Bot。"""
    sleep_service = getattr(ctx.service, "sleep_service", None)
    if sleep_service is None:
        return "睡眠功能不可用(未注入睡眠服务)"
    if sleep_service.wake(reason="awake_command"):
        return "我被叫醒了。"
    return "我没有在睡觉呀。"


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
