"""设置类命令：/开播状态、/卡片风格、/config。"""

from __future__ import annotations

import asyncio
from typing import Any

from . import cards, db
from .commands import UNNAMED, command_args, conv_group_id, fail, shots
from .render import STYLE_ORDER

try:
    from neobot_app.commands.model import PERM_EVERYONE, PERM_SUB_ADMIN
except Exception:  # pragma: no cover
    PERM_EVERYONE = 0
    PERM_SUB_ADMIN = 1

#: 开播状态总览的渲染超时（渲染端口本身是串行的，给足时间但别无限等）
OVERVIEW_TIMEOUT = 25.0
#: /开播状态 实时查询的总体预算：超过就退回最近一次轮询结果，命令不能无限等
STATUS_QUERY_TIMEOUT = 15.0
OVERVIEW_FILENAME = "streaming_parser_overview.png"
RANDOM_WORDS = ("随机", "random")

STATUS_LABELS = {0: "未开播", 1: "直播中", 2: "轮播中"}


def status_label(live_status: int) -> str:
    """0 未开播 / 1 直播中 / 2 轮播（轮播不算开播，但要在总览里区分出来）。"""
    return STATUS_LABELS.get(int(live_status), "未知")


def style_list_text() -> str:
    return " / ".join(STYLE_ORDER)


def match_style(value: str | None) -> str | None:
    """把用户输入的风格名归一成已登记风格或 random；不合法返回 None。"""
    wanted = (value or "").strip().lower()
    if not wanted:
        return None
    if wanted in RANDOM_WORDS:
        return "random"
    if wanted in STYLE_ORDER:
        return wanted
    return None


def config_lines(setting: Any, config: Any) -> list[str]:
    """卡片里展示的当前设置 + 用法。"""
    default_style = getattr(config, "default_card_style", "random") if config else "random"
    return [
        "开播后触发 AI 回复：" + ("开" if setting.ai_reply_live else "关"),
        "下播后触发 AI 回复：" + ("开" if setting.ai_reply_live_end else "关"),
        "卡片风格：" + (setting.card_style or default_style),
        "监听新直播间时自动开启：开播推送 " + ("开" if setting.default_push_live else "关")
        + "、下播推送 " + ("开" if setting.default_push_live_end else "关"),
        "/config 开播AI 开|关    只发卡片不叫 AI：/config 开播AI 关",
        "/config 下播AI 开|关",
        "/config 风格 " + style_list_text() + "|随机",
        "/config 开播推送默认 开|关",
        "/config 下播推送默认 开|关",
    ]


async def _setting_view(state: Any, group_id: int) -> Any:
    async with state.database.session() as session:
        return db.setting_view(await db.get_group_setting(session, group_id))


def group_defaults(config: Any) -> dict[str, Any]:
    """建群设置行时用的默认值，全部取自插件配置。

    任何一条建行路径都要用同一份默认值，否则 /config 里看到的值和 /监听
    实际用的群级默认会对不上（空 defaults 会落到 db 模型自带的默认值）。
    """
    return {
        "card_style": config.default_card_style,
        "ai_reply_live": config.default_ai_reply_live,
        "ai_reply_live_end": config.default_ai_reply_live_end,
        "default_push_live": config.default_push_live,
        "default_push_live_end": config.default_push_live_end,
    }


async def _ensure_setting(state: Any, group_id: int, config: Any) -> Any:
    async with state.database.transaction() as session:
        return db.setting_view(
            await db.ensure_group_setting(session, group_id, group_defaults(config))
        )


async def _set_field(state: Any, group_id: int, field: str, value: Any) -> None:
    async with state.database.transaction() as session:
        setting = await db.ensure_group_setting(session, group_id, group_defaults(state.config))
        setattr(setting, field, value)


async def collect_states(
    ctx: Any, state: Any, rows: list[Any], *, query_remote: bool = True
) -> tuple[dict[int, Any], bool]:
    """取每个直播间的状态：优先刚刚向 B 站查的实时结果，其次用最近一次轮询落库的结果。

    query_remote=False 表示跳过实时查询（调用方已经等超时了），只读本地快照。
    返回 (状态映射, 是否全部来自实时查询)。
    """
    room_ids = [row.room_id for row in rows]
    fresh: dict[int, Any] = {}
    poller = getattr(state, "poller", None)
    if query_remote and poller is not None and room_ids:
        try:
            fresh = await poller.refresh(room_ids)
        except Exception as exc:
            ctx.logger.warning(f"实时查询直播状态失败，改用最近一次轮询结果: {exc!r}")
    async with state.database.session() as session:
        stored: dict[int, Any] = {}
        for room_id in room_ids:
            stored[room_id] = db.room_view(await db.get_room_state(session, room_id))
    states: dict[int, Any] = {}
    for room_id in room_ids:
        snapshot = fresh.get(room_id)
        if snapshot is not None:
            states[room_id] = db.RoomStateView(
                room_id=room_id,
                live_status=snapshot.live_status,
                title=snapshot.title,
                cover_url=snapshot.cover_url,
                area_name=snapshot.area_name,
                online=snapshot.online,
            )
        elif stored.get(room_id) is not None:
            states[room_id] = stored[room_id]
    return states, bool(room_ids) and len(fresh) == len(room_ids)


