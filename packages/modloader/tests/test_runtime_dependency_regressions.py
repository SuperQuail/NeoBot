"""跨来源依赖与重载恢复的行为回归，对应 issue #172、#173、#174。"""

import asyncio
from pathlib import Path

import pytest

from neobot_contracts.ports.plugin import PluginState
from neobot_modloader.loading.models import DiscoveredPlugin
from neobot_modloader.state import PluginStateStore
from runtime_regression_helpers import make_plugin, make_runtime, start_runtime


@pytest.mark.parametrize("official_prerequisite", [True, False])
async def test_cross_source_dependency_is_resolved_after_merging_directories(
    tmp_path: Path, official_prerequisite: bool
) -> None:
    official = tmp_path / "official"
    users = tmp_path / "plugins"
    base_root, addon_root = (official, users) if official_prerequisite else (users, official)
    make_plugin(base_root, "base")
    make_plugin(addon_root, "addon", dependencies=("base>=1.0",))
    runtime = make_runtime(tmp_path, builtin_plugin_dirs=(official,))

    discovered = {item.name: item for item in runtime.discover_all() if isinstance(item, DiscoveredPlugin)}
    assert discovered["addon"].auto_disabled is False
    await start_runtime(runtime)
    try:
        assert runtime.manager.get_state("base") is PluginState.RUNNING
        assert runtime.manager.get_state("addon") is PluginState.RUNNING
    finally:
        await runtime.stop_all()


async def test_official_duplicate_is_selected_before_global_version_resolution(
    tmp_path: Path,
) -> None:
    official = tmp_path / "official"
    make_plugin(official, "base", version="1.0.0")
    make_plugin(tmp_path / "plugins", "base", version="9.0.0")
    make_plugin(tmp_path / "plugins", "addon", dependencies=("base>=2.0",))
    runtime = make_runtime(tmp_path, builtin_plugin_dirs=(official,))

    await start_runtime(runtime)
    try:
        assert runtime.manager.get_plugin("base").version == "1.0.0"
        assert runtime.manager.get_record("addon") is None
        snapshot = next(item for item in runtime.snapshot_plugins() if item.name == "addon")
        assert "版本" in (snapshot.disabled_reason or "")
    finally:
        await runtime.stop_all()


async def test_cross_source_cycle_only_disables_its_dependency_subgraph(tmp_path: Path) -> None:
    official = tmp_path / "official"
    make_plugin(official, "base", dependencies=("addon",))
    make_plugin(tmp_path / "plugins", "addon", dependencies=("base",))
    make_plugin(tmp_path / "plugins", "solo")
    runtime = make_runtime(tmp_path, builtin_plugin_dirs=(official,))

    await start_runtime(runtime)
    try:
        assert runtime.manager.get_state("solo") is PluginState.RUNNING
        assert runtime.manager.get_record("base") is None
        assert runtime.manager.get_record("addon") is None
        snapshots = {item.name: item for item in runtime.snapshot_plugins()}
        assert "循环" in (snapshots["base"].disabled_reason or "")
        assert "循环" in (snapshots["addon"].disabled_reason or "")
    finally:
        await runtime.stop_all()


async def test_disabled_official_name_cannot_be_replaced_by_third_party(tmp_path: Path) -> None:
    official = tmp_path / "official"
    make_plugin(official, "base", enabled=False)
    make_plugin(tmp_path / "plugins", "base", version="9.0.0")
    make_plugin(tmp_path / "plugins", "addon", dependencies=("base",))
    runtime = make_runtime(tmp_path, builtin_plugin_dirs=(official,))

    await start_runtime(runtime)
    try:
        assert runtime.manager.get_record("base") is None
        assert runtime.manager.get_record("addon") is None
        snapshots = {item.name: item for item in runtime.snapshot_plugins()}
        assert snapshots["base"].official
        assert snapshots["base"].enabled is False
    finally:
        await runtime.stop_all()


