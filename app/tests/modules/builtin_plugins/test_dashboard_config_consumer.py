"""dashboard 插件配置消费者：原地生效声明与失败回滚（bugfixes/feat(2) §6）。

守住三件事：
1. 运行期安全字段（探针四项 / bot_info_cache_ttl / log_buffer_size / history_max_days）保存即生效；
2. 绑定期与安全类字段（host / port / base_path / manage_plugins ...）仍要求重启；
3. apply_config 失败时**旧配置保持不变**，错误向上传播给面板。
"""

from __future__ import annotations


import pytest

from neobot_app.builtin_plugins.dashboard import DashboardPlugin
from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.hot_reload import DashboardConfigConsumer
from neobot_app.builtin_plugins.dashboard.metrics import Metrics
from neobot_app.runtime.plugin_config_reload import classify_plugin_path


class _StubServer:
    def __init__(self) -> None:
        self.applied: list[DashboardConfig] = []
        self.fail = False

    def apply_runtime_config(self, config: DashboardConfig) -> None:
        if self.fail:
            raise RuntimeError("监听侧拒绝应用")
        self.applied.append(config)


def _plugin() -> tuple[DashboardPlugin, _StubServer]:
    plugin = DashboardPlugin()
    plugin.config = DashboardConfig()
    server = _StubServer()
    plugin.server = server  # type: ignore[assignment]
    return plugin, server


async def test_runtime_safe_config_applies_in_place() -> None:
    plugin, server = _plugin()
    consumer = DashboardConfigConsumer(plugin)

    await consumer.apply_config({"latency_probe_interval_seconds": 120, "log_buffer_size": 300})

    assert plugin.config is not None
    assert plugin.config.latency_probe_interval_seconds == 120
    assert server.applied[-1].latency_probe_interval_seconds == 120
    assert server.applied[-1].log_buffer_size == 300


def test_binding_and_security_fields_require_restart() -> None:
    consumer = DashboardConfigConsumer(DashboardPlugin())

    for key in ("host", "port", "base_path", "manage_plugins", "allow_remote_manage",
                "session_timeout_minutes", "secure_cookies", "trust_proxy_headers",
                "login_max_failures", "login_rate_limit_window_seconds"):
        hot, reason = classify_plugin_path(consumer, f"plugin.dashboard.{key}")
        assert hot is False, f"{key} 必须仍然要求重启"
        assert reason


def test_runtime_safe_fields_are_declared_hot() -> None:
    consumer = DashboardConfigConsumer(DashboardPlugin())

    for key in ("latency_probe_interval_seconds", "latency_probe_idle_seconds",
                "latency_probe_active_window_seconds", "latency_probe_gate_check_seconds",
                "bot_info_cache_ttl", "log_buffer_size", "history_max_days"):
        hot, reason = classify_plugin_path(consumer, f"plugin.dashboard.{key}")
        assert hot is True, f"{key} 应当可以运行期生效"
        assert reason


def test_unknown_field_defaults_to_restart() -> None:
    """保守假设：新增字段若忘记登记，按「需要重启」处理，不能误判为热重载。"""
    consumer = DashboardConfigConsumer(DashboardPlugin())

    hot, reason = classify_plugin_path(consumer, "plugin.dashboard.brand_new_field")

    assert hot is False
    assert "未声明" in reason


async def test_invalid_config_is_rejected_and_state_kept() -> None:
    plugin, server = _plugin()
    consumer = DashboardConfigConsumer(plugin)

    with pytest.raises(Exception):
        await consumer.apply_config({"port": 70000})

    assert plugin.config is not None and plugin.config.port == 9981
    assert server.applied == []


async def test_server_failure_keeps_old_plugin_config() -> None:
    plugin, server = _plugin()
    server.fail = True
    consumer = DashboardConfigConsumer(plugin)

    with pytest.raises(RuntimeError, match="监听侧拒绝应用"):
        await consumer.apply_config({"latency_probe_interval_seconds": 90})

    assert plugin.config is not None
    assert plugin.config.latency_probe_interval_seconds == 60


def test_metrics_runtime_setters_rebuild_buffers(tmp_path) -> None:
    metrics = Metrics(data_dir=tmp_path, log_buffer_size=3)
    for index in range(5):
        metrics.record_log({"message": f"m{index}", "time": "", "timestamp": 0})
    assert metrics.logs()["total"] == 3

    metrics.set_log_buffer_capacity(2)
    items = metrics.logs()["items"]
    assert [item["message"] for item in items] == ["m3", "m4"]

    metrics._stats["history"] = [{"date": f"2026-01-{i:02d}", "count": i} for i in range(1, 10)]
    metrics.set_history_max_days(3)
    assert len(metrics._stats["history"]) == 3
    assert metrics._stats["history"][-1]["date"] == "2026-01-09"


def test_latency_staleness_hides_old_samples() -> None:
    import time

    metrics = Metrics(data_dir=__import__("pathlib").Path("."), latency_samples=60)
    assert metrics.latency_series()["stale"] is False

    metrics.record_latency(12.5, ok=True)
    assert metrics.latency_series()["current_ms"] == 12.5

    metrics.set_latency_stale_after(0.001)
    time.sleep(0.01)
    result = metrics.latency_series()
    assert result["stale"] is True
    assert result["current_ms"] is None
