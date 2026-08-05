from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from neobot_contracts.models import ConversationRef
from neobot_modloader.context import MarkdownSkillRegistrar, RuntimePluginContext


class FakeAgent:
    description = "Echo agent"
    tool_definitions: list[dict[str, Any]] = []

    async def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"messages": [{"role": "assistant", "content": "ok"}]}

    async def stream_invoke(self, state: dict[str, Any]):
        if False:
            yield state

    async def close(self) -> None:
        pass


class FakeRegistry:
    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}

    def register(self, name: str, agent: Any) -> None:
        self.agents[name] = agent

    def unregister(self, name: str) -> Any | None:
        return self.agents.pop(name, None)

    @property
    def names(self) -> list[str]:
        return list(self.agents)


class DrainableFakeRegistry(FakeRegistry):
    """带 unregister_and_drain 的底层注册表，用于验证插件侧 registrar 的代理行为。"""

    def __init__(self) -> None:
        super().__init__()
        self.drained: list[str] = []

    async def unregister_and_drain(
        self, name: str, *, drain_timeout_seconds: float | None = None
    ) -> Any | None:
        self.drained.append(name)
        return self.agents.pop(name, None)


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, Any]] = []

    async def send_private_msg(self, user_id: int, message: Any) -> str:
        self.calls.append(("private", user_id, message))
        return "private-ok"

    async def send_group_msg(self, group_id: int, message: Any) -> str:
        self.calls.append(("group", group_id, message))
        return "group-ok"

    async def send(self, conversation: ConversationRef, message: Any) -> str:
        self.calls.append(("send", conversation, message))
        return "send-ok"


