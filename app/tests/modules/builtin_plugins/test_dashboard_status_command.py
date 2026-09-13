"""spec(4) Part D：/status 命令、四块白名单与降级（R23-R25、R28 / A55-A62、A70-A71）。"""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from neobot_app.builtin_plugins.dashboard import DashboardPlugin
from neobot_app.builtin_plugins.dashboard import status_card
from neobot_app.commands.model import PERM_SUB_ADMIN
from neobot_app.commands.registry import CommandRegistry
from neobot_app.commands.service import CommandService
from neobot_app.screenshot import (
    RenderOptions,
    ScreenshotOptions,
    ScreenshotResult,
    ScreenshotService,
    ScreenshotUnavailable,
    UnavailableScreenshots,
)
from neobot_contracts.models import ConversationRef
from neobot_modloader.context import PluginCommandRegistrar

BOT = 88888
SUPER = 10000
SUB = 30000
STRANGER = 40000
PNG = b"\x89PNG\r\n\x1a\n" + b"status-image"


# ---------------------------------------------------------------------------
# 替身
# ---------------------------------------------------------------------------


class FakeServices:
    def __init__(self, mapping: dict[str, Any] | None = None) -> None:
        self._mapping = dict(mapping or {})

    def get(self, name: str, default: Any = None) -> Any:
        return self._mapping.get(name, default)


class FakeHost:
    def __init__(self, services: FakeServices) -> None:
        self.services = services


class FakeScreenshots:
    def __init__(self, *, data: bytes | None = PNG, error: Exception | None = None) -> None:
        self.data = data
        self.error = error
        self.calls: list[str] = []

    async def render(self, *, html: str, options: RenderOptions, base_url: str | None = None):
        self.calls.append(html)
        if self.error is not None:
            raise self.error
        return ScreenshotResult(self.data or b"", "png", 720, 120, 720.0, 120.0, 1.0)


class FakePluginCtx:
    """面板插件上下文替身：注册桥 + 宿主服务 + 发图能力。"""

    def __init__(
        self,
        *,
        registrar: PluginCommandRegistrar,
        services: FakeServices,
        control: Any = None,
        screenshots: Any = None,
        logger: Any = None,
    ) -> None:
        self.app_commands = registrar
        self.plugin_host = FakeHost(services)
        self.plugin_control = control
        self.screenshots = screenshots
        self.logger = logger
        self.sent_images: list[tuple[Any, bytes | None, str | None]] = []

    def conversation_from_event(self, event: dict[str, Any]) -> ConversationRef:
        if event.get("group_id") is not None:
            return ConversationRef(kind="group", id=str(event["group_id"]))
        return ConversationRef(kind="private", id=str(event["user_id"]))

    async def send_image(
        self,
        conversation: ConversationRef,
        *,
        path: Any = None,
        data: bytes | None = None,
        filename: str | None = None,
    ) -> Any:
        self.sent_images.append((conversation, data, filename))
        return SimpleNamespace(status="ok")


class FakeMetrics:
    def __init__(
        self,
        *,
        logs: list[dict[str, Any]] | None = None,
        today: int = 12,
        total: int = 345,
        latency: float | None = 42.5,
    ) -> None:
        self._logs = logs or []
        self._today = today
        self._total = total
        self._latency = latency

    def latency_series(self) -> dict[str, Any]:
        return {"current_ms": self._latency}

    def message_stats(self) -> dict[str, Any]:
        return {"today": self._today, "total": self._total, "started_at": 0.0}

    def logs(self, *, since: int = 0, limit: int = 200) -> dict[str, Any]:
        return {"items": list(self._logs), "last_id": len(self._logs), "total": len(self._logs)}


class FakeServer:
    version = "1.0.0"

    def __init__(self, metrics: FakeMetrics | None = None, bot: dict[str, Any] | None = None) -> None:
        self.metrics = metrics or FakeMetrics()
        self._bot = bot or {
            "online": True,
            "app_name": "OneBot",
            "app_version": "11.0",
            "nickname": "小助手",
            "user_id": 123456789,
        }
        self.uptime_seconds = 3 * 86400 + 4 * 3600 + 5 * 60

    async def bot_info(self) -> dict[str, Any]:
        return dict(self._bot)


