"""插件工具包（一插件多技能）与消息处理器「交主管线」意图的回归测试。

覆盖 spec(5) 落地时新增的两条通用能力：

1. `@plugin.tool(package=...)` 把工具拆成**可独立加载**的技能包
   （技能名 {plugin}_{package}、工具最终名仍是 {plugin}__{tool}）；
2. `ctx.agent_reply(background, preactivate=[...])`：插件消息处理器把控制权交回
   主回复管线，并声明本轮要预激活哪些技能包（一次性、随事件对象传递）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from neobot_modloader.agent_intent import (
    current_event_context,
    normalize_preactivate,
    request_agent_reply,
)
from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.plugin import Plugin
from neobot_modloader.plugins.tools import bind_tools


class _NullLogger:
    def debug(self, *args: Any, **kwargs: Any) -> None: ...
    def info(self, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, *args: Any, **kwargs: Any) -> None: ...
    def error(self, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, *args: Any, **kwargs: Any) -> None: ...


class _DispatchCtx:
    """事件上下文替身（字段与 neobot_app.runtime.event_context.EventContext 对齐）。"""

    def __init__(self, raw_event: dict) -> None:
        self.raw_event = raw_event
        self.consumed = False
        self.skip_ai_reply = False
        self.agent_reply_intent: dict[str, Any] | None = None
        self.agent_reply_requested = False

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True

    def agent_reply(self, background: str = "", *, preactivate: Any = ()) -> None:
        names = normalize_preactivate(preactivate)
        if not background and not names:
            return
        self.agent_reply_intent = {
            "background": str(background),
            "preactivate": names,
        }
        self.agent_reply_requested = True

    def take_agent_reply_intent(self) -> dict[str, Any] | None:
        intent = self.agent_reply_intent
        self.agent_reply_intent = None
        return intent

    def has_agent_reply_intent(self) -> bool:
        return self.agent_reply_intent is not None


class _SkillRegistry:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}

    def register(self, skill: Any) -> None:
        self.items[skill.name] = skill

    def unregister(self, name: str) -> bool:
        return self.items.pop(name, None) is not None

    def get(self, name: str) -> Any:
        return self.items.get(name)


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
        plugin_registry=None,
        host=None,
        plugin_control=None,
        markdown_skill_registry=None,
        record_skill_cleanup=None,
    )


def _packaged_plugin() -> Plugin:
    plugin = Plugin("demo", version="1.0.0", description="demo plugin")
    plugin.tool_package("bottle", description="瓶子包", instructions="瓶子包的说明")
    plugin.tool_package("chengyu", description="接龙包")

    @plugin.tool("write", description="写", package="bottle")
    async def write(content: str) -> str:
        return f"write:{content}"

    @plugin.tool("pick", description="捞", package="bottle")
    async def pick() -> str:
        return "pick"

    @plugin.tool("submit", description="提交", package="chengyu")
    async def submit(word: str) -> str:
        return f"submit:{word}"

    return plugin


async def _bind_into_registry(plugin: Plugin, tmp_path: Path) -> _SkillRegistry:
    registry = _SkillRegistry()
    cleanups: list[Any] = []
    from neobot_modloader.host import PluginHostFacade, TrackedPluginHostFacade

    facade = TrackedPluginHostFacade(PluginHostFacade(skills=registry), cleanups.append)
    ctx = RuntimePluginContext(
        plugin_name=plugin.name,
        plugin_dir=Path(tmp_path),
        data_dir=Path(tmp_path) / "data",
        config={},
        logger=_NullLogger(),
        adapter=object(),
        host=facade,
        record_skill_cleanup=cleanups.append,
    )
    await bind_tools(plugin, plugin._tool_registrations, ctx)
    registry.cleanups = cleanups  # type: ignore[attr-defined]
    return registry


async def test_tool_packages_become_independent_skills(tmp_path: Path) -> None:
    """A：一个插件的两个包注册成两个技能，最终工具名仍是 {plugin}__{tool}。"""
    registry = await _bind_into_registry(_packaged_plugin(), tmp_path)

    assert sorted(registry.items) == ["demo_bottle", "demo_chengyu"]
    bottle = registry.items["demo_bottle"]
    assert bottle.tool_prefix == "demo"
    assert bottle.description == "瓶子包"
    assert bottle.instructions == "瓶子包的说明"
    assert [tool["function"]["name"] for tool in bottle.get_tools()] == ["write", "pick"]


async def test_tool_packages_activation_selects_only_that_package(tmp_path: Path) -> None:
    """B：按需加载 / 预激活可以只激活一个包（不是整套工具）。"""
    from neobot_app.skills.activation import SkillToolActivation
    from neobot_app.skills.base import SkillManager

    registry = await _bind_into_registry(_packaged_plugin(), tmp_path)
    manager = SkillManager(eager_tool_skills=set())
    for skill in registry.items.values():
        manager.register(skill)

    assert manager.deferred_skill_names == ["demo_bottle", "demo_chengyu"]
    assert manager.get_tools([]) == []
    assert [
        tool["function"]["name"] for tool in manager.get_tools(["demo_bottle"])
    ] == ["demo__write", "demo__pick"]

    activation = SkillToolActivation(manager)
    assert activation.tools() == []
    activation.load({"skills": ["demo_bottle"]})
    assert [tool["function"]["name"] for tool in activation.tools()] == [
        "demo__write",
        "demo__pick",
    ]
    assert activation.consume_dirty() is True
    # 路由仍按最终工具名精确匹配
    assert await manager.execute("demo__write", {"content": "hi"}) == "write:hi"
    assert await manager.execute("demo__submit", {"word": "x"}) == "submit:x"


async def test_ungrouped_tools_keep_legacy_single_skill(tmp_path: Path) -> None:
    """C：不声明 package 时行为与历史完全一致（技能名 = 插件名）。"""
    plugin = Plugin("solo", version="1.0.0", description="solo")

    @plugin.tool("ping", description="p")
    async def ping() -> str:
        return "pong"

    registry = await _bind_into_registry(plugin, tmp_path)

    assert list(registry.items) == ["solo"]
    assert registry.items["solo"].tool_prefix == "solo"


async def test_message_handler_agent_reply_intent_is_recorded(tmp_path: Path) -> None:
    """D：消息处理器通过 ctx.agent_reply 登记意图（含预激活技能包），一次消费即清除。"""
    plugin = Plugin("intent_demo", version="1.0.0")
    hook_bus = PluginHookBus()

    @plugin.message(keywords=["漂流瓶"])
    async def entry(ctx: Any, event: dict[str, Any]) -> None:
        ctx.agent_reply("事实 + 提示词", preactivate=["intent_demo_bottle"])

    context = _runtime_context(plugin, hook_bus, tmp_path)
    await plugin.on_load(context)
    dispatch_ctx = _DispatchCtx(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 888,
            "user_id": 7,
            "raw_message": "想玩漂流瓶",
            "message": [{"type": "text", "data": {"text": "想玩漂流瓶"}}],
        }
    )
    try:
        await hook_bus.dispatch(dispatch_ctx)
    finally:
        await plugin.on_stop()

    assert dispatch_ctx.has_agent_reply_intent() is True
    intent = dispatch_ctx.take_agent_reply_intent()
    assert intent == {
        "background": "事实 + 提示词",
        "preactivate": ("intent_demo_bottle",),
    }
    # 一次性：取出后即清除
    assert dispatch_ctx.has_agent_reply_intent() is False
    assert dispatch_ctx.take_agent_reply_intent() is None
    # 不拦截 AI 回复、不消费消息
    assert dispatch_ctx.skip_ai_reply is False
    assert dispatch_ctx.consumed is False


async def test_message_handler_without_intent_changes_nothing(tmp_path: Path) -> None:
    """E：未登记意图时既有行为完全不变（无意图、不消费、不拦截）。"""
    plugin = Plugin("no_intent", version="1.0.0")
    hook_bus = PluginHookBus()
    seen: list[dict[str, Any]] = []

    @plugin.message(keywords=["漂流瓶"])
    async def entry(event: dict[str, Any]) -> None:
        seen.append(event)

    context = _runtime_context(plugin, hook_bus, tmp_path)
    await plugin.on_load(context)
    dispatch_ctx = _DispatchCtx(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 7,
            "raw_message": "想玩漂流瓶",
            "message": [{"type": "text", "data": {"text": "想玩漂流瓶"}}],
        }
    )
    try:
        await hook_bus.dispatch(dispatch_ctx)
    finally:
        await plugin.on_stop()

    assert len(seen) == 1
    assert dispatch_ctx.has_agent_reply_intent() is False
    assert dispatch_ctx.take_agent_reply_intent() is None
    assert dispatch_ctx.consumed is False
    assert dispatch_ctx.skip_ai_reply is False


async def test_agent_reply_outside_dispatch_is_ignored(tmp_path: Path) -> None:
    """F：事件分发之外调用 agent_reply 只是返回 False，绝不抛异常。"""
    plugin = Plugin("outside", version="1.0.0")
    hook_bus = PluginHookBus()
    context = _runtime_context(plugin, hook_bus, tmp_path)

    assert context.agent_reply("背景", preactivate=["x"]) is False
    assert request_agent_reply("背景") is False
    assert current_event_context() is None


def test_normalize_preactivate_dedupes_and_drops_blanks() -> None:
    assert normalize_preactivate(None) == ()
    assert normalize_preactivate(["a", " ", "a", "b"]) == ("a", "b")
    assert normalize_preactivate("a") == ("a",)
