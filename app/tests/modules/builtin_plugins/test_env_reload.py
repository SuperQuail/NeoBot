"""保存 .env 后的热重载契约（issue #74）。

背景：.env 的值不进 config.toml 的配置快照，所以「只改环境变量」时配置 diff 是空的，
热重载消费者一个都不会被触发 —— 新凭据要等重启才生效，而面板却提示
「配置已重载，本次没有检测到配置项变化」。这里钉住三件事：

1. 保存 env 时必须**显式声明** env 这条变更路径（否则消费者不触发）；
2. provider 消费者必须声明关心 env，且能被这条路径选中；
3. 提示文案必须说清「哪些已重建、哪些仍需重启进程」，不能复用 diff 空分支那句话。
"""

from __future__ import annotations

from typing import Any

from neobot_app.builtin_plugins.dashboard.api import (
    ENV_RESTART_HINT,
    DashboardApi,
    _env_reload_message,
)
from neobot_app.runtime.hot_reload_registry import HotReloadRegistry
from neobot_app.runtime.provider_reload import ProviderReloadConsumer


# ── 1. 文案契约 ───────────────────────────────────────────────


def test_message_without_env_change_does_not_demand_restart() -> None:
    message, needs_restart = _env_reload_message({}, env_written=False)
    assert needs_restart is False
    assert "未检测到环境变量改动" in message
    assert "重启进程" not in message


def test_message_after_provider_rebuilt_lists_scope_and_restart_hint() -> None:
    """重建成功：说明覆盖范围，并且仍然提示重启（TTS/生图等覆盖不到）。"""
    result = {
        "hot_reload": {
            "applied": [{"name": "provider", "applied": True}],
            "failed": [],
        }
    }
    message, needs_restart = _env_reload_message(result, env_written=True)

    assert needs_restart is True
    assert "已重建 provider" in message
    assert "主对话" in message and "视觉" in message and "档案总结" in message
    assert ENV_RESTART_HINT in message
    # 绝不能出现「没有检测到配置项变化」这句误导话术
    assert "没有检测到配置项变化" not in message


def test_message_reports_rebuild_failure() -> None:
    """重建失败：必须说清仍在用旧凭据，并带上原因。"""
    result = {
        "hot_reload": {
            "applied": [],
            "failed": [{"name": "provider", "applied": False, "error": "api_key 无效"}],
        }
    }
    message, needs_restart = _env_reload_message(result, env_written=True)

    assert needs_restart is True
    assert "重建失败" in message
    assert "api_key 无效" in message
    assert "旧凭据" in message


# ── 2. 消费者声明 ─────────────────────────────────────────────


def test_provider_consumer_declares_env_path() -> None:
    """provider 消费者必须声明关心 env —— 平台凭据来自 .env。"""
    consumer = ProviderReloadConsumer(builder=lambda config: None, installers={})
    assert "env" in consumer.config_paths
    assert "models" in consumer.config_paths


def _preserve_global_rules(*paths: str):
    """注册消费者会把策略写进**进程级**全局规则表，且 `unregister_rule` 会连基线一起删。

    `HotReloadRegistry.register` -> `register_rules(consumer.hot_reload_policies)`
    （`runtime/hot_reload_registry.py:152`）改写的是 `config/hot_reload.py` 的模块全局
    `RULES`。不还原的话，后续用例看到的「分类基线」已经被污染 —— 实测会让
    `test_hot_reload.py::test_classify_known_paths` 因顺序不同而失败。
    所以这里先快照、后还原（不能直接 unregister，那会把基线条目一起删掉）。
    """

    from contextlib import contextmanager

    from neobot_app.config import hot_reload

    @contextmanager
    def _ctx():
        backup = {
            path: next((rule for rule in hot_reload.RULES if rule.path == path), None)
            for path in paths
        }
        try:
            yield
        finally:
            hot_reload.RULES = tuple(
                rule for rule in hot_reload.RULES if rule.path not in paths
            )
            for rule in backup.values():
                if rule is not None:
                    hot_reload.register_rule(rule)

    return _ctx()


def test_env_path_selects_provider_consumer() -> None:
    """给注册表传 env 这条路径时，provider 消费者必须被选中。"""
    consumer = ProviderReloadConsumer(builder=lambda config: None, installers={})
    registry = HotReloadRegistry()

    with _preserve_global_rules("models", "env"):
        registry.register(consumer)

        assert registry.consumers_for(["env"]) == (consumer,)
        assert registry.consumers_for(["something_else"]) == ()


# ── 3. 重载入口必须把 env 路径透传给宿主命令 ───────────────────


class _RecordingCommands:
    """假的 host_commands：记录被调用时收到的参数。"""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._result = result or {}

    async def call(self, name: str, **kwargs: Any) -> Any:
        self.calls.append((name, kwargs))
        return dict(self._result)


class _StubApi:
    """只满足 `_reload_config` 依赖的最小替身：_service / _models_config / logger。"""

    def __init__(self, commands: _RecordingCommands) -> None:
        self._commands = commands

        class _Logger:
            def warning(self, *args: Any, **kwargs: Any) -> None: ...
            def error(self, *args: Any, **kwargs: Any) -> None: ...

        self.logger = _Logger()

    def _service(self, name: str, default: Any = None) -> Any:
        return self._commands if name == "host_commands" else default

    def _models_config(self) -> Any:
        return None


async def test_reload_forwards_env_path_to_host_command() -> None:
    """保存 env 时，`extra_changed_paths=("env",)` 必须传到 config.reload。"""
    commands = _RecordingCommands(
        {"status": "ok", "message": "配置已重载，本次没有检测到配置项变化。"}
    )
    api = _StubApi(commands)

    result = await DashboardApi._reload_config(
        api, with_changes=False, extra_changed_paths=("env",)
    )

    assert commands.calls == [("config.reload", {"extra_changed_paths": ("env",)})]
    assert result["ok"] is True


async def test_reload_keeps_pipeline_message_when_env_declared() -> None:
    """声明了 env 路径时，不得用「没有检测到配置项变化」覆盖掉重载信息。"""
    commands = _RecordingCommands(
        {"status": "ok", "message": "配置已热重载：1 项立即生效，0 项需重启。"}
    )
    api = _StubApi(commands)

    result = await DashboardApi._reload_config(
        api, with_changes=False, extra_changed_paths=("env",)
    )

    assert result["message"] == "配置已热重载：1 项立即生效，0 项需重启。"


async def test_reload_keeps_hot_reload_report() -> None:
    """热重载报告要被透传出去 —— env 保存要靠它说明「哪些组件已重建」。"""
    report = {"applied": [{"name": "provider", "applied": True}], "failed": []}
    commands = _RecordingCommands({"status": "ok", "message": "ok", "hot_reload": report})
    api = _StubApi(commands)

    result = await DashboardApi._reload_config(api, with_changes=False)

    assert result["hot_reload"] == report


async def test_reload_without_extra_paths_keeps_legacy_call_shape() -> None:
    """没有额外路径时不带参：宿主命令实现未必接受 **kwargs，别为此改外部契约。"""
    commands = _RecordingCommands({"status": "ok", "message": "ok"})
    api = _StubApi(commands)

    await DashboardApi._reload_config(api, with_changes=False)

    assert commands.calls == [("config.reload", {})]