class FakeSnapshot:
    def __init__(self, name: str, version: str, state: str, *, enabled: bool = True) -> None:
        self.name = name
        self.version = version
        self.state = state
        self.enabled = enabled


class FakeControl:
    def __init__(self, snapshots: list[FakeSnapshot] | None = None) -> None:
        self._snapshots = snapshots if snapshots is not None else [
            FakeSnapshot("dashboard", "1.0.0", "running"),
            FakeSnapshot("starship", "0.2.0", "error"),
            FakeSnapshot("off_plugin", "0.1.0", "stopped", enabled=False),
        ]

    def snapshot(self) -> list[FakeSnapshot]:
        return list(self._snapshots)


def make_config(*, sub_admins: list[int] | None = None) -> Any:
    chat = SimpleNamespace(admin_accounts=[SUPER], sub_admin_accounts=list(sub_admins or []))
    return SimpleNamespace(chat=chat, bot=SimpleNamespace(account=BOT))


def text_message(text: str, *, user_id: int, at_qqs: list[int] | None = None) -> Any:
    segments = [{"type": "text", "data": {"text": text}}]
    for qq in at_qqs or []:
        segments.append({"type": "at", "data": {"qq": str(qq)}})
    return SimpleNamespace(user_id=user_id, message=segments)


def build_harness(
    *,
    screenshots: Any = None,
    metrics: FakeMetrics | None = None,
    control: Any = None,
    services: dict[str, Any] | None = None,
    sub_admins: list[int] | None = None,
    config: Any = None,
) -> tuple[DashboardPlugin, FakePluginCtx, CommandService, list[str]]:
    plugin = DashboardPlugin()
    plugin.server = FakeServer(metrics)
    registry = CommandRegistry()
    logger_messages: list[str] = []
    registrar = PluginCommandRegistrar(
        plugin_name="dashboard",
        registry=registry,
        record_cleanup=None,
        logger=SimpleNamespace(warning=lambda message: logger_messages.append(str(message))),
    )
    ctx = FakePluginCtx(
        registrar=registrar,
        services=FakeServices(services),
        control=control if control is not None else FakeControl(),
        screenshots=screenshots,
    )
    plugin._register_status_command(ctx)
    replies: list[str] = []

    async def send_callback(kind: str, conv_id: str, text: str, at: int | None) -> None:
        replies.append(text)

    service = CommandService(
        config=config if config is not None else make_config(sub_admins=sub_admins or [SUB]),
        registry=registry,
        register_builtins=False,
        send_callback=send_callback,
    )
    return plugin, ctx, service, replies


# ---------------------------------------------------------------------------
# A55-A58：权限三档与生命周期
# ---------------------------------------------------------------------------


async def test_sub_admin_gets_image() -> None:
    """A55：次级管理员发 /status -> 正常回图。"""
    screenshots = FakeScreenshots()
    _plugin, ctx, service, replies = build_harness(screenshots=screenshots)

    result = await service.handle_message(
        text_message("/status", user_id=SUB, at_qqs=[BOT]), kind="group", queue_key="42"
    )

    assert result.consumed is True
    assert len(ctx.sent_images) == 1
    conversation, data, filename = ctx.sent_images[0]
    assert conversation == ConversationRef(kind="group", id="42")
    assert data == PNG
    assert filename == "status.png"
    assert replies == []  # 图片已自行发送，命令服务不再回文本
    assert len(screenshots.calls) == 1


async def test_super_admin_can_use_status() -> None:
    """A56：超级管理员同样可用（is_sub_admin 含超管）。"""
    _plugin, ctx, service, _replies = build_harness(screenshots=FakeScreenshots())

    result = await service.handle_message(
        text_message("/status", user_id=SUPER, at_qqs=[BOT]), kind="group", queue_key="42"
    )

    assert result.consumed is True
    assert len(ctx.sent_images) == 1


