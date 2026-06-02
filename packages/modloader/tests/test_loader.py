from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from neobot_modloader.loader import DiscoveredPlugin, FilesystemPluginLoader, LoadedPlugin, PluginLoadError
from neobot_modloader.plugin import Plugin


PLUGIN_SOURCE = "from neobot_modloader import Plugin\nplugin = Plugin({name!r}, version={version!r})\n"


class FilesystemPluginLoaderTest(unittest.TestCase):
    def test_loads_file_plugin_object(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "ping.py").write_text(PLUGIN_SOURCE.format(name="ping", version="1.0.0"), encoding="utf-8")

            result = FilesystemPluginLoader().load_all(root)[0]

            self.assertIsInstance(result, LoadedPlugin)
            assert isinstance(result, LoadedPlugin)
            self.assertEqual(result.name, "ping")
            self.assertEqual(result.version, "1.0.0")
            self.assertIsInstance(result.plugin, Plugin)

    def test_rejects_setup_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "legacy.py").write_text("def setup(ctx): pass\n", encoding="utf-8")

            result = FilesystemPluginLoader().load_all(root)[0]

            self.assertIsInstance(result, PluginLoadError)

    def test_rejects_old_object_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "legacy_obj.py").write_text(
                "class Old:\n"
                "    name = 'old'\n"
                "    version = '1'\n"
                "    async def on_load(self, ctx): pass\n"
                "    async def on_start(self): pass\n"
                "    async def on_stop(self): pass\n"
                "plugin = Old()\n",
                encoding="utf-8",
            )

            result = FilesystemPluginLoader().load_all(root)[0]

            self.assertIsInstance(result, PluginLoadError)

    def test_loads_package_manifest_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "hello"
            package.mkdir()
            (package / "plugin.toml").write_text(
                "name = \"hello\"\n"
                "version = \"0.2.0\"\n"
                "priority = 5\n"
                "[config]\n"
                "reply = \"pong\"\n",
                encoding="utf-8",
            )
            (package / "__init__.py").write_text(PLUGIN_SOURCE.format(name="hello", version="0.2.0"), encoding="utf-8")

            result = FilesystemPluginLoader().load_all(root)[0]

            self.assertIsInstance(result, LoadedPlugin)
            assert isinstance(result, LoadedPlugin)
            self.assertEqual(result.name, "hello")
            self.assertEqual(result.config, {"reply": "pong"})
            self.assertEqual(result.priority, 5)

    def test_manifest_name_conflict_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "bad"
            package.mkdir()
            (package / "plugin.toml").write_text("name = \"manifest\"\n", encoding="utf-8")
            (package / "__init__.py").write_text(PLUGIN_SOURCE.format(name="code", version="0.1.0"), encoding="utf-8")

            result = FilesystemPluginLoader().load_all(root)[0]

            self.assertIsInstance(result, PluginLoadError)

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
                ("app", "name = \"app\"\nversion = \"0.1.0\"\npriority = 100\ndependencies = [\"base\"]\n"),
                ("base", "name = \"base\"\nversion = \"0.1.0\"\npriority = 0\n"),
            ):
                package = root / name
                package.mkdir()
                (package / "plugin.toml").write_text(manifest, encoding="utf-8")
                (package / "__init__.py").write_text(PLUGIN_SOURCE.format(name=name, version="0.1.0"), encoding="utf-8")

            results = FilesystemPluginLoader().load_all(root)

            self.assertEqual([result.name for result in results if isinstance(result, LoadedPlugin)], ["base", "app"])

    def test_duplicate_plugin_names_return_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for dirname in ("first", "second"):
                package = root / dirname
                package.mkdir()
                (package / "__init__.py").write_text(PLUGIN_SOURCE.format(name="same", version="0.1.0"), encoding="utf-8")

            results = FilesystemPluginLoader().load_all(root)

            self.assertEqual(sum(isinstance(result, LoadedPlugin) for result in results), 1)
            self.assertEqual(sum(isinstance(result, PluginLoadError) for result in results), 1)


if __name__ == "__main__":
    unittest.main()
