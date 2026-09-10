"""event 参数注入回归测试。

部署环境曾报错：
    Cannot resolve parameter 'event' for handler ..._dashboard_count_message
原因是 @plugin.message 处理器写成 event: dict[str, Any] 时，约定名注入被
「有注解即视为模型参数」的规则挡住。event 注入的是原始事件字典，没有对应的
运行时类型，因此必须允许 dict 形态注解。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest

from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.loader import FilesystemPluginLoader
from neobot_modloader.message import Message
from neobot_modloader.plugin import Plugin
from neobot_modloader.plugins.injection import parameter_injection_kind
from neobot_modloader.plugins.tools import build_tool_schema


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


def _runtime_context(plugin: Plugin, hook_bus: PluginHookBus, tmp_path: Path) -> RuntimePluginContext:
    return RuntimePluginContext(
        plugin_name=plugin.name,
        plugin_dir=Path(tmp_path),
        data_dir=Path(tmp_path) / "data",
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


# ---------------------------------------------------------------------------
# 分类
# ---------------------------------------------------------------------------


def test_event_accepts_dict_style_annotations() -> None:
    assert parameter_injection_kind("event", dict[str, Any]) == "event"
    assert parameter_injection_kind("event", dict) == "event"
    assert parameter_injection_kind("event", Mapping[str, Any]) == "event"
    assert parameter_injection_kind("event", dict[str, Any] | None) == "event"
    assert parameter_injection_kind("event", Any) == "event"


def test_other_names_keep_annotation_priority() -> None:
    """非 event 的 dict 注解仍是模型参数，约定名注入不得扩大。"""
    assert parameter_injection_kind("payload", dict[str, Any]) is None
    assert parameter_injection_kind("ctx", dict[str, Any]) is None
    assert parameter_injection_kind("event", str) is None
    assert parameter_injection_kind("event", list[str]) is None


def test_agent_state_alias_unchanged() -> None:
    """state 属于 agent 请求别名，行为不受本次修复影响。"""
    assert parameter_injection_kind("state", dict[str, Any]) == "state"
    assert parameter_injection_kind("task", str) == "task"


def test_explicit_tool_schema_still_wins_for_event() -> None:
    """工具显式声明 parameters 时，event 仍按模型参数处理。"""
    assert (
        parameter_injection_kind(
            "event", dict[str, Any], explicit_model_parameter=True
        )
        is None
    )


def test_tool_schema_keeps_unrelated_dict_parameters() -> None:
    async def handler(event: dict[str, Any], payload: dict[str, Any], query: str) -> None:
        pass

    schema = build_tool_schema(handler)
    assert set(schema["properties"]) == {"payload", "query"}


# ---------------------------------------------------------------------------
# 分发
# ---------------------------------------------------------------------------


async def test_message_handler_with_dict_event_annotation_receives_event(
    tmp_path: Path,
) -> None:
    plugin = Plugin("annotated")
    hook_bus = PluginHookBus()
    seen: list[dict[str, Any]] = []

    @plugin.message(priority=-100)
    async def on_message(event: dict[str, Any]) -> None:
        seen.append(event)

    context = _runtime_context(plugin, hook_bus, tmp_path)
    await plugin.on_load(context)
    try:
        await hook_bus.dispatch(
            _DispatchCtx(
                {
                    "post_type": "message",
                    "message_type": "private",
                    "user_id": 42,
                    "message": [{"type": "text", "data": {"text": "hi"}}],
                }
            )
        )
    finally:
        await plugin.on_stop()

    assert len(seen) == 1
    assert seen[0]["user_id"] == 42


async def test_future_annotations_plugin_message_handler_works(tmp_path: Path) -> None:
    """部署现场形态：插件模块使用 from __future__ import annotations。"""
    plugin_dir = tmp_path / "dashboard_like"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.toml").write_text(
        'name = "dashboard_like"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (plugin_dir / "__init__.py").write_text(
        "from __future__ import annotations\n"
        "from typing import Any\n"
        "from neobot_modloader import Plugin\n"
        "\n"
        "plugin = Plugin('dashboard_like', version='1.0.0')\n"
        "seen: list[Any] = []\n"
        "\n"
        "@plugin.message(priority=-100)\n"
        "async def on_message(event: dict[str, Any]) -> None:\n"
        "    seen.append(event)\n",
        encoding="utf-8",
    )

    loaded = FilesystemPluginLoader().load_one(plugin_dir)
    assert loaded is not None and hasattr(loaded, "plugin")
    hook_bus = PluginHookBus()
    context = _runtime_context(loaded.plugin, hook_bus, tmp_path)
    await loaded.plugin.on_load(context)
    try:
        await hook_bus.dispatch(
            _DispatchCtx(
                {
                    "post_type": "message",
                    "message_type": "group",
                    "group_id": 7,
                    "user_id": 9,
                }
            )
        )
    finally:
        await loaded.plugin.on_stop()

    handler = loaded.plugin._registrations[0].handler
    seen = handler.__globals__["seen"]
    assert [item["group_id"] for item in seen] == [7]