async def test_stranger_is_denied_and_handler_not_executed() -> None:
    """A57：普通成员 -> 需要权限:次级管理员，且 handler 未执行（无截图、无副作用）。"""
    screenshots = FakeScreenshots()
    _plugin, ctx, service, replies = build_harness(screenshots=screenshots)

    result = await service.handle_message(
        text_message("/status", user_id=STRANGER, at_qqs=[BOT]), kind="group", queue_key="42"
    )

    assert result.consumed is True
    assert replies and "需要权限:次级管理员" in replies[0]
    assert ctx.sent_images == []
    assert screenshots.calls == []


async def test_registered_permission_is_sub_admin() -> None:
    """A55：命令权限等级必须是次级管理员（D20）。"""
    _plugin, _ctx, service, _replies = build_harness(screenshots=FakeScreenshots())
    command = service.registry.get("status")
    assert command is not None
    assert command.permission == PERM_SUB_ADMIN
    assert command.source == "dashboard"


async def test_status_command_disappears_after_unregister_all() -> None:
    """A58：插件停用 / 卸载时随 unregister_all() 摘除命令。"""
    _plugin, ctx, service, _replies = build_harness(screenshots=FakeScreenshots())
    assert service.registry.get("status") is not None

    ctx.app_commands.unregister_all()

    assert service.registry.get("status") is None
    result = await service.handle_message(
        text_message("/status", user_id=SUB, at_qqs=[BOT]), kind="group", queue_key="42"
    )
    assert result.consumed is False


# ---------------------------------------------------------------------------
# A59-A61：HTML 自包含 + 四块白名单 + 敏感串
# ---------------------------------------------------------------------------


def install_fake_usage(monkeypatch: pytest.MonkeyPatch, services: dict[str, Any]) -> None:
    """把用量仓储换成替身，让「用量」块有真实字段可断言（无需真库）。"""
    import neobot_storage.repositories.usage as usage_repo

    class FakeRepo:
        def __init__(self, session: Any) -> None:
            self._session = session

        async def series_since(self, since: Any, *, bucket: str = "hour") -> list[dict[str, Any]]:
            return [
                {
                    "at": "2026-09-13T10:00:00",
                    "calls": 3,
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "cache_hit_tokens": 20,
                    "cost_cny": 1.5,
                }
            ]

    class FakeSession:
        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *exc: Any) -> bool:
            return False

    monkeypatch.setattr(usage_repo, "SqlAlchemyUsageRepository", FakeRepo)
    services["usage_session_factory"] = lambda: FakeSession()


