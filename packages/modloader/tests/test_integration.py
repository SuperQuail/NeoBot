from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.runtime import PluginRuntime


class FakeLogger:
    def info(self, *args: Any, **kwargs: Any) -> None:
        pass

    def error(self, *args: Any, **kwargs: Any) -> None:
        pass

    def exception(self, *args: Any, **kwargs: Any) -> None:
        pass

    def warning(self, *args: Any, **kwargs: Any) -> None:
        pass


class FakeLoggerFactory:
    def get_logger(self, name: str) -> Any:
        return FakeLogger()


class DispatchCtx:
    def __init__(self, raw_event: dict[str, Any]) -> None:
        self.raw_event = raw_event
        self.consumed = False
        self.skip_ai_reply = False

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True


class IntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.plugin_dir = Path(self.tmp.name) / "plugins"
        self.data_dir = Path(self.tmp.name) / "data"
        self.plugin_dir.mkdir()
        self.data_dir.mkdir()

        self.mock_adapter = AsyncMock()
        self.hook_bus = PluginHookBus()
        self.runtime = PluginRuntime(
            plugin_dir=self.plugin_dir,
            data_dir=self.data_dir,
            adapter=self.mock_adapter,
            logger_factory=FakeLoggerFactory(),
            hook_bus=self.hook_bus,
        )

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    def _write_pkg(self, name: str, init_py: str, manifest: str | None = None) -> None:
        package = self.plugin_dir / name
        package.mkdir()
        if manifest is not None:
            (package / "plugin.toml").write_text(manifest, encoding="utf-8")
        (package / "__init__.py").write_text(init_py, encoding="utf-8")

    async def _dispatch(self, raw_event: dict[str, Any]) -> DispatchCtx:
        ctx = DispatchCtx(raw_event)
        await self.hook_bus.dispatch(ctx)
        return ctx

    async def test_e2e_command_with_image_segment(self) -> None:
        self._write_pkg(
            "vision",
            textwrap.dedent(
                """\
                from neobot_modloader import ImageSegment, Plugin, Reply

                plugin = Plugin("vision")

                @plugin.command("识图 <img:image>")
                async def vision(img: ImageSegment, reply: Reply):
                    await reply.send(img)
                """
            ),
        )

        self.runtime.load_all()
        await self.runtime.load_registered()
        await self.runtime.start_all()

        await self._dispatch(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 12345,
                "message": [
                    {"type": "text", "data": {"text": "/识图"}},
                    {"type": "image", "data": {"url": "https://example/image.png"}},
                ],
            }
        )

        self.mock_adapter.send.assert_called_once()
        self.assertEqual(self.mock_adapter.send.call_args.args[1], [{"type": "image", "data": {"url": "https://example/image.png"}}])

    async def test_e2e_config_injection(self) -> None:
        self._write_pkg(
            "ping",
            textwrap.dedent(
                """\
                from pydantic import BaseModel
                from neobot_modloader import Plugin, Reply

                class Config(BaseModel):
                    reply: str

                plugin = Plugin("ping", version="1.0.0", config=Config)

                @plugin.command("ping")
                async def ping(reply: Reply, config: Config):
                    await reply.send(config.reply)
                """
            ),
            manifest='name = "ping"\nversion = "1.0.0"\n[config]\nreply = "pong"\n',
        )

        self.runtime.load_all()
        await self.runtime.load_registered()
        await self.runtime.start_all()
        await self._dispatch({"post_type": "message", "message_type": "private", "user_id": 1, "raw_message": "/ping"})

        self.assertEqual(self.mock_adapter.send.call_args.args[1], "pong")


if __name__ == "__main__":
    unittest.main()
