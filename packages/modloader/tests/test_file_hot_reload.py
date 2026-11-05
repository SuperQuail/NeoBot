from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from neobot_contracts.ports.logging import NullLogger
from neobot_contracts.ports.plugin import PluginState
from neobot_modloader.hot_reload import PluginHotReloader
from neobot_modloader.runtime import PluginRuntime


class _LoggerFactory:
    def get_logger(self, name: str) -> NullLogger:
        return NullLogger()


async def _runtime(root: Path, *, hot_reload: bool = True, watch: bool = False) -> tuple[PluginRuntime, Path]:
    package = root / "plugins" / "hot"
    nested = package / "nested"
    nested.mkdir(parents=True)
    (package / "plugin.toml").write_text(f'name = "hot"\nhot_reload = {str(hot_reload).lower()}\n')
    (package / "__init__.py").write_text(
        "from neobot_modloader import Plugin\nfrom .nested.values import VALUE\nplugin = Plugin('hot', version=VALUE)\n"
    )
    (nested / "__init__.py").write_text("")
    source = nested / "values.py"
    source.write_text("VALUE = '1'\n")
    runtime = PluginRuntime(
        plugin_dir=package.parent,
        data_dir=root / "data",
        adapter=object(),
        logger_factory=_LoggerFactory(),
        watch=watch,
    )
    runtime.load_all()
    await runtime.load_registered()
    if watch:
        runtime._hot_reloader.poll_interval = 0.01
        runtime._hot_reloader.debounce = 0
    await runtime.start_all()
    return runtime, source


@pytest.mark.asyncio
async def test_saved_nested_source_reloads_after_debounce(tmp_path: Path) -> None:
    runtime, source = await _runtime(tmp_path)
    watcher = PluginHotReloader(runtime, debounce=0.3)
    await watcher.poll_once(now=0)
    previous = runtime.manager.get_plugin("hot")
    source.write_text("VALUE = '2'\n")
    await watcher.poll_once(now=1)
    source.write_text("VALUE = '3'\n")
    await watcher.poll_once(now=1.2)
    await watcher.poll_once(now=1.4)
    assert runtime.manager.get_plugin("hot") is previous
    await watcher.poll_once(now=1.6)
    assert runtime.manager.get_plugin("hot").version == "3"
    assert runtime.manager.get_state("hot") is PluginState.RUNNING
    await runtime.stop_all()


@pytest.mark.asyncio
async def test_invalid_save_retains_old_generation_and_retries_only_new_content(tmp_path: Path) -> None:
    runtime, source = await _runtime(tmp_path)
    watcher = PluginHotReloader(runtime, debounce=0)
    runtime.reload_plugin_result = AsyncMock(wraps=runtime.reload_plugin_result)
    await watcher.poll_once(now=0)
    previous = runtime.manager.get_plugin("hot")
    source.write_text("VALUE = (\n")
    await watcher.poll_once(now=1)
    await watcher.poll_once(now=2)
    assert runtime.manager.get_plugin("hot") is previous
    assert runtime.manager.get_state("hot") is PluginState.RUNNING
    assert runtime.reload_plugin_result.await_count == 1
    source.write_text("VALUE = '2'\n")
    await watcher.poll_once(now=3)
    assert runtime.manager.get_plugin("hot").version == "2"
    assert runtime.reload_plugin_result.await_count == 2
    await runtime.stop_all()


@pytest.mark.asyncio
async def test_removed_entry_retains_old_generation_until_restored(tmp_path: Path) -> None:
    runtime, source = await _runtime(tmp_path)
    watcher = PluginHotReloader(runtime, debounce=0)
    await watcher.poll_once(now=0)
    entry = source.parents[1] / "__init__.py"
    content = entry.read_text()
    entry.unlink()
    source.write_text("VALUE = '2'\n")
    await watcher.poll_once(now=1)
    assert runtime.manager.get_plugin("hot").version == "1"
    entry.write_text(content)
    await watcher.poll_once(now=2)
    assert runtime.manager.get_plugin("hot").version == "2"
    await runtime.stop_all()


