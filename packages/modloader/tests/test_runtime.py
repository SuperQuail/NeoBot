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

    def warning(self, *args: Any, **kwargs: Any) -> None:
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
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('registrar')\n"
                "@plugin.on_load\n"
                "async def load(host):\n"
                "    host.commands.register('registrar.cmd', 'cmd', lambda: 'ok')\n"
                "    host.queries.register('registrar.query', 'query', lambda: 'q')\n"
                "    host.capabilities.register('registrar.cap', 'cap', lambda: 'c')\n"
                "    host.lifecycle.subscribe('config.changed', lambda stage: None)\n",
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
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('hot', version='1')\n",
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
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('hot', version='2')\n",
                encoding="utf-8",
            )

            self.assertTrue(await runtime.reload_plugin("hot"))

            self.assertEqual(runtime.manager.get_plugin("hot").version, "2")

    async def test_reload_plugin_still_raises_key_error_for_missing_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir()
            runtime = PluginRuntime(
                plugin_dir=plugin_dir,
                data_dir=root / "data",
                adapter=object(),
                logger_factory=FakeLoggerFactory(),
            )

            with self.assertRaises(KeyError):
                await runtime.reload_plugin("missing")

    async def test_load_path_loads_and_starts_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir()
            plugin_file = plugin_dir / "hot.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('hot', version='1')\n",
                encoding="utf-8",
            )
            runtime = PluginRuntime(
                plugin_dir=plugin_dir,
                data_dir=root / "data",
                adapter=object(),
                logger_factory=FakeLoggerFactory(),
            )

            result = await runtime.control.load_path(plugin_file)

            self.assertTrue(result.ok)
            self.assertEqual(result.name, "hot")
            self.assertEqual(result.state, "running")
            self.assertEqual(runtime.manager.get_plugin("hot").version, "1")

    async def test_unload_cleans_host_registrations_and_runtime_tracking(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir()
            plugin_file = plugin_dir / "registrar.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('registrar')\n"
                "@plugin.on_load\n"
                "async def load(host):\n"
                "    host.commands.register('registrar.cmd', 'cmd', lambda: 'ok')\n",
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

            load_result = await runtime.control.load_path(plugin_file)
            self.assertTrue(load_result.ok)
            self.assertIn("registrar.cmd", host.commands.names())

            unload_result = await runtime.control.unload("registrar")

            self.assertTrue(unload_result.ok)
            self.assertEqual(unload_result.state, "unloaded")
            self.assertNotIn("registrar.cmd", host.commands.names())
            self.assertNotIn("registrar", runtime._loaded_paths)
            self.assertNotIn("registrar", runtime._loaded_modules)

    async def test_snapshot_reports_disabled_and_missing_dependency_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir()
            disabled_prefix = plugin_dir / "_off"
            disabled_prefix.mkdir()
            (disabled_prefix / "plugin.toml").write_text("name = \"off\"\nversion = \"1\"\n", encoding="utf-8")
            (disabled_prefix / "__init__.py").write_text("from neobot_modloader import Plugin\nplugin = Plugin('off')\n", encoding="utf-8")
            disabled_manifest = plugin_dir / "manifest_off"
            disabled_manifest.mkdir()
            (disabled_manifest / "plugin.toml").write_text("name = \"manifest_off\"\nenabled = false\n", encoding="utf-8")
            (disabled_manifest / "__init__.py").write_text("raise RuntimeError('should not import')\n", encoding="utf-8")
            missing_dep = plugin_dir / "dep"
            missing_dep.mkdir()
            (missing_dep / "plugin.toml").write_text(
                "name = \"dep\"\npython_dependencies = [\"package-that-should-not-exist-xyz\"]\n",
                encoding="utf-8",
            )
            (missing_dep / "__init__.py").write_text("from neobot_modloader import Plugin\nplugin = Plugin('dep')\n", encoding="utf-8")
            runtime = PluginRuntime(
                plugin_dir=plugin_dir,
                data_dir=root / "data",
                adapter=object(),
                logger_factory=FakeLoggerFactory(),
            )

            snapshots = {snapshot.name: snapshot for snapshot in runtime.control.snapshot()}

            self.assertFalse(snapshots["off"].enabled)
            self.assertEqual(snapshots["off"].state, "unloaded")
            self.assertFalse(snapshots["manifest_off"].enabled)
            self.assertEqual(snapshots["dep"].state, "error")
            self.assertEqual(snapshots["dep"].missing_python_dependencies, ("package-that-should-not-exist-xyz",))

    async def test_load_path_returns_structured_error_for_missing_dependency(self) -> None:
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
            (package / "__init__.py").write_text("from neobot_modloader import Plugin\nplugin = Plugin('dep')\n", encoding="utf-8")
            runtime = PluginRuntime(
                plugin_dir=plugin_dir,
                data_dir=root / "data",
                adapter=object(),
                logger_factory=FakeLoggerFactory(),
            )

            result = await runtime.control.load_path(package, auto_install_dependencies=False)

            self.assertFalse(result.ok)
            self.assertEqual(result.name, "dep")
            self.assertEqual(result.state, "error")
            self.assertIn("缺少 PyPI 依赖", result.error or "")

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
            (package / "__init__.py").write_text("from neobot_modloader import Plugin\nplugin = Plugin('dep')\n", encoding="utf-8")
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
