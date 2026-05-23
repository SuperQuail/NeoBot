from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from neobot_modloader.host import PluginHostFacade
from neobot_modloader.runtime import PluginRuntime


class FakeLogger:
    def info(self, *args: Any, **kwargs: Any) -> None:
        pass

    def error(self, *args: Any, **kwargs: Any) -> None:
        pass

    def exception(self, *args: Any, **kwargs: Any) -> None:
        pass


class FakeLoggerFactory:
    def get_logger(self, name: str) -> Any:
        return FakeLogger()


class PluginRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_plugin_host_registrations_are_cleaned_on_stop(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir()
            (plugin_dir / "registrar.py").write_text(
                "def setup(ctx):\n"
                "    ctx.plugin_host.commands.register('registrar.cmd', 'cmd', lambda: 'ok')\n"
                "    ctx.plugin_host.queries.register('registrar.query', 'query', lambda: 'q')\n"
                "    ctx.plugin_host.capabilities.register('registrar.cap', 'cap', lambda: 'c')\n"
                "    ctx.plugin_host.lifecycle.subscribe('config.changed', lambda stage: None)\n",
                encoding="utf-8",
            )
            host = PluginHostFacade()
            runtime = PluginRuntime(
                plugin_dir=plugin_dir,
                data_dir=root / "data",
                adapter=object(),
                logger_factory=FakeLoggerFactory(),
                host=host,
            )

            runtime.load_all()
            await runtime.load_registered()
            await runtime.start_all()

            self.assertIn("registrar.cmd", host.commands.names())
            self.assertIn("registrar.query", host.queries.names())
            self.assertIn("registrar.cap", host.capabilities.names())

            await runtime.stop_all()

            self.assertNotIn("registrar.cmd", host.commands.names())
            self.assertNotIn("registrar.query", host.queries.names())
            self.assertNotIn("registrar.cap", host.capabilities.names())


if __name__ == "__main__":
    unittest.main()
