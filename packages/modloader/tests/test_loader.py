from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from neobot_modloader.loader import FilesystemPluginLoader, LoadedPlugin, PluginLoadError
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


if __name__ == "__main__":
    unittest.main()