async def test_image_html_contains_four_blocks_and_is_self_contained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A60 / A59：图片版必含四块；HTML 自包含。"""
    screenshots = FakeScreenshots()
    services: dict[str, Any] = {}
    install_fake_usage(monkeypatch, services)
    _plugin, _ctx, service, _replies = build_harness(screenshots=screenshots, services=services)

    await service.handle_message(
        text_message("/status", user_id=SUB, at_qqs=[BOT]), kind="group", queue_key="42"
    )

    html = screenshots.calls[0]
    for name in status_card.BLOCK_NAMES:
        assert f">{name}<" in html
    assert "<script" not in html.lower()
    assert "https://" not in html
    assert "http://" not in html
    assert "<link" not in html.lower()
    # 关键字段（A60）
    for field in ("在线状态", "延迟", "运行时长", "今日消息", "累计消息", "协议端", "金额", "缓存命中 Token"):
        assert field in html


async def test_image_never_contains_sensitive_values() -> None:
    """A61：QQ 号 / 昵称 / API Key / 提示词 / 日志正文 / 安装路径一律不出现。"""
    metrics = FakeMetrics(
        logs=[
            {
                "id": 1,
                "time": "10:00:00",
                "datetime": "2026-09-13 10:00:00",
                "ts": time.time(),
                "level": "error",
                "module": "app.reply",
                "message": "sk-secret-key 你是一个乐于助人的助手",
            }
        ]
    )
    screenshots = FakeScreenshots()
    _plugin, _ctx, service, _replies = build_harness(
        screenshots=screenshots, metrics=metrics, services={}
    )

    await service.handle_message(
        text_message("/status", user_id=SUB, at_qqs=[BOT]), kind="group", queue_key="42"
    )
    html = screenshots.calls[0]

    for secret in (
        "sk-secret-key",
        "你是一个乐于助人的助手",
        "小助手",  # 昵称
        "123456789",  # QQ 号
        "/remote/path",  # 安装路径
        "owner/repo",  # repo 地址
        "password",
        "api_key",
    ):
        assert secret not in html, f"HTML 不应包含敏感串: {secret}"
    # 允许出现的是「时间 + 模块名」
    assert "app.reply" in html
    assert "2026-09-13 10:00:00" in html


async def test_plugin_block_only_exposes_name_version_state() -> None:
    """A60 / A61：插件块只有名称 / 版本 / 状态，不含路径与配置值。"""
    control = FakeControl(
        [
            FakeSnapshot("dashboard", "1.0.0", "running"),
            FakeSnapshot("off", "0.3.0", "stopped", enabled=False),
        ]
    )
    screenshots = FakeScreenshots()
    _plugin, _ctx, service, _replies = build_harness(screenshots=screenshots, control=control)

    await service.handle_message(
        text_message("/status", user_id=SUB, at_qqs=[BOT]), kind="group", queue_key="42"
    )
    html = screenshots.calls[0]

    assert "dashboard" in html and "1.0.0" in html and "运行中" in html
    assert "已停用" in html
    assert "/remote/path" not in html


# ---------------------------------------------------------------------------
# A62：块名参数
# ---------------------------------------------------------------------------


async def test_selected_blocks_only_render_those_two() -> None:
    """A62：/status 用量 插件 只渲染选中的两块。"""
    screenshots = FakeScreenshots()
    _plugin, _ctx, service, _replies = build_harness(screenshots=screenshots)

    await service.handle_message(
        text_message("/status 用量 插件", user_id=SUB, at_qqs=[BOT]), kind="group", queue_key="42"
    )

    html = screenshots.calls[0]
    assert ">用量<" in html
    assert ">插件<" in html
    assert ">概况<" not in html
    assert ">错误<" not in html


async def test_unknown_block_returns_error_without_screenshot() -> None:
    """A62：未知块名 -> 明确错误且不截图。"""
    screenshots = FakeScreenshots()
    _plugin, _ctx, service, replies = build_harness(screenshots=screenshots)

    await service.handle_message(
        text_message("/status 报表", user_id=SUB, at_qqs=[BOT]), kind="group", queue_key="42"
    )

    assert screenshots.calls == []
    assert replies and "未知的块名" in replies[0] and "报表" in replies[0]
    assert "概况" in replies[0]  # 提示可用块名


# ---------------------------------------------------------------------------
# A70：降级
# ---------------------------------------------------------------------------


async def test_unavailable_screenshots_degrade_to_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A70：UnavailableScreenshots -> 等价纯文本 + 启用提示，不报错，总耗时 <= 25s。"""
    services: dict[str, Any] = {}
    install_fake_usage(monkeypatch, services)
    _plugin, ctx, service, replies = build_harness(
        screenshots=UnavailableScreenshots(), services=services
    )

    started = time.monotonic()
    result = await service.handle_message(
        text_message("/status", user_id=SUB, at_qqs=[BOT]), kind="group", queue_key="42"
    )
    elapsed = time.monotonic() - started

    assert result.consumed is True
    assert ctx.sent_images == []
    assert replies, "降级时必须回文本"
    text = replies[0]
    for name in status_card.BLOCK_NAMES:
        assert f"【{name}】" in text
    for field in ("在线状态", "延迟", "运行时长", "今日消息", "累计消息", "协议端", "缓存命中 Token"):
        assert field in text
    assert status_card.FALLBACK_HINT in text
    assert elapsed <= 25.0


async def test_screenshot_failure_degrades_to_text() -> None:
    """A70：渲染抛错同样降级（不抛异常）。"""
    _plugin, ctx, service, replies = build_harness(
        screenshots=FakeScreenshots(error=ScreenshotUnavailable("no chromium"))
    )

    result = await service.handle_message(
        text_message("/status", user_id=SUB, at_qqs=[BOT]), kind="group", queue_key="42"
    )

    assert result.consumed is True
    assert ctx.sent_images == []
    assert replies and status_card.FALLBACK_HINT in replies[0]


