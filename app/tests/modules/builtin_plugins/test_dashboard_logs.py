"""日志缓冲保留脱敏上下文，API 指标独立计数。"""

from types import SimpleNamespace

from neobot_contracts.ports.logging import NullLogger
from neobot_contracts.ports.runtime_event import RuntimeEnvelope
from neobot_modloader.hooks import PluginHookBus

from neobot_app.builtin_plugins.dashboard import DashboardPlugin
from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.metrics import Metrics


def test_log_buffer_preserves_context_and_original_timestamp(tmp_path) -> None:
    metrics = Metrics(data_dir=tmp_path)
    payload = {
        "time": "2026-10-31T10:20:30+08:00",
        "timestamp": 0,
        "level": "ERROR",
        "module": "app.reply",
        "message": "请求失败",
        "file": "app/src/neobot_app/reply/orchestrator.py",
        "line": 42,
        "function": "reply",
        "fields": {"conversation_id": "test-group", "request": {"token": "***REDACTED***"}},
        "exception": {
            "type": "ValueError",
            "message": "请求内容无效",
            "traceback": "Traceback (most recent call last):\nValueError: 请求内容无效",
        },
    }

    metrics.record_log(payload)
    payload["fields"]["request"]["token"] = "changed"
    payload["exception"]["message"] = "changed"

    item = metrics.logs()["items"][0]
    assert item["message"] == "请求失败"
    assert item["time"] == "10:20:30"
    assert item["timestamp"] == item["ts"] == 0
    assert item["file"] == "app/src/neobot_app/reply/orchestrator.py"
    assert item["line"] == 42
    assert item["function"] == "reply"
    assert item["fields"]["request"]["token"] == "***REDACTED***"
    assert item["exception"]["message"] == "请求内容无效"


def test_legacy_log_events_keep_empty_context_without_counting_api_calls(tmp_path) -> None:
    metrics = Metrics(data_dir=tmp_path)
    metrics.record_log({"message": "发送API请求: {'action': 'get_status'}"})

    item = metrics.logs()["items"][0]
    assert item["fields"] == {}
    assert item["exception"] is None
    assert item["file"] == item["function"] == ""
    assert item["line"] is None
    assert metrics.api_calls()["total_calls"] == 0


def test_explicit_api_metrics_count_without_log_text_or_duplicate_counting(tmp_path) -> None:
    metrics = Metrics(data_dir=tmp_path)
    metrics.record_api_call("get_status")
    metrics.record_api_call("get_status")
    metrics.record_api_call("send_group_msg")
    metrics.record_api_call("")
    metrics.record_log({"message": "发送API请求: {'action': 'get_status'}"})

    assert metrics.api_calls() == {
        "total_calls": 3,
        "unique_actions": 2,
        "items": [
            {"action": "get_status", "count": 2},
            {"action": "send_group_msg", "count": 1},
        ],
    }
    assert metrics.logs()["total"] == 1


async def test_metric_subscription_stays_separate_from_logs_and_stops_on_unload(tmp_path, monkeypatch) -> None:
    from neobot_app.builtin_plugins import dashboard
    from neobot_app.builtin_plugins.dashboard import system

    metrics = Metrics(data_dir=tmp_path)

    async def noop(*_args) -> None:
        pass

    server = SimpleNamespace(metrics=metrics, start=noop, stop=noop)
    monkeypatch.setattr(dashboard, "DashboardServer", lambda **_kwargs: server)
    monkeypatch.setattr(system, "prime", lambda: None)
    plugin = DashboardPlugin()
    monkeypatch.setattr(plugin, "_register_status_command", lambda _ctx: None)
    monkeypatch.setattr(plugin, "_register_config_consumer", lambda _ctx: None)
    monkeypatch.setattr(plugin, "_start_latency_task", noop)
    bus = PluginHookBus()
    subscriptions = []
    ctx = SimpleNamespace(
        config=DashboardConfig(),
        logger=NullLogger(),
        plugin_name="dashboard",
        data_dir=tmp_path,
        hook_bus=bus,
        record_subscription=subscriptions.append,
    )
    await plugin.load(ctx)
    try:
        assert len(subscriptions) == 2
        metric = RuntimeEnvelope(kind="metric", stage="onebot.api.sent", payload={"action": "get_status"})
        await bus.dispatch_envelope(metric)
        await bus.dispatch_envelope(RuntimeEnvelope(kind="metric", stage="other", payload={"action": "ignore"}))
        await bus.dispatch_envelope(RuntimeEnvelope(kind="metric", stage="onebot.api.sent", payload={"action": 123}))
        assert metrics.logs()["total"] == 0
        assert metrics.api_calls()["items"] == [{"action": "get_status", "count": 1}]
        await bus.dispatch_envelope(
            RuntimeEnvelope(kind="log", stage="info", payload={"message": "发送API请求: {'action': 'get_status'}"})
        )
        assert metrics.logs()["total"] == 1
        assert metrics.api_calls()["total_calls"] == 1
    finally:
        await plugin.unload()

    await bus.dispatch_envelope(metric)
    assert metrics.api_calls()["total_calls"] == 1
    for subscription in subscriptions:
        subscription.unsubscribe()
