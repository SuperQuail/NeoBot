"""适配器监听设置热重载（AdapterSupervisor）测试。

生产场景：用户在网页面板把 access token / 端口改好并保存，不重启进程就要
生效。这里锁死三条契约：

1. 设置一致时不做任何重启（避免无谓地断开框架连接）；
2. 设置变化时按「停 → 改 → 启」执行，且改的是适配器内部设置而不是换对象
   （对象被几十处持有引用）；
3. 新设置起不来时回滚到旧设置并重新监听，同时把异常抛给调用方。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from neobot_adapter.onebot.receiver.settings import ReverseWsSettings
from neobot_app.runtime.adapter_supervisor import AdapterSupervisor
from neobot_contracts.ports.logging import NullLogger


class _FakeReconfigurableAdapter:
    """按 OneBotAdapter 的能力面实现：settings 属性 + reconfigure + start/stop。"""

    def __init__(self, settings: ReverseWsSettings, *, fail_start_for: Any = None) -> None:
        self._settings = settings
        self._fail_start_for = fail_start_for
        self.reconfigure_calls: list[ReverseWsSettings] = []
        self.events: list[str] = []
        self.connected = False

    @property
    def settings(self) -> ReverseWsSettings:
        return self._settings

    def reconfigure(self, settings: ReverseWsSettings) -> None:
        self.events.append(f"reconfigure:{settings.port}")
        self.reconfigure_calls.append(settings)
        self._settings = settings

    async def start(self) -> None:
        self.events.append("start")
        if self._fail_start_for is not None and self._settings == self._fail_start_for:
            raise OSError("port already in use")

    async def stop(self) -> None:
        self.events.append("stop")


class _NonReconfigurableAdapter:
    """local 模式形态：没有 settings / reconfigure。"""

    connected = True


def _settings(port: int = 8080, token: str = "") -> ReverseWsSettings:
    return ReverseWsSettings(host="0.0.0.0", port=port, access_token=token)


def _config(port: int = 8080, token: str = "", host: str = "0.0.0.0") -> Any:
    return SimpleNamespace(
        adapter=SimpleNamespace(
            reverse_ws_host=host,
            reverse_ws_port=port,
            reverse_ws_access_token=token,
        )
    )


# ── 能力查询 ────────────────────────────────────────────────────────


def test_reconfigurable_detected_by_interface() -> None:
    supervisor = AdapterSupervisor(_FakeReconfigurableAdapter(_settings()))

    assert supervisor.reconfigurable is True


def test_non_reconfigurable_adapter_is_reported_as_unsupported() -> None:
    supervisor = AdapterSupervisor(_NonReconfigurableAdapter())

    assert supervisor.reconfigurable is False
    assert supervisor.describe()["reconfigurable"] is False


async def test_apply_config_raises_for_unsupported_adapter() -> None:
    supervisor = AdapterSupervisor(_NonReconfigurableAdapter(), logger=NullLogger())

    with pytest.raises(RuntimeError, match="不支持运行期修改监听设置"):
        await supervisor.apply_config(_config(port=9090))


# ── 无需重启的情形 ──────────────────────────────────────────────────


async def test_unchanged_settings_skip_restart() -> None:
    adapter = _FakeReconfigurableAdapter(_settings(port=8080))
    supervisor = AdapterSupervisor(adapter, logger=NullLogger())

    await supervisor.apply_config(_config(port=8080))

    assert adapter.events == []


async def test_missing_adapter_config_is_ignored() -> None:
    adapter = _FakeReconfigurableAdapter(_settings())
    supervisor = AdapterSupervisor(adapter, logger=NullLogger())

    await supervisor.apply_config(SimpleNamespace())

    assert adapter.events == []


# ── 生效路径 ────────────────────────────────────────────────────────


async def test_port_change_restarts_listener() -> None:
    adapter = _FakeReconfigurableAdapter(_settings(port=8080))
    supervisor = AdapterSupervisor(adapter, logger=NullLogger())

    await supervisor.apply_config(_config(port=9090))

    assert adapter.events == ["stop", "reconfigure:9090", "start"]
    assert adapter.settings.port == 9090


async def test_token_change_restarts_listener() -> None:
    adapter = _FakeReconfigurableAdapter(_settings(port=8080))
    supervisor = AdapterSupervisor(adapter, logger=NullLogger())

    await supervisor.apply_config(_config(port=8080, token="s3cret"))

    assert adapter.settings.access_token == "s3cret"
    assert adapter.settings.token_enabled is True
    assert "start" in adapter.events


async def test_reconfigure_keeps_same_adapter_object() -> None:
    """必须原地改设置：适配器对象被技能/文件服务等大量组件持有引用。"""
    adapter = _FakeReconfigurableAdapter(_settings(port=8080))
    supervisor = AdapterSupervisor(adapter, logger=NullLogger())

    await supervisor.reconfigure(_settings(port=9090))

    assert supervisor.adapter is adapter


# ── 失败回滚 ────────────────────────────────────────────────────────


async def test_failed_restart_rolls_back_to_previous_settings() -> None:
    adapter = _FakeReconfigurableAdapter(
        _settings(port=8080), fail_start_for=_settings(port=9090)
    )
    supervisor = AdapterSupervisor(adapter, logger=NullLogger())

    with pytest.raises(OSError, match="port already in use"):
        await supervisor.apply_config(_config(port=9090))

    assert adapter.settings.port == 8080  # 已回滚
    assert adapter.events == [
        "stop",
        "reconfigure:9090",
        "start",  # 新设置启动失败
        "reconfigure:8080",
        "start",  # 回滚后重新监听
    ]


async def test_rollback_failure_is_reported_and_raised() -> None:
    class _AlwaysFailingStart(_FakeReconfigurableAdapter):
        async def start(self) -> None:
            self.events.append("start")
            raise OSError("cannot bind")

    adapter = _AlwaysFailingStart(_settings(port=8080))
    supervisor = AdapterSupervisor(adapter, logger=NullLogger())

    with pytest.raises(OSError, match="cannot bind"):
        await supervisor.reconfigure(_settings(port=9090))

    assert adapter.settings.port == 8080


# ── 状态展示 ────────────────────────────────────────────────────────


def test_describe_reports_listen_state() -> None:
    adapter = _FakeReconfigurableAdapter(_settings(port=8080, token="t"))
    adapter.connected = True
    supervisor = AdapterSupervisor(adapter)

    described = supervisor.describe()

    assert described == {
        "address": "ws://0.0.0.0:8080",
        "token_enabled": True,
        "connected": True,
        "reconfigurable": True,
    }


def test_describe_survives_adapter_without_settings() -> None:
    supervisor = AdapterSupervisor(_NonReconfigurableAdapter())

    assert supervisor.describe()["address"] == ""


def test_consumer_protocol_shape() -> None:
    """注册表依赖的声明：消费者名、关心的前缀、生效方式。"""
    assert AdapterSupervisor.config_paths == ("adapter",)
    policies = AdapterSupervisor.hot_reload_policies
    assert policies[0].path == "adapter"
    assert policies[0].hot_reload is True
