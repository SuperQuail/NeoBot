from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.loader import FilesystemPluginLoader, LoadedPlugin
from neobot_modloader.plugin import Plugin


class FakeLogger:
    def info(self, *args: Any, **kwargs: Any) -> None:
        pass

    def warning(self, *args: Any, **kwargs: Any) -> None:
        pass

    def debug(self, *args: Any, **kwargs: Any) -> None:
        pass

    def error(self, *args: Any, **kwargs: Any) -> None:
        pass

    def exception(self, *args: Any, **kwargs: Any) -> None:
        pass


class DispatchCtx:
    def __init__(self, raw_event: dict[str, Any]) -> None:
        self.raw_event = raw_event
        self.consumed = False
        self.skip_ai_reply = False

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True


class DashboardCompatTest(unittest.IsolatedAsyncioTestCase):
    def dashboard_path(self) -> Path:
        root = Path(__file__).resolve().parents[3]
        path = root / "plugins" / "NeoBot_Dashboard"
        if not path.exists():
            self.skipTest(f"Dashboard plugin not present: {path}")
        return path

    def test_loader_accepts_dashboard_new_plugin_entrypoint(self) -> None:
        result = FilesystemPluginLoader().load_one(self.dashboard_path())

        self.assertIsInstance(result, LoadedPlugin)
        assert isinstance(result, LoadedPlugin)
        self.assertEqual(result.name, "dashboard")
        self.assertEqual(result.version, "0.9.1")
        self.assertIsInstance(result.plugin, Plugin)

    async def test_dashboard_on_load_accepts_new_runtime_context(self) -> None:
        result = FilesystemPluginLoader().load_one(self.dashboard_path())
        self.assertIsInstance(result, LoadedPlugin)
        assert isinstance(result, LoadedPlugin)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            hook_bus = PluginHookBus()
            ctx = RuntimePluginContext(
                plugin_name=result.name,
                plugin_dir=self.dashboard_path(),
                data_dir=root / "data",
                config={"manage_plugins": False},
                logger=FakeLogger(),
                adapter=object(),
                hook_bus=hook_bus,
                record_subscription=lambda _subscription: None,
                plugin_control=object(),
            )

            await result.plugin.on_load(ctx)
            try:
                await hook_bus.dispatch(
                    DispatchCtx(
                        {
                            "post_type": "message",
                            "message_type": "private",
                            "user_id": 1,
                            "raw_message": "hello",
                            "sender": {"nickname": "tester"},
                        }
                    )
                )
            finally:
                await result.plugin.on_stop()


if __name__ == "__main__":
    unittest.main()
