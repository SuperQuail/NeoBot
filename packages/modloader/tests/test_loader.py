from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from neobot_modloader.loader import DiscoveredPlugin, FilesystemPluginLoader, LoadedPlugin, PluginLoadError
from neobot_modloader.plugin import FunctionPlugin


class FilesystemPluginLoaderTest(unittest.TestCase):
    def test_loads_file_plugin_setup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "ping.py").write_text(
                "def setup(ctx):\n"
                "    ctx.loaded = True\n",
                encoding="utf-8",
            )
            result = FilesystemPluginLoader().load_all(root)[0]
            self.assertIsInstance(result, LoadedPlugin)
            assert isinstance(result, LoadedPlugin)
            self.assertEqual(result.name, "ping")
            self.assertIsInstance(result.plugin, FunctionPlugin)

    def test_loads_package_plugin_manifest_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "hello"
            package.mkdir()
            (package / "plugin.toml").write_text(
                "name = \"hello_plugin\"\n"
                "version = \"0.2.0\"\n"
                "[config]\n"
                "reply = \"pong\"\n",
                encoding="utf-8",
            )
            (package / "__init__.py").write_text(
                "class Plugin:\n"
                "    name = 'hello_plugin'\n"
                "    version = '0.2.0'\n"
                "    async def on_load(self, ctx): pass\n"
                "    async def on_start(self): pass\n"
                "    async def on_stop(self): pass\n"
                "plugin = Plugin()\n",
                encoding="utf-8",
            )
            result = FilesystemPluginLoader().load_all(root)[0]
            self.assertIsInstance(result, LoadedPlugin)
            assert isinstance(result, LoadedPlugin)
            self.assertEqual(result.name, "hello_plugin")
            self.assertEqual(result.version, "0.2.0")
            self.assertEqual(result.config, {"reply": "pong"})

    def test_loads_manifest_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "meta"
            package.mkdir()
            (package / "plugin.toml").write_text(
                "name = \"meta\"\n"
                "version = \"1.2.3\"\n"
                "description = \"Metadata plugin\"\n"
                "author = \"NeoBot\"\n"
                "priority = 5\n"
                "min_neobot_version = \"1.0.0\"\n",
                encoding="utf-8",
            )
            (package / "__init__.py").write_text("def setup(ctx): pass\n", encoding="utf-8")

            result = FilesystemPluginLoader().load_all(root)[0]

            self.assertIsInstance(result, LoadedPlugin)
            assert isinstance(result, LoadedPlugin)
            self.assertEqual(result.description, "Metadata plugin")
            self.assertEqual(result.author, "NeoBot")
            self.assertEqual(result.priority, 5)
            self.assertEqual(result.min_neobot_version, "1.0.0")

    def test_reads_python_dependencies_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "deps"
            package.mkdir()
            (package / "plugin.toml").write_text(
                "name = \"deps\"\npython_dependencies = [\"requests>=2\"]\n",
                encoding="utf-8",
            )
            (package / "__init__.py").write_text("def setup(ctx): pass\n", encoding="utf-8")

            result = FilesystemPluginLoader().load_all(root)[0]

            self.assertIsInstance(result, LoadedPlugin)
            assert isinstance(result, LoadedPlugin)
            self.assertEqual(result.python_dependencies, ("requests>=2",))

    def test_discover_all_reads_metadata_without_importing_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "discover"
            package.mkdir()
            (package / "plugin.toml").write_text(
                "name = \"discover\"\ndescription = \"d\"\npython_dependencies = [\"package-that-should-not-exist-xyz\"]\n",
                encoding="utf-8",
            )
            (package / "__init__.py").write_text("raise RuntimeError('should not import')\n", encoding="utf-8")

            result = FilesystemPluginLoader().discover_all(root)[0]

            self.assertIsInstance(result, DiscoveredPlugin)
            assert isinstance(result, DiscoveredPlugin)
            self.assertEqual(result.name, "discover")
            self.assertEqual(result.description, "d")
            self.assertEqual(result.missing_python_dependencies, ("package-that-should-not-exist-xyz",))

    def test_package_plugin_supports_relative_imports(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "relative"
            package.mkdir()
            (package / "helper.py").write_text("VALUE = 'pong'\n", encoding="utf-8")
            (package / "__init__.py").write_text(
                "from .helper import VALUE\n"
                "def setup(ctx):\n"
                "    ctx.value = VALUE\n",
                encoding="utf-8",
            )
            result = FilesystemPluginLoader().load_all(root)[0]
            self.assertIsInstance(result, LoadedPlugin)

    def test_supports_create_plugin_and_skips_private_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "_hidden.py").write_text("raise RuntimeError('should not load')", encoding="utf-8")
            (root / "factory.py").write_text(
                "class Plugin:\n"
                "    name = 'factory'\n"
                "    version = '0.1.0'\n"
                "    async def on_load(self, ctx): pass\n"
                "    async def on_start(self): pass\n"
                "    async def on_stop(self): pass\n"
                "def create_plugin():\n"
                "    return Plugin()\n",
                encoding="utf-8",
            )
            results = FilesystemPluginLoader().load_all(root)
            self.assertEqual(len(results), 1)
            self.assertIsInstance(results[0], LoadedPlugin)

    def test_bad_plugin_returns_error_without_stopping_scan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "bad.py").write_text("raise RuntimeError('bad')", encoding="utf-8")
            (root / "good.py").write_text("def setup(ctx): pass\n", encoding="utf-8")
            results = FilesystemPluginLoader().load_all(root)
            self.assertEqual(len(results), 2)
            self.assertTrue(any(isinstance(result, PluginLoadError) for result in results))
            self.assertTrue(any(isinstance(result, LoadedPlugin) for result in results))

    def test_rejects_unsafe_manifest_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "unsafe"
            package.mkdir()
            (package / "plugin.toml").write_text("name = \"../escape\"\n", encoding="utf-8")
            (package / "__init__.py").write_text("def setup(ctx): pass\n", encoding="utf-8")
            result = FilesystemPluginLoader().load_all(root)[0]
            self.assertIsInstance(result, PluginLoadError)

    def test_rejects_manifest_name_with_colon_or_space(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for dirname, plugin_name in (("colon", "bad:name"), ("space", "bad name")):
                package = root / dirname
                package.mkdir()
                (package / "plugin.toml").write_text(f"name = {plugin_name!r}\n", encoding="utf-8")
                (package / "__init__.py").write_text("def setup(ctx): pass\n", encoding="utf-8")

            results = FilesystemPluginLoader().load_all(root)

            self.assertEqual(len(results), 2)
            self.assertTrue(all(isinstance(result, PluginLoadError) for result in results))

    def test_disabled_package_plugin_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "disabled"
            package.mkdir()
            (package / "plugin.toml").write_text("enabled = false\n", encoding="utf-8")
            (package / "__init__.py").write_text("raise RuntimeError('should not load')\n", encoding="utf-8")

            self.assertEqual(FilesystemPluginLoader().load_all(root), [])

    def test_dependencies_are_loaded_before_dependants(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, manifest in (
                ("app", "name = \"app\"\npriority = 100\ndependencies = [\"base\"]\n"),
                ("base", "name = \"base\"\npriority = 0\n"),
            ):
                package = root / name
                package.mkdir()
                (package / "plugin.toml").write_text(manifest, encoding="utf-8")
                (package / "__init__.py").write_text("def setup(ctx): pass\n", encoding="utf-8")

            results = FilesystemPluginLoader().load_all(root)

            self.assertEqual([result.name for result in results if isinstance(result, LoadedPlugin)], ["base", "app"])

    def test_independent_plugins_are_ordered_by_priority_then_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, priority in (("low", 0), ("high_b", 10), ("high_a", 10)):
                package = root / name
                package.mkdir()
                (package / "plugin.toml").write_text(f"name = \"{name}\"\npriority = {priority}\n", encoding="utf-8")
                (package / "__init__.py").write_text("def setup(ctx): pass\n", encoding="utf-8")

            results = FilesystemPluginLoader().load_all(root)

            self.assertEqual(
                [result.name for result in results if isinstance(result, LoadedPlugin)],
                ["high_a", "high_b", "low"],
            )

    def test_duplicate_plugin_names_return_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for dirname in ("first", "second"):
                package = root / dirname
                package.mkdir()
                (package / "plugin.toml").write_text("name = \"same\"\n", encoding="utf-8")
                (package / "__init__.py").write_text("def setup(ctx): pass\n", encoding="utf-8")

            results = FilesystemPluginLoader().load_all(root)

            self.assertEqual(sum(isinstance(result, LoadedPlugin) for result in results), 1)
            self.assertEqual(sum(isinstance(result, PluginLoadError) for result in results), 1)

    def test_rejects_invalid_manifest_field_types(self) -> None:
        cases = {
            "bad_enabled": "enabled = \"yes\"\n",
            "bad_priority": "priority = \"high\"\n",
            "bad_dependencies": "dependencies = \"base\"\n",
            "bad_dependency_name": "dependencies = [\"bad:name\"]\n",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for dirname, manifest in cases.items():
                package = root / dirname
                package.mkdir()
                (package / "plugin.toml").write_text(manifest, encoding="utf-8")
                (package / "__init__.py").write_text("def setup(ctx): pass\n", encoding="utf-8")

            results = FilesystemPluginLoader().load_all(root)

            self.assertEqual(len(results), len(cases))
            self.assertTrue(all(isinstance(result, PluginLoadError) for result in results))

    def test_missing_dependency_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "app"
            package.mkdir()
            (package / "plugin.toml").write_text("dependencies = [\"missing\"]\n", encoding="utf-8")
            (package / "__init__.py").write_text("def setup(ctx): pass\n", encoding="utf-8")

            result = FilesystemPluginLoader().load_all(root)[0]

            self.assertIsInstance(result, PluginLoadError)

    def test_cyclic_dependency_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, dependency in (("a", "b"), ("b", "a")):
                package = root / name
                package.mkdir()
                (package / "plugin.toml").write_text(f"name = \"{name}\"\ndependencies = [\"{dependency}\"]\n", encoding="utf-8")
                (package / "__init__.py").write_text("def setup(ctx): pass\n", encoding="utf-8")

            results = FilesystemPluginLoader().load_all(root)

            self.assertTrue(any(isinstance(result, PluginLoadError) for result in results))


if __name__ == "__main__":
    unittest.main()
