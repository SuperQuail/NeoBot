from __future__ import annotations

import tempfile
import unittest
import copy
from pathlib import Path
from typing import Any

from neobot_chat import Workflow
from pydantic import BaseModel

from neobot_modloader.agent import AgentRequest
from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.host import PluginHostFacade
from neobot_modloader.message import ImageSegment, MessageChain
from neobot_modloader.plugin import Plugin
from neobot_modloader.plugins.agents import PluginAgentRegistrar
from neobot_modloader.reply import Reply
from neobot_modloader.plugins.markdown_skills import _normalize_allowed_tools, scan_plugin_skills
from neobot_modloader.plugins.registration import validate_plugin_name, validate_qualified_tool_name


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, Any]] = []

    async def send(self, conversation: Any, message: Any) -> str:
        self.calls.append((conversation, message))
        return "ok"

    async def send_private_msg(self, user_id: int, message: Any) -> str:
        self.calls.append((user_id, message))
        return "ok"

    async def send_group_msg(self, group_id: int, message: Any) -> str:
        self.calls.append((group_id, message))
        return "ok"


class DispatchCtx:
    def __init__(self, raw_event: dict[str, Any]) -> None:
        self.raw_event = raw_event
        self.consumed = False
        self.skip_ai_reply = False

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True


class FakeAgentRegistry:
    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}

    @property
    def names(self) -> list[str]:
        return list(self.agents)

    def register(self, name: str, agent: Any) -> None:
        self.agents[name] = agent

    def unregister(self, name: str) -> Any | None:
        return self.agents.pop(name, None)


class FakeSkillRegistry:
    """模拟 SkillManager 的最小实现（前缀 + 路由执行）。"""

    def __init__(self) -> None:
        self._skills: dict[str, Any] = {}

    def register(self, skill: Any) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Skill '{skill.name}' 已注册")
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> None:
        self._skills.pop(name, None)

    def get(self, name: str) -> Any | None:
        return self._skills.get(name)

    def get_tools(self) -> list[dict]:
        tools: list[dict] = []
        for skill in self._skills.values():
            for tool_def in skill.get_tools():
                prefixed = copy.deepcopy(tool_def)
                prefixed["function"]["name"] = f"{skill.name}__{tool_def['function']['name']}"
                tools.append(prefixed)
        return tools

    async def execute(self, prefixed_name: str, args: dict[str, Any]) -> str:
        skill_name, _, tool_name = prefixed_name.partition("__")
        skill = self._skills.get(skill_name)
        if skill is None:
            return f"未找到 Skill: {skill_name}"
        return await skill.execute(tool_name, args)


class FakeMarkdownSkillRegistry:
    """模拟 neobot_chat SkillRegistry 的 owner-aware 接口。"""

    def __init__(self) -> None:
        self._skills: dict[str, Any] = {}

    def register_many(self, owner: str, skills: list[Any]) -> None:
        for skill in skills:
            qualified = f"{owner}:{skill.name}"
            if qualified in self._skills:
                raise ValueError(f"Skill 已注册: {qualified}")
            self._skills[qualified] = skill

    def unregister_owner(self, owner: str) -> list[str]:
        prefix = f"{owner}:"
        removed = [name for name in self._skills if name.startswith(prefix)]
        for name in removed:
            self._skills.pop(name, None)
        return removed


class Config(BaseModel):
    reply: str = "pong"


class CityRequest(BaseModel):
    city: str
    days: int = 1


class Item(BaseModel):
    name: str


class Order(BaseModel):
    items: list[Item]


class ConflictOrderA(BaseModel):
    """同名不同结构 Item 之冲突用例 A（模块级定义，get_type_hints 才能解析）。"""

    class Item(BaseModel):
        name: str

    item: Item


class ConflictOrderB(BaseModel):
    class Item(BaseModel):
        sku: str

    item: Item


class ReuseOuter1(BaseModel):
    """同名同结构 Item 之复用用例。"""

    class Item(BaseModel):
        name: str

    item: Item


class ReuseOuter2(BaseModel):
    class Item(BaseModel):
        name: str

    item: Item


class DependencyConflictA(BaseModel):
    class Leaf(BaseModel):
        name: str

    class Wrapper(BaseModel):
        leaf: "DependencyConflictA.Leaf"

    wrapper: Wrapper


class DependencyConflictB(BaseModel):
    class Leaf(BaseModel):
        sku: str

    class Wrapper(BaseModel):
        leaf: "DependencyConflictB.Leaf"

    wrapper: Wrapper


