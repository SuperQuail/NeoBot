from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from neobot_contracts.models import ConversationRef
from neobot_modloader.context import PluginContext


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


class MessageModel(BaseModel):
    message_type: str
    user_id: int | None = None
    group_id: int | None = None
    raw_message: str | None = None
    message: list[dict[str, Any]] | None = None


class PluginContextTest(unittest.IsolatedAsyncioTestCase):
    def make_context(
        self,
        data_dir: Path,
        adapter: FakeAdapter | None = None,
        agent_registry: FakeRegistry | None = None,
        record_agent_registration: Any | None = None,
    ) -> PluginContext:
        return PluginContext(
            plugin_name="test",
            plugin_dir=data_dir,
            data_dir=data_dir / "data",
            config={"reply": "pong"},
            logger=None,
            adapter=adapter or FakeAdapter(),
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
            self.assertEqual(
                adapter.calls,
                [("send", ConversationRef(kind="group", id="123"), "pong")],
            )

    def test_message_text_supports_raw_model_and_segments(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ctx = self.make_context(Path(temp))
            self.assertEqual(ctx.message_text({"raw_message": "hello"}), "hello")
            self.assertEqual(
                ctx.message_text(
                    {
                        "message": [
                            {"type": "text", "data": {"text": "he"}},
                            {"type": "image", "data": {"url": "x"}},
                            {"type": "text", "data": {"text": "llo"}},
                        ]
                    }
                ),
                "hello",
            )
            model = MessageModel(message_type="private", user_id=1, raw_message="model")
            self.assertEqual(ctx.message_text(model), "model")

    def test_conversation_from_event_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ctx = self.make_context(Path(temp))
            self.assertTrue(ctx.data_dir.exists())
            self.assertEqual(ctx.require_config("reply"), "pong")
            self.assertEqual(
                ctx.conversation_from_event(MessageModel(message_type="private", user_id=1)),
                ConversationRef(kind="private", id="1"),
            )
            with self.assertRaises(KeyError):
                ctx.require_config("missing")
            with self.assertRaises(ValueError):
                ctx.conversation_from_event({})

    def test_agent_registrar_registers_namespaced_agent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            registry = FakeRegistry()
            recorded: list[tuple[str, Any]] = []
            ctx = self.make_context(
                Path(temp),
                agent_registry=registry,
                record_agent_registration=lambda name, agent: recorded.append((name, agent)),
            )
            agent = FakeAgent()

            registered_name = ctx.agents.register("echo", agent)

            self.assertEqual(registered_name, "plugin:test:echo")
            self.assertIs(registry.agents[registered_name], agent)
            self.assertEqual(recorded, [(registered_name, agent)])
            self.assertEqual(ctx.agents.names, [registered_name])
            self.assertEqual(
                ctx.agents.snapshot(),
                [{"name": registered_name, "description": "Echo agent"}],
            )
            self.assertIn("plugin:test:echo", ctx.agents.list_agents())
            self.assertEqual(
                ctx.agents.list_agents("echo"),
                "Agent plugin:test:echo: Echo agent",
            )

    def test_agent_registrar_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ctx = self.make_context(Path(temp), agent_registry=FakeRegistry())
            with self.assertRaises(ValueError):
                ctx.agents.register(" bad", FakeAgent())
            with self.assertRaises(ValueError):
                ctx.agents.register("bad:name", FakeAgent())
            with self.assertRaises(TypeError):
                ctx.agents.register("bad", object())

    def test_agent_registrar_requires_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            ctx = self.make_context(Path(temp))
            with self.assertRaises(RuntimeError):
                ctx.agents.register("echo", FakeAgent())


if __name__ == "__main__":
    unittest.main()
