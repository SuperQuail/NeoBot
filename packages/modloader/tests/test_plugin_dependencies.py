"""插件依赖体系：版本约束、拓扑排序、自动禁用、前置调用、反向联动。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from neobot_contracts.ports.plugin import PluginState
from neobot_modloader.dependency import (
    PluginDependencyError,
    parse_dependencies,
    parse_dependency,
    version_satisfies,
)
from neobot_modloader.loading.models import (
    DisabledPlugin,
    DiscoveredPlugin,
    LoadedPlugin,
)
from neobot_modloader.loading.ordering import (
    CODE_CYCLE,
    CODE_DISABLED,
    CODE_MISSING,
    CODE_VERSION,
    order_discovery_results,
    order_results,
    resolve_load_order,
)
from neobot_modloader.runtime import PluginRuntime
from neobot_modloader.state import PluginStateStore

PLUGIN_SOURCE = (
    "from neobot_modloader import Plugin\n"
    "plugin = Plugin({name!r}, version={version!r}, dependencies={dependencies!r})\n"
)


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


def make_package(
    root: Path,
    name: str,
    *,
    version: str = "1.0.0",
    dependencies: tuple[str, ...] = (),
    priority: int = 0,
    body: str = "",
) -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    lines = [
        f'name = "{name}"',
        f'version = "{version}"',
        f"priority = {priority}",
    ]
    if dependencies:
        rendered = ", ".join(repr(item) for item in dependencies)
        lines.append(f"dependencies = [{rendered}]")
    (directory / "plugin.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (directory / "__init__.py").write_text(
        "from neobot_modloader import Plugin\n"
        f"plugin = Plugin({name!r}, version={version!r}, dependencies={dependencies!r})\n"
        + body,
        encoding="utf-8",
    )
    return directory


def make_runtime(root: Path, **kwargs: Any) -> PluginRuntime:
    plugin_dir = root / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    return PluginRuntime(
        plugin_dir=plugin_dir,
        data_dir=root / "data",
        adapter=object(),
        logger_factory=FakeLoggerFactory(),
        **kwargs,
    )


def _loaded(name: str, version: str = "1.0.0", *, dependencies: tuple[str, ...] = (), priority: int = 0) -> LoadedPlugin:
    return LoadedPlugin(
        name=name,
        version=version,
        plugin=object(),
        plugin_dir=Path(".") / name,
        config={},
        dependencies=dependencies,
        priority=priority,
    )


# ---------------------------------------------------------------------------
# 依赖声明解析
# ---------------------------------------------------------------------------


class DependencyParsingTest(unittest.TestCase):
    def test_parses_name_only(self) -> None:
        dependency = parse_dependency("dashboard")
        self.assertEqual(dependency.name, "dashboard")
        self.assertEqual(dependency.specifier, "")
        self.assertEqual(dependency.describe(), "dashboard")

    def test_parses_version_constraint(self) -> None:
        dependency = parse_dependency("dashboard>=1.2.0")
        self.assertEqual(dependency.name, "dashboard")
        self.assertEqual(dependency.specifier, ">=1.2.0")
        self.assertEqual(dependency.describe(), "dashboard>=1.2.0")

    def test_parses_multiple_constraints(self) -> None:
        dependency = parse_dependencies(["metrics>=1.2,<2.0"])
        self.assertEqual(dependency[0].specifier, ">=1.2,<2.0")

    def test_rejects_invalid_expressions(self) -> None:
        for value in ("", "  ", "dashboard>=", ">>>1.0", "a b", "dashboard==abc"):
            with self.assertRaises((ValueError, TypeError)):
                parse_dependency(value)

    def test_tolerates_whitespace_around_operator(self) -> None:
        dependency = parse_dependency("dashboard >= 1.0.0")
        self.assertEqual(dependency.name, "dashboard")
        self.assertIs(dependency.matches("1.2.0"), True)

    def test_rejects_duplicate_dependencies(self) -> None:
        with self.assertRaises(ValueError):
            parse_dependencies(["a", "a>=1.0"])

    def test_rejects_single_string(self) -> None:
        with self.assertRaises(TypeError):
            parse_dependencies("a")  # type: ignore[arg-type]


class VersionSatisfactionTest(unittest.TestCase):
    def test_operators(self) -> None:
        cases = [
            ("1.2.3", ">=1.0.0", True),
            ("0.9.0", ">=1.0.0", False),
            ("1.0.0", ">=1.0.0", True),
            ("1.0", ">=1.0.0", True),
            ("2.0.0", "<2.0.0", False),
            ("1.9.9", "<2.0.0", True),
            ("1.0.0", "==1.0", True),
            ("1.0.1", "==1.0", False),
            ("1.0.1", "!=1.0.0", True),
        ]
        for version, specifier, expected in cases:
            self.assertIs(version_satisfies(version, specifier), expected, f"{version}{specifier}")

    def test_compatible_release(self) -> None:
        self.assertIs(version_satisfies("1.4.2", "~=1.4.0"), True)
        self.assertIs(version_satisfies("1.4.9", "~=1.4.0"), True)
        self.assertIs(version_satisfies("1.5.0", "~=1.4.0"), False)
        self.assertIs(version_satisfies("1.9.0", "~=1.4"), True)
        self.assertIs(version_satisfies("2.0.0", "~=1.4"), False)

    def test_unknown_version_is_not_a_failure(self) -> None:
        # 源码运行拿不到版本号时不能把插件判死
        self.assertIsNone(version_satisfies(None, ">=1.0.0"))
        self.assertIsNone(version_satisfies("0.0.0", ">=1.0.0"))
        self.assertIsNone(version_satisfies("abc", ">=1.0.0"))

    def test_prerelease_ignored(self) -> None:
        self.assertIs(version_satisfies("1.0.0-alpha.23", ">=1.0.0"), True)


# ---------------------------------------------------------------------------
# 拓扑排序与自动禁用
# ---------------------------------------------------------------------------


class ResolveLoadOrderTest(unittest.TestCase):
    def test_dependency_comes_first(self) -> None:
        ordering = resolve_load_order([_loaded("app", dependencies=("base",)), _loaded("base")])
        self.assertEqual(list(ordering.ordered), ["base", "app"])
        self.assertEqual(ordering.blocked, {})

    def test_priority_applies_within_same_level(self) -> None:
        ordering = resolve_load_order(
            [_loaded("low", priority=0), _loaded("high", priority=10)]
        )
        self.assertEqual(list(ordering.ordered), ["high", "low"])

    def test_missing_dependency_blocks_only_dependant(self) -> None:
        ordering = resolve_load_order([_loaded("app", dependencies=("base",)), _loaded("solo")])
        self.assertEqual(sorted(ordering.ordered), ["solo"])
        self.assertEqual(ordering.blocked["app"].code, CODE_MISSING)

    def test_version_mismatch_blocks(self) -> None:
        ordering = resolve_load_order(
            [_loaded("app", dependencies=("base>=2.0",)), _loaded("base", version="1.0.0")]
        )
        self.assertEqual(list(ordering.ordered), ["base"])
        issue = ordering.blocked["app"]
        self.assertEqual(issue.code, CODE_VERSION)
        self.assertIn("base>=2.0", issue.reason)

    def test_version_match_loads(self) -> None:
        ordering = resolve_load_order(
            [_loaded("app", dependencies=("base>=1.0",)), _loaded("base", version="1.4.0")]
        )
        self.assertEqual(list(ordering.ordered), ["base", "app"])

    def test_disabled_dependency_blocks_with_reason(self) -> None:
        ordering = resolve_load_order(
            [_loaded("app", dependencies=("base",))],
            unavailable={"base": "插件已停用"},
        )
        self.assertEqual(list(ordering.ordered), [])
        self.assertEqual(ordering.blocked["app"].code, CODE_DISABLED)
        self.assertIn("插件已停用", ordering.blocked["app"].reason)

    def test_blocked_propagates_transitively(self) -> None:
        ordering = resolve_load_order(
            [
                _loaded("top", dependencies=("middle",)),
                _loaded("middle", dependencies=("base",)),
            ]
        )
        self.assertEqual(ordering.blocked["middle"].code, CODE_MISSING)
        self.assertEqual(ordering.blocked["top"].code, CODE_DISABLED)

    def test_cycle_blocks_every_member(self) -> None:
        ordering = resolve_load_order(
            [
                _loaded("a", dependencies=("b",)),
                _loaded("b", dependencies=("a",)),
                _loaded("safe"),
            ]
        )
        self.assertEqual(list(ordering.ordered), ["safe"])
        self.assertEqual(ordering.blocked["a"].code, CODE_CYCLE)
        self.assertEqual(ordering.blocked["b"].code, CODE_CYCLE)

    def test_duplicate_names_reported(self) -> None:
        ordering = resolve_load_order([_loaded("dup"), _loaded("dup")])
        self.assertEqual(ordering.duplicates, ("dup",))
        self.assertEqual(list(ordering.ordered), ["dup"])


class OrderResultsTest(unittest.TestCase):
    def test_load_path_produces_disabled_entry(self) -> None:
        results = order_results(
            [
                _loaded("app", dependencies=("base",)),
            ]
        )
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], DisabledPlugin)
        assert isinstance(results[0], DisabledPlugin)
        self.assertEqual(results[0].name, "app")
        self.assertEqual(results[0].code, CODE_MISSING)

    def test_discovery_path_marks_auto_disabled(self) -> None:
        results = order_discovery_results(
            [
                DiscoveredPlugin(name="app", version="1.0.0", plugin_dir=Path("app"), dependencies=("base",)),
                DiscoveredPlugin(name="base", version="1.0.0", plugin_dir=Path("base"), enabled=False),
            ]
        )
        by_name = {result.name: result for result in results if isinstance(result, DiscoveredPlugin)}
        self.assertTrue(by_name["app"].auto_disabled)
        self.assertIsNotNone(by_name["app"].disabled_reason)
        self.assertIn("base", by_name["app"].disabled_reason or "")


# ---------------------------------------------------------------------------
# 加载器 / 运行时行为
# ---------------------------------------------------------------------------


class DependencyRuntimeTest(unittest.IsolatedAsyncioTestCase):
    def test_loader_orders_by_dependency_and_version(self) -> None:
        from neobot_modloader.loader import FilesystemPluginLoader

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_package(root, "base", version="2.0.0")
            make_package(root, "app", dependencies=("base>=1.0",), priority=100)
            results = FilesystemPluginLoader().load_all(root)

            names = [result.name for result in results if isinstance(result, LoadedPlugin)]
            self.assertEqual(names, ["base", "app"])

    def test_loader_disables_dependant_on_version_mismatch(self) -> None:
        from neobot_modloader.loader import FilesystemPluginLoader

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            make_package(root, "base", version="1.0.0")
            make_package(root, "app", dependencies=("base>=2.0",))
            results = FilesystemPluginLoader().load_all(root)

            disabled = [result for result in results if isinstance(result, DisabledPlugin)]
            self.assertEqual([item.name for item in disabled], ["app"])
            self.assertEqual(disabled[0].code, CODE_VERSION)

    async def test_runtime_skips_unsatisfied_dependency_without_failing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            make_package(plugin_dir, "solo")
            make_package(plugin_dir, "app", dependencies=("base",))
            runtime = make_runtime(root)

            runtime.load_all()
            await runtime.load_registered()
            await runtime.start_all()

            self.assertEqual(runtime.manager.get_state("solo"), PluginState.RUNNING)
            self.assertIsNone(runtime.manager.get_record("app"))
            snapshots = {item.name: item for item in runtime.snapshot_plugins()}
            self.assertIn("前置插件", snapshots["app"].disabled_reason or "")
            await runtime.stop_all()

    async def test_capability_call_and_require(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            make_package(
                plugin_dir,
                "base",
                body=(
                    "\n@plugin.capability('greet')\n"
                    "async def greet(payload):\n"
                    "    return 'hello ' + str(payload.get('who', ''))\n"
                ),
            )
            make_package(
                plugin_dir,
                "app",
                dependencies=("base>=1.0",),
                body=(
                    "\n@plugin.on_load\n"
                    "async def _load(ctx):\n"
                    "    handle = ctx.require_plugin('base', '>=1.0')\n"
                    "    ctx.settings_result = await handle.call('greet', {'who': 'starship'})\n"
                ),
            )
            runtime = make_runtime(root)
            runtime.load_all()
            await runtime.load_registered()
            await runtime.start_all()

            handle = runtime.manager.registry_view.require("base", ">=1.0")
            self.assertEqual(await handle.call("greet", {"who": "x"}), "hello x")
            self.assertEqual(runtime.manager.get_state("app"), PluginState.RUNNING)
            await runtime.stop_all()

    async def test_require_rejects_unknown_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = make_runtime(root)

            with self.assertRaises(PluginDependencyError):
                runtime.manager.registry_view.require("nope")

    async def test_disabling_dependency_cascades_and_restores(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            make_package(plugin_dir, "base")
            make_package(plugin_dir, "app", dependencies=("base",))
            store = PluginStateStore(root / "plugin_state.json")
            runtime = make_runtime(root, state_store=store)

            runtime.load_all()
            await runtime.load_registered()
            await runtime.start_all()
            self.assertEqual(runtime.manager.get_state("app"), PluginState.RUNNING)

            # 停用前置插件：依赖它的插件被联动停用
            outcome = await runtime.set_enabled("base", False)
            self.assertTrue(outcome.ok)
            self.assertIsNone(runtime.manager.get_record("app"))

            # 重新启用前置插件：依赖插件自动恢复
            outcome = await runtime.set_enabled("base", True)
            self.assertTrue(outcome.ok)
            self.assertEqual(runtime.manager.get_state("base"), PluginState.RUNNING)
            self.assertEqual(runtime.manager.get_state("app"), PluginState.RUNNING)
            await runtime.stop_all()

    async def test_snapshot_reports_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plugin_dir = root / "plugins"
            make_package(plugin_dir, "base")
            make_package(plugin_dir, "app", dependencies=("base",))
            runtime = make_runtime(root)

            runtime.load_all()
            await runtime.load_registered()
            await runtime.start_all()

            snapshots = {item.name: item for item in runtime.snapshot_plugins()}
            self.assertEqual(snapshots["base"].dependents, ("app",))
            self.assertEqual(snapshots["app"].dependency_issues, ())
            report = runtime.control.dependencies("base")
            self.assertEqual(report["dependents"], ["app"])
            await runtime.stop_all()


if __name__ == "__main__":
    unittest.main()