def _collect_refs(node: Any, refs: list[str]) -> list[str]:
    """递归收集 schema 内所有 $ref 值。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                refs.append(value)
            else:
                _collect_refs(value, refs)
    elif isinstance(node, list):
        for item in node:
            _collect_refs(item, refs)
    return refs


class PluginApiTest(unittest.IsolatedAsyncioTestCase):
    def make_context(
        self,
        plugin: Plugin,
        hook_bus: PluginHookBus,
        adapter: FakeAdapter,
        config: dict[str, Any] | None = None,
        agent_registry: FakeAgentRegistry | None = None,
        plugin_registry: Any | None = None,
        host: Any | None = None,
        plugin_control: Any | None = None,
        markdown_skill_registry: FakeMarkdownSkillRegistry | None = None,
        record_skill_cleanup: Any | None = None,
    ) -> RuntimePluginContext:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        return RuntimePluginContext(
            plugin_name=plugin.name,
            plugin_dir=root,
            data_dir=root / "data",
            config=config or {},
            logger=None,
            adapter=adapter,
            hook_bus=hook_bus,
            record_subscription=lambda _subscription: None,
            agent_registry=agent_registry,
            plugin_registry=plugin_registry,
            host=host,
            plugin_control=plugin_control,
            markdown_skill_registry=markdown_skill_registry,
            record_skill_cleanup=record_skill_cleanup,
        )

    async def test_command_captures_image_and_injects_reply(self) -> None:
        plugin = Plugin("vision")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        seen: list[str | None] = []

        @plugin.command("识图 <img:image>")
        async def vision(img: ImageSegment, reply: Reply) -> None:
            seen.append(img.url)
            await reply.send(img)

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter))
        await hook_bus.dispatch(
            DispatchCtx(
                {
                    "post_type": "message",
                    "message_type": "private",
                    "user_id": 1,
                    "message": [
                        {"type": "text", "data": {"text": "/识图"}},
                        {"type": "image", "data": {"url": "https://example/image.png"}},
                    ],
                }
            )
        )

        self.assertEqual(seen, ["https://example/image.png"])
        self.assertEqual(adapter.calls[0][1], [{"type": "image", "data": {"url": "https://example/image.png"}}])

    async def test_message_filter_and_config_injection(self) -> None:
        plugin = Plugin("ping", config=Config)
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()

        @plugin.message(text="ping")
        async def ping(reply: Reply, config: Config) -> None:
            await reply.send(config.reply)

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, {"reply": "PONG"}))
        await hook_bus.dispatch(
            DispatchCtx({"post_type": "message", "message_type": "private", "user_id": 1, "raw_message": "ping"})
        )

        self.assertEqual(adapter.calls[0][1], "PONG")

    async def test_lifecycle_decorators_run(self) -> None:
        plugin = Plugin("life")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        seen: list[str] = []

        @plugin.on_load
        async def loaded() -> None:
            seen.append("load")

        @plugin.on_startup
        async def started() -> None:
            seen.append("start")

        @plugin.on_shutdown
        async def stopped() -> None:
            seen.append("stop")

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter))
        await plugin.on_start()
        await plugin.on_stop()

        self.assertEqual(seen, ["load", "start", "stop"])

    async def test_failed_shutdown_runs_all_handlers_and_allows_rebind(self) -> None:
        plugin = Plugin("life")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        seen: list[str] = []

        @plugin.on_shutdown
        async def succeeds() -> None:
            seen.append("succeeds")

        @plugin.on_shutdown
        async def fails() -> None:
            seen.append("fails")
            raise RuntimeError("shutdown")

        context = self.make_context(plugin, hook_bus, adapter)
        await plugin.on_load(context)
        with self.assertRaisesRegex(RuntimeError, "shutdown"):
            await plugin.on_stop()

        self.assertEqual(seen, ["fails", "succeeds"])
        self.assertFalse(plugin._bound)
        await plugin.on_load(context)
        self.assertTrue(plugin._bound)

    async def test_lifecycle_injects_context_and_plugin_control(self) -> None:
        plugin = Plugin("life")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        control = object()
        seen: list[tuple[str, bool, bool]] = []

        @plugin.on_load
        async def loaded(ctx: RuntimePluginContext, context: RuntimePluginContext, plugin_control: Any) -> None:
            seen.append((ctx.plugin_name, ctx is context, plugin_control is control))

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, plugin_control=control))

        self.assertEqual(seen, [("life", True, True)])

    async def test_agent_handler_registers_and_returns_string(self) -> None:
        plugin = Plugin("demo", config=Config)
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        registry = FakeAgentRegistry()
        seen: list[tuple[str, str, str]] = []

        @plugin.agent("echo", description="Echo agent")
        async def echo(task: str, request: AgentRequest, config: Config, logger: Any, data_dir: Path) -> str:
            seen.append((task, request.delegate_context, config.reply))
            self.assertTrue(data_dir.exists())
            self.assertIsNotNone(logger)
            return f"{config.reply}: {task}"

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, {"reply": "PONG"}, registry))

        self.assertIn("demo.echo", registry.agents)
        agent = registry.agents["demo.echo"]
        self.assertEqual(agent.description, "Echo agent")
        result = await agent.invoke(
            {
                "messages": [{"role": "user", "content": "hello"}],
                "_delegate_context": "ctx",
            }
        )

        self.assertEqual(seen, [("hello", "ctx", "PONG")])
        self.assertEqual(result["messages"][-1], {"role": "assistant", "content": "PONG: hello"})

    async def test_legacy_agent_registry_drain_fallback_closes_exactly_once(self) -> None:
        class LegacyAgent:
            description = "legacy"
            tool_definitions: list[dict[str, Any]] = []

            def __init__(self) -> None:
                self.close_count = 0

            async def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
                return state

            async def stream_invoke(self, state: dict[str, Any]):
                if False:
                    yield state

            async def close(self) -> None:
                self.close_count += 1

        registry = FakeAgentRegistry()
        registrar = PluginAgentRegistrar(
            plugin_name="legacy", registry=registry, record_registration=None
        )
        agent = LegacyAgent()
        registered_name = registrar.register("worker", agent)

        self.assertIs(await registrar.unregister_and_drain(registered_name), agent)
        self.assertIsNone(await registrar.unregister_and_drain(registered_name))
        self.assertEqual(agent.close_count, 1)

    async def test_agent_handler_normalizes_message_chain_result(self) -> None:
        plugin = Plugin("demo")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        registry = FakeAgentRegistry()

        @plugin.agent("chain")
        async def chain() -> MessageChain:
            return MessageChain().text("result")

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, agent_registry=registry))
        result = await registry.agents["demo.chain"].invoke({"messages": [{"role": "user", "content": "go"}]})

        self.assertEqual(result["messages"][-1]["role"], "assistant")
        self.assertEqual(result["messages"][-1]["content"], [{"type": "text", "data": {"text": "result"}}])

    async def test_agent_factory_wraps_workflow(self) -> None:
        plugin = Plugin("flow")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        registry = FakeAgentRegistry()

        async def step(state: dict[str, Any]) -> dict[str, Any]:
            messages = list(state.get("messages", []))
            messages.append({"role": "assistant", "content": "workflow done"})
            return {**state, "messages": messages}

        @plugin.agent("worker", description="Workflow agent", factory=True)
        def build_worker() -> Workflow:
            return Workflow().add_step(step)

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, agent_registry=registry))
        agent = registry.agents["flow.worker"]
        result = await agent.invoke({"messages": [{"role": "user", "content": "run"}]})
        chunks = [chunk async for chunk in agent.stream_invoke({"messages": [{"role": "user", "content": "run"}]})]

        self.assertEqual(agent.description, "Workflow agent")
        self.assertEqual(agent.tool_definitions, [])
        self.assertEqual(result["messages"][-1]["content"], "workflow done")
        self.assertEqual(chunks[-1].state["messages"][-1]["content"], "workflow done")

    async def test_agent_factory_wraps_agent_like_and_closes(self) -> None:
        class Target:
            description = "target description"
            tool_definitions = [{"type": "function", "function": {"name": "tool", "arguments": "{}"}}]

            def __init__(self) -> None:
                self.closed = False

            async def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
                return {"messages": [{"role": "assistant", "content": "ok"}]}

            async def stream_invoke(self, state: dict[str, Any]):
                yield "custom"

            async def close(self) -> None:
                self.closed = True

        plugin = Plugin("factory")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        registry = FakeAgentRegistry()
        target = Target()

        @plugin.agent("target", factory=True)
        def build_target() -> Target:
            return target

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, agent_registry=registry))
        agent = registry.agents["factory.target"]
        chunks = [chunk async for chunk in agent.stream_invoke({})]
        await agent.close()

        self.assertEqual(agent.description, "target description")
        self.assertEqual(agent.tool_definitions, Target.tool_definitions)
        self.assertEqual(chunks, ["custom"])
        self.assertTrue(target.closed)

    async def test_agent_handler_return_none_raises(self) -> None:
        plugin = Plugin("bad")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        registry = FakeAgentRegistry()

        @plugin.agent("none")
        async def none_agent() -> None:
            return None

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, agent_registry=registry))

        with self.assertRaises(TypeError):
            await registry.agents["bad.none"].invoke({"messages": [{"role": "user", "content": "x"}]})

    async def test_agent_factory_without_invoke_fails_load(self) -> None:
        plugin = Plugin("bad")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        registry = FakeAgentRegistry()

        @plugin.agent("broken", factory=True)
        def broken() -> object:
            return object()

        with self.assertRaises(TypeError):
            await plugin.on_load(self.make_context(plugin, hook_bus, adapter, agent_registry=registry))

    async def test_duplicate_agent_name_fails_load(self) -> None:
        plugin = Plugin("dup")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        registry = FakeAgentRegistry()

        @plugin.agent("echo")
        async def first() -> str:
            return "first"

        @plugin.agent("echo")
        async def second() -> str:
            return "second"

        with self.assertRaises(ValueError):
            await plugin.on_load(self.make_context(plugin, hook_bus, adapter, agent_registry=registry))

    def test_agent_name_validation(self) -> None:
        plugin = Plugin("bad")

        with self.assertRaises(ValueError):
            plugin.agent("bad.name")

    async def test_tool_registers_and_executes(self) -> None:
        plugin = Plugin("weather", config=Config)
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)
        seen: list[tuple[str, str]] = []

        @plugin.tool("query", description="查询天气")
        async def query(city: str, config: Config, logger: Any, data_dir: Path) -> str:
            seen.append((city, config.reply))
            self.assertIsNotNone(logger)
            self.assertTrue(data_dir.exists())
            return f"{city}: 晴"

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, {"reply": "PONG"}, host=host))

        names = [tool["function"]["name"] for tool in skills.get_tools()]
        self.assertEqual(names, ["weather__query"])
        result = await skills.execute("weather__query", {"city": "上海"})

        self.assertEqual(result, "上海: 晴")
        self.assertEqual(seen, [("上海", "PONG")])
        skills.unregister("weather")
        self.assertEqual(skills.get_tools(), [])

    async def test_tool_schema_generated_from_signature(self) -> None:
        plugin = Plugin("calc")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("add", description="加法")
        async def add(a: int, b: float = 1.5, tags: list[str] | None = None) -> str:
            return str(a)

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        schema = skills.get_tools()[0]["function"]["parameters"]

        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["properties"]["a"], {"type": "integer"})
        self.assertEqual(schema["properties"]["b"], {"type": "number", "default": 1.5})
        self.assertEqual(schema["properties"]["tags"], {"type": "array", "items": {"type": "string"}})
        self.assertEqual(schema["required"], ["a"])
        self.assertNotIn("ctx", schema["properties"])

    async def test_tool_duplicate_name_fails_load(self) -> None:
        plugin = Plugin("dup")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("ping")
        async def first() -> str:
            return "first"

        @plugin.tool("ping")
        async def second() -> str:
            return "second"

        with self.assertRaises(ValueError):
            await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))

    def test_tool_name_validation(self) -> None:
        plugin = Plugin("bad")

        with self.assertRaises(ValueError):
            plugin.tool("bad-name")
        with self.assertRaises(ValueError):
            plugin.tool("a__b")

    async def test_tool_explicit_empty_parameters_are_honored(self) -> None:
        plugin = Plugin("empty")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("noargs", parameters={})
        async def noargs(name: str) -> str:
            return name

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        schema = skills.get_tools()[0]["function"]["parameters"]

        # 显式 parameters={} 必须生效，而不是被 or 短路回自动 schema
        self.assertEqual(schema, {"type": "object"})

    async def test_tool_explicit_parameters_shell_preserved(self) -> None:
        plugin = Plugin("explicit")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool(
            "fixed",
            parameters={
                "properties": {"x": {"type": "integer"}},
                "required": ["x"],
            },
        )
        async def fixed(y: str) -> str:
            return y

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        schema = skills.get_tools()[0]["function"]["parameters"]

        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["properties"], {"x": {"type": "integer"}})
        self.assertEqual(schema["required"], ["x"])

    async def test_tool_schema_union_annotations(self) -> None:
        plugin = Plugin("union")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("f")
        async def f(amount: int | float | None = None, tag: str | None = None) -> str:
            return "ok"

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        schema = skills.get_tools()[0]["function"]["parameters"]

        # int | float 收敛为 number；str | None 收敛为 string
        self.assertEqual(schema["properties"]["amount"], {"type": "number"})
        self.assertEqual(schema["properties"]["tag"], {"type": "string"})
        self.assertEqual(schema["required"], [])

    async def test_tool_skips_bind_without_host(self) -> None:
        plugin = Plugin("none")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()

        @plugin.tool("t")
        async def t() -> str:
            return "ok"

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter))
        self.assertEqual(len(plugin._tool_registrations), 1)

    def _write_skill(self, root: Path, name: str, keywords: str) -> Path:
        skill_dir = root / "skills" / name
        skill_dir.mkdir(parents=True)
        md = skill_dir / "SKILL.md"
        md.write_text(
            f"---\nname: {name}\nkeywords: {keywords}\ndescription: 测试技能\n---\n正文",
            encoding="utf-8",
        )
        return md

    async def test_markdown_skills_discovered_and_registered(self) -> None:
        plugin = Plugin("weather")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        registry = FakeMarkdownSkillRegistry()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self._write_skill(root, "forecast", "天气 气温")

        await plugin.on_load(self._ctx_with_dir(plugin, hook_bus, adapter, root, registry))

        self.assertIn("weather:forecast", registry._skills)
        skill = registry._skills["weather:forecast"]
        self.assertEqual(skill.name, "forecast")
        self.assertEqual(skill.content, "正文")

    async def test_markdown_skills_unregister_all(self) -> None:
        plugin = Plugin("weather")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        registry = FakeMarkdownSkillRegistry()
        cleanups: list[Any] = []
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self._write_skill(root, "forecast", "天气")

        ctx = self._ctx_with_dir(
            plugin, hook_bus, adapter, root, registry, record_skill_cleanup=cleanups.append
        )
        await plugin.on_load(ctx)

        self.assertIn("weather:forecast", registry._skills)
        for cleanup in cleanups:
            cleanup()
        self.assertNotIn("weather:forecast", registry._skills)

    async def test_markdown_skills_invalid_file_skipped(self) -> None:
        plugin = Plugin("bad")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        registry = FakeMarkdownSkillRegistry()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self._write_skill(root, "good", "天气")
        (root / "skills" / "broken").mkdir(parents=True)
        (root / "skills" / "broken" / "SKILL.md").write_text("没有 frontmatter", encoding="utf-8")

        await plugin.on_load(self._ctx_with_dir(plugin, hook_bus, adapter, root, registry))

        self.assertEqual(list(registry._skills), ["bad:good"])

    async def test_markdown_skills_crlf_and_eof_frontmatter(self) -> None:
        plugin = Plugin("win")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        registry = FakeMarkdownSkillRegistry()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        # Windows 写文件常见 CRLF 行尾
        (root / "skills" / "crlf").mkdir(parents=True)
        (root / "skills" / "crlf" / "SKILL.md").write_bytes(
            b"---\r\nname: crlf\r\ndescription: \xe6\xb5\x8b\xe8\xaf\x95\r\n---\r\nbody line\r\n"
        )
        # 关闭分隔符后没有换行（EOF 结尾）也必须能被解析
        (root / "skills" / "eof").mkdir(parents=True)
        (root / "skills" / "eof" / "SKILL.md").write_text("---\nname: eof\ndescription: 测试\n---", encoding="utf-8")

        await plugin.on_load(self._ctx_with_dir(plugin, hook_bus, adapter, root, registry))

        self.assertIn("win:crlf", registry._skills)
        self.assertIn("win:eof", registry._skills)
        self.assertEqual(registry._skills["win:crlf"].content, "body line\n")
        self.assertEqual(registry._skills["win:eof"].content, "")

    async def test_markdown_skills_skips_pycache_and_oversize(self) -> None:
        plugin = Plugin("scan")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        registry = FakeMarkdownSkillRegistry()
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self._write_skill(root, "good", "天气")
        (root / "skills" / "__pycache__").mkdir(parents=True)
        (root / "skills" / "__pycache__" / "SKILL.md").write_text(
            "---\nname: cache\n---\nbody", encoding="utf-8"
        )
        (root / "skills" / "huge").mkdir(parents=True)
        (root / "skills" / "huge" / "SKILL.md").write_text(
            "---\nname: huge\n---\n" + "x" * (200 * 1024), encoding="utf-8"
        )

        await plugin.on_load(self._ctx_with_dir(plugin, hook_bus, adapter, root, registry))

        self.assertEqual(list(registry._skills), ["scan:good"])

    async def test_markdown_skills_register_failure_fails_load(self) -> None:
        plugin = Plugin("conflict")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        registry = FakeMarkdownSkillRegistry()
        # 预置同名技能，让 register_many 抛 ValueError
        registry.register_many("conflict", [type("S", (), {"name": "good", "description": "d", "content": "c", "path": Path(".")})()])
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self._write_skill(root, "good", "天气")

        with self.assertRaises(ValueError):
            await plugin.on_load(self._ctx_with_dir(plugin, hook_bus, adapter, root, registry))

    async def test_markdown_skills_without_registry_skipped(self) -> None:
        plugin = Plugin("noskill")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self._write_skill(root, "good", "天气")

        @plugin.tool("t")
        async def t() -> str:
            return "ok"

        # 未注入共享 Skill 注册表：技能跳过（不抛错），工具仍正常绑定
        ctx = self._ctx_with_dir(plugin, hook_bus, adapter, root, host=host)
        self.assertFalse(ctx.markdown_skills.available)
        await plugin.on_load(ctx)
        self.assertEqual([tool["function"]["name"] for tool in skills.get_tools()], ["noskill__t"])

    def _ctx_with_dir(
        self,
        plugin: Plugin,
        hook_bus: PluginHookBus,
        adapter: FakeAdapter,
        plugin_dir: Path,
        markdown_skill_registry: FakeMarkdownSkillRegistry | None = None,
        record_skill_cleanup: Any | None = None,
        host: Any | None = None,
    ) -> RuntimePluginContext:
        return RuntimePluginContext(
            plugin_name=plugin.name,
            plugin_dir=plugin_dir,
            data_dir=plugin_dir / "data",
            config={},
            logger=None,
            adapter=adapter,
            hook_bus=hook_bus,
            record_subscription=lambda _subscription: None,
            markdown_skill_registry=markdown_skill_registry,
            record_skill_cleanup=record_skill_cleanup,
            host=host,
        )


    def test_normalize_allowed_tools_splits_on_whitespace_and_comma(self) -> None:
        # Agent Skills 标准：allowed-tools 为空白分隔（也可 YAML 列表）
        self.assertEqual(_normalize_allowed_tools("a b,c"), ("a", "b", "c"))
        self.assertEqual(_normalize_allowed_tools(" weather__query "), ("weather__query",))
        self.assertEqual(_normalize_allowed_tools("a, a b, b"), ("a", "b"))
        self.assertEqual(_normalize_allowed_tools([" a ", "b", "a"]), ("a", "b"))
        self.assertEqual(_normalize_allowed_tools(""), ())
        with self.assertRaisesRegex(ValueError, "字符串"):
            _normalize_allowed_tools(123)

    def _scan_skill(self, root: Path, rel_dir: str, content: str):
        path = root / "skills" / rel_dir / "SKILL.md"
        path.parent.mkdir(parents=True)
        path.write_text(content, encoding="utf-8")
        return scan_plugin_skills(root)

    def test_skill_rejects_invalid_names(self) -> None:
        # 大写 / 下划线 / 连续连字符 / 超长 name 一律拒绝
        for name in ["Weather", "bad_skill", "bad--skill", "n" * 65]:
            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            root = Path(temp.name)
            _, errors = self._scan_skill(root, name, f"---\nname: {name}\ndescription: 测试\n---\n正文")
            self.assertEqual(len(errors), 1, name)
            self.assertIn("kebab-case", errors[0])
        # name 与父目录名不一致拒绝
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        _, errors = self._scan_skill(root, "other", "---\nname: expected\ndescription: 测试\n---\n正文")
        self.assertIn("不一致", errors[0])

    def test_skill_rejects_missing_or_long_description(self) -> None:
        cases = [
            ("d1", "---\nname: d1\ndescription: \n---\n正文", "description 必填"),
            ("d2", "---\nname: d2\n---\n正文", "description 必填"),
            ("d3", f"---\nname: d3\ndescription: {'x' * 2049}\n---\n正文", "超过 2048 字符"),
        ]
        for rel_dir, content, expected in cases:
            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            root = Path(temp.name)
            _, errors = self._scan_skill(root, rel_dir, content)
            self.assertEqual(len(errors), 1, rel_dir)
            self.assertIn(expected, errors[0])

    def test_skill_rejects_invalid_metadata(self) -> None:
        cases = [
            ("m1", "---\nname: m1\ndescription: 测试\nmetadata:\n  1: x\n---\n正文"),
            ("m2", "---\nname: m2\ndescription: 测试\nmetadata: not-a-dict\n---\n正文"),
        ]
        for rel_dir, content in cases:
            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            root = Path(temp.name)
            _, errors = self._scan_skill(root, rel_dir, content)
            self.assertEqual(len(errors), 1, rel_dir)
            self.assertIn("metadata 必须是 dict", errors[0])

    def test_skill_rejects_oversized_license_and_compatibility(self) -> None:
        cases = [
            ("l1", f"---\nname: l1\ndescription: 测试\nlicense: {'L' * 257}\n---\n正文", "license 超过 256"),
            ("c1", f"---\nname: c1\ndescription: 测试\ncompatibility: [{'x' * 100}, {'y' * 200}]\n---\n正文", "compatibility 超过 256"),
        ]
        for rel_dir, content, expected in cases:
            temp = tempfile.TemporaryDirectory()
            self.addCleanup(temp.cleanup)
            root = Path(temp.name)
            _, errors = self._scan_skill(root, rel_dir, content)
            self.assertEqual(len(errors), 1, rel_dir)
            self.assertIn(expected, errors[0])

    def test_skill_allowed_tools_parsed_from_whitespace_frontmatter(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        content = (
            "---\nname: w\nkeywords: x\ndescription: 测试\n"
            "allowed-tools: weather__query city__get, other__tool\n---\n正文"
        )
        skills, errors = self._scan_skill(root, "w", content)
        self.assertEqual(errors, [])
        self.assertEqual(
            skills[0].allowed_tools, ("weather__query", "city__get", "other__tool")
        )
        # YAML 列表形式逐项校验；含空白的项不是合法最终工具名
        list_content = (
            "---\nname: l\ndescription: 测试\nallowed-tools:\n  - a\n  - b b\n  - a\n---\n正文"
        )
        skills, errors = self._scan_skill(root, "l", list_content)
        self.assertEqual(len(errors), 1)
        self.assertIn("invalid allowed-tools entry", errors[0])
        self.assertNotIn("l", [skill.name for skill in skills])

    def test_skill_valid_fields_accepted(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        content = (
            "---\nname: full\ndescription: 测试\nlicense: MIT\n"
            "compatibility: [4.4, 4.5]\nmetadata:\n  author: me\n"
            "allowed-tools: a b\n---\n正文"
        )
        skills, errors = self._scan_skill(root, "full", content)
        self.assertEqual(errors, [])
        self.assertEqual(skills[0].license, "MIT")
        self.assertEqual(skills[0].compatibility, "4.4, 4.5")
        self.assertEqual(skills[0].metadata, {"author": "me"})
        self.assertEqual(skills[0].allowed_tools, ("a", "b"))

    async def test_tool_base_model_argument_instantiated(self) -> None:
        plugin = Plugin("bm")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)
        seen: list[Any] = []

        @plugin.tool("q")
        async def q(payload: CityRequest) -> str:
            seen.append(payload)
            return f"{payload.city}:{payload.days}"

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        result = await skills.execute("bm__q", {"payload": {"city": "上海", "days": 2}})

        self.assertEqual(result, "上海:2")
        self.assertIsInstance(seen[0], CityRequest)
        self.assertEqual(seen[0].city, "上海")

    async def test_tool_base_model_invalid_argument_returns_friendly_error(self) -> None:
        plugin = Plugin("bm")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("q")
        async def q(payload: CityRequest) -> str:
            return payload.city

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        result = await skills.execute("bm__q", {"payload": {"city": 123}})

        self.assertIn("参数 payload 校验失败", result)
        self.assertIn("CityRequest", result)

    async def test_tool_container_and_optional_arguments_converted(self) -> None:
        plugin = Plugin("conv")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("tags")
        async def tags(tags: list[str], amount: int | None = None) -> str:
            return ",".join(tags) + f":{amount}"

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        result = await skills.execute("conv__tags", {"tags": ["a", "b"], "amount": "3"})

        self.assertEqual(result, "a,b:3")

    def test_validate_qualified_tool_name(self) -> None:
        self.assertEqual(validate_qualified_tool_name("weather", "query"), "weather__query")
        self.assertEqual(validate_qualified_tool_name("my-plugin", "query"), "my-plugin__query")
        # 插件名含点 → 最终全局名含点，拒绝
        with self.assertRaises(ValueError):
            validate_qualified_tool_name("my.plugin", "query")
        # 插件名 + 工具名组合超 64 字符，拒绝
        with self.assertRaises(ValueError):
            validate_qualified_tool_name("p" * 40, "t" * 30)

    async def test_tool_qualified_name_with_dot_plugin_fails_load(self) -> None:
        plugin = Plugin("my.plugin")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("t")
        async def t() -> str:
            return "ok"

        with self.assertRaises(ValueError):
            await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))

    async def test_tool_qualified_name_too_long_fails_load(self) -> None:
        plugin = Plugin("p" * 40)
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("t" * 30)
        async def t() -> str:
            return "ok"

        with self.assertRaises(ValueError):
            await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))

    def test_validate_plugin_name_rejects_double_underscore(self) -> None:
        # `__` 与工具命名空间分隔符冲突，直接拒绝
        with self.assertRaises(ValueError):
            validate_plugin_name("foo__bar")
        with self.assertRaises(ValueError):
            validate_plugin_name("__leading")
        with self.assertRaises(ValueError):
            validate_plugin_name("trailing__")
        # 单下划线仍允许
        self.assertEqual(validate_plugin_name("my_plugin"), "my_plugin")

    async def test_tool_schema_nested_base_model_defs_hoisted_to_root(self) -> None:
        plugin = Plugin("order")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("q")
        async def q(order: Order) -> str:
            return "ok"

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        schema = skills.get_tools()[0]["function"]["parameters"]

        # $defs 上提到 parameters 根层，Item 定义完整可解析
        self.assertIn("$defs", schema)
        self.assertEqual(schema["$defs"]["Item"]["type"], "object")
        self.assertEqual(schema["$defs"]["Item"]["properties"]["name"]["type"], "string")
        # properties 中所有 $ref 指向根层有效 $defs（无悬空引用）
        refs = _collect_refs(schema, [])
        self.assertTrue(refs)
        for ref in refs:
            self.assertTrue(ref.startswith("#/$defs/"))
            self.assertIn(ref.removeprefix("#/$defs/"), schema["$defs"])
        # 属性层不再残留自己的 $defs
        self.assertNotIn("$defs", schema["properties"]["order"])

    async def test_tool_schema_flat_base_model_without_defs(self) -> None:
        plugin = Plugin("flatbm")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("q")
        async def q(payload: CityRequest) -> str:
            return payload.city

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        schema = skills.get_tools()[0]["function"]["parameters"]

        # 扁平 BaseModel 行为不变：无 $defs，属性结构直接内联
        self.assertNotIn("$defs", schema)
        self.assertEqual(schema["properties"]["payload"]["type"], "object")
        self.assertEqual(
            schema["properties"]["payload"]["properties"]["city"], {"title": "City", "type": "string"}
        )

    async def test_tool_schema_same_name_defs_conflict_uniquified(self) -> None:
        """两个参数各自含同名但结构不同的嵌套模型时，后者的 $defs 不能被静默丢弃。

        修复前：setdefault 以先出现者为准，第二个参数的 $ref 指向第一个的
        Item 定义，结构被丢弃；修复后按 {参数名}__{def 名} 唯一化并重写 $ref。
        """
        plugin = Plugin("conflict")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("q")
        async def q(a: ConflictOrderA, b: ConflictOrderB) -> str:
            return "ok"

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        schema = skills.get_tools()[0]["function"]["parameters"]

        # 两个参数各自的 $ref 指向不同的定义，且结构各自正确
        ref_a = schema["properties"]["a"]["properties"]["item"]["$ref"]
        ref_b = schema["properties"]["b"]["properties"]["item"]["$ref"]
        self.assertNotEqual(ref_a, ref_b)
        self.assertTrue(ref_a.startswith("#/$defs/"))
        self.assertTrue(ref_b.startswith("#/$defs/"))
        def_name_a = ref_a.removeprefix("#/$defs/")
        def_name_b = ref_b.removeprefix("#/$defs/")
        self.assertIn(def_name_a, schema["$defs"])
        self.assertIn(def_name_b, schema["$defs"])
        self.assertEqual(schema["$defs"][def_name_a]["properties"]["name"]["type"], "string")
        self.assertEqual(schema["$defs"][def_name_b]["properties"]["sku"]["type"], "string")
        # 所有 $ref 均指向根层有效 $defs，无悬空引用
        refs = _collect_refs(schema, [])
        for ref in refs:
            self.assertIn(ref.removeprefix("#/$defs/"), schema["$defs"])

    async def test_tool_schema_same_name_defs_identical_reused(self) -> None:
        """同名且结构相同的嵌套定义应直接复用，不产生多余的唯一化 key。"""
        plugin = Plugin("reuse")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("q")
        async def q(a: ReuseOuter1, b: ReuseOuter2) -> str:
            return "ok"

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        schema = skills.get_tools()[0]["function"]["parameters"]

        self.assertIn("Item", schema["$defs"])
        refs = {ref for ref in _collect_refs(schema, []) if ref.startswith("#/$defs/")}
        self.assertEqual(refs, {"#/$defs/Item"})

    def test_markdown_skill_with_bom_frontmatter_parsed(self) -> None:
        """带 UTF-8 BOM 的 SKILL.md 也能正常解析（修复前整体被丢弃）。"""
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        path = root / "skills" / "bom"
        path.mkdir(parents=True)
        (path / "SKILL.md").write_bytes(
            "\ufeff---\nname: bom\ndescription: 测试\nkeywords: 天气\n---\n正文".encode("utf-8")
        )

        skills, errors = scan_plugin_skills(root)

        self.assertEqual(errors, [])
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].name, "bom")
        self.assertEqual(skills[0].description, "测试")
        self.assertEqual(skills[0].content, "正文")

    async def test_tool_coerce_failure_returns_single_line_summary(self) -> None:
        plugin = Plugin("coerce")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("q")
        async def q(payload: CityRequest) -> str:
            return payload.city

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        result = await skills.execute("coerce__q", {"payload": {"city": 123}})

        self.assertIn("参数 payload 校验失败", result)
        self.assertIn("CityRequest", result)
        # 单行摘要：无换行、无 pydantic 文档 URL、长度受限
        self.assertNotIn("\n", result)
        self.assertNotIn("pydantic.dev", result)
        self.assertLessEqual(len(result), 200)

    async def test_tool_model_cannot_forge_hidden_di_arguments(self) -> None:
        plugin = Plugin("secure")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)
        seen: list[Any] = []

        @plugin.tool("whoami")
        async def whoami(ctx: RuntimePluginContext) -> str:
            seen.append(ctx)
            return ctx.plugin_name

        context = self.make_context(plugin, hook_bus, adapter, host=host)
        await plugin.on_load(context)
        result = await skills.execute("secure__whoami", {"ctx": "forged"})

        self.assertEqual(result, "secure")
        self.assertEqual(seen, [context])

    async def test_tool_schema_renames_identical_wrapper_with_conflicting_leaf(self) -> None:
        plugin = Plugin("dependency")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("q")
        async def q(a: DependencyConflictA, b: DependencyConflictB) -> str:
            return "ok"

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        schema = skills.get_tools()[0]["function"]["parameters"]
        wrapper_a = schema["properties"]["a"]["properties"]["wrapper"]["$ref"]
        wrapper_b = schema["properties"]["b"]["properties"]["wrapper"]["$ref"]
        self.assertNotEqual(wrapper_a, wrapper_b)
        for wrapper_ref, leaf_field in ((wrapper_a, "name"), (wrapper_b, "sku")):
            wrapper = schema["$defs"][wrapper_ref.removeprefix("#/$defs/")]
            leaf_ref = wrapper["properties"]["leaf"]["$ref"]
            leaf = schema["$defs"][leaf_ref.removeprefix("#/$defs/")]
            self.assertIn(leaf_field, leaf["properties"])

    async def test_tool_rejects_reserved_final_name(self) -> None:
        plugin = Plugin("skills")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        host = PluginHostFacade(skills=FakeSkillRegistry())

        @plugin.tool("read_manifest")
        async def read_manifest() -> str:
            return "shadowed"

        with self.assertRaisesRegex(ValueError, "reserved qualified tool name"):
            await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))

    async def test_tool_rejects_malformed_and_oversized_explicit_schemas(self) -> None:
        cases = [
            ({"type": "array"}, "object root"),
            ({"properties": {"x": {"enum": [{1}]}}}, "JSON-serializable"),
            ({"properties": {"x": {"$ref": "#/$defs/Missing"}}}, "dangling local ref"),
            ({"description": "x" * (65 * 1024)}, "exceed"),
        ]
        for index, (parameters, expected) in enumerate(cases):
            with self.subTest(index=index):
                plugin = Plugin(f"schema{index}")
                hook_bus = PluginHookBus()
                adapter = FakeAdapter()
                host = PluginHostFacade(skills=FakeSkillRegistry())

                @plugin.tool("bad", parameters=parameters)
                async def bad() -> str:
                    return "bad"

                with self.assertRaisesRegex(ValueError, expected):
                    await plugin.on_load(
                        self.make_context(plugin, hook_bus, adapter, host=host)
                    )

    async def test_tool_caps_output_and_hides_exception_details(self) -> None:
        plugin = Plugin("bounded")
        hook_bus = PluginHookBus()
        adapter = FakeAdapter()
        skills = FakeSkillRegistry()
        host = PluginHostFacade(skills=skills)

        @plugin.tool("large")
        async def large() -> str:
            return "x" * 20000

        @plugin.tool("failure")
        async def failure() -> str:
            raise RuntimeError("api-key=super-secret")

        await plugin.on_load(self.make_context(plugin, hook_bus, adapter, host=host))
        output = await skills.execute("bounded__large", {})
        error = await skills.execute("bounded__failure", {})

        self.assertLessEqual(len(output), 16400)
        self.assertTrue(output.endswith("...[truncated]"))
        self.assertEqual(error, "工具执行失败 [failure]")
        self.assertNotIn("super-secret", error)


if __name__ == "__main__":
    unittest.main()
