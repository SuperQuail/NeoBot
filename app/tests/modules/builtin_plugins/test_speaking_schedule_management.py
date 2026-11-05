from types import SimpleNamespace
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest
import tomlkit

from neobot_app.builtin_plugins.speaking_schedule.commands import HELP, run_command
from neobot_app.builtin_plugins.speaking_schedule.runtime import ScheduleRuntime
from neobot_app.builtin_plugins.speaking_schedule.state import ClockHealth, MuteStore
from neobot_app.commands.permissions import PermissionManager
from neobot_app.runtime.speaking_policy import SpeakingPolicyRegistry
from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.speaking import SpeakingDecision
from neobot_modloader.host import PluginHostFacade


@pytest.fixture
def subject(tmp_path):
    host = PluginHostFacade()
    registry = SpeakingPolicyRegistry()
    host.services.register("speaking_policy", registry)
    host.services.register("config", SimpleNamespace(bot=SimpleNamespace(account="123")))
    ctx = SimpleNamespace(plugin_host=host, config={}, data_dir=tmp_path, send=AsyncMock())
    runtime = ScheduleRuntime(ctx)
    registry.register("speaking_schedule", runtime.evaluate)
    return runtime


def command(args, *, user=1, kind="group"):
    permissions = PermissionManager(
        SimpleNamespace(chat=SimpleNamespace(admin_accounts=["1"], sub_admin_accounts=["2"]))
    )
    return SimpleNamespace(
        service=SimpleNamespace(permissions=permissions), user_id=user, kind=kind, conv_id="42", args=args
    )


@pytest.mark.parametrize(
    "args", [["状态"], ["设置", "默认", "1", "09:00-10:00"], ["静默", "默认", "1h"], ["恢复", "默认"]]
)
async def test_unauthorized_cannot_send_or_write(subject, args):
    subject.registry.bypass = lambda _: pytest.fail("unauthorized bypass")
    assert await run_command(subject, command(args, user=3)) is None
    subject.ctx.send.assert_not_awaited()
    assert list(subject.ctx.data_dir.iterdir()) == []


@pytest.mark.parametrize("user", [1, 2])
async def test_admin_direct_reply_scopes_bypass(subject, user):
    conversation = ConversationRef("group", "42")
    subject.mutes.set("123", "default", 60)
    other = subject.registry.register("other", lambda _: SpeakingDecision(False, "other policy"))

    async def send(conv, text):
        assert conv == conversation
        assert "临时静默" in text
        assert subject.registry.evaluate(conv).reason == "other policy"
        other()
        assert subject.registry.evaluate(conv).allowed

    subject.ctx.send.side_effect = send
    assert await run_command(subject, command(["状态"], user=user)) is None
    subject.ctx.send.assert_awaited_once()
    assert subject.registry.evaluate(conversation).reason == "临时静默"


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["设置", "本私聊", "1", "10:00-11:00"],
        ["设置", "默认", "0", "bad"],
        ["静默", "默认", "0m"],
        ["恢复", "未知"],
        ["设置", "默认", "1", "10:00-11:00", "wrong"],
    ],
)
async def test_invalid_help_is_deterministic(subject, args):
    await run_command(subject, command(args))
    assert subject.ctx.send.await_args.args[1] == HELP
    assert list(subject.ctx.data_dir.iterdir()) == []


async def test_save_sync_comments_and_atomic_rollback(subject, monkeypatch):
    path = subject.ctx.data_dir / "config.toml"
    source = '# user zone\ntimezone = "UTC" # inline\n# user windows\nwindows = []\n\n[[overrides]]\n# retained conversation\nkind = "private"\nid = "5"\nwindows = []\n'
    path.write_text(source, encoding="utf-8")
    await subject.apply_config(tomlkit.parse(source).unwrap())
    await run_command(subject, command(["设置", "默认", "1,3", "09:00-10:00"]))
    stored = path.read_text(encoding="utf-8")
    assert "# retained conversation" in stored
    assert "# user zone" in stored and "# inline" in stored and "# user windows" in stored
    assert subject.ctx.config == subject.config.model_dump() == tomlkit.parse(stored).unwrap()
    before = subject.config.model_dump()
    import neobot_app.builtin_plugins.speaking_schedule.state as state

    def fail(*args):
        raise OSError("read-only")

    monkeypatch.setattr(state.os, "replace", fail)
    await run_command(subject, command(["设置", "默认", "2", "12:00-13:00"]))
    assert subject.config.model_dump() == before == subject.ctx.config
    assert path.read_text(encoding="utf-8") == stored
    assert "保存失败" in subject.ctx.send.await_args.args[1]
    assert not list(subject.ctx.data_dir.glob(".schedule-*"))