@pytest.mark.parametrize("code_dependencies", [(), ("other",)])
async def test_manifest_dependencies_control_registry_disable_and_restore(
    tmp_path: Path, code_dependencies: tuple[str, ...]
) -> None:
    users = tmp_path / "plugins"
    make_plugin(users, "base")
    make_plugin(users, "addon", dependencies=("base",), code_dependencies=code_dependencies)
    runtime = make_runtime(tmp_path, state_store=PluginStateStore(tmp_path / "plugin_state.json"))

    await start_runtime(runtime)
    try:
        assert runtime.manager.registry_view.dependents_of("base") == ["addon"]
        assert runtime.manager.registry_view.require("addon").dependencies == ("base",)
        assert runtime.control.dependencies("addon")["dependencies"] == ["base"]
        assert (await runtime.set_enabled("base", False)).ok
        assert runtime.manager.get_record("addon") is None
        assert (await runtime.set_enabled("base", True)).ok
        assert runtime.manager.get_state("addon") is PluginState.RUNNING
    finally:
        await runtime.stop_all()


async def test_code_only_dependency_remains_effective(tmp_path: Path) -> None:
    users = tmp_path / "plugins"
    make_plugin(users, "base")
    make_plugin(users, "addon", code_dependencies=("base",))
    runtime = make_runtime(tmp_path)

    await start_runtime(runtime)
    try:
        assert runtime.manager.registry_view.dependents_of("base") == ["addon"]
        assert runtime.manager.get_state("addon") is PluginState.RUNNING
    finally:
        await runtime.stop_all()


@pytest.mark.parametrize("failure", ["disabled", "syntax", "startup"])
async def test_failed_prerequisite_reload_restores_running_dependents(tmp_path: Path, failure: str) -> None:
    users = tmp_path / "plugins"
    base = make_plugin(users, "base", hot_reload=failure != "disabled")
    make_plugin(users, "addon", dependencies=("base",))
    runtime = make_runtime(tmp_path)
    await start_runtime(runtime)
    old_base = runtime.manager.get_plugin("base")
    if failure == "syntax":
        (base / "__init__.py").write_text("this is not python !!!\n", encoding="utf-8")
    elif failure == "startup":
        make_plugin(
            users,
            "base",
            body="\n@plugin.on_startup\nasync def start(ctx):\n    raise RuntimeError('candidate failed')\n",
        )

    try:
        outcome = await runtime.reload_plugin_result("base")
        assert outcome.ok is False
        assert runtime.manager.get_plugin("base") is old_base
        assert runtime.manager.get_state("base") is PluginState.RUNNING
        assert runtime.manager.get_state("addon") is PluginState.RUNNING
        assert runtime.control.dependencies("addon")["auto_disabled"] is False
    finally:
        await runtime.stop_all()


async def test_reload_reports_dependent_restore_failure(tmp_path: Path) -> None:
    users = tmp_path / "plugins"
    make_plugin(users, "base")
    make_plugin(users, "addon", dependencies=("base",))
    runtime = make_runtime(tmp_path)
    await start_runtime(runtime)
    make_plugin(
        users,
        "addon",
        dependencies=("base",),
        body="\n@plugin.on_startup\nasync def start(ctx):\n    raise RuntimeError('dependent failed')\n",
    )

    try:
        outcome = await runtime.reload_plugin_result("base")
        assert outcome.ok is False
        assert runtime.manager.get_state("base") is PluginState.RUNNING
        assert "addon" in (outcome.error or "")
        assert "dependent failed" in (outcome.error or "")
    finally:
        await runtime.stop_all()


async def test_reload_restores_dependent_when_changed_prerequisite_is_not_first(tmp_path: Path) -> None:
    users = tmp_path / "plugins"
    make_plugin(users, "other")
    make_plugin(users, "base")
    make_plugin(users, "addon", dependencies=("other", "base"))
    runtime = make_runtime(tmp_path)
    await start_runtime(runtime)

    try:
        assert (await runtime.reload_plugin_result("base")).ok
        assert runtime.manager.get_state("addon") is PluginState.RUNNING
    finally:
        await runtime.stop_all()


