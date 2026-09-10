from __future__ import annotations

import tempfile
import unittest
import asyncio
from pathlib import Path
from typing import Any

from neobot_modloader.host import PluginHostFacade
from neobot_modloader.loader import DiscoveredPlugin, LoadedPlugin
from neobot_modloader.runtime import PluginRuntime
from neobot_contracts.ports.plugin import PluginState


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


async def _hold_lock(lock: Any, started: asyncio.Event, release: asyncio.Event) -> None:
    await lock.acquire()
    started.set()
    await release.wait()
    lock.release()


async def _acquire_release(lock: Any) -> None:
    await lock.acquire()
    lock.release()


class PluginRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def make_runtime(self, root: Path, *, loader: Any | None = None) -> PluginRuntime:
        plugin_dir = root / "plugins"
        plugin_dir.mkdir()
        return PluginRuntime(
            plugin_dir=plugin_dir,
            data_dir=root / "data",
            adapter=object(),
            logger_factory=FakeLoggerFactory(),
            loader=loader,
        )

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

    async def test_concurrent_reloads_serialize_complete_generations(self) -> None:
        class LifecyclePlugin:
            name = "hot"

            def __init__(self, version: str, stop_entered: asyncio.Event | None = None, resume: asyncio.Event | None = None) -> None:
                self.version = version
                self.stop_entered = stop_entered
                self.resume = resume

            async def on_load(self, ctx: Any) -> None:
                pass

            async def on_start(self) -> None:
                pass

            async def on_stop(self) -> None:
                if self.stop_entered is not None:
                    self.stop_entered.set()
                if self.resume is not None:
                    await self.resume.wait()

        class SequenceLoader:
            def __init__(self, path: Path, plugins: list[Any]) -> None:
                self.path = path
                self.plugins = plugins
                self.calls = 0

            def load_one(self, path: Path) -> LoadedPlugin:
                plugin = self.plugins[self.calls]
                self.calls += 1
                return LoadedPlugin(plugin.name, plugin.version, plugin, path.parent, {}, source_path=path)

            def clear_module_cache(self, module_names: tuple[str, ...]) -> None:
                pass

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "plugins" / "hot.py"
            stop_entered = asyncio.Event()
            resume = asyncio.Event()
            first = LifecyclePlugin("1", stop_entered, resume)
            second = LifecyclePlugin("2")
            third = LifecyclePlugin("3")
            loader = SequenceLoader(path, [second, third])
            runtime = self.make_runtime(root, loader=loader)
            path.touch()
            runtime._register(LoadedPlugin("hot", "1", first, path.parent, {}, source_path=path))
            await runtime.manager.load_plugin("hot")
            await runtime.manager.start_plugin("hot")

            reload_one = asyncio.create_task(runtime.reload_plugin_result("hot"))
            await stop_entered.wait()
            reload_two = asyncio.create_task(runtime.reload_plugin_result("hot"))
            await asyncio.sleep(0)
            self.assertEqual(loader.calls, 1)
            resume.set()
            results = await asyncio.gather(reload_one, reload_two)

            self.assertTrue(all(result.ok for result in results))
            self.assertEqual(loader.calls, 2)
            self.assertEqual(runtime.manager.get_plugin("hot").version, "3")

    async def test_concurrent_same_path_loads_do_not_import_next_generation_early(self) -> None:
        load_entered = asyncio.Event()
        resume = asyncio.Event()

        class LifecyclePlugin:
            name = "hot"

            def __init__(self, version: str, wait: bool = False) -> None:
                self.version = version
                self.wait = wait

            async def on_load(self, ctx: Any) -> None:
                if self.wait:
                    load_entered.set()
                    await resume.wait()

            async def on_start(self) -> None:
                pass

            async def on_stop(self) -> None:
                pass

        class SequenceLoader:
            def __init__(self, plugins: list[Any]) -> None:
                self.plugins = plugins
                self.calls = 0

            def load_one(self, path: Path) -> LoadedPlugin:
                plugin = self.plugins[self.calls]
                self.calls += 1
                return LoadedPlugin(plugin.name, plugin.version, plugin, path.parent, {}, source_path=path)

            def clear_module_cache(self, module_names: tuple[str, ...]) -> None:
                pass

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            loader = SequenceLoader([LifecyclePlugin("1", wait=True), LifecyclePlugin("2")])
            runtime = self.make_runtime(root, loader=loader)
            path = runtime.plugin_dir / "hot.py"
            path.touch()

            load_one = asyncio.create_task(runtime.load_plugin_path(path))
            await load_entered.wait()
            load_two = asyncio.create_task(runtime.load_plugin_path(path))
            await asyncio.sleep(0)
            self.assertEqual(loader.calls, 1)
            resume.set()
            results = await asyncio.gather(load_one, load_two)

            self.assertTrue(all(result.ok for result in results))
            self.assertEqual(loader.calls, 2)
            self.assertEqual(runtime.manager.get_plugin("hot").version, "2")

    async def test_failed_reload_reports_running_generation_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "hot.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('hot')\n", encoding="utf-8"
            )
            loaded = await runtime.load_plugin_path(plugin_file)
            self.assertTrue(loaded.ok)
            old_modules = runtime._loaded_modules["hot"]
            plugin_file.write_text("VALUE = 1\n", encoding="utf-8")

            result = await runtime.reload_plugin_result("hot")

            self.assertFalse(result.ok)
            self.assertEqual(result.state, "running")
            self.assertIsNotNone(runtime.manager.get_plugin("hot"))
            import sys

            self.assertTrue(all(name in sys.modules for name in old_modules))

    async def test_reload_package_reimports_child_without_removing_replacement(self) -> None:
        import sys

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir()
            package = plugin_dir / "hot_package"
            package.mkdir()
            (package / "__init__.py").write_text(
                "from neobot_modloader import Plugin\n"
                "from .child import VERSION\n"
                "plugin = Plugin('hot-package', version=VERSION)\n",
                encoding="utf-8",
            )
            child = package / "child.py"
            child.write_text("VERSION = '1'\n", encoding="utf-8")
            runtime = PluginRuntime(
                plugin_dir=plugin_dir,
                data_dir=root / "data",
                adapter=object(),
                logger_factory=FakeLoggerFactory(),
            )
            result = await runtime.control.load_path(package)
            self.assertTrue(result.ok)
            old_modules = runtime._loaded_modules["hot-package"]

            child.write_text("VERSION = '2'\n", encoding="utf-8")
            self.assertTrue(await runtime.reload_plugin("hot-package"))

            new_modules = runtime._loaded_modules["hot-package"]
            self.assertEqual(runtime.manager.get_plugin("hot-package").version, "2")
            self.assertTrue(set(old_modules).isdisjoint(new_modules))
            self.assertTrue(all(name in sys.modules for name in new_modules))
            self.assertTrue(all(name not in sys.modules for name in old_modules))

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

    async def test_register_failure_clears_module_cache_for_reload(self) -> None:
        """注册失败（manager 层面同名单冲突）后，失败插件的模块必须从 sys.modules 清除。

        修复前：失败模块滞留 sys.modules，修复代码后重载时 `from .impl import`
        复用旧模块，新代码不生效；修复后重载能拿到新版本。
        """
        import sys

        from neobot_modloader.context import RuntimePluginContext
        from neobot_modloader.hooks import PluginHookBus
        from neobot_modloader.plugin import Plugin

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir()
            package = plugin_dir / "dup"
            package.mkdir()
            (package / "plugin.toml").write_text('name = "dup"\nversion = "1"\n', encoding="utf-8")
            (package / "__init__.py").write_text(
                "from neobot_modloader import Plugin\n"
                "from .impl import VERSION\n"
                "plugin = Plugin('dup', version=VERSION)\n",
                encoding="utf-8",
            )
            (package / "impl.py").write_text("VERSION = '1'\n", encoding="utf-8")
            runtime = PluginRuntime(
                plugin_dir=plugin_dir,
                data_dir=root / "data",
                adapter=object(),
                logger_factory=FakeLoggerFactory(),
            )
            # 预置同名单插件占用名字，让 load_all 的 _register 走到 except 分支
            occupier = Plugin("dup", version="0")
            occupier_ctx = RuntimePluginContext(
                plugin_name="dup",
                plugin_dir=Path("."),
                data_dir=Path("."),
                config={},
                logger=None,
                adapter=object(),
                hook_bus=PluginHookBus(),
                record_subscription=lambda _subscription: None,
            )
            runtime.manager.register(occupier, occupier_ctx)
            runtime.load_all()
            self.assertEqual(runtime.manager.names(), ["dup"])

            # 注册失败的模块已从 sys.modules 清除
            stale = [n for n in sys.modules if n.startswith("neobot_user_plugins.dup_")]
            self.assertEqual(stale, [])

            # 修复代码、释放名字后重载：新代码生效（版本 2）
            (package / "impl.py").write_text("VERSION = '2'\n", encoding="utf-8")
            (package / "plugin.toml").write_text('name = "dup"\nversion = "2"\n', encoding="utf-8")
            await runtime.manager.remove_plugin("dup")
            result = await runtime.control.load_path(package)

            self.assertTrue(result.ok)
            self.assertEqual(runtime.manager.get_plugin("dup").version, "2")

    async def test_self_unload_inside_on_load_does_not_deadlock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "suicide.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('suicide')\n"
                "@plugin.on_load\n"
                "async def load(ctx):\n"
                "    await ctx.plugin_control.unload('suicide')\n",
                encoding="utf-8",
            )
            result = await asyncio.wait_for(runtime.control.load_path(plugin_file), timeout=5)
            self.assertFalse(result.ok)
            self.assertIsNone(runtime.manager.get_record("suicide"))

    async def test_control_self_calls_inside_on_load_do_not_deadlock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "suicide.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('suicide')\n"
                "@plugin.on_load\n"
                "async def load(ctx):\n"
                "    await ctx.plugin_control.stop('suicide')\n"
                "    await ctx.plugin_control.unload('suicide')\n",
                encoding="utf-8",
            )
            result = await asyncio.wait_for(runtime.control.load_path(plugin_file), timeout=5)
            self.assertFalse(result.ok)
            self.assertIsNone(runtime.manager.get_record("suicide"))

    async def test_two_plugin_mutual_unload_does_not_deadlock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            (runtime.plugin_dir / "a.py").write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('a')\n"
                "@plugin.on_shutdown\n"
                "async def stop_a(ctx):\n"
                "    await ctx.plugin_control.unload('b')\n",
                encoding="utf-8",
            )
            (runtime.plugin_dir / "b.py").write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('b')\n"
                "@plugin.on_shutdown\n"
                "async def stop_b(ctx):\n"
                "    await ctx.plugin_control.unload('a')\n",
                encoding="utf-8",
            )
            runtime.load_all()
            await runtime.load_registered()
            await runtime.start_all()

            result = await asyncio.wait_for(runtime.unload_plugin("a"), timeout=5)

            self.assertTrue(result.ok, result)
            self.assertIsNone(runtime.manager.get_record("a"))
            self.assertIsNone(runtime.manager.get_record("b"))

    async def test_rename_then_concurrent_same_path_loads_hold_one_name_lock(self) -> None:
        import sys
        import types

        entered = asyncio.Event()
        resume = asyncio.Event()
        namespace = sys.modules.setdefault("neobot_user_plugins", types.ModuleType("neobot_user_plugins"))
        namespace.rename_events = {"entered": entered, "resume": resume}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "alpha.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('alpha')\n",
                encoding="utf-8",
            )
            first = await runtime.control.load_path(plugin_file)
            self.assertTrue(first.ok)
            await runtime.unload_plugin("alpha")
            from neobot_modloader.manager import ReentrantLock

            runtime._operation_paths[plugin_file] = "alpha"
            runtime._operation_locks["alpha"] = ReentrantLock()
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "import neobot_user_plugins as nup\n"
                "plugin = Plugin('beta')\n"
                "@plugin.on_load\n"
                "async def hold(ctx):\n"
                "    nup.rename_events['entered'].set()\n"
                "    await nup.rename_events['resume'].wait()\n",
                encoding="utf-8",
            )
            load1 = asyncio.create_task(runtime.control.load_path(plugin_file))
            await entered.wait()
            load2 = asyncio.create_task(runtime.control.load_path(plugin_file))
            await asyncio.sleep(0)
            # 两个并发同路径加载必须落在同一个名字锁（beta）上，而不是陈旧映射的 alpha 锁
            self.assertEqual(list(runtime._operation_locks), ["beta"])
            self.assertEqual(runtime._operation_paths.get(plugin_file), "beta")
            resume.set()
            results = await asyncio.wait_for(asyncio.gather(load1, load2), timeout=5)
            self.assertTrue(all(result.ok for result in results))
            self.assertIsNone(runtime.manager.get_record("alpha"))
            self.assertEqual(runtime.manager.get_plugin("beta").version, "0.1.0")

    async def test_unload_and_reload_prune_operation_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "alpha.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('alpha')\n", encoding="utf-8"
            )
            result = await runtime.control.load_path(plugin_file)
            self.assertTrue(result.ok)
            self.assertEqual(runtime._operation_paths.get(plugin_file), "alpha")

            await runtime.unload_plugin("alpha")
            self.assertEqual(runtime._operation_paths, {})
            self.assertNotIn("alpha", runtime._operation_locks)

            await runtime.control.load_path(plugin_file)
            self.assertEqual(runtime._operation_paths.get(plugin_file), "alpha")
            self.assertTrue(await runtime.reload_plugin("alpha"))
            # 活记录保留唯一的 path/name 绑定，后续同路径导入仍会串行。
            self.assertEqual(runtime._operation_paths.get(plugin_file), "alpha")
            self.assertIn("alpha", runtime._operation_locks)

    async def test_load_all_rerun_skips_already_registered(self) -> None:
        import sys

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            (runtime.plugin_dir / "a.py").write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('a')\n", encoding="utf-8"
            )
            (runtime.plugin_dir / "b.py").write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('b')\n", encoding="utf-8"
            )
            runtime.load_all()
            first_modules = dict(runtime._loaded_modules)
            runtime.load_all()
            self.assertEqual(sorted(runtime.manager.names()), ["a", "b"])
            self.assertEqual(runtime._loaded_modules, first_modules)
            for name, modules in runtime._loaded_modules.items():
                present = {m for m in sys.modules if m.startswith(f"neobot_user_plugins.{name}_")}
                self.assertEqual(present, set(modules))

    async def test_load_all_does_not_disturb_in_flight_operations(self) -> None:
        import sys
        import types

        entered = asyncio.Event()
        resume = asyncio.Event()
        namespace = sys.modules.setdefault("neobot_user_plugins", types.ModuleType("neobot_user_plugins"))
        namespace.race_events = {"entered": entered, "resume": resume}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "race.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "import neobot_user_plugins as nup\n"
                "plugin = Plugin('race')\n"
                "@plugin.on_load\n"
                "async def load(ctx):\n"
                "    nup.race_events['entered'].set()\n"
                "    await nup.race_events['resume'].wait()\n",
                encoding="utf-8",
            )
            load_task = asyncio.create_task(runtime.control.load_path(plugin_file))
            await entered.wait()
            runtime.load_all()
            resume.set()
            result = await asyncio.wait_for(load_task, timeout=5)
            self.assertTrue(result.ok)
            self.assertEqual(runtime.manager.names(), ["race"])
            modules = runtime._loaded_modules["race"]
            self.assertTrue(all(m in sys.modules for m in modules))

    async def test_unload_retries_failed_on_stop(self) -> None:
        import sys

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "retry.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "attempts = [0]\n"
                "plugin = Plugin('retry')\n"
                "@plugin.on_shutdown\n"
                "async def shutdown(ctx):\n"
                "    attempts[0] += 1\n"
                "    if attempts[0] < 2:\n"
                "        raise RuntimeError('busy')\n",
                encoding="utf-8",
            )
            result = await runtime.control.load_path(plugin_file)
            self.assertTrue(result.ok)
            module = sys.modules[runtime._loaded_modules["retry"][0]]
            stopped = await runtime.stop_plugin("retry")
            self.assertFalse(stopped.ok)
            record = runtime.manager.get_record("retry")
            assert record is not None
            self.assertEqual(record.state, PluginState.STOPPED)
            self.assertTrue(record.stop_failed)
            self.assertEqual(module.attempts, [1])

            unloaded = await asyncio.wait_for(runtime.unload_plugin("retry"), timeout=5)
            self.assertTrue(unloaded.ok)
            self.assertIsNone(runtime.manager.get_record("retry"))
            self.assertEqual(module.attempts, [2])

    async def test_reload_all_retries_plugin_that_failed_at_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "broken.py"
            plugin_file.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
            runtime.load_all()
            await runtime.load_registered()
            self.assertIsNone(runtime.manager.get_record("broken"))

            plugin_file.write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('broken')\n", encoding="utf-8"
            )
            await asyncio.wait_for(runtime.reload_all(), timeout=5)

            record = runtime.manager.get_record("broken")
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record.state, PluginState.RUNNING)

    async def test_load_all_prompts_for_missing_python_dependencies_when_enabled(self) -> None:
        class FakeInstaller:
            def __init__(self) -> None:
                self.requirements: list[str] = []

            def confirm_and_install_sync(self, requirements: list[str]) -> object:
                """启动装配期走同步入口。"""
                self.requirements.extend(requirements)
                return object()

            async def confirm_and_install(self, requirements: list[str]) -> object:
                """运行期（安装/热重载）走异步入口。"""
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

    async def test_cancelled_load_leaves_terminal_state_and_runs_teardown(self) -> None:
        import sys
        import types

        entered = asyncio.Event()
        resume = asyncio.Event()
        cleaned: list[str] = []
        namespace = sys.modules.setdefault("neobot_user_plugins", types.ModuleType("neobot_user_plugins"))
        namespace.cancel_events = {"entered": entered, "resume": resume, "cleaned": cleaned}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "cancel.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "import neobot_user_plugins as nup\n"
                "plugin = Plugin('cancel')\n"
                "class Sub:\n"
                "    def unsubscribe(self):\n"
                "        nup.cancel_events['cleaned'].append('sub')\n"
                "@plugin.on_load\n"
                "async def load(ctx):\n"
                "    nup.cancel_events['entered'].set()\n"
                "    ctx.record_subscription(Sub())\n"
                "    await nup.cancel_events['resume'].wait()\n",
                encoding="utf-8",
            )
            load_task = asyncio.create_task(runtime.control.load_path(plugin_file))
            await entered.wait()
            load_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await load_task

            record = runtime.manager.get_record("cancel")
            self.assertIsNotNone(record)
            assert record is not None
            # 终态 + 明确取消错误 + 回滚资源已清理
            self.assertEqual(record.state, PluginState.ERROR)
            self.assertIn("取消", str(record.error or ""))
            self.assertEqual(cleaned, ["sub"])

            # 后续 start 是真正的 no-op，报告错误而非 ok
            result = await runtime.start_plugin("cancel")
            self.assertFalse(result.ok)
            self.assertEqual(result.state, "error")

    async def test_cancelled_start_leaves_terminal_state_and_runs_teardown(self) -> None:
        import sys
        import types

        entered = asyncio.Event()
        resume = asyncio.Event()
        cleaned: list[str] = []
        start_calls: list[int] = []
        namespace = sys.modules.setdefault("neobot_user_plugins", types.ModuleType("neobot_user_plugins"))
        namespace.cancel_events = {
            "entered": entered,
            "resume": resume,
            "cleaned": cleaned,
            "start_calls": start_calls,
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "cancel.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "import neobot_user_plugins as nup\n"
                "plugin = Plugin('cancel')\n"
                "class Sub:\n"
                "    def unsubscribe(self):\n"
                "        nup.cancel_events['cleaned'].append('sub')\n"
                "@plugin.on_load\n"
                "async def load(ctx):\n"
                "    ctx.record_subscription(Sub())\n"
                "@plugin.on_startup\n"
                "async def startup(ctx):\n"
                "    nup.cancel_events['start_calls'].append(1)\n"
                "    nup.cancel_events['entered'].set()\n"
                "    await nup.cancel_events['resume'].wait()\n",
                encoding="utf-8",
            )
            result = await runtime.control.load_path(plugin_file, start=False)
            self.assertTrue(result.ok)
            self.assertEqual(runtime.manager.get_state("cancel"), PluginState.LOADED)

            start_task = asyncio.create_task(runtime.control.start("cancel"))
            await entered.wait()
            start_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await start_task

            record = runtime.manager.get_record("cancel")
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record.state, PluginState.ERROR)
            self.assertIn("取消", str(record.error or ""))
            self.assertEqual(cleaned, ["sub"])
            self.assertEqual(start_calls, [1])

            stopped = await runtime.stop_plugin("cancel")
            self.assertFalse(stopped.ok)
            self.assertEqual(start_calls, [1])

    async def test_reload_all_unloads_plugins_disabled_via_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            package = runtime.plugin_dir / "off"
            package.mkdir()
            (package / "plugin.toml").write_text('name = "off"\nversion = "1"\n', encoding="utf-8")
            (package / "__init__.py").write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('off', version='1')\n", encoding="utf-8"
            )
            result = await runtime.control.load_path(package)
            self.assertTrue(result.ok)
            self.assertEqual(runtime.manager.get_state("off"), PluginState.RUNNING)

            (package / "plugin.toml").write_text('name = "off"\nenabled = false\n', encoding="utf-8")
            await asyncio.wait_for(runtime.reload_all(), timeout=5)

            # 禁用插件被卸载，不再 RUNNING，也不再出现"插件未找到"误报路径
            self.assertIsNone(runtime.manager.get_record("off"))

    async def test_operation_busy_load_path_clears_imported_modules(self) -> None:
        import sys

        from neobot_modloader.manager import ReentrantLock

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "busy.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('busy')\n", encoding="utf-8"
            )
            lock_busy = runtime._operation_locks.setdefault("busy", ReentrantLock())
            lock_zzz = runtime._operation_locks.setdefault("zzz", ReentrantLock())
            await lock_zzz.acquire()  # 本任务持有更大的名字锁 → bind('busy') 越序
            started = asyncio.Event()
            release = asyncio.Event()
            holder = asyncio.create_task(_hold_lock(lock_busy, started, release))
            await started.wait()

            result = await runtime.control.load_path(plugin_file)

            self.assertFalse(result.ok)
            self.assertIn("busy", result.error or "")
            # bind 抛 OperationBusy 前已导入的新一代模块必须被清除
            self.assertFalse(any(n.startswith("neobot_user_plugins.busy_") for n in sys.modules))
            self.assertNotIn(plugin_file, runtime._operation_paths)
            self.assertNotIn(plugin_file, runtime._operation_path_users)
            self.assertNotIn(plugin_file, runtime._committed_operation_paths)
            lock_zzz.release()
            release.set()
            await holder

    async def test_cancelled_path_lock_wait_clears_imported_generation_and_binding(self) -> None:
        import sys

        from neobot_modloader.manager import ReentrantLock

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "cancel_bind.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('cancel-bind')\n",
                encoding="utf-8",
            )
            lock = runtime._operation_locks.setdefault("cancel-bind", ReentrantLock())
            started = asyncio.Event()
            release = asyncio.Event()
            holder = asyncio.create_task(_hold_lock(lock, started, release))
            await started.wait()
            load_task = asyncio.create_task(runtime.control.load_path(plugin_file))

            async def wait_for_binding() -> None:
                while runtime._operation_paths.get(plugin_file) != "cancel-bind":
                    await asyncio.sleep(0)

            await asyncio.wait_for(wait_for_binding(), timeout=5)

            load_task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await load_task

            self.assertFalse(any(name.startswith("neobot_user_plugins.cancel_bind_") for name in sys.modules))
            self.assertNotIn(plugin_file, runtime._operation_paths)
            self.assertNotIn(plugin_file, runtime._operation_path_users)
            release.set()
            await holder

    async def test_failed_operations_do_not_leak_operation_locks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            baseline = set(runtime._operation_locks)

            self.assertFalse((await runtime.unload_plugin("ghost")).ok)
            self.assertFalse((await runtime.start_plugin("ghost")).ok)
            self.assertFalse((await runtime.stop_plugin("ghost")).ok)
            self.assertFalse((await runtime.reload_plugin_result("ghost")).ok)
            self.assertEqual(set(runtime._operation_locks), baseline)

            bad = runtime.plugin_dir / "bad.py"
            bad.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
            self.assertFalse((await runtime.control.load_path(bad)).ok)
            self.assertEqual(set(runtime._operation_locks), baseline)
            self.assertEqual(runtime._operation_paths, {})

            fail = runtime.plugin_dir / "fail.py"
            fail.write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('fail')\n"
                "@plugin.on_load\n"
                "async def load(ctx):\n"
                "    raise RuntimeError('nope')\n",
                encoding="utf-8",
            )
            self.assertFalse((await runtime.control.load_path(fail)).ok)
            self.assertEqual(set(runtime._operation_locks), baseline)
            self.assertEqual(runtime._operation_paths, {})
            self.assertEqual(runtime._operation_path_users, {})
            self.assertEqual(runtime._committed_operation_paths, set())

    async def test_operation_busy_ignores_waiters_without_holder(self) -> None:
        from neobot_modloader.manager import ReentrantLock

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            lock_a = runtime._operation_locks.setdefault("a", ReentrantLock())
            lock_z = runtime._operation_locks.setdefault("z", ReentrantLock())
            await lock_a.acquire()
            await lock_z.acquire()  # 本任务持有 z（越序请求 a）
            waiter = asyncio.create_task(_acquire_release(lock_a))
            await asyncio.sleep(0)
            lock_a.release()  # a 无持有者、仅剩排队等待者
            # 旧 in_use() 逻辑会因等待者误报 OperationBusy；新逻辑只看实际持有者
            async with runtime._named_operation("a"):
                pass
            await waiter
            lock_z.release()

    async def test_runtime_rejects_forged_escape_name_without_tracking_it(self) -> None:
        class UnsafePlugin:
            name = ".."
            version = "1"

            async def on_load(self, ctx: Any) -> None:
                pass

            async def on_start(self) -> None:
                pass

            async def on_stop(self) -> None:
                pass

        class UnsafeLoader:
            def load_one(self, path: Path) -> LoadedPlugin:
                plugin = UnsafePlugin()
                return LoadedPlugin("..", "1", plugin, path.parent, {}, source_path=path)

            def clear_module_cache(self, module_names: tuple[str, ...]) -> None:
                pass

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root, loader=UnsafeLoader())
            plugin_file = runtime.plugin_dir / "escape.py"
            plugin_file.touch()

            from unittest.mock import patch

            with patch("neobot_modloader.runtime.validate_plugin_name", return_value=".."):
                result = await runtime.control.load_path(plugin_file)

            self.assertFalse(result.ok)
            self.assertEqual(runtime.manager.names(), [])
            self.assertEqual(runtime._loaded_paths, {})
            self.assertEqual(runtime._operation_paths, {})
            self.assertEqual(runtime._operation_locks, {})

    async def test_runtime_rejects_data_directory_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir()
            data_dir = root / "data"
            data_dir.mkdir()
            outside = root / "outside"
            outside.mkdir()
            try:
                (data_dir / "escape").symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlinks unavailable: {exc}")
            plugin_file = plugin_dir / "escape.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('escape')\n",
                encoding="utf-8",
            )
            runtime = PluginRuntime(
                plugin_dir=plugin_dir,
                data_dir=data_dir,
                adapter=object(),
                logger_factory=FakeLoggerFactory(),
            )

            result = await runtime.control.load_path(plugin_file)

            self.assertFalse(result.ok)
            self.assertIsNone(runtime.manager.get_record("escape"))
            self.assertEqual(runtime._operation_paths, {})

    async def test_reload_all_unloads_prefix_disabled_and_deleted_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            disabled = runtime.plugin_dir / "disabled.py"
            deleted = runtime.plugin_dir / "deleted.py"
            disabled.write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('disabled')\n",
                encoding="utf-8",
            )
            deleted.write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('deleted')\n",
                encoding="utf-8",
            )
            runtime.load_all()
            await runtime.load_registered()
            await runtime.start_all()
            disabled.rename(runtime.plugin_dir / "_disabled.py")
            deleted.unlink()

            outcomes = await runtime.reload_all()

            by_name = {outcome.name: outcome for outcome in outcomes}
            self.assertTrue(by_name["disabled"].ok)
            self.assertTrue(by_name["deleted"].ok)
            self.assertIsNone(runtime.manager.get_record("disabled"))
            self.assertIsNone(runtime.manager.get_record("deleted"))
            self.assertEqual(runtime._loaded_paths, {})

    async def test_reload_all_returns_disable_unload_failures(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "stuck.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('stuck')\n"
                "@plugin.on_shutdown\n"
                "async def shutdown(ctx):\n"
                "    raise RuntimeError('cannot stop')\n",
                encoding="utf-8",
            )
            self.assertTrue((await runtime.control.load_path(plugin_file)).ok)
            plugin_file.rename(runtime.plugin_dir / "_stuck.py")

            outcomes = await runtime.reload_all()

            outcome = next(item for item in outcomes if item.name == "stuck")
            self.assertFalse(outcome.ok)
            self.assertIn("cannot stop", outcome.error or "")
            self.assertNotEqual(runtime.manager.get_state("stuck"), PluginState.RUNNING)
            self.assertTrue((await runtime.control.force_unload("stuck")).ok)

    async def test_self_unload_stop_failure_is_returned_to_outer_unload(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "self_stop.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('self-stop')\n"
                "@plugin.on_shutdown\n"
                "async def shutdown(ctx):\n"
                "    await ctx.plugin_control.unload('self-stop')\n"
                "    raise RuntimeError('self stop failed')\n",
                encoding="utf-8",
            )
            self.assertTrue((await runtime.control.load_path(plugin_file)).ok)

            result = await asyncio.wait_for(runtime.control.unload("self-stop"), timeout=5)

            self.assertFalse(result.ok)
            self.assertIn("self stop failed", result.error or "")

    async def test_force_unload_removes_permanently_failing_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "stuck.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('stuck')\n"
                "@plugin.on_shutdown\n"
                "async def shutdown(ctx):\n"
                "    raise RuntimeError('permanent stop failure')\n",
                encoding="utf-8",
            )
            self.assertTrue((await runtime.control.load_path(plugin_file)).ok)
            failed = await runtime.control.unload("stuck")
            self.assertFalse(failed.ok)

            forced = await runtime.control.unload("stuck", force=True)

            self.assertTrue(forced.ok)
            self.assertTrue(forced.requires_restart)
            self.assertIn("permanent stop failure", forced.error or "")
            self.assertIsNone(runtime.manager.get_record("stuck"))
            self.assertNotIn("stuck", runtime._loaded_modules)
            self.assertNotIn("stuck", runtime._loaded_paths)

    async def test_failed_new_generation_restores_old_running_generation(self) -> None:
        import sys

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "transaction.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('transaction', version='1')\n",
                encoding="utf-8",
            )
            self.assertTrue((await runtime.control.load_path(plugin_file)).ok)
            old_modules = runtime._loaded_modules["transaction"]
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('transaction', version='2')\n"
                "@plugin.on_load\n"
                "async def load(ctx):\n"
                "    raise RuntimeError('new generation failed')\n",
                encoding="utf-8",
            )

            result = await runtime.reload_plugin_result("transaction")

            self.assertFalse(result.ok)
            self.assertEqual(result.state, PluginState.RUNNING.value)
            self.assertIn("new generation failed", result.error or "")
            self.assertEqual(runtime.manager.get_plugin("transaction").version, "1")
            self.assertEqual(runtime._loaded_modules["transaction"], old_modules)
            self.assertTrue(all(module in sys.modules for module in old_modules))
            live_generations = {
                module
                for module in sys.modules
                if module.startswith("neobot_user_plugins.transaction_")
            }
            self.assertEqual(live_generations, set(old_modules))

    async def test_reload_surfaces_old_generation_stop_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "stop_failure.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('stop-failure', version='1')\n"
                "@plugin.on_shutdown\n"
                "async def shutdown(ctx):\n"
                "    await ctx.plugin_control.unload('stop-failure')\n"
                "    raise RuntimeError('old generation stop failed')\n",
                encoding="utf-8",
            )
            self.assertTrue((await runtime.control.load_path(plugin_file)).ok)
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('stop-failure', version='2')\n",
                encoding="utf-8",
            )

            result = await runtime.reload_plugin_result("stop-failure")

            self.assertFalse(result.ok)
            self.assertIn("old generation stop failed", result.error or "")
            self.assertEqual(runtime.manager.get_plugin("stop-failure").version, "1")
            self.assertNotEqual(runtime.manager.get_state("stop-failure"), PluginState.RUNNING)
            self.assertTrue((await runtime.control.force_unload("stop-failure")).ok)

    async def test_control_start_loads_registered_unloaded_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "sleeping.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('sleeping')\n",
                encoding="utf-8",
            )
            runtime.load_all()
            self.assertEqual(runtime.manager.get_state("sleeping"), PluginState.UNLOADED)

            result = await runtime.control.start("sleeping")

            self.assertTrue(result.ok)
            self.assertEqual(result.state, PluginState.RUNNING.value)
            self.assertEqual(runtime.manager.get_state("sleeping"), PluginState.RUNNING)

    async def test_control_start_reports_unloaded_record_load_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "broken_start.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\n"
                "plugin = Plugin('broken-start')\n"
                "@plugin.on_load\n"
                "async def load(ctx):\n"
                "    raise RuntimeError('load before start failed')\n",
                encoding="utf-8",
            )
            runtime.load_all()

            result = await runtime.control.start("broken-start")

            self.assertFalse(result.ok)
            self.assertEqual(result.state, PluginState.ERROR.value)
            self.assertIn("load before start failed", result.error or "")
            self.assertTrue((await runtime.control.force_unload("broken-start")).ok)

    async def test_control_stop_reports_registered_unloaded_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = self.make_runtime(root)
            plugin_file = runtime.plugin_dir / "sleeping.py"
            plugin_file.write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('sleeping')\n",
                encoding="utf-8",
            )
            runtime.load_all()

            result = await runtime.control.stop("sleeping")

            self.assertTrue(result.ok)
            self.assertEqual(result.state, PluginState.UNLOADED.value)
            self.assertIsNone(result.error)


if __name__ == "__main__":
    unittest.main()
