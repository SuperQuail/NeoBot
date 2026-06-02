from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from neobot_chat import Workflow
from pydantic import BaseModel

from neobot_modloader.agent import AgentRequest
from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.message import ImageSegment, MessageChain
from neobot_modloader.plugin import Plugin
from neobot_modloader.reply import Reply


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


class Config(BaseModel):
    reply: str = "pong"


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


if __name__ == "__main__":
    unittest.main()