def register_settings_commands(registrar: Any, ctx: Any, state: Any) -> list[str]:
    names: list[str] = []

    @registrar.register(
        "开播状态",
        description="出一张开播状态总览图：本群关注的主播，开播中的带粉色圆环",
        permission=PERM_EVERYONE,
    )
    async def _overview(command_ctx: Any) -> None:
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
                cards.message_card(title="本群还没有监听任何直播间", lines=["用 /监听 房间号 添加第一个"]),
                screenshots=shots(ctx),
            )
            return
        config = state.config
        rows = rows[: int(config.overview_max_hosts)]
        try:
            states, is_fresh = await asyncio.wait_for(
                collect_states(ctx, state, rows), timeout=STATUS_QUERY_TIMEOUT
            )
        except (asyncio.TimeoutError, TimeoutError):
            # 实时查询整体超时（风控/网络挂着）：退回库里最近一次轮询结果，
            # 不能因为一个卡住的上游接口让 /开播状态 一直不回话。
            ctx.logger.warning(
                f"实时查询直播状态超过 {STATUS_QUERY_TIMEOUT:g} 秒，改用最近一次轮询结果"
            )
            states, is_fresh = await collect_states(ctx, state, rows, query_remote=False)
        live_count = sum(1 for view in states.values() if int(view.live_status) == 1)
        title = "本群关注的主播"
        source_note = "刚刚查询" if is_fresh else "最近一次轮询"
        summary = (
            "共 " + str(len(rows)) + " 位，" + str(live_count) + " 位正在直播（" + source_note + "）"
        )
        hosts = await state.build_overview_hosts(rows, states)
        table = [
            [
                row.name or UNNAMED,
                status_label(int(states[row.room_id].live_status)) if row.room_id in states else "未开播",
                str(row.room_id),
            ]
            for row in rows
        ]
        payload = cards.rows_card(
            title=title,
            subtitle=summary,
            columns=["主播", "状态", "房间号"],
            rows=table,
            note="总览图不可用（渲染或发送失败），这里是文字版",
        )
        style = await state.style_for(group_id)
        image = None
        try:
            image = await asyncio.wait_for(
                state.renderer.render_overview(
                    hosts, style=style, title_text=title, summary_text=summary
                ),
                timeout=OVERVIEW_TIMEOUT,
            )
        except (asyncio.TimeoutError, TimeoutError):
            ctx.logger.warning("渲染开播状态总览图超时，退回文字版")
        if image is not None:
            try:
                sent = await command_ctx.service.send_image_bytes(
                    command_ctx.kind,
                    command_ctx.conv_id,
                    image,
                    at_user_id=None,
                    filename=OVERVIEW_FILENAME,
                )
            except Exception:
                sent = False
            if sent:
                return
            ctx.logger.warning("发送开播状态总览图失败，退回文字版")
        # 渲染或发送失败都只降级一次：不再让卡片渲染器把同一份表格重画一遍
        # （同一端口失败时那会再等一整个渲染超时）。
        await command_ctx.reply_plain(cards.payload_text(payload))

    names.append("开播状态")

    @registrar.register(
        "卡片风格",
        description="查看或设置本群的开播/下播卡片风格",
        usage="[sakura|neon|minimal|随机]",
        permission=PERM_SUB_ADMIN,
        params=(("风格", "sakura（樱花粉）/ neon（霓虹暗）/ minimal（极简）/ 随机"),),
    )
    async def _style(command_ctx: Any) -> None:
        group_id = conv_group_id(command_ctx)
        if not group_id:
            await fail(command_ctx, ctx, "只能在群里使用", "这个命令需要在群聊里发送。")
            return
        args = command_args(command_ctx)
        chosen = match_style(args[0]) if args else None
        if args and chosen is None:
            await fail(command_ctx, ctx, "没有这个风格", "可选：" + style_list_text() + " 或 随机")
            return
        config = state.config
        setting = await _setting_view(state, group_id)
        if setting is None:
            setting = await _ensure_setting(state, group_id, config)
        if not args:
            await cards.send_card(
                command_ctx,
                cards.kv_card(
                    title="卡片风格",
                    items=[
                        ("当前风格", setting.card_style or config.default_card_style),
                        ("可选风格", style_list_text()),
                    ],
                    note="用法：/卡片风格 neon；改回每次随机：/卡片风格 随机",
                ),
                screenshots=shots(ctx),
            )
            return
        await _set_field(state, group_id, "card_style", chosen)
        await cards.send_card(
            command_ctx,
            cards.kv_card(
                title="卡片风格已更新",
                items=[("当前风格", "每次随机" if chosen == "random" else chosen), ("可选风格", style_list_text())],
            ),
            screenshots=shots(ctx),
        )

    names.append("卡片风格")

    @registrar.register(
        "config",
        description="查看或修改本群的推送设置（含开播/下播是否触发 AI 回复）",
        usage="[配置项] [值]",
        permission=PERM_SUB_ADMIN,
        params=(("配置项", "开播AI / 下播AI / 风格 / 开播推送默认 / 下播推送默认"), ("值", "开|关 或风格名")),
    )
    async def _config(command_ctx: Any) -> None:
        group_id = conv_group_id(command_ctx)
        if not group_id:
            await fail(command_ctx, ctx, "只能在群里使用", "这个命令需要在群聊里发送。")
            return
        config = state.config
        setting = await _setting_view(state, group_id)
        if setting is None:
            setting = await _ensure_setting(state, group_id, config)
        args = command_args(command_ctx)
        if not args:
            await cards.send_card(
                command_ctx,
                cards.message_card(title="本群推送设置", lines=config_lines(setting, config)),
                screenshots=shots(ctx),
            )
            return
        key = args[0].lower()
        value = args[1] if len(args) > 1 else None
        await _apply_config(ctx, state, command_ctx, group_id, key, value, config)

    names.append("config")
    return names


