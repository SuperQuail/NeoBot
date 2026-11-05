from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
import pytest


def test_mute_monotonic_restart_accounts(tmp_path):
    from neobot_app.builtin_plugins.speaking_schedule.state import MuteStore

    wall = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    mono = [10.0]
    path = tmp_path / "mutes.json"
    store = MuteStore(path, now=lambda: wall[0], monotonic=lambda: mono[0])
    store.set("a", "group:1", 60)
    wall[0] += timedelta(seconds=20)
    restarted = MuteStore(path, now=lambda: wall[0], monotonic=lambda: mono[0])
    assert restarted.remaining("a", "group:1") == 40
    assert restarted.remaining("b", "group:1") == 0
    wall[0] -= timedelta(days=5)
    mono[0] += 60
    assert store.remaining("a", "group:1") == 0
    restarted.clear("a", "group:1")
    assert MuteStore(path).remaining("a", "group:1") == 0


def test_clock_validation():
    from neobot_app.builtin_plugins.speaking_schedule.state import ClockHealth

    clock = ClockHealth(monotonic=lambda: 100)
    assert not clock.sample({"self_id": 2, "time": 1000}, "1", 1000)
    assert clock.sample({"self_id": 1, "time": 1000}, "1", 1001)
    assert not clock.sample({"self_id": 1, "time": 1000}, "1", 1001)
    assert not clock.sample({"self_id": 1, "time": 1}, "1", 1001)
    assert "异常" in clock.status()


@pytest.fixture
async def runtime(tmp_path):
    import shutil
    from neobot_app.builtin_plugins import builtin_plugin_dirs
    from neobot_app.runtime.speaking_policy import SpeakingPolicyRegistry
    from neobot_app.commands.registry import CommandRegistry
    from neobot_modloader.host import PluginHostFacade
    from neobot_modloader.runtime import PluginRuntime
    from neobot_modloader.state import PluginStateStore
    from neobot_contracts.ports.logging import NullLogger

    root = tmp_path / "official"
    shutil.copytree(builtin_plugin_dirs()[0] / "speaking_schedule", root / "speaking_schedule")
    host = PluginHostFacade()
    policy = SpeakingPolicyRegistry()
    host.services.register("speaking_policy", policy)
    host.services.register("config", SimpleNamespace(bot=SimpleNamespace(account="123")))
    commands = CommandRegistry()
    rt = PluginRuntime(
        plugin_dir=tmp_path / "user",
        data_dir=tmp_path / "data",
        builtin_plugin_dirs=(root,),
        state_store=PluginStateStore(tmp_path / "state.json"),
        adapter=object(),
        logger_factory=SimpleNamespace(get_logger=lambda _: NullLogger()),
        host=host,
        app_commands=commands,
    )
    rt.load_all()
    await rt.load_registered()
    await rt.start_all()
    yield rt, policy, commands
    for name in reversed(rt.manager.names()):
        await rt.unload_plugin(name)


async def test_real_lifecycle_consumer_hook(runtime):
    rt, policy, commands = runtime
    assert not policy.has_policies
    assert rt.control.get("speaking_schedule").enabled is False
    result = await rt.set_enabled("speaking_schedule", True)
    assert result.ok, result.error
    assert policy.has_policies
    consumer = rt.control.config_consumer("speaking_schedule")
    assert consumer is not None
    await consumer.apply_config(
        {"timezone": "UTC", "windows": [dict(weekdays=[1], start="00:00", end="00:01")], "overrides": []}
    )
    assert consumer.config.timezone == "UTC"
    await rt.hook_bus.dispatch(
        SimpleNamespace(
            raw_event={"post_type": "message", "self_id": 123, "time": int(datetime.now(timezone.utc).timestamp())},
            consumed=False,
        )
    )
    assert "正常" in consumer.clock.status()
    assert commands.get("作息").permission == 1
    await rt.set_enabled("speaking_schedule", False)
    assert not policy.has_policies
    assert rt.control.config_consumer("speaking_schedule") is None
    assert commands.get("作息") is None


