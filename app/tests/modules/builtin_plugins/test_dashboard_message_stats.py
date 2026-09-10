"""官方 dashboard 插件：消息统计处理器回归测试。

部署现场曾报错 Cannot resolve parameter 'event' for handler _dashboard_count_message，
导致面板的今日/累计消息数永远为 0。这里直接加载真实插件包并派发一条消息事件，
验证处理器被调用且统计生效。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.loader import FilesystemPluginLoader

from neobot_app.builtin_plugins.dashboard.metrics import Metrics


class _NullLogger:
    def debug(self, *args: Any, **kwargs: Any) -> None: ...
    def info(self, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, *args: Any, **kwargs: Any) -> None: ...
    def error(self, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, *args: Any, **kwargs: Any) -> None: ...


class _DispatchCtx:
    def __init__(self, raw_event: dict) -> None:
        self.raw_event = raw_event
        self.consumed = False
        self.skip_ai_reply = False

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True


class _StubServer:
    def __init__(self, metrics: Metrics) -> None:
        self.metrics = metrics
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True

    async def probe_latency(self) -> None:
        return None


def _dashboard_dir() -> Path:
    from neobot_app.builtin_plugins import dashboard as dashboard_module

    return Path(dashboard_module.__file__).resolve().parent


def _plugin_module(plugin: Any) -> Any:
    """加载器给插件分配的是合成模块名，用处理器函数反查真实模块。"""
    handler = plugin._registrations[0].handler
    return sys.modules[handler.__module__]


async def test_dashboard_counts_messages_with_annotated_event(tmp_path: Path) -> None:
    loaded = FilesystemPluginLoader(
        source="official", namespace="neobot_builtin_plugins"
    ).load_one(_dashboard_dir())
    assert loaded is not None and hasattr(loaded, "plugin")
    plugin = loaded.plugin
    instance = _plugin_module(plugin)._instance

    metrics = Metrics(data_dir=tmp_path, logger=_NullLogger())
    stub = _StubServer(metrics)
    instance.server = stub

    async def _skip_start(_ctx: Any) -> None:
        """跳过真实 HTTP 服务启动，只验证消息处理器绑定与分发。"""

    instance.load = _skip_start  # type: ignore[method-assign]

    hook_bus = PluginHookBus()
    context = RuntimePluginContext(
        plugin_name=plugin.name,
        plugin_dir=_dashboard_dir(),
        data_dir=tmp_path / "data",
        config={},
        logger=_NullLogger(),
        adapter=object(),
        hook_bus=hook_bus,
        record_subscription=lambda _subscription: None,
        agent_registry=None,
        plugin_registry=None,
        host=None,
        plugin_control=None,
        markdown_skill_registry=None,
        record_skill_cleanup=None,
    )
    await plugin.on_load(context)
    try:
        await hook_bus.dispatch(
            _DispatchCtx(
                {
                    "post_type": "message",
                    "message_type": "private",
                    "user_id": 12345,
                    "sender": {"nickname": "测试"},
                }
            )
        )
    finally:
        await plugin.on_stop()

    stats = metrics.message_stats()
    assert stats["total"] == 1
    assert stats["today"] == 1
    assert metrics.active_users(5)["items"][0]["user_id"] == 12345
    assert stub.stopped is True


async def test_dashboard_ignores_non_message_events(tmp_path: Path) -> None:
    loaded = FilesystemPluginLoader(
        source="official", namespace="neobot_builtin_plugins"
    ).load_one(_dashboard_dir())
    assert loaded is not None and hasattr(loaded, "plugin")
    plugin = loaded.plugin
    instance = _plugin_module(plugin)._instance

    metrics = Metrics(data_dir=tmp_path, logger=_NullLogger())
    instance.server = _StubServer(metrics)

    async def _skip_start(_ctx: Any) -> None:
        return None

    instance.load = _skip_start  # type: ignore[method-assign]

    hook_bus = PluginHookBus()
    context = RuntimePluginContext(
        plugin_name=plugin.name,
        plugin_dir=_dashboard_dir(),
        data_dir=tmp_path / "data",
        config={},
        logger=_NullLogger(),
        adapter=object(),
        hook_bus=hook_bus,
        record_subscription=lambda _subscription: None,
        agent_registry=None,
        plugin_registry=None,
        host=None,
        plugin_control=None,
        markdown_skill_registry=None,
        record_skill_cleanup=None,
    )
    await plugin.on_load(context)
    try:
        await hook_bus.dispatch(
            _DispatchCtx({"post_type": "notice", "notice_type": "group_upload"})
        )
    finally:
        await plugin.on_stop()

    assert metrics.message_stats()["total"] == 0


def test_dashboard_handler_annotation_is_dict() -> None:
    """确保处理器保持 event: dict[str, Any] 写法（触发本次修复的形态）。"""
    loaded = FilesystemPluginLoader(
        source="official", namespace="neobot_builtin_plugins"
    ).load_one(_dashboard_dir())
    assert loaded is not None and hasattr(loaded, "plugin")
    handler = next(
        registration.handler
        for registration in loaded.plugin._registrations
        if registration.kind == "message"
    )
    assert handler.__annotations__["event"] == "dict[str, Any]"
