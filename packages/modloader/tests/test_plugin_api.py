from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.message import ImageSegment
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


class Config(BaseModel):
    reply: str = "pong"


class PluginApiTest(unittest.IsolatedAsyncioTestCase):
    def make_context(self, plugin: Plugin, hook_bus: PluginHookBus, adapter: FakeAdapter, config: dict[str, Any] | None = None) -> RuntimePluginContext:
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


if __name__ == "__main__":
    unittest.main()
