"""NeoBot 流媒体解析插件：B 站直播间监听与开播/下播推送。

一期能力：
- 监听直播间（房间号 / 短号 / 链接 / UP 主空间链接），按群保存订阅；
- 轮询开播与下播，跳变时推送卡片，并可选触发一次 AI 回复；
- 开播状态总览图（头像 + 昵称，开播中的主播带粉色圆环）；
- 卡片多种风格，默认每次随机，可用命令固定。

部署侧不需要前端工具链：模板是纯 HTML/CSS，字体是随包分发的 woff2，
由宿主已有的 Chromium 截图端口出图。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from neobot_modloader import Plugin

from . import commands, db
from .assets import AssetCache
from .bilibili.client import BilibiliLiveClient, HttpxTransport
from .bilibili.errors import BilibiliAPIError, BilibiliTransportError
from .chat_guide import register_chat_guide
from .config import StreamConfig
from .logs import log_at
from .notify import Notifier
from .panel import register_surface
from .panel_guide import register_guide
from .poller import LivePoller
from .render import CardRenderer, resolve_style

PLUGIN_VERSION = "0.3.1"
PLUGIN_DESCRIPTION = "流媒体平台解析：B 站直播间监听、开播/下播推送与卡片渲染"

PLUGIN_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = PLUGIN_DIR / "templates"

#: 总览图并发拉头像的上限
AVATAR_CONCURRENCY = 6
#: 单个头像的取图预算：超时用占位头像，不能让总览图卡在一个慢 CDN 上
AVATAR_TIMEOUT = 5.0
#: 停止轮询时等待任务自然收尾的时间，超时就取消
STOP_TIMEOUT = 5.0


plugin = Plugin(
    "streaming_parser",
    version=PLUGIN_VERSION,
    description=PLUGIN_DESCRIPTION,
    author="SuperQuail",
    config=StreamConfig,
)

database = plugin.sqlite_database(
    db.DATABASE_NAME,
    filename=db.DATABASE_FILENAME,
    metadata=db.Base.metadata,
    migrations=db.MIGRATIONS,
)


class PluginState:
    """插件运行时状态：持有客户端 / 渲染器 / 轮询器等长生命周期对象。"""

    def __init__(self) -> None:
        self.database: Any = None
        self.client: BilibiliLiveClient | None = None
        self.assets: AssetCache | None = None
        self.renderer: CardRenderer | None = None
        self.notifier: Notifier | None = None
        self.poller: LivePoller | None = None
        self.config: StreamConfig | None = None
        self.ctx: Any = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    # ── 订阅查找 ─────────────────────────────────────────────────────────

    async def resolve_target(self, kind: str, value: int) -> dict[str, Any]:
        """把房间号/短号/UID 解析成真实房间号与主播信息。"""
        client = self._require_client()
        short_id = 0
        if kind == "room":
            init = await client.fetch_live_room_init(value)
            room_id = init.room_id
            uid = init.uid
            short_id = init.short_id
        else:
            status = await client.fetch_user_live_status(value)
            if not status.has_room:
                raise ValueError("这个 UP 主没有开通直播间")
            room_id = status.room_id
            uid = value
        name = ""
        avatar_url = ""
        if uid:
            try:
                card = await client.fetch_user_card(uid)
                name = card.name
                avatar_url = card.face
            except (BilibiliAPIError, BilibiliTransportError):
                pass
        return {
            "room_id": room_id,
            "uid": uid,
            "short_id": short_id,
            "name": name,
            "avatar_url": avatar_url,
        }

    async def find_subscription(self, group_id: int, kind: str, value: int) -> Any:
        """按用户输入找到订阅记录；先直接命中，再走一次解析。"""
        if kind == "room":
            async with self.database.session() as session:
                direct = db.sub_view(
                    await db.get_subscription(session, group_id, value)
                )
            if direct is not None:
                return direct
        try:
            resolved = await self.resolve_target(kind, value)
        except (BilibiliAPIError, BilibiliTransportError, ValueError):
            return None
        async with self.database.session() as session:
            return db.sub_view(
                await db.get_subscription(session, group_id, resolved["room_id"])
            )

    # ── 风格 ────────────────────────────────────────────────────────────

    async def style_name_for(self, group_id: int) -> str:
        config = self._require_config()
        async with self.database.session() as session:
            setting = db.setting_view(await db.get_group_setting(session, group_id))
        if setting is not None and setting.card_style:
            return setting.card_style
        return config.default_card_style

    async def style_for(self, group_id: int) -> str:
        return resolve_style(await self.style_name_for(group_id))

    # ── 总览图数据 ───────────────────────────────────────────────────────

    async def build_overview_hosts(
        self, rows: list[Any], states: dict[int, Any]
    ) -> list[dict[str, Any]]:
        """把订阅列表变成总览图需要的 {avatar_src, name, live}。"""
        assets = self._require_assets()
        semaphore = asyncio.Semaphore(AVATAR_CONCURRENCY)

        async def one(row: Any) -> dict[str, Any]:
            async with semaphore:
                avatar = ""
                if row.avatar_url:
                    try:
                        avatar = await asyncio.wait_for(
                            assets.fetch_data_uri(row.avatar_url),
                            timeout=AVATAR_TIMEOUT,
                        )
                    except (asyncio.TimeoutError, TimeoutError):
                        log_at(
                            getattr(self.ctx, "logger", None),
                            "debug",
                            f"拉取主播头像超时（{AVATAR_TIMEOUT:g}s），改用占位头像: {row.avatar_url}",
                        )
            state_row = states.get(row.room_id)
            live = state_row is not None and int(state_row.live_status) == 1
            return {
                "avatar_src": avatar,
                "name": row.name or ("房间 " + str(row.room_id)),
                "live": live,
            }

        return list(await asyncio.gather(*(one(row) for row in rows)))

    # ── 生命周期 ────────────────────────────────────────────────────────

    def _require_client(self) -> BilibiliLiveClient:
        if self.client is None:
            raise RuntimeError("插件尚未加载完成")
        return self.client

    def _require_assets(self) -> AssetCache:
        if self.assets is None:
            raise RuntimeError("插件尚未加载完成")
        return self.assets

    def _require_config(self) -> StreamConfig:
        if self.config is None:
            raise RuntimeError("插件尚未加载完成")
        return self.config

    def setup(self, ctx: Any, config: StreamConfig) -> None:
        """on_load 时装配所有运行时对象。"""
        self.ctx = ctx
        self.config = config
        self.database = database
        self.client = BilibiliLiveClient(
            HttpxTransport(),
            cookie=config.cookie,
            user_agent=config.user_agent or None,
            timeout=config.request_timeout,
        )
        self.assets = AssetCache(
            Path(ctx.data_dir) / "assets",
            timeout=max(10.0, config.request_timeout * 1.5),
            user_agent=config.user_agent or None,
            ttl_days=config.asset_cache_days,
            logger=ctx.logger,
        )
        self.renderer = CardRenderer(
            TEMPLATE_DIR,
            screenshots_provider=lambda: getattr(ctx, "screenshots", None),
            timeout=config.render_timeout,
            scale=config.render_scale,
        )
        self.notifier = Notifier(
            ctx=ctx,
            database=self.database,
            renderer=self.renderer,
            assets=self.assets,
            config=config,
            logger=ctx.logger,
        )
        self.poller = LivePoller(
            client=self.client,
            database=self.database,
            poll_interval=config.poll_interval_seconds,
            concurrency=config.poll_concurrency,
            logger=ctx.logger,
        )

    async def start_polling(self) -> None:
        if self.poller is None or self.notifier is None:
            return
        if self._task is not None and not self._task.done():
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(
            self.poller.run(self._stop, self.notifier.handle_transition),
            name="streaming_parser_poller",
        )

    async def stop_polling(self) -> None:
        """停轮询：先给任务自然收尾的机会，超时则取消并等它真正结束。

        这里必须等到任务结束才返回——modloader 紧接着会 close_databases()，
        任务还活着会让它在已关闭的引擎上继续读写（之前 cancel 后直接 return
        就是这个隐患）。
        """
        self._stop.set()
        task, self._task = self._task, None
        if task is None:
            return
        logger = getattr(self.ctx, "logger", None)
        try:
            # wait_for 超时会自己 cancel 并等任务完成，所以这里不用再 cancel 一次
            await asyncio.wait_for(task, timeout=STOP_TIMEOUT)
        except TimeoutError:
            log_at(logger, "warning", f"轮询任务未在 {STOP_TIMEOUT:g} 秒内退出，已取消")
        except asyncio.CancelledError:
            # 只吞「被取消的轮询任务」；外层自己被取消（关停/重载流程取消）必须继续抛，
            # 否则关停信号会被悄悄吃掉。
            current = asyncio.current_task()
            if current is None or current.cancelling():
                raise
        except Exception as exc:
            log_at(logger, "warning", f"轮询任务异常退出: {exc!r}")

    async def aclose(self) -> None:
        """关闭轮询用的 HTTP 连接（可重复调用）。

        数据库不在这里关：modloader 会在 on_stop 的关闭处理器之后统一
        close_databases()，这里再关一次会让热重载拿到已关闭的引擎。
        """
        logger = getattr(self.ctx, "logger", None)
        for holder in (self.client, self.assets):
            close = getattr(holder, "aclose", None)
            if not callable(close):
                continue
            try:
                await close()
            except Exception as exc:
                log_at(logger, "warning", f"关闭 HTTP 连接失败: {exc!r}")


state = PluginState()

register_surface(plugin, state)
register_guide(plugin)
register_chat_guide(plugin, state)

#: 命令在 on_load 里注册：宿主命令表（ctx.app_commands）要到那时才注入，
#:  注册进去的命令才会出现在 /help 列表与详情里。


@plugin.on_load
async def _on_load(ctx: Any) -> None:
    config = ctx.config
    if isinstance(config, BaseModel):
        config = StreamConfig(**config.model_dump())
    elif isinstance(config, dict):
        config = StreamConfig(**config)
    state.setup(ctx, config)
    expired = state.assets.purge_expired() if state.assets is not None else 0
    registered = commands.register_commands(ctx, state)
    ctx.logger.info(
        f"{ctx.plugin_name} 已加载：轮询间隔 {config.poll_interval_seconds}s，"
        f"清理过期图片缓存 {expired} 个，注册命令 {len(registered)} 条"
    )


@plugin.on_startup
async def _on_startup(ctx: Any) -> None:
    await state.start_polling()
    ctx.logger.info(f"{ctx.plugin_name} 已启动，开始监听直播间开播状态")


@plugin.on_shutdown
async def _on_shutdown(ctx: Any) -> None:
    # 顺序有讲究：先等轮询任务真正结束，再关它用到的 HTTP 连接；
    # 数据库由 modloader 在本处理器返回后统一关闭。
    await state.stop_polling()
    await state.aclose()
    ctx.logger.info(f"{ctx.plugin_name} 已停止")