@pytest.mark.parametrize("dependencies", [("other", "base"), ("base", "other")])
@pytest.mark.parametrize("persistent", [False, True])
async def test_manual_disable_during_prerequisite_shutdown_cancels_dependent_restore(
    tmp_path: Path, dependencies: tuple[str, ...], persistent: bool
) -> None:
    users = tmp_path / "plugins"
    make_plugin(users, "other")
    make_plugin(
        users,
        "base",
        body=(
            "\nimport asyncio\n"
            "plugin.entered = asyncio.Event()\n"
            "plugin.release = asyncio.Event()\n"
            "@plugin.on_shutdown\n"
            "async def shutdown(ctx):\n"
            "    plugin.entered.set()\n"
            "    await plugin.release.wait()\n"
        ),
    )
    make_plugin(users, "addon", dependencies=dependencies)
    store = PluginStateStore(tmp_path / "plugin_state.json") if persistent else None
    runtime = make_runtime(tmp_path, state_store=store)
    await start_runtime(runtime)
    old_base = runtime.manager.get_plugin("base")
    task = asyncio.create_task(runtime.reload_plugin_result("base", auto_install_dependencies=False))
    try:
        await asyncio.wait_for(old_base.entered.wait(), timeout=2)
        assert runtime.manager.get_record("addon") is None
        assert (await runtime.set_enabled("addon", False)).ok
        assert not runtime._resolve_enabled_state("addon", True)
        old_base.release.set()
        assert (await asyncio.wait_for(task, timeout=2)).ok
        assert runtime.manager.get_state("base") is PluginState.RUNNING
        assert runtime.manager.get_record("addon") is None
        assert not runtime._resolve_enabled_state("addon", True)
        assert not runtime.dependency_report("addon")["auto_disabled"]
    finally:
        old_base.release.set()
        await asyncio.gather(task, return_exceptions=True)
        current = runtime.manager.get_plugin("base")
        if current is not None:
            current.release.set()
        await runtime.stop_all()


async def test_reload_restores_complete_transitive_dependency_tree(tmp_path: Path) -> None:
    users = tmp_path / "plugins"
    make_plugin(users, "base")
    make_plugin(users, "middle", dependencies=("base",))
    make_plugin(users, "leaf", dependencies=("middle",))
    runtime = make_runtime(tmp_path)
    await start_runtime(runtime)

    try:
        assert (await runtime.reload_plugin_result("base")).ok
        assert runtime.manager.get_state("middle") is PluginState.RUNNING
        assert runtime.manager.get_state("leaf") is PluginState.RUNNING
    finally:
        await runtime.stop_all()


async def test_cancelled_candidate_startup_restores_previous_dependents(tmp_path: Path) -> None:
    users = tmp_path / "plugins"
    make_plugin(users, "base")
    make_plugin(users, "addon", dependencies=("base",))
    runtime = make_runtime(tmp_path)
    await start_runtime(runtime)
    old_base = runtime.manager.get_plugin("base")
    make_plugin(
        users,
        "base",
        body=(
            "\nimport asyncio\n"
            "plugin.started = asyncio.Event()\n"
            "@plugin.on_startup\n"
            "async def start(ctx):\n"
            "    plugin.started.set()\n"
            "    await asyncio.Event().wait()\n"
        ),
    )

    task = asyncio.create_task(runtime.reload_plugin_result("base"))
    try:
        async with asyncio.timeout(5):
            while runtime.manager.get_plugin("base") is old_base:
                await asyncio.sleep(0)
            await runtime.manager.get_plugin("base").started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert runtime.manager.get_plugin("base") is old_base
        assert runtime.manager.get_state("base") is PluginState.RUNNING
        assert runtime.manager.get_state("addon") is PluginState.RUNNING
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await runtime.stop_all()
