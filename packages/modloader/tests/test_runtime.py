from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from neobot_modloader.host import PluginHostFacade
from neobot_modloader.loader import DiscoveredPlugin
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
    async def test_discover_all_returns_plugin_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir()
            package = plugin_dir / "meta"
            package.mkdir()
            (package / "plugin.toml").write_text(
                "name = \"meta\"\ndescription = \"Meta\"\npython_dependencies = [\"package-that-should-not-exist-xyz\"]\n",
                encoding="utf-8",
            )
            (package / "__init__.py").write_text("raise RuntimeError('should not import')\n", encoding="utf-8")
            runtime = PluginRuntime(
                plugin_dir=plugin_dir,
                data_dir=root / "data",
                adapter=object(),
                logger_factory=FakeLoggerFactory(),
            )

            result = runtime.discover_all()[0]

            self.assertIsInstance(result, DiscoveredPlugin)
            assert isinstance(result, DiscoveredPlugin)
            self.assertEqual(result.name, "meta")
            self.assertEqual(result.description, "Meta")

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

    async def test_reload_plugin_reimports_updated_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir()
            plugin_file = plugin_dir / "hot.py"
            plugin_file.write_text(
                "class Plugin:\n"
                "    name = 'hot'\n"
                "    version = '1'\n"
                "    async def on_load(self, ctx): self.ctx = ctx\n"
                "    async def on_start(self): pass\n"
                "    async def on_stop(self): pass\n"
                "plugin = Plugin()\n",
                encoding="utf-8",
            )
            runtime = PluginRuntime(
                plugin_dir=plugin_dir,
                data_dir=root / "data",
                adapter=object(),
                logger_factory=FakeLoggerFactory(),
            )
            runtime.load_all()
            await runtime.load_registered()
            await runtime.start_all()
            self.assertEqual(runtime.manager.get_plugin("hot").version, "1")

            plugin_file.write_text(
                "class Plugin:\n"
                "    name = 'hot'\n"
                "    version = '2'\n"
                "    async def on_load(self, ctx): self.ctx = ctx\n"
                "    async def on_start(self): pass\n"
                "    async def on_stop(self): pass\n"
                "plugin = Plugin()\n",
                encoding="utf-8",
            )

            self.assertTrue(await runtime.reload_plugin("hot"))

            self.assertEqual(runtime.manager.get_plugin("hot").version, "2")

    async def test_load_all_prompts_for_missing_python_dependencies_when_enabled(self) -> None:
        class FakeInstaller:
            def __init__(self) -> None:
                self.requirements: list[str] = []

            def confirm_and_install(self, requirements: list[str]) -> object:
                self.requirements.extend(requirements)
                return object()

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir()
            package = plugin_dir / "dep"
            package.mkdir()
            (package / "plugin.toml").write_text(
                "name = \"dep\"\npython_dependencies = [\"package-that-should-not-exist-xyz\"]\n",
                encoding="utf-8",
            )
            (package / "__init__.py").write_text("def setup(ctx): pass\n", encoding="utf-8")
            installer = FakeInstaller()
            runtime = PluginRuntime(
                plugin_dir=plugin_dir,
                data_dir=root / "data",
                adapter=object(),
                logger_factory=FakeLoggerFactory(),
                dependency_installer=installer,
            )

            runtime.load_all(auto_install_dependencies=True)

            self.assertEqual(installer.requirements, ["package-that-should-not-exist-xyz"])


if __name__ == "__main__":
    unittest.main()