async def test_render_timeout_degrades_to_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """A70：渲染挂起 -> 命令内兜底超时降级（预算压到 0.05s 以免真等 25s）。"""
    _plugin, ctx, service, replies = build_harness(screenshots=FakeScreenshots())

    async def hang(*args: Any, **kwargs: Any) -> bytes | None:
        await asyncio.sleep(30)
        return None

    monkeypatch.setattr(status_card, "render_status_png", hang)
    monkeypatch.setattr(status_card, "COMMAND_TIMEOUT_SECONDS", 0.05)
    started = time.monotonic()
    result = await service.handle_message(
        text_message("/status", user_id=SUB, at_qqs=[BOT]), kind="group", queue_key="42"
    )
    elapsed = time.monotonic() - started

    assert result.consumed is True
    assert ctx.sent_images == []
    assert replies and status_card.FALLBACK_HINT in replies[0]
    assert elapsed < 25.0


# ---------------------------------------------------------------------------
# A71：共享 operation_lock（用真实 ScreenshotService + 假后端）
# ---------------------------------------------------------------------------


class _TemporaryPage:
    def run_cdp(self, method: str, **kwargs: Any) -> Any:
        if method == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "frame-1"}}}
        return None

    def run_js(self, script: str, *args: Any) -> bool:
        return True


class _FakeBackend:
    def __init__(self, manager: Any) -> None:
        self.manager = manager
        self.lock = asyncio.Lock()

    @property
    def operation_lock(self) -> asyncio.Lock:
        return self.lock

    async def get_manager(self) -> Any:
        return self.manager


async def test_concurrent_status_calls_share_operation_lock() -> None:
    """A71：并发两次 /status 不产生 Chromium 并发（第二次排队完成）。"""
    active = 0
    max_active = 0

    async def capture(options: ScreenshotOptions) -> ScreenshotResult:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        return ScreenshotResult(PNG, "png", 720, 120, 720.0, 120.0, 1.0)

    manager = MagicMock()
    manager._open_temporary_page = AsyncMock(return_value=(object(), _TemporaryPage()))
    manager._apply_temporary_capture_metrics = AsyncMock(return_value=(_TemporaryPage(), False, None))
    manager._restore_temporary_capture_metrics = AsyncMock()
    manager._close_temporary_page = AsyncMock()
    manager.capture = capture
    service_port = ScreenshotService(_FakeBackend(manager))

    plugin, ctx, service, _replies = build_harness(screenshots=service_port)

    async def run_once() -> Any:
        return await service.handle_message(
            text_message("/status", user_id=SUB, at_qqs=[BOT]), kind="group", queue_key="42"
        )

    results = await asyncio.gather(run_once(), run_once())

    assert [item.consumed for item in results] == [True, True]
    assert len(ctx.sent_images) == 2
    assert max_active == 1, "截图必须串行（共享 operation_lock）"


# ---------------------------------------------------------------------------
# 白名单与渲染器接线
# ---------------------------------------------------------------------------


def test_block_whitelist_is_hardcoded() -> None:
    """4.9：白名单硬编码、不可配置。"""
    assert status_card.BLOCK_NAMES == ("概况", "用量", "插件", "错误")
    assert status_card.normalize_blocks(None) == status_card.BLOCK_NAMES
    assert status_card.normalize_blocks(["用量"]) == ("用量",)
    assert status_card.normalize_blocks(["插件", "用量"]) == ("用量", "插件")
    assert status_card.unknown_blocks(["用量", "报表"]) == ["报表"]


def test_format_duration() -> None:
    assert status_card.format_duration(3 * 86400 + 4 * 3600 + 5 * 60) == "3 天 4 小时 5 分"
    assert status_card.format_duration(3600) == "1 小时 0 分"
    assert status_card.format_duration(None) == "未知"


async def test_collect_status_blocks_uses_in_process_services() -> None:
    """A59：不需要面板登录 / 面板 HTTP —— 直接从进程内服务取数。"""
    metrics = FakeMetrics()
    plugin = DashboardPlugin()
    plugin.server = FakeServer(metrics)
    ctx = FakePluginCtx(
        registrar=PluginCommandRegistrar(
            plugin_name="dashboard", registry=CommandRegistry(), record_cleanup=None
        ),
        services=FakeServices({"usage_session_factory": None}),
        control=FakeControl(),
    )

    blocks = await status_card.collect_status_blocks(ctx, None, console=plugin.server)

    assert set(blocks) == set(status_card.BLOCK_NAMES)
    text = status_card.build_status_text(status_card.build_status_payload(blocks))
    assert "在线" in text
    assert "不可用" in text  # usage_session_factory 缺失时如实标注


