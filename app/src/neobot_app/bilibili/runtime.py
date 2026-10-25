"""B站运行时装配：服务、回复引擎、轮询器、日记与命令注册。

由 bootstrap 创建并随应用生命周期启动/停止；所有失败都降级为日志，不影响主进程。
"""
from __future__ import annotations

import asyncio
import contextlib
import inspect
import re
from datetime import datetime, timedelta
from typing import Any

from neobot_app.bilibili.channel import BilibiliCrossChatChannel
from neobot_app.bilibili.comment_monitor import BilibiliCommentMonitor
from neobot_app.core import DATA_DIR
from neobot_app.bilibili.diary import BilibiliDiaryService, BilibiliDiarySkill
from neobot_app.bilibili.live_interact import BilibiliLiveInteractor
from neobot_app.bilibili.video_frames import VideoFrameService
from neobot_app.bilibili.media import BilibiliVideoService
from neobot_app.bilibili.video_tasks import BilibiliVideoTaskManager
from neobot_app.bilibili.private_monitor import BilibiliPrivateMonitor
from neobot_app.bilibili.reply_engine import BilibiliReplyEngine
from neobot_app.bilibili.service import BilibiliService
from neobot_app.skills.bilibili_link import BilibiliLinkSkill
from neobot_app.skills.bilibili_live import BilibiliLiveSkill
from neobot_app.skills.bilibili_read import BilibiliReadSkill
from neobot_app.skills.bilibili_video_frames import BilibiliVideoFramesSkill
from neobot_app.skills.bilibili_memory import BilibiliMemorySkill
from neobot_app.skills.bilibili_tools import (
    BilibiliSearchSkill,
    BilibiliUserSkill,
    BilibiliVideoSkill,
)
from neobot_contracts.ports.logging import Logger, NullLogger


async def _maybe_await(value: Any) -> None:
    if inspect.isawaitable(value):
        await value


#: summary 完成后等待 30 分钟再生成日记；summary 未结束则 diary 一直等。
DIARY_SUMMARY_SETTLE_SECONDS = 1800.0