class RuntimePluginContextTest(unittest.IsolatedAsyncioTestCase):
    def make_context(
        self,
        data_dir: Path,
        adapter: FakeAdapter | None = None,
        agent_registry: FakeRegistry | None = None,
        record_agent_registration: Any | None = None,
    ) -> RuntimePluginContext:
        return RuntimePluginContext(
            plugin_name="test",
            plugin_dir=data_dir,
            data_dir=data_dir / "data",
            config={"reply": "pong"},
            logger=None,
            adapter=adapter or FakeAdapter(),
            hook_bus=object(),
            record_subscription=lambda _subscription: None,
            agent_registry=agent_registry,
            record_agent_registration=record_agent_registration,
        )

    async def test_send_methods_delegate_to_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            adapter = FakeAdapter()
            ctx = self.make_context(Path(temp), adapter)
            await ctx.send_private(10001, "hello")
            await ctx.send_group(123, "hello")
            await ctx.send(ConversationRef(kind="group", id="456"), "hi")
            self.assertEqual(adapter.calls[0], ("private", 10001, "hello"))
            self.assertEqual(adapter.calls[1], ("group", 123, "hello"))
            self.assertEqual(adapter.calls[2][0], "send")

    async def test_reply_uses_conversation_from_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            adapter = FakeAdapter()
            ctx = self.make_context(Path(temp), adapter)
            await ctx.reply({"message_type": "group", "group_id": 123}, "pong")
            self.assertEqual(adapter.calls, [("send", ConversationRef(kind="group", id="123"), "pong")])

    def test_conversation_from_event_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ctx = self.make_context(Path(temp))
            self.assertTrue(ctx.data_dir.exists())
            self.assertEqual(ctx.config["reply"], "pong")
            self.assertEqual(
                ctx.conversation_from_event({"message_type": "private", "user_id": 1}),
                ConversationRef(kind="private", id="1"),
            )
            with self.assertRaises(ValueError):
                ctx.conversation_from_event({})

    def test_agent_registrar_registers_exposed_agent_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            registry = FakeRegistry()
            recorded: list[tuple[str, Any]] = []
            ctx = self.make_context(
                Path(temp),
                agent_registry=registry,
                record_agent_registration=lambda name, agent: recorded.append((name, agent)),
            )

            registered_name = ctx.agents.register("echo", FakeAgent())

            self.assertEqual(registered_name, "test.echo")
            self.assertIn(registered_name, registry.agents)
            self.assertEqual(len(recorded), 1)
            self.assertEqual(ctx.agents.snapshot(), [{"name": registered_name, "description": "Echo agent"}])

    def test_agent_registrar_handles_method_style_names(self) -> None:
        class MethodStyleRegistry(FakeRegistry):
            # 鸭子类型注册表把 names 写成方法而非属性时也必须能查重
            def names(self) -> list[str]:
                return list(self.agents)

        with tempfile.TemporaryDirectory() as temp:
            registry = MethodStyleRegistry()
            ctx = self.make_context(Path(temp), agent_registry=registry)

            registered_name = ctx.agents.register("echo", FakeAgent())

            self.assertEqual(registered_name, "test.echo")
            # 与真实注册表已存在的同名 Agent 冲突必须被检测到
            with self.assertRaises(ValueError):
                ctx.agents.register("echo", FakeAgent())

    async def test_agent_registrar_unregister_and_drain_delegates_to_registry(self) -> None:
        """PluginAgentRegistrar 必须暴露 unregister_and_drain 并代理到底层排空注册表。"""
        with tempfile.TemporaryDirectory() as temp:
            registry = DrainableFakeRegistry()
            ctx = self.make_context(Path(temp), agent_registry=registry)

            registered_name = ctx.agents.register("echo", FakeAgent())

            removed = await ctx.agents.unregister_and_drain(registered_name)

            self.assertEqual(registry.drained, [registered_name])
            self.assertNotIn(registered_name, registry.agents)
            self.assertNotIn(registered_name, ctx.agents._registered)
            self.assertIsNotNone(removed)

    async def test_agent_registrar_unregister_and_drain_falls_back_to_unregister(self) -> None:
        """底层注册表无 unregister_and_drain 时，回退到 unregister 逻辑（卸载仍生效）。"""
        with tempfile.TemporaryDirectory() as temp:
            registry = FakeRegistry()
            ctx = self.make_context(Path(temp), agent_registry=registry)

            registered_name = ctx.agents.register("echo", FakeAgent())

            removed = await ctx.agents.unregister_and_drain(registered_name)

            self.assertNotIn(registered_name, registry.agents)
            self.assertNotIn(registered_name, ctx.agents._registered)
            self.assertIsNotNone(removed)

    def test_markdown_skill_registrar_failure_leaves_clean_state(self) -> None:
        class FailingRegistry:
            def register_many(self, owner: str, skills: list[Any]) -> None:
                raise ValueError("conflict")

            def unregister_owner(self, owner: str) -> list[str]:
                return []

        cleanups: list[Any] = []
        registrar = MarkdownSkillRegistrar(
            plugin_name="p", registry=FailingRegistry(), record_cleanup=cleanups.append
        )
        self.assertTrue(registrar.available)

        with self.assertRaises(ValueError):
            registrar.register([object()])

        # 注册失败不置 _registered、不记录清理；unregister_all 幂等
        self.assertFalse(registrar._registered)
        self.assertEqual(cleanups, [])
        registrar.unregister_all()
        registrar.unregister_all()
        self.assertFalse(registrar._registered)

    def test_markdown_skill_registrar_unavailable(self) -> None:
        registrar = MarkdownSkillRegistrar(plugin_name="p", registry=None, record_cleanup=None)
        self.assertFalse(registrar.available)
        registrar.unregister_all()  # 幂等、不抛错
        with self.assertRaises(RuntimeError):
            registrar.register([object()])

    def test_markdown_skill_unregister_failure_is_retryable(self) -> None:
        class RetryRegistry:
            def __init__(self) -> None:
                self.calls = 0

            def register_many(self, owner: str, skills: list[Any]) -> None:
                pass

            def unregister_owner(self, owner: str) -> list[str]:
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("busy")
                return [owner]

        registry = RetryRegistry()
        registrar = MarkdownSkillRegistrar(plugin_name="p", registry=registry, record_cleanup=None)
        registrar.register([object()])

        with self.assertRaises(RuntimeError):
            registrar.unregister_all()
        self.assertTrue(registrar._registered)

        registrar.unregister_all()
        self.assertFalse(registrar._registered)
        self.assertEqual(registry.calls, 2)


if __name__ == "__main__":
    unittest.main()
