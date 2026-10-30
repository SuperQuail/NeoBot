"""订阅类命令：监听 / 取消监听 / 监听列表（推送开关见 commands_toggle.py）。

与旧实现的区别：
1. 命令注册进宿主命令表（ctx.app_commands.register），因此会出现在 /help 列表与详情里，
   权限校验与参数切分都交给宿主统一处理；
2. 回复统一走 cards.send_card（与 /help 同一套卡片渲染），渲染不可用时自动降级纯文本。

注意：宿主命令在群聊里需要 @机器人 才会触发，私聊直接发即可。
"""

from __future__ import annotations

from typing import Any

from . import cards, db
from .bilibili.errors import BilibiliAPIError, BilibiliTransportError
from .bilibili.urls import live_room_page_url
from .subscriptions import SubscriptionService, parse_target
from .subscriptions import push_defaults as push_defaults

try:  # 无 NeoBot 环境（CI/单测）退化成常量，取值与本体一致
    from neobot_app.commands.model import PERM_EVERYONE, PERM_SUB_ADMIN
except Exception:  # pragma: no cover
    PERM_EVERYONE = 0
    PERM_SUB_ADMIN = 1

UNNAMED = "未命名"


def parse_switch(value: str | None) -> bool | None:
    """开/关文案解析；无法识别返回 None。"""
    text = (value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on", "开", "开启"}:
        return True
    if text in {"0", "false", "no", "n", "off", "关", "关闭"}:
        return False
    return None


def conv_group_id(command_ctx: Any) -> int:
    """取群号；私聊返回 0（这些命令只在群里生效）。"""
    if str(getattr(command_ctx, "kind", "")) != "group":
        return 0
    try:
        return int(getattr(command_ctx, "conv_id", 0))
    except (TypeError, ValueError):
        return 0


def command_args(command_ctx: Any) -> list[str]:
    """命令参数列表（宿主已用 shlex 切分）。"""
    return [str(item) for item in (getattr(command_ctx, "args", None) or [])]


def shots(ctx: Any) -> Any:
    """每次都现取截图端口：软重启会换新实例，不能缓存。"""
    return getattr(ctx, "screenshots", None)


def usage_card(title: str, lines: list[str]) -> dict[str, Any]:
    return cards.message_card(
        title=title, lines=lines, note="群聊里需要先 @机器人 再发命令"
    )


async def fail(
    command_ctx: Any, ctx: Any, title: str, text: str, hint: str = ""
) -> None:
    """统一的失败卡片。"""
    await cards.send_card(
        command_ctx,
        cards.error_card(title=title, text=text, hint=hint),
        screenshots=shots(ctx),
    )


def register_commands(ctx: Any, state: Any) -> list[str]:
    """注册全部命令，返回请求注册的命令名（/help 里能看到的就是这些）。"""
    registrar = getattr(ctx, "app_commands", None)
    if registrar is None or not getattr(registrar, "available", True):
        ctx.logger.warning("命令注册表不可用，streaming_parser 的命令未注册")
        return []
    registered = _register_subscription_commands(registrar, ctx, state)
    from .commands_toggle import register_toggle_commands
    from .settings_commands import register_settings_commands

    registered += register_toggle_commands(registrar, ctx, state)
    registered += register_settings_commands(registrar, ctx, state)
    renames = getattr(registrar, "renames", None)
    if callable(renames):
        for requested, actual in renames():
            ctx.logger.warning(f"命令 /{requested} 因重名被注册为 /{actual}")
    return registered


def _register_subscription_commands(registrar: Any, ctx: Any, state: Any) -> list[str]:
    names: list[str] = []

    @registrar.register(
        "监听",
        description="让本群监听一个直播间（开播/下播时推送卡片）",
        usage="<房间号|短号|直播间链接|UP主空间链接>",
        permission=PERM_SUB_ADMIN,
        params=(("目标", "房间号、短号、直播间链接或 UP 主空间链接"),),
    )
    async def _subscribe(command_ctx: Any) -> None:
        group_id = conv_group_id(command_ctx)
        if not group_id:
            await fail(command_ctx, ctx, "只能在群里使用", "这个命令需要在群聊里发送。")
            return
        args = command_args(command_ctx)
        if not args:
            await cards.send_card(
                command_ctx,
                usage_card(
                    "监听直播间",
                    [
                        "/监听 <房间号|短号|直播间链接|UP主空间链接>",
                        "例如：/监听 1914112138",
                        "例如：/监听 https://space.bilibili.com/392669996",
                    ],
                ),
                screenshots=shots(ctx),
            )
            return
        try:
            kind, value = parse_target(args[0])
        except ValueError as exc:
            await fail(command_ctx, ctx, "参数不对", str(exc))
            return
        try:
            resolved = await state.resolve_target(kind, value)
        except (BilibiliAPIError, BilibiliTransportError) as exc:
            await fail(command_ctx, ctx, "查询直播间失败", str(exc))
            return
        except ValueError as exc:
            await fail(command_ctx, ctx, "没有找到直播间", str(exc))
            return
        view, created = await SubscriptionService(state).create_resolved(
            group_id, resolved
        )
        title = "已开始监听" if created else "已更新监听信息"
        name = resolved.get("name") or UNNAMED
        room_id = view.room_id
        push_live = view.push_live
        push_live_end = view.push_live_end
        await cards.send_card(
            command_ctx,
            cards.kv_card(
                title=title,
                items=[
                    ("主播", name),
                    ("房间号", str(room_id)),
                    ("开播推送", "开" if push_live else "关"),
                    ("下播推送", "开" if push_live_end else "关"),
                    ("直播间", live_room_page_url(room_id)),
                ],
                note="新订阅按本群默认建推送（/config 开播推送默认、下播推送默认 可改）；"
                "单个直播间用 /开播推送、/下播推送 关掉，AI 回复也用 /config 调",
            ),
            screenshots=shots(ctx),
        )

    names.append("监听")

    @registrar.register(
        "取消监听",
        description="取消本群对某个直播间的监听",
        usage="<房间号|短号|直播间链接|UP主空间链接>",
        permission=PERM_SUB_ADMIN,
        params=(("目标", "与 /监听 相同的目标写法"),),
    )
    async def _unsubscribe(command_ctx: Any) -> None:
        group_id = conv_group_id(command_ctx)
        if not group_id:
            await fail(command_ctx, ctx, "只能在群里使用", "这个命令需要在群聊里发送。")
            return
        args = command_args(command_ctx)
        if not args:
            await cards.send_card(
                command_ctx,
                usage_card("取消监听", ["/取消监听 <房间号|短号|链接>"]),
                screenshots=shots(ctx),
            )
            return
        try:
            kind, value = parse_target(args[0])
        except ValueError as exc:
            await fail(command_ctx, ctx, "参数不对", str(exc))
            return
        row = await state.find_subscription(group_id, kind, value)
        if row is None:
            await fail(
                command_ctx,
                ctx,
                "没有监听这个直播间",
                "本群当前没有监听它。",
                hint="用 /监听列表 看看都在监听什么",
            )
            return
        removed = await SubscriptionService(state).remove(group_id, row.room_id)
        if removed:
            await cards.send_card(
                command_ctx,
                cards.kv_card(
                    title="已取消监听",
                    items=[
                        ("直播间", row.name or UNNAMED),
                        ("房间号", str(row.room_id)),
                    ],
                ),
                screenshots=shots(ctx),
            )
        else:
            await fail(command_ctx, ctx, "取消失败", "请稍后再试一次。")

    names.append("取消监听")

    @registrar.register(
        "监听列表",
        description="列出本群监听的全部直播间与推送开关",
        permission=PERM_EVERYONE,
    )
    async def _list(command_ctx: Any) -> None:
        group_id = conv_group_id(command_ctx)
        if not group_id:
            await fail(command_ctx, ctx, "只能在群里使用", "这个命令需要在群聊里发送。")
            return
        async with state.database.session() as session:
            rows = [
                db.sub_view(row)
                for row in await db.list_group_subscriptions(session, group_id)
            ]
        if not rows:
            await cards.send_card(
                command_ctx,
                cards.message_card(
                    title="本群还没有监听任何直播间",
                    lines=["用 /监听 房间号 添加第一个"],
                ),
                screenshots=shots(ctx),
            )
            return
        table = [
            [
                str(index),
                row.name or UNNAMED,
                str(row.room_id),
                "开" if row.push_live else "关",
                "开" if row.push_live_end else "关",
            ]
            for index, row in enumerate(rows, start=1)
        ]
        await cards.send_card(
            command_ctx,
            cards.rows_card(
                title="本群监听的直播间",
                subtitle="共 " + str(len(rows)) + " 个",
                columns=["#", "主播", "房间号", "开播推送", "下播推送"],
                rows=table,
                note="用 /开播推送 或 /下播推送 单独开关某一个直播间",
            ),
            screenshots=shots(ctx),
        )

    names.append("监听列表")
    return names
