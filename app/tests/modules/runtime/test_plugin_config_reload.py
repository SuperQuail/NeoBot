"""插件配置「原地生效」判定与编排（bugfixes/feat(2) §6）。"""

from __future__ import annotations

from typing import Any

from neobot_app.config.hot_reload import HotReloadRule
from neobot_app.runtime.plugin_config_reload import (
    PluginConfigChange,
    apply_plugin_config_change,
    classify_plugin_path,
    diff_plugin_config,
    diff_summary,
    plugin_config_path,
)


class _Consumer:
    config_paths = ("plugin.demo",)
    hot_reload_policies = (
        HotReloadRule("plugin.demo.interval", True, "运行期安全"),
        HotReloadRule("plugin.demo.port", False, "需要重启"),
    )

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.applied: list[dict[str, Any]] = []

    async def apply_config(self, config: dict[str, Any]) -> None:
        if self.fail:
            raise RuntimeError("boom")
        self.applied.append(dict(config))


def test_plugin_config_path_namespace() -> None:
    assert plugin_config_path("dashboard", "port") == "plugin.dashboard.port"


def test_classify_uses_longest_prefix() -> None:
    consumer = _Consumer()
    # 全局默认（plugin.demo.* 未声明的子路径）由更短的前缀规则命中
    assert classify_plugin_path(consumer, "plugin.demo.interval")[0] is True
    assert classify_plugin_path(consumer, "plugin.demo.port")[0] is False
    assert classify_plugin_path(consumer, "plugin.demo.other")[0] is False
    assert "未声明" in classify_plugin_path(consumer, "plugin.demo.other")[1]


def test_diff_marks_hot_and_restart() -> None:
    changes = diff_plugin_config(
        _Consumer(),
        plugin_name="demo",
        before={"interval": 15, "port": 9981, "same": 1},
        after={"interval": 60, "port": 9999, "same": 1},
    )
    by_key = {item.key: item for item in changes}
    assert set(by_key) == {"interval", "port"}
    assert by_key["interval"].hot_reload is True
    assert by_key["port"].hot_reload is False


def test_diff_summary_shape_matches_bot_config() -> None:
    changes = [
        PluginConfigChange("plugin.demo.interval", "interval", 15, 60, True, "运行期安全"),
        PluginConfigChange("plugin.demo.port", "port", 9981, 9999, False, "需要重启"),
    ]
    summary = diff_summary(changes)
    assert summary["hot_reload_count"] == 1
    assert summary["needs_restart_count"] == 1


async def test_apply_calls_consumer_for_hot_changes_only() -> None:
    consumer = _Consumer()

    result = await apply_plugin_config_change(
        consumer, plugin_name="demo", before={"interval": 15}, after={"interval": 60}
    )

    assert result.ok is True
    assert result.applied == ("interval",)
    assert consumer.applied == [{"interval": 60}]


async def test_no_hot_change_does_not_touch_consumer() -> None:
    consumer = _Consumer()

    result = await apply_plugin_config_change(
        consumer, plugin_name="demo", before={"port": 9981}, after={"port": 9999}
    )

    assert result.ok is False
    assert result.needs_restart == ("port",)
    assert consumer.applied == []
    assert result.error == ""


async def test_no_change_is_a_noop() -> None:
    consumer = _Consumer()

    result = await apply_plugin_config_change(
        consumer, plugin_name="demo", before={"interval": 15}, after={"interval": 15}
    )

    assert result.ok is False
    assert result.has_changes is False
    assert consumer.applied == []


async def test_failure_is_reported_and_consumer_state_untouched() -> None:
    consumer = _Consumer(fail=True)

    result = await apply_plugin_config_change(
        consumer, plugin_name="demo", before={"interval": 15}, after={"interval": 60}
    )

    assert result.ok is False
    assert "RuntimeError" in result.error
    assert consumer.applied == []


async def test_hot_and_restart_can_coexist() -> None:
    consumer = _Consumer()

    result = await apply_plugin_config_change(
        consumer,
        plugin_name="demo",
        before={"interval": 15, "port": 9981},
        after={"interval": 60, "port": 9999},
    )

    assert result.ok is True
    assert result.applied == ("interval",)
    assert result.needs_restart == ("port",)
