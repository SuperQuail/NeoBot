"""schema 默认值 与 运行期回退值 必须一致。

审查发现两处「同一配置项两个默认值」：字段缺失时的 getattr 回退与 dataclass
默认值、schema 默认值互相矛盾，会让同一份配置在不同代码路径下表现不同。
"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.config.schemas.bot import Chat, ScheduledTask
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.runtime.scheduled_tasks import ScheduledTaskConfig


def _bare_orchestrator(config) -> ReplyOrchestrator:
    orchestrator = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orchestrator._config = config
    return orchestrator


# ── reply_mode ──────────────────────────────────────────────────────


def test_reply_mode_schema_default_is_agent() -> None:
    assert Chat().reply_mode == "agent"


def test_resolve_mode_fallback_matches_schema_default() -> None:
    """字段缺失/配置为空时必须回退到 schema 默认值 agent，而不是 common。"""
    assert _bare_orchestrator(None)._resolve_mode() == "agent"
    assert _bare_orchestrator(SimpleNamespace(chat=SimpleNamespace()))._resolve_mode() == "agent"


def test_resolve_mode_honours_explicit_common() -> None:
    config = SimpleNamespace(chat=SimpleNamespace(reply_mode="common"))
    assert _bare_orchestrator(config)._resolve_mode() == "common"


def test_resolve_mode_rejects_unknown_value() -> None:
    config = SimpleNamespace(chat=SimpleNamespace(reply_mode="nonsense"))
    assert _bare_orchestrator(config)._resolve_mode() == "agent"


# ── poll_interval_seconds ───────────────────────────────────────────


def test_poll_interval_schema_default_is_ten() -> None:
    assert ScheduledTask().poll_interval_seconds == 10


def test_scheduled_task_config_defaults_match_schema() -> None:
    assert ScheduledTaskConfig().poll_interval_seconds == 10
    built = ScheduledTaskConfig.from_schema(SimpleNamespace())
    assert built.poll_interval_seconds == 10


def test_poll_interval_override_is_honoured() -> None:
    built = ScheduledTaskConfig.from_schema(
        SimpleNamespace(poll_interval_seconds=30)
    )
    assert built.poll_interval_seconds == 30


# ── missed_window_grace_seconds ─────────────────────────────────────


def test_missed_window_grace_schema_default_is_five_minutes() -> None:
    assert ScheduledTask().missed_window_grace_seconds == 300


def test_missed_window_grace_config_defaults_match_schema() -> None:
    assert ScheduledTaskConfig().missed_window_grace_seconds == 300
    built = ScheduledTaskConfig.from_schema(SimpleNamespace())
    assert built.missed_window_grace_seconds == 300


def test_missed_window_grace_override_is_honoured() -> None:
    built = ScheduledTaskConfig.from_schema(
        SimpleNamespace(missed_window_grace_seconds=60)
    )
    assert built.missed_window_grace_seconds == 60