# ---------------------------------------------------------------------------
# 卡片美化：分块卡片化 / 状态色 / 表格条带（本轮新增）
# ---------------------------------------------------------------------------


def _styled_payload(*, errors: int = 2) -> dict[str, Any]:
    blocks = {
        "概况": [
            status_card._kv(
                "",
                [
                    ("在线状态", "在线"),
                    ("延迟", "38 ms"),
                    ("运行时长", "3 天 4 小时 5 分"),
                    ("今日消息", "412"),
                    ("累计消息", "18,904"),
                    ("协议端", "NapCat 4.8.2"),
                ],
            )
        ],
        "用量": [
            status_card._kv("近 24 小时", [("金额", "¥1.2840"), ("调用次数", "137")]),
            status_card._kv("近 7 天", [("金额", "¥12.9050"), ("调用次数", "1,284")]),
        ],
        "插件": [
            status_card._table(
                "",
                ("名称", "版本", "状态"),
                [("dashboard", "0.1.0", "运行中"), ("legacy", "0.0.9", "已停用")],
            )
        ],
        "错误": [status_card._kv("", [("近 24 小时 ERROR", str(errors)), ("最近一次异常", "无")])],
    }
    return status_card.build_status_payload(blocks, subtitle="QQ · 次级管理员", footer="页脚")


def test_overview_is_rendered_as_metric_tiles() -> None:
    """概况块用指标卡片墙（值带状态色），不再是六行键值表。"""
    html = status_card.build_status_html(_styled_payload())

    assert 'class="stat-label">在线状态<' in html
    assert 'class="stat-label">协议端<' in html
    assert "stat--ok" in html  # 在线 -> 绿
    assert "--stat-cols: 3" in html
    assert "在线状态" in html and "NapCat 4.8.2" in html


def test_usage_windows_are_laid_out_side_by_side() -> None:
    """用量两个窗口（近 24 小时 / 近 7 天）并排成两栏，省一半高度。"""
    html = status_card.build_status_html(_styled_payload())

    assert 'class="grid"' in html
    assert "--grid-cols: 2" in html
    assert html.count('class="grid-cell"') == 2
    assert "近 24 小时" in html and "近 7 天" in html


def test_error_block_uses_danger_tone_only_when_errors_exist() -> None:
    """错误块有条目时整块转告警配色（headings + 面板 + 左侧色条）。"""
    with_errors = status_card.build_status_html(_styled_payload(errors=2))
    without = status_card.build_status_html(_styled_payload(errors=0))

    assert 'class="block block--heading tone-danger"' in with_errors
    assert 'class="block block--kv tone-danger"' in with_errors
    assert 'class="block block--heading tone-danger"' not in without
    assert "近 24 小时 ERROR" in with_errors


def test_plugin_state_and_overview_values_are_toned() -> None:
    """插件状态与概况取值按语义着色（运行中绿 / 已停用灰）。"""
    html = status_card.build_status_html(_styled_payload())

    assert "cell--ok" in html and "运行中" in html
    assert "cell--muted" in html and "已停用" in html
    assert status_card.value_tone("在线") == "ok"
    assert status_card.value_tone("离线") == "danger"
    assert status_card.value_tone("未知") == "muted"
    assert status_card.value_tone("38 ms") == ""


def test_status_card_blocks_keep_self_contained_theme_art() -> None:
    """美化后仍是自包含卡片（无外链 / 脚本），且四块标题仍在。"""
    html = status_card.build_status_html(_styled_payload())

    for name in status_card.BLOCK_NAMES:
        assert f">{name}<" in html
    assert "http://" not in html and "https://" not in html
    assert "<script" not in html.lower() and "<link" not in html.lower()
    assert "@import" not in html
    assert 'class="card-emblem"' in html  # 主题徽章（内联 SVG）


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(pytest.main([__file__]))