class BilibiliRuntime:
    """B站功能的一站式运行时。"""

    def __init__(
        self,
        *,
        config: Any,
        provider: Any,
        archive_service: Any,
        uow_factory: Any,
        command_service: Any,
        asr_service: Any = None,
        vision_provider: Any = None,
        on_live_event: Any = None,
        willing_service: Any = None,
        flow_registry: Any = None,
        archive_summary_service: Any = None,
        notification_hub: Any = None,
        logger: Logger | None = None,
        bot_name: str = "",
        bot_data: str = "",
        prompt_store: Any = None,
    ) -> None:
        self._config = config
        self._logger = logger or NullLogger()
        self._archive_summary_service = archive_summary_service
        self._archive_service = archive_service
        self._command_service = command_service
        self._started = False
        cfg = getattr(config, "bilibili", None)
        self.service = BilibiliService(cfg, logger=self._logger)
        self.video_service = BilibiliVideoService(
            self.service,
            asr_service=asr_service,
            archive_service=archive_service,
            logger=self._logger,
        )
        self.video_task_manager = BilibiliVideoTaskManager(
            video_service=self.video_service,
            notification_hub=notification_hub,
            logger=self._logger,
        )
        self.video_frames_service = VideoFrameService(
            self.service,
            vision_provider=vision_provider,
            logger=self._logger,
            data_dir=DATA_DIR,
        )
        self.engine = BilibiliReplyEngine(
            provider,
            archive_service=archive_service,
            uow_factory=uow_factory,
            video_service=self.video_service,
            bot_name=bot_name,
            bot_uid=0,
            bot_data=bot_data,
            flow_registry=flow_registry,
        )
        self.comment_monitor = BilibiliCommentMonitor.from_config(
            self.service, self.engine, cfg, data_dir=DATA_DIR
        )
        self.private_monitor = BilibiliPrivateMonitor.from_config(
            self.service, self.engine, cfg
        )
        self.diary = BilibiliDiaryService.from_config(
            provider,
            self.service,
            cfg,
            archive_service=archive_service,
            data_dir=DATA_DIR,
            bot_name=bot_name,
            bot_data=bot_data,
        )
        self.diary_skill = BilibiliDiarySkill(self.diary)
        live_bot_name = (
            str(getattr(cfg, "live_interaction_mention_names", None)[0]).strip()
            if getattr(cfg, "live_interaction_mention_names", None)
            else bot_name
        )
        self.live_interactor = BilibiliLiveInteractor(
            self.service,
            provider=provider,
            bot_name=live_bot_name,
            bot_data=bot_data,
            logger=self._logger,
            cooldown_seconds=float(
                getattr(cfg, "live_interaction_cooldown_seconds", 5.0) or 0.0
            ),
            max_reply_chars=int(
                getattr(cfg, "live_interaction_max_reply_chars", 40) or 40
            ),
            at_only=bool(getattr(cfg, "live_interaction_at_only", True)),
            asr_service=asr_service,
            vision_provider=vision_provider,
            on_event=on_live_event,
            willing_service=willing_service,
            flow_registry=flow_registry,
            mention_names=list(getattr(cfg, "live_interaction_mention_names", None) or []),
            reply_chance=float(getattr(cfg, "live_interaction_reply_chance", 0.15) or 0.15),
            asr_default_enabled=bool(getattr(cfg, "live_interaction_asr_enabled", False)),
            prompt_store=prompt_store,
            auto_look_enabled=bool(getattr(cfg, "live_interaction_auto_look_enabled", False)),
            auto_look_interval_minutes=int(getattr(cfg, "live_interaction_auto_look_interval_minutes", 30) or 30),
            screenshot_replies=bool(getattr(cfg, "live_interaction_screenshot_replies", False)),
            archive_service=archive_service,
            summary_every=int(getattr(cfg, "live_interaction_summary_every", 200) or 0),
        )
        self.channel = BilibiliCrossChatChannel(
            self.service, self.engine, live_interactor=self.live_interactor
        )
        self._diary_task: asyncio.Task[None] | None = None
        #: 当前扫码登录任务与代次：新 /login 取消旧任务，旧任务不再回复消息。
        self._login_task: asyncio.Task[None] | None = None
        self._login_attempt = 0

    def apply_config(self, config: Any) -> None:
        """热重载直播间与 B 站运行期配置；不重建连接。"""
        self._config = config
        cfg = getattr(config, "bilibili", None)
        if cfg is None:
            return
        live = self.live_interactor
        live._reply_chance = max(
            0.0,
            min(
                1.0,
                float(getattr(cfg, "live_interaction_reply_chance", 0.15) or 0.15),
            ),
        )
        live._cooldown = max(
            0.0,
            float(getattr(cfg, "live_interaction_cooldown_seconds", 5.0) or 0.0),
        )
        live._max_reply_chars = max(
            1,
            int(getattr(cfg, "live_interaction_max_reply_chars", 20) or 20),
        )
        live._asr_default_enabled = bool(
            getattr(cfg, "live_interaction_asr_enabled", False)
        )
        live._auto_look_interval_minutes = max(
            5,
            int(getattr(cfg, "live_interaction_auto_look_interval_minutes", 30) or 30),
        )
        was_auto_look = live._auto_look_enabled
        live._auto_look_enabled = bool(
            getattr(cfg, "live_interaction_auto_look_enabled", False)
        )
        live._screenshot_replies = bool(
            getattr(cfg, "live_interaction_screenshot_replies", False)
        )
        live._summary_every = max(
            0, int(getattr(cfg, "live_interaction_summary_every", 200) or 0)
        )
        # @ 识别名单是文档承诺热生效的「名单类运行时读取项」，与构造逻辑保持一致
        live._mention_names = tuple(
            str(name).strip()
            for name in (getattr(cfg, "live_interaction_mention_names", None) or ())
            if str(name).strip()
        )
        if was_auto_look != live._auto_look_enabled:
            task = getattr(live, "_auto_look_task", None)
            if task is not None and not task.done():
                task.cancel()
                live._auto_look_task = None
            if live._auto_look_enabled and getattr(live, "_running", False):
                import asyncio

                live._auto_look_task = asyncio.create_task(
                    live._auto_look_loop(), name="bilibili-live-auto-look"
                )
        self._logger.info("B站运行期配置已热更新")

    # ── 生命周期 ──

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        try:
            await self.service.start()
        except Exception:
            self._logger.exception("B站服务启动失败（已降级为休眠）")
        try:
            await self.comment_monitor.start()
            await self.private_monitor.start()
        except Exception:
            self._logger.exception("B站轮询器启动失败（已跳过）")
        try:
            await self.live_interactor.start()
        except Exception:
            self._logger.exception("B站直播交互器启动失败（已跳过）")

    async def stop(self) -> None:
        self._started = False
        login_task = self._login_task
        self._login_task = None
        if login_task is not None:
            login_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await login_task
        task = self._diary_task
        self._diary_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        try:
            await self.live_interactor.stop()
        except Exception:
            self._logger.exception("B站直播交互器停止失败")
        for monitor in (self.comment_monitor, self.private_monitor):
            try:
                await _maybe_await(monitor.stop())
            except Exception:
                self._logger.exception("B站轮询器停止失败")
        try:
            await self.service.stop()
        except Exception:
            self._logger.exception("B站服务停止失败")

    async def run(self) -> None:
        """后台常驻协程：随应用启动，被取消时停止全部子服务。"""
        await self.start()
        if getattr(getattr(self._config, "bilibili", None), "dynamic_diary_enabled", False):
            self._diary_task = asyncio.create_task(self._diary_loop())
        try:
            await asyncio.Event().wait()
        finally:
            await self.stop()

    # ── 每日动态日记 ──

    def set_archive_summary_service(self, service: Any) -> None:
        """日记前 5 分钟用它把群聊摘要刷新到最新。"""
        self._archive_summary_service = service

    def _seconds_until_diary(self, now: datetime | None = None) -> float | None:
        """距下一次 dynamic_diary_time（HH:MM）的秒数；未启用/配置非法返回 None。"""
        cfg = getattr(self._config, "bilibili", None)
        if not getattr(cfg, "dynamic_diary_enabled", False):
            return None
        raw = str(getattr(cfg, "dynamic_diary_time", "") or "").strip()
        try:
            hour_text, minute_text = raw.split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
        except (TypeError, ValueError):
            hour = minute = -1
        if not (0 <= hour < 24 and 0 <= minute < 60):
            self._logger.warning(f"B站动态日记时间配置非法: {raw!r}（应为 HH:MM）")
            return None
        current = now or datetime.now().astimezone()
        target = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= current:
            target += timedelta(days=1)  # 今天的时间点已过，排到明天
        return (target - current).total_seconds()

    async def _diary_loop(self) -> None:
        while True:
            delay = self._seconds_until_diary()
            if delay is None:
                return
            summary = self._archive_summary_service
            if summary is not None:
                # 原定时间前 5 分钟启动 summary；不设超时，结束后再等 30 分钟。
                await asyncio.sleep(max(0.0, delay - 300.0))
                try:
                    await summary.flush_all()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._logger.warning("B站日记前摘要刷新失败", error=str(exc))
                await asyncio.sleep(DIARY_SUMMARY_SETTLE_SECONDS)
            else:
                await asyncio.sleep(delay)
            try:
                result = await self.diary.run()
            except asyncio.CancelledError:
                raise
            except Exception:
                # 单次失败只记日志，主循环与后续调度继续。
                self._logger.exception("B站动态日记执行失败")
                continue
            if not result.get("ok"):
                self._logger.warning(
                    f"B站动态日记未发布: {result.get('error') or '未知原因'}"
                )

    # ── 对外门面 ──

    async def login_with_qr(self, *, on_qr: Any = None, on_status: Any = None) -> bool:
        ok = await self.service.login_with_qr(on_qr=on_qr, on_status=on_status)
        if ok and self._started:
            await self._ensure_live_listener()
        return ok

    async def _ensure_live_listener(self) -> None:
        """登录后把可能没在跑的直播监听器拉起来，避免"登录了但要重启才监听"。"""
        try:
            await self.live_interactor.ensure_started()
        except Exception:
            self._logger.exception("B站直播交互器自动启动失败")

    async def publish_dynamic(self, text: str, images: Any = None) -> int:
        return await self.service.publish_dynamic(text, images)

    # ── 命令注册 ──

    def register_commands(self, command_service: Any) -> None:
        from neobot_app.commands.model import PERM_EVERYONE, Command

        registry = command_service.registry
        self._register_login_command(registry, command_service)
        self._register_live_commands(registry, command_service)
        if not _has_command(registry, "bili"):
            registry.register(
                Command(
                    name="bili",
                    description="B站账号状态卡片/发动态（登录用 /login bilibili）",
                    usage="[status|dynamic <文本>]",
                    permission=PERM_EVERYONE,
                    handler=self._handle_bili,
                    params=(
                        ("status", "查看B站账号状态卡片"),
                        ("dynamic <文本>", "发布一条B站纯文本动态"),
                    ),
                )
            )

    def _register_live_commands(self, registry: Any, command_service: Any) -> None:
        """直播间交互命令；与 streaming_parser 监听插件完全独立。"""
        from neobot_app.commands.model import PERM_EVERYONE, PERM_SUB_ADMIN, Command

        async def _send_live_card(
            ctx: Any,
            *,
            title: str,
            rows: list[tuple[str, str]],
            fallback: str,
        ) -> Any:
            from neobot_app.commands.card import send_card

            return await send_card(
                ctx,
                title=title,
                blocks=[{"kind": "kv", "items": rows}],
                fallback_text=fallback,
                filename="bilibili-live-state.png",
            )

        async def _toggle(ctx: Any) -> str:
            args = [str(a).strip() for a in (ctx.args or [])]
            if len(args) < 2:
                return "用法：/直播互动 <房间号|直播间链接> 开|关"
            room_id = _digits(args[0])
            if room_id <= 0:
                return "没有从参数里找到直播间房间号"
            action = _switch(args[1])
            if action is None:
                return "第二个参数只能是 开 或 关"
            if action:
                await self.live_interactor.ensure_started()
                result = await self.live_interactor.enable(room_id, auto_reply=True)
                if not result.get("ok"):
                    return f"启用失败：{result.get('error') or '未知错误'}"
                return await _send_live_card(
                    ctx,
                    title="直播互动状态",
                    rows=[
                        ("房间", f"{result.get('name') or room_id}（{room_id}）"),
                        ("监听", "开"),
                        ("自动回复", "开"),
                    ],
                    fallback=f"直播间 {room_id} 监听开，自动回复开",
                )
            result = await self.live_interactor.disable(room_id)
            return await _send_live_card(
                ctx,
                title="直播互动状态",
                rows=[("房间", room_id), ("监听", "关")],
                fallback=f"直播间 {room_id} 监听关",
            )

        async def _toggle_ai(ctx: Any) -> str:
            args = [str(a).strip() for a in (ctx.args or [])]
            if len(args) < 2:
                return "用法：/直播互动AI <房间号> 开|关"
            room_id = _digits(args[0])
            action = _switch(args[1])
            if room_id <= 0 or action is None:
                return "房间号或开关参数无效"
            result = await self.live_interactor.set_auto_reply(room_id, action)
            if not result.get("ok"):
                return f"设置失败：{result.get('error') or '未知错误'}"
            return await _send_live_card(
                ctx,
                title="直播互动状态",
                rows=[("房间", room_id), ("自动回复", "开" if action else "关")],
                fallback=f"直播间 {room_id} 自动回复{'开' if action else '关'}",
            )

        async def _toggle_asr(ctx: Any) -> str:
            args = [str(a).strip() for a in (ctx.args or [])]
            if len(args) < 2:
                return "用法：/直播ASR <房间号> 开|关"
            room_id = _digits(args[0])
            action = _switch(args[1])
            if room_id <= 0 or action is None:
                return "房间号或开关参数无效"
            result = await self.live_interactor.set_asr(room_id, action)
            if not result.get("ok"):
                return f"设置失败：{result.get('error') or '未知错误'}"
            return await _send_live_card(
                ctx,
                title="直播互动状态",
                rows=[("房间", room_id), ("ASR", "开" if action else "关")],
                fallback=f"直播间 {room_id} ASR{'开' if action else '关'}",
            )

        async def _list(ctx: Any) -> str:
            rooms = self.live_interactor.list_rooms()
            if not rooms:
                return "还没有启用的直播间交互；用 /直播互动 <房间号> 开 启用。"
            lines = ["已启用的直播间交互："]
            for room in rooms:
                lines.append(
                    f"- {room.get('name') or '(未命名)'}（{room.get('room_id')}，"
                    f"真实房间 {room.get('real_room_id')}，"
                    f"自动回复{'开' if room.get('auto_reply') else '关'}，"
                    f"ASR{'开' if room.get('asr', True) else '关'}）"
                )
            return "\n".join(lines)

        async def _speak(ctx: Any) -> str:
            args = [str(a).strip() for a in (ctx.args or [])]
            if len(args) < 2:
                return "用法：/直播发言 <房间号|直播间链接> <文本>"
            room_id = _digits(args[0])
            text = " ".join(args[1:]).strip()
            if room_id <= 0 or not text:
                return "房间号或发言内容无效"
            result = await self.live_interactor.send_danmaku(room_id, text)
            if not result.get("ok"):
                return f"发送失败：{result.get('error') or '未知错误'}"
            return f"已发送直播间弹幕到 {room_id}"

        for name, description, usage, handler, permission in (
            (
                "直播互动",
                "启用/停用直播间弹幕交互（与开播监听插件无关）",
                "<房间号|链接> 开|关",
                _toggle,
                PERM_SUB_ADMIN,
            ),
            (
                "直播互动AI",
                "开关某个直播间的自动回复",
                "<房间号> 开|关",
                _toggle_ai,
                PERM_SUB_ADMIN,
            ),
            (
                "直播ASR",
                "开关某个直播间的 ASR 上下文（默认打开）",
                "<房间号> 开|关",
                _toggle_asr,
                PERM_SUB_ADMIN,
            ),
            (
                "直播互动列表",
                "查看已启用的直播间交互",
                "",
                _list,
                PERM_EVERYONE,
            ),
            (
                "直播发言",
                "用当前登录的B站账号手动发一条直播弹幕",
                "<房间号|链接> <文本>",
                _speak,
                PERM_SUB_ADMIN,
            ),
        ):
            if _has_command(registry, name):
                continue
            registry.register(
                Command(
                    name=name,
                    description=description,
                    usage=usage,
                    permission=permission,
                    handler=handler,
                )
            )

    def _register_login_command(self, registry: Any, command_service: Any) -> None:
        from neobot_app.commands.model import PERM_SUPER_ADMIN, Command

        async def _send(
            kind: str, conv_id: str, text: str, *, at_user_id: int | None = None
        ) -> None:
            try:
                await command_service.reply_to(
                    kind, conv_id, text, at_user_id=at_user_id
                )
            except Exception:
                self._logger.warning("B站登录结果消息发送失败")

        async def _handler(ctx: Any) -> None:
            args = [str(a).lower() for a in (ctx.args or [])]
            if args and args[0] not in ("bilibili", "b站", "bili"):
                await ctx.reply("用法：/login bilibili（扫码登录B站）")
                return
            if self.service.available:
                await ctx.reply("B站已登录。如需重新登录，请先在B站 App 退出登录后重试，或删除 cookies 文件。")
                return

            # 同一时间只保留一个登录流程：旧流程的二维码和结果都不再回给用户。
            old_task = self._login_task
            self._login_task = None
            if old_task is not None and not old_task.done():
                old_task.cancel()
            self._login_attempt += 1
            attempt = self._login_attempt

            async def _on_qr(login: Any) -> None:
                png = getattr(login, "png_bytes", None)
                if png:
                    # 发图超时多是带宽问题，图片基本都能送达；不在这里做失败兜底。
                    await command_service.send_image_bytes(
                        ctx.kind,
                        ctx.conv_id,
                        png,
                        at_user_id=ctx.user_id,
                        filename="bilibili-login.png",
                    )
                else:
                    await ctx.reply("请用B站App扫码登录：" + str(getattr(login, "url", "")))

            async def _run() -> None:
                ok = False
                try:
                    ok = await self.login_with_qr(on_qr=_on_qr)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self._logger.exception("B站扫码登录失败")
                if attempt != self._login_attempt:
                    return
                # 成功优先：B站侧已经登录时，不再把旧流程的失败报给用户。
                if not ok and self.service.available:
                    ok = True
                try:
                    reason = str(self.service.status().get("error") or "").strip()
                except Exception:
                    reason = ""
                if ok:
                    text = "B站登录成功。"
                    if reason:
                        text += f"\n注意：{reason}"
                    await _send(ctx.kind, ctx.conv_id, text)
                elif reason:
                    await _send(ctx.kind, ctx.conv_id, f"B站登录未完成：{reason}")
                else:
                    await _send(
                        ctx.kind,
                        ctx.conv_id,
                        "B站登录超时或未确认，请重新发送 /login bilibili。",
                    )

            task = asyncio.create_task(_run())
            self._login_task = task

            def _clear(done: asyncio.Task[None]) -> None:
                if self._login_task is done:
                    self._login_task = None

            task.add_done_callback(_clear)
            return None

        if not _has_command(registry, "login"):
            registry.register(
                Command(
                    name="login",
                    description="扫码登录外部平台（当前支持 bilibili）",
                    usage="bilibili",
                    permission=PERM_SUPER_ADMIN,
                    handler=_handler,
                    params=(("bilibili", "B站扫码登录"),),
                )
            )

    async def _handle_bili(self, ctx: Any) -> str | None:
        args = list(ctx.args or [])
        sub = str(args[0]).lower() if args else "status"
        if sub in ("status", "状态", ""):
            from neobot_app.bilibili.account_card import send_account_card

            await self.service.refresh()
            bilibili_cfg = getattr(self._config, "bilibili", None)
            return await send_account_card(
                ctx,
                self.service,
                extra_rows=[
                    (
                        "评论回复",
                        "开"
                        if getattr(bilibili_cfg, "comment_reply_enabled", False)
                        else "关",
                    ),
                    (
                        "私信回复",
                        "开"
                        if getattr(bilibili_cfg, "private_message_enabled", False)
                        else "关",
                    ),
                ],
            )
        if sub in ("dynamic", "动态"):
            # 状态卡片对所有人开放；发动态仍是写操作，保持次级管理员门槛。
            from neobot_app.commands.model import PERM_SUB_ADMIN

            permissions = getattr(getattr(ctx, "service", None), "permissions", None)
            allowed = (
                permissions is not None
                and permissions.can(ctx.user_id, PERM_SUB_ADMIN)
            )
            if not allowed:
                return "发B站动态需要次级管理员权限。"
            text = " ".join(str(a) for a in args[1:]).strip()
            if not text:
                return "用法：/bili dynamic <文本>"
            if not self.service.available:
                return "B站未登录，先发送 /login bilibili。"
            try:
                dyn_id = await self.publish_dynamic(text)
            except Exception as exc:
                self._logger.warning("B站动态发布失败", error=str(exc))
                return "发布B站动态失败，请稍后重试"
            return f"已发布B站动态，dynamic_id={dyn_id}"
        return "用法：/bili [status|dynamic <文本>]"