async def test_restore_keeps_schedule_and_account_isolation(subject, monkeypatch):
    import neobot_app.builtin_plugins.speaking_schedule.runtime as module

    monkeypatch.setattr(module, "utc_now", lambda: datetime(2026, 11, 2, 12, tzinfo=timezone.utc))
    await subject.apply_config({"timezone": "UTC", "windows": [dict(weekdays=[1], start="09:00", end="10:00")]})
    subject.mutes.set("123", "group:42", 60)
    subject.mutes.set("456", "group:42", 60)
    await run_command(subject, command(["恢复", "本群"]))
    assert subject.evaluate(ConversationRef("group", "42")).reason == "不在允许发言时段"
    assert subject.mutes.remaining("456", "group:42") > 0


def test_clock_account_switch_and_staleness():
    mono = [0.0]
    clock = ClockHealth(monotonic=lambda: mono[0])
    assert clock.sample({"self_id": 1, "time": 1000}, "1", 1000)
    assert clock.sample({"self_id": 2, "time": 999}, "2", 1000)
    assert clock.latest == 999
    mono[0] = 301
    assert "过期" in clock.status()
    for stamp in [True, float("nan"), float("inf"), "1000", None, 1121, 879]:
        assert not clock.sample({"self_id": 2, "time": stamp}, "2", 1000)
    assert clock.sample({"self_id": 2, "time": 1120}, "2", 1000)


def test_mute_expiry_boundaries_and_rollback(tmp_path, monkeypatch):
    import neobot_app.builtin_plugins.speaking_schedule.state as state

    wall = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    mono = [0.0]
    path = tmp_path / "mutes.json"
    store = MuteStore(path, now=lambda: wall[0], monotonic=lambda: mono[0])
    for seconds in [0, -1, float("nan"), float("inf"), 365 * 86400 + 1]:
        with pytest.raises(ValueError):
            store.set("a", "default", seconds)
    store.set("a", "default", 60)
    original = path.read_bytes()

    def fail(*args):
        raise OSError("read-only")

    monkeypatch.setattr(state, "atomic_write", fail)
    with pytest.raises(OSError):
        store.set("a", "default", 120)
    with pytest.raises(OSError):
        store.clear("a", "default")
    assert store.remaining("a", "default") == 60 and path.read_bytes() == original
    wall[0] += timedelta(seconds=60)
    assert MuteStore(path, now=lambda: wall[0]).remaining("a", "default") == 0
    mono[0] = 60
    assert store.remaining("a", "default") == 0


async def test_send_exception_revokes_bypass(subject):
    conversation = ConversationRef("group", "42")
    subject.mutes.set("123", "default", 60)
    subject.ctx.send.side_effect = OSError("transport failed")
    with pytest.raises(OSError):
        await run_command(subject, command(["状态"]))
    assert not subject.registry.evaluate(conversation).allowed


async def test_scope_override_preserves_other_comments(subject):
    path = subject.ctx.data_dir / "config.toml"
    path.write_text(
        'timezone = "UTC"\nwindows = []\n[[overrides]]\n# private note\nkind = "private"\nid = "5"\nwindows = []\n',
        encoding="utf-8",
    )
    await subject.apply_config(tomlkit.parse(path.read_text()).unwrap())
    await run_command(subject, command(["设置", "本群", "2", "22:00-01:00", "次日"]))
    assert "# private note" in path.read_text()
    assert subject.config.overrides[1].windows[0].next_day
    assert subject.config.overrides[0].id == "5"


async def test_invalid_hot_update_keeps_effective_config(subject):
    original = subject.config.model_dump()
    with pytest.raises(ValueError):
        await subject.apply_config({"timezone": "Invalid/Zone"})
    assert subject.config.model_dump() == original
    assert subject.ctx.config == {}


async def test_account_switch_status_discards_previous_health(subject):
    assert subject.clock.sample({"self_id": 123, "time": 1000}, "123", 1000)
    subject.ctx.plugin_host.services.get("config").bot.account = "456"
    assert "未收到本账号" in subject.status(ConversationRef("group", "42"))