async def _apply_config(
    ctx: Any, state: Any, command_ctx: Any, group_id: int, key: str, value: str | None, config: Any
) -> None:
    """写入一项群配置并回一张卡片。"""
    from .commands import parse_switch

    switch = parse_switch(value)
    if key in {"开播ai", "liveai"}:
        if switch is None:
            await fail(command_ctx, ctx, "用法不对", "/config 开播AI 开|关")
            return
        await _set_field(state, group_id, "ai_reply_live", switch)
        await cards.send_card(
            command_ctx,
            cards.kv_card(title="已更新", items=[("开播后触发 AI 回复", "开" if switch else "关")]),
            screenshots=shots(ctx),
        )
        return
    if key in {"下播ai", "liveendai"}:
        if switch is None:
            await fail(command_ctx, ctx, "用法不对", "/config 下播AI 开|关")
            return
        await _set_field(state, group_id, "ai_reply_live_end", switch)
        await cards.send_card(
            command_ctx,
            cards.kv_card(title="已更新", items=[("下播后触发 AI 回复", "开" if switch else "关")]),
            screenshots=shots(ctx),
        )
        return
    if key in {"风格", "style", "卡片风格"}:
        chosen = match_style(value)
        if chosen is None:
            await fail(command_ctx, ctx, "用法不对", "/config 风格 " + style_list_text() + "|随机")
            return
        await _set_field(state, group_id, "card_style", chosen)
        await cards.send_card(
            command_ctx,
            cards.kv_card(title="已更新", items=[("卡片风格", "每次随机" if chosen == "random" else chosen)]),
            screenshots=shots(ctx),
        )
        return
    if key in {"开播推送默认", "defaultpushlive"}:
        if switch is None:
            await fail(command_ctx, ctx, "用法不对", "/config 开播推送默认 开|关")
            return
        await _set_field(state, group_id, "default_push_live", switch)
        await cards.send_card(
            command_ctx,
            cards.kv_card(title="已更新", items=[("新订阅默认开播推送", "开" if switch else "关")]),
            screenshots=shots(ctx),
        )
        return
    if key in {"下播推送默认", "defaultpushliveend"}:
        if switch is None:
            await fail(command_ctx, ctx, "用法不对", "/config 下播推送默认 开|关")
            return
        await _set_field(state, group_id, "default_push_live_end", switch)
        await cards.send_card(
            command_ctx,
            cards.kv_card(title="已更新", items=[("新订阅默认下播推送", "开" if switch else "关")]),
            screenshots=shots(ctx),
        )
        return
    await cards.send_card(
        command_ctx,
        cards.message_card(title="不认识的配置项：" + key, lines=config_lines(await _ensure_setting(state, group_id, config), config)),
        screenshots=shots(ctx),
    )