@pytest.mark.asyncio
@pytest.mark.parametrize("running", [True, False])
async def test_static_resources_and_ignored_directories_do_not_restart_backend(tmp_path: Path, running: bool) -> None:
    runtime, source = await _runtime(tmp_path)
    if not running:
        await runtime.manager.stop_plugin("hot")
        await runtime.manager.load_plugin("hot")
    watcher = PluginHotReloader(runtime, debounce=0)
    await watcher.poll_once(now=0)
    previous = runtime.manager.get_plugin("hot")
    package = source.parents[1]
    for directory in ("web", "node_modules", ".git", "__pycache__", "plugins_data"):
        child = package / directory
        child.mkdir(exist_ok=True)
        (child / ("app.js" if directory == "web" else "ignored.py")).write_text("changed")
    await watcher.poll_once(now=1)
    assert runtime.manager.get_plugin("hot") is previous
    source.write_text("VALUE = '2'\n")
    await watcher.poll_once(now=2)
    assert runtime.manager.get_plugin("hot").version == "2"
    assert runtime.manager.get_state("hot") is (PluginState.RUNNING if running else PluginState.LOADED)
    await runtime.stop_all()


@pytest.mark.asyncio
async def test_explicit_stop_or_hot_reload_opt_out_prevents_automatic_start(tmp_path: Path) -> None:
    runtime, source = await _runtime(tmp_path)
    watcher = PluginHotReloader(runtime, debounce=0)
    await watcher.poll_once(now=0)
    await runtime.stop_plugin("hot")
    source.write_text("VALUE = '2'\n")
    await watcher.poll_once(now=1)
    assert runtime.manager.get_plugin("hot").version == "1"
    assert runtime.manager.get_state("hot") is PluginState.STOPPED
    other, other_source = await _runtime(tmp_path / "opt-out", hot_reload=False)
    other_watcher = PluginHotReloader(other, debounce=0)
    await other_watcher.poll_once(now=0)
    other_source.write_text("VALUE = '2'\n")
    await other_watcher.poll_once(now=1)
    assert other.manager.get_plugin("hot").version == "1"
    await runtime.stop_all()
    await other.stop_all()


@pytest.mark.asyncio
async def test_symbolic_link_cannot_expand_scan_into_external_source(tmp_path: Path) -> None:
    runtime, source = await _runtime(tmp_path)
    watcher = PluginHotReloader(runtime, debounce=0)
    external = tmp_path / "external"
    external.mkdir()
    foreign = external / "private.py"
    foreign.write_text("old")
    (source.parents[1] / "linked").symlink_to(external, target_is_directory=True)
    await watcher.poll_once(now=0)
    previous = runtime.manager.get_plugin("hot")
    foreign.write_text("new")
    await watcher.poll_once(now=1)
    assert runtime.manager.get_plugin("hot") is previous
    await runtime.stop_all()


@pytest.mark.asyncio
async def test_stop_waits_for_inflight_reload_even_when_stop_caller_is_cancelled(tmp_path: Path) -> None:
    runtime, source = await _runtime(tmp_path)
    watcher = PluginHotReloader(runtime, poll_interval=0.01, debounce=0)
    entered, release = asyncio.Event(), asyncio.Event()
    reload_plugin = runtime.reload_plugin_result

    async def held_reload(*args, **kwargs):
        entered.set()
        await release.wait()
        return await reload_plugin(*args, **kwargs)

    runtime.reload_plugin_result = held_reload
    await watcher.start()
    try:
        source.write_text("VALUE = '2'\n")
        await asyncio.wait_for(entered.wait(), timeout=2)
        stopping = asyncio.create_task(watcher.stop())
        await asyncio.sleep(0)
        stopping.cancel()
        await asyncio.sleep(0)
        assert not stopping.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await stopping
        assert runtime.manager.get_plugin("hot").version == "2"
    finally:
        release.set()
        await watcher.stop()
        await runtime.stop_all()


@pytest.mark.asyncio
async def test_save_during_reload_is_not_swallowed_by_new_generation_baseline(tmp_path: Path) -> None:
    runtime, source = await _runtime(tmp_path)
    watcher = PluginHotReloader(runtime, debounce=0)
    await watcher.poll_once(now=0)
    reload_plugin = runtime.reload_plugin_result

    async def edit_after_candidate_load(*args, **kwargs):
        outcome = await reload_plugin(*args, **kwargs)
        source.write_text("VALUE = '3'\n")
        return outcome

    runtime.reload_plugin_result = edit_after_candidate_load
    source.write_text("VALUE = '2'\n")
    await watcher.poll_once(now=1)
    assert runtime.manager.get_plugin("hot").version == "2"
    runtime.reload_plugin_result = reload_plugin
    await watcher.poll_once(now=2)
    assert runtime.manager.get_plugin("hot").version == "3"
    await runtime.stop_all()