def _digits(value: Any) -> int:
    match = re.search(r"\d+", str(value or ""))
    if match is None:
        return 0
    try:
        return int(match.group(0))
    except ValueError:
        return 0


def _switch(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if text in {"开", "开启", "on", "1", "true", "yes"}:
        return True
    if text in {"关", "关闭", "off", "0", "false", "no"}:
        return False
    return None

def _has_command(registry: Any, name: str) -> bool:
    try:
        return registry.get(name) is not None
    except Exception:
        return False


def build_bilibili_skills(
    *,
    archive_service: Any,
    uow_factory: Any,
    runtime: BilibiliRuntime | None,
) -> list[Any]:
    """构造需要注册进 SkillManager 的B站技能（runtime 为空时仍注册账号/记忆技能）。"""
    skills: list[Any] = []
    try:
        skills.append(BilibiliLinkSkill(uow_factory=uow_factory, archive_service=archive_service))
        skills.append(BilibiliMemorySkill(archive_service=archive_service))
    except Exception:
        pass
    if runtime is not None:
        skills.append(runtime.diary_skill)
        for factory in (
            lambda: BilibiliSearchSkill(
                service=runtime.service, video_service=runtime.video_service
            ),
            lambda: BilibiliVideoSkill(
                service=runtime.service,
                video_service=runtime.video_service,
                archive_service=archive_service,
                task_manager=runtime.video_task_manager,
            ),
            lambda: BilibiliUserSkill(
                service=runtime.service,
                archive_service=archive_service,
                uow_factory=uow_factory,
            ),
            lambda: BilibiliLiveSkill(
                live_interactor=runtime.live_interactor,
                service=runtime.service,
            ),
            lambda: BilibiliVideoFramesSkill(
                video_frames_service=runtime.video_frames_service,
            ),
            lambda: BilibiliReadSkill(service=runtime.service),
        ):
            try:
                skills.append(factory())
            except Exception:
                pass
    return skills

class BilibiliRuntimeConfigConsumer:
    """将 [bilibili] 段的热重载转给运行时。"""

    name = "bilibili"

    def __init__(self, runtime: BilibiliRuntime) -> None:
        self._runtime = runtime

    @property
    def config_paths(self) -> tuple[str, ...]:
        return ("bilibili",)

    @property
    def hot_reload_policies(self) -> tuple[Any, ...]:
        from neobot_app.config.hot_reload import HotReloadRule

        return (
            HotReloadRule(
                "bilibili",
                True,
                "B站/直播间运行期配置现取现用；连接与登录态不重建",
            ),
        )

    async def apply_config(self, config: Any) -> None:
        self._runtime.apply_config(config)
