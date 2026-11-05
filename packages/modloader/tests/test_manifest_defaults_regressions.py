"""清单默认值跟随插件代际更新，对应 issue #175。"""

from pathlib import Path

from neobot_contracts.ports.plugin import PluginState
from runtime_regression_helpers import make_plugin, make_runtime, start_runtime


async def test_reload_refreshes_defaults_and_preserves_saved_overrides(tmp_path: Path) -> None:
    users = tmp_path / "plugins"
    make_plugin(users, "demo", defaults={"value": 1, "override": 1})
    runtime = make_runtime(tmp_path)
    await start_runtime(runtime)
    config = runtime.plugin_config_path("demo")
    assert config is not None
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("override = 9\n", encoding="utf-8")
    make_plugin(users, "demo", defaults={"value": 2, "override": 2, "new_value": 3})

    try:
        outcome = await runtime.reload_plugin_result("demo")
        assert outcome.ok
        record = runtime.manager.get_record("demo")
        assert record is not None
        assert record.context.config == {"value": 2, "override": 9, "new_value": 3}
        assert runtime.plugin_config_defaults("demo") == {
            "value": 2,
            "override": 2,
            "new_value": 3,
        }
    finally:
        await runtime.stop_all()


async def test_failed_candidate_restores_previous_generation_defaults(tmp_path: Path) -> None:
    users = tmp_path / "plugins"
    make_plugin(users, "demo", defaults={"value": 1})
    runtime = make_runtime(tmp_path)
    await start_runtime(runtime)
    make_plugin(
        users,
        "demo",
        defaults={"value": 2, "new_value": 3},
        body="\n@plugin.on_startup\nasync def start(ctx):\n    raise RuntimeError('candidate failed')\n",
    )

    try:
        outcome = await runtime.reload_plugin_result("demo")
        assert not outcome.ok
        assert runtime.manager.get_state("demo") is PluginState.RUNNING
        assert runtime.manager.get_record("demo").context.config == {"value": 1}
        assert runtime.plugin_config_defaults("demo") == {"value": 1}
        make_plugin(users, "demo", defaults={"value": 4})
        assert (await runtime.reload_plugin_result("demo")).ok
        assert runtime.manager.get_record("demo").context.config == {"value": 4}
    finally:
        await runtime.stop_all()


async def test_unload_and_reinstall_same_name_discards_old_defaults(tmp_path: Path) -> None:
    users = tmp_path / "plugins"
    make_plugin(users, "demo", defaults={"value": 1})
    runtime = make_runtime(tmp_path)
    await start_runtime(runtime)
    assert (await runtime.unload_plugin("demo")).ok
    path = make_plugin(users, "demo", defaults={"value": 7})

    try:
        assert (await runtime.load_plugin_path(path)).ok
        assert runtime.manager.get_record("demo").context.config == {"value": 7}
        assert runtime.plugin_config_defaults("demo") == {"value": 7}
    finally:
        await runtime.stop_all()
