from datetime import datetime
import importlib.util
import pytest

PACKAGE = "neobot_app.builtin_plugins.speaking_schedule"


def test_plugin_package_exists():
    assert importlib.util.find_spec(PACKAGE) is not None


def modules():
    from neobot_app.builtin_plugins.speaking_schedule.config import ScheduleConfig
    from neobot_app.builtin_plugins.speaking_schedule.schedule import evaluate, next_boundary

    return ScheduleConfig, evaluate, next_boundary


@pytest.mark.parametrize(
    "stamp,allowed",
    [("2026-11-01T23:30:00+08:00", True), ("2026-11-02T00:30:00+08:00", True), ("2026-11-02T01:00:00+08:00", False)],
)
def test_week_wrap(stamp, allowed):
    from neobot_contracts.models import ConversationRef

    C, evaluate, boundary = modules()
    cfg = C(windows=[dict(weekdays=[7], start="23:00", end="01:00", next_day=True)])
    now = datetime.fromisoformat(stamp)
    assert evaluate(cfg, ConversationRef("group", "1"), now).allowed is allowed
    assert boundary(cfg, ConversationRef("group", "1"), now) > now


@pytest.mark.parametrize(
    "windows",
    [
        [dict(weekdays=[1], start="23:00", end="01:00")],
        [dict(weekdays=[1], start="01:00", end="02:00", next_day=True)],
        [dict(weekdays=[1], start="01:00", end="01:00")],
        [dict(weekdays=[7], start="23:00", end="01:00", next_day=True), dict(weekdays=[1], start="00:30", end="02:00")],
    ],
)
def test_invalid_windows(windows):
    C, _, _ = modules()
    with pytest.raises(ValueError):
        C(windows=windows)


def test_overrides_and_defaults_isolated():
    from neobot_contracts.models import ConversationRef

    C, evaluate, _ = modules()
    a, b = C(), C()
    a.windows.append("sentinel")
    assert b.windows == []
    cfg = C(
        windows=[dict(weekdays=[1], start="09:00", end="10:00")], overrides=[dict(kind="group", id="1", windows=[])]
    )
    now = datetime.fromisoformat("2026-11-02T12:00:00+08:00")
    assert evaluate(cfg, ConversationRef("group", "1"), now).allowed
    assert not evaluate(cfg, ConversationRef("private", "1"), now).allowed
    with pytest.raises(ValueError):
        C(overrides=[dict(kind="group", id="1", windows=[])] * 2)


def test_multiple_windows_adjacent_and_override_replacement():
    from neobot_contracts.models import ConversationRef

    C, evaluate, boundary = modules()
    cfg = C(
        timezone="UTC",
        windows=[
            dict(weekdays=[1], start="09:00", end="10:00"),
            dict(weekdays=[1], start="10:00", end="11:00"),
            dict(weekdays=[1], start="14:00", end="15:00"),
        ],
        overrides=[dict(kind="private", id="1", windows=[dict(weekdays=[1], start="20:00", end="21:00")])],
    )
    group, private = ConversationRef("group", "1"), ConversationRef("private", "1")
    now = datetime.fromisoformat("2026-11-02T09:30:00+00:00")
    assert evaluate(cfg, group, now).allowed
    assert not evaluate(cfg, private, now).allowed
    assert boundary(cfg, group, now).hour == 11
    assert evaluate(cfg, group, now.replace(hour=14)).allowed
    assert not evaluate(cfg, group, now.replace(hour=12)).allowed
    assert evaluate(cfg, private, now.replace(hour=20)).allowed
    with pytest.raises(ValueError):
        C(timezone="Invalid/Nowhere")


@pytest.mark.parametrize(
    "start,end,stamp,expected",
    [
        ("02:00", "02:30", "2026-03-07T00:00:00-05:00", "2026-03-15T02:00:00-04:00"),
        ("01:15", "01:45", "2026-11-01T01:30:00-04:00", "2026-11-01T01:45:00-04:00"),
        ("01:15", "01:45", "2026-11-01T01:50:00-04:00", "2026-11-01T01:15:00-05:00"),
        ("01:15", "01:45", "2026-11-01T01:30:00-05:00", "2026-11-01T01:45:00-05:00"),
        ("09:00", "10:00", "2026-03-08T08:59:30-04:00", "2026-03-08T09:00:00-04:00"),
        ("09:00", "10:00", "2026-03-08T09:00:00-04:00", "2026-03-08T10:00:00-04:00"),
    ],
)
def test_dst_and_normal_next_boundary(start, end, stamp, expected):
    from datetime import timedelta, timezone
    from neobot_contracts.models import ConversationRef

    C, evaluate, boundary = modules()
    cfg = C(timezone="America/New_York", windows=[dict(weekdays=[7], start=start, end=end)])
    conversation = ConversationRef("group", "1")
    now = datetime.fromisoformat(stamp)
    result = boundary(cfg, conversation, now)
    assert result is not None
    assert result.isoformat() == expected
    real_boundary = result.astimezone(timezone.utc)
    assert (
        evaluate(cfg, conversation, real_boundary - timedelta(seconds=1)).allowed
        != evaluate(cfg, conversation, real_boundary).allowed
    )