@pytest.mark.asyncio
async def test_runtime_starts_and_stops_source_monitor_with_plugin_lifecycle(tmp_path: Path) -> None:
    runtime, source = await _runtime(tmp_path, watch=True)
    try:
        source.write_text("VALUE = '2'\n")
        async with asyncio.timeout(2):
            while runtime.manager.get_plugin("hot").version != "2":
                await asyncio.sleep(0.01)
        assert runtime.manager.get_state("hot") is PluginState.RUNNING
    finally:
        await runtime.stop_all()
    assert runtime._hot_reloader._task is None
    source.write_text("VALUE = '3'\n")
    await asyncio.sleep(0.03)
    assert runtime.manager.get_plugin("hot").version == "2"
    assert runtime.manager.get_state("hot") is PluginState.STOPPED


@pytest.mark.asyncio
async def test_one_scan_error_does_not_block_other_plugins_or_later_recovery(tmp_path: Path, monkeypatch) -> None:
    from neobot_modloader import hot_reload

    runtime, source = await _runtime(tmp_path)
    other_source = source.parents[2] / "other.py"
    other_source.write_text("from neobot_modloader import Plugin\nplugin = Plugin('other', version='1')\n")
    assert (await runtime.load_plugin_path(other_source)).ok
    watcher = PluginHotReloader(runtime, debounce=0)
    await watcher.poll_once(now=0)
    fingerprint = hot_reload._fingerprint

    def unreadable(path):
        if path.name == "hot":
            raise PermissionError("source temporarily unavailable")
        return fingerprint(path)

    monkeypatch.setattr(hot_reload, "_fingerprint", unreadable)
    source.write_text("VALUE = '2'\n")
    other_source.write_text("from neobot_modloader import Plugin\nplugin = Plugin('other', version='2')\n")
    await watcher.poll_once(now=1)
    assert runtime.manager.get_plugin("hot").version == "1"
    assert runtime.manager.get_plugin("other").version == "2"
    monkeypatch.setattr(hot_reload, "_fingerprint", fingerprint)
    await watcher.poll_once(now=2)
    assert runtime.manager.get_plugin("hot").version == "2"
    await runtime.stop_all()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["stop", "disable"])
async def test_manual_stop_during_cascade_wins_over_pending_automatic_reload(tmp_path: Path, operation: str) -> None:
    runtime, source = await _runtime(tmp_path)
    watcher = PluginHotReloader(runtime, debounce=0)
    await watcher.poll_once(now=0)
    cascade = runtime._cascade_stop_dependents
    entered, release = asyncio.Event(), asyncio.Event()

    async def hold_reload_cascade(name, *, reason):
        result = await cascade(name, reason=reason)
        if "正在重载" in reason:
            entered.set()
            await release.wait()
        return result

    runtime._cascade_stop_dependents = hold_reload_cascade
    source.write_text("VALUE = '2'\n")
    polling = asyncio.create_task(watcher.poll_once(now=1))
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        if operation == "stop":
            assert (await runtime.stop_plugin("hot")).ok
        else:
            assert (await runtime.set_enabled("hot", False)).ok
        release.set()
        await polling
        if operation == "stop":
            assert runtime.manager.get_state("hot") is PluginState.STOPPED
            assert runtime.manager.get_plugin("hot").version == "1"
        else:
            assert runtime.manager.get_record("hot") is None
            assert not runtime._resolve_enabled_state("hot", True)
    finally:
        release.set()
        await polling
        await runtime.stop_all()


@pytest.mark.asyncio
async def test_save_during_dependency_cascade_is_not_swallowed_by_restored_generation(tmp_path: Path) -> None:
    runtime, source = await _runtime(tmp_path)
    addon_source = source.parents[2] / "addon.py"
    addon_source.write_text(
        "from neobot_modloader import Plugin\nplugin = Plugin('addon', version='1', dependencies=('hot',))\n"
    )
    assert (await runtime.load_plugin_path(addon_source)).ok
    watcher = PluginHotReloader(runtime, debounce=0)
    await watcher.poll_once(now=0)
    reload_plugin = runtime.reload_plugin_result
    original_addon = runtime.manager.get_plugin("addon")

    async def save_after_cascade(name, **kwargs):
        outcome = await reload_plugin(name, **kwargs)
        if name == "hot":
            addon_source.write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('addon', version='2', dependencies=('hot',))\n"
            )
        return outcome

    runtime.reload_plugin_result = save_after_cascade
    source.write_text("VALUE = '2'\n")
    await watcher.poll_once(now=1)
    assert runtime.manager.get_plugin("hot").version == "2"
    assert runtime.manager.get_plugin("addon") is not original_addon
    assert runtime.manager.get_plugin("addon").version == "1"
    runtime.reload_plugin_result = reload_plugin
    await watcher.poll_once(now=2)
    assert runtime.manager.get_plugin("addon").version == "2"
    await runtime.stop_all()