async def test_real_reload_recovers_config_and_mute(runtime):
    from neobot_contracts.models import ConversationRef

    rt, policy, commands = runtime
    assert (await rt.set_enabled("speaking_schedule", True)).ok
    consumer = rt.control.config_consumer("speaking_schedule")
    await consumer.save_config({"timezone": "UTC", "windows": [], "overrides": []})
    consumer.mutes.set("123", "group:42", 60)
    assert not policy.evaluate(ConversationRef("group", "42")).allowed
    assert (await rt.set_enabled("speaking_schedule", False)).ok
    assert policy.evaluate(ConversationRef("group", "42")).allowed
    assert (await rt.set_enabled("speaking_schedule", True)).ok
    recovered = rt.control.config_consumer("speaking_schedule")
    assert recovered is not consumer
    assert recovered.config.timezone == "UTC"
    assert not policy.evaluate(ConversationRef("group", "42")).allowed
    assert commands.get("作息") is not None
    latest = consumer.clock.latest
    await rt.hook_bus.dispatch(
        SimpleNamespace(
            raw_event={"post_type": "message", "self_id": 123, "time": int(datetime.now(timezone.utc).timestamp())},
            consumed=False,
        )
    )
    assert recovered.clock.latest is not None
    assert consumer.clock.latest == latest


@pytest.mark.parametrize("enabled", [False, True])
async def test_real_snapshot_advertises_config_hot_reload(runtime, enabled):
    rt, _, _ = runtime
    if enabled:
        assert (await rt.set_enabled("speaking_schedule", True)).ok
    snapshot = rt.control.get("speaking_schedule")
    assert snapshot.enabled is enabled
    assert snapshot.config_hot_reload is True


async def test_dashboard_save_applies_consumer_without_reloading(runtime, monkeypatch):
    import importlib
    import json
    from unittest.mock import AsyncMock

    from neobot_app.builtin_plugins.dashboard.api import DashboardApi
    from neobot_contracts.models import ConversationRef
    from neobot_contracts.ports.logging import NullLogger

    rt, policy, commands = runtime
    assert (await rt.set_enabled("speaking_schedule", True)).ok
    consumer = rt.control.config_consumer("speaking_schedule")
    original_command = commands.get("作息")
    monkeypatch.setattr(
        importlib.import_module(type(consumer).__module__),
        "utc_now",
        lambda: datetime(2026, 11, 2, 12, tzinfo=timezone.utc),
    )
    reload = AsyncMock(side_effect=AssertionError("consumer must apply without reloading"))
    monkeypatch.setattr(rt.control, "reload", reload)
    api = DashboardApi(
        console=SimpleNamespace(
            plugin_control=rt.control, manage_plugins=True, allow_remote_manage=True, logger=NullLogger()
        )
    )
    request = SimpleNamespace(match_info={"name": "speaking_schedule"})
    before = json.loads((await api.plugin_config_get(request)).text)
    assert policy.evaluate(ConversationRef("group", "43")).allowed
    config = {
        "timezone": "UTC",
        "windows": [dict(weekdays=[1], start="09:00", end="10:00", next_day=False)],
        "overrides": [dict(kind="group", id="42", windows=[])],
    }
    request.can_read_body = True
    request.json = AsyncMock(return_value={"config": config, "revision": before["revision"], "reload": True})
    response = await api.plugin_config_save(request)
    saved = json.loads(response.text)
    assert response.status == 200 and saved["ok"] and saved["applied"], saved
    assert saved["changes"]["hot_reload_count"] == 3
    assert saved["changes"]["needs_restart_count"] == 0
    assert consumer.config.model_dump() == config == consumer.ctx.config
    assert rt.control.plugin_config_values("speaking_schedule") == config
    assert rt.control.config_consumer("speaking_schedule") is consumer
    assert commands.get("作息") is original_command
    assert not policy.evaluate(ConversationRef("group", "43")).allowed
    assert policy.evaluate(ConversationRef("group", "42")).allowed
    reload.assert_not_awaited()
    assert saved["config_hot_reload"] is True
