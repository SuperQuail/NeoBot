"""连接就绪探针测试。

核心断言只有一条：**框架没连上不是启动失败**。探针必须把「还没连上」
表达成可继续运行的状态，而不是异常 —— 这正是此前面板被回滚、进程退出的根因。
"""

from __future__ import annotations

from typing import Any

import pytest

from neobot_app.runtime.connection_readiness import (
    ConnectionReadinessProbe,
    ConnectionState,
)
from neobot_contracts.ports.logging import NullLogger


class _FakeSettings:
    host = "0.0.0.0"
    port = 8080


class _FakeAdapter:
    """可配置连接结果与等待调用的假适配器。"""

    def __init__(
        self,
        *,
        connected: bool = False,
        wait_result: bool | None = None,
        wait_error: Exception | None = None,
        settings: Any = None,
    ) -> None:
        self.connected = connected
        self._wait_result = wait_result
        self._wait_error = wait_error
        self.settings = settings
        self.wait_calls: list[float | None] = []

    def wait_for_connection(self, timeout: float | None = None) -> bool:
        self.wait_calls.append(timeout)
        if self._wait_error is not None:
            raise self._wait_error
        return bool(self._wait_result)


class _HttpOnlyAdapter:
    """没有 settings、只有 http_url 的适配器（local 模式形态）。"""

    def __init__(self) -> None:
        self.connected = False
        self.http_url = "http://127.0.0.1:8090"
        self.ws_url = "ws://127.0.0.1:8090/ws"

    def wait_for_connection(self, timeout: float | None = None) -> bool:
        return False


# ── 不抛错是硬约束 ──────────────────────────────────────────────────


async def test_observe_never_raises_when_connection_times_out() -> None:
    """等待窗口内没连上：返回未连接状态，绝不抛异常。"""
    adapter = _FakeAdapter(wait_result=False)
    probe = ConnectionReadinessProbe(adapter, logger=NullLogger(), wait_seconds=0.01)

    state = await probe.observe()

    assert state.connected is False
    assert state.wait_timed_out is True
    assert "等待框架连接" in state.status_text()


async def test_observe_never_raises_when_adapter_errors() -> None:
    """适配器自身报错也必须降级为「未连接」，不能升级为启动失败。"""
    adapter = _FakeAdapter(wait_error=RuntimeError("boom"))
    probe = ConnectionReadinessProbe(adapter, logger=NullLogger(), wait_seconds=0.01)

    state = await probe.observe()

    assert state.connected is False
    assert state.wait_timed_out is True


async def test_observe_returns_immediately_when_already_connected() -> None:
    adapter = _FakeAdapter(connected=True, wait_result=True)
    probe = ConnectionReadinessProbe(adapter, logger=NullLogger(), wait_seconds=30.0)

    state = await probe.observe()

    assert state.connected is True
    assert state.waited_seconds == 0.0
    # 已连接时不该再进等待窗口。
    assert adapter.wait_calls == []


async def test_observe_reports_connected_without_timeout_flag() -> None:
    adapter = _FakeAdapter(wait_result=True)
    probe = ConnectionReadinessProbe(adapter, logger=NullLogger(), wait_seconds=0.01)

    state = await probe.observe()

    assert state.connected is True
    assert state.wait_timed_out is False
    assert "框架已连接" in state.status_text()


async def test_wait_seconds_passed_through_to_adapter() -> None:
    adapter = _FakeAdapter(wait_result=False)
    probe = ConnectionReadinessProbe(adapter, logger=NullLogger(), wait_seconds=12.5)

    await probe.observe()

    assert adapter.wait_calls == [12.5]


async def test_zero_wait_means_wait_forever_not_zero_timeout() -> None:
    """wait_seconds=0 的语义是「无限等待」（沿用适配器既有约定）。"""
    adapter = _FakeAdapter(wait_result=False)
    probe = ConnectionReadinessProbe(adapter, logger=NullLogger(), wait_seconds=0.0)

    await probe.observe()

    assert adapter.wait_calls == [None]


# ── 快照与地址 ──────────────────────────────────────────────────────


def test_snapshot_does_not_block() -> None:
    adapter = _FakeAdapter(connected=False)
    probe = ConnectionReadinessProbe(adapter, logger=NullLogger())

    state = probe.snapshot()

    assert state.connected is False
    assert state.wait_timed_out is False
    assert adapter.wait_calls == []


def test_address_prefers_reverse_ws_settings() -> None:
    adapter = _FakeAdapter(settings=_FakeSettings())
    probe = ConnectionReadinessProbe(adapter, logger=NullLogger())

    assert probe.address() == "ws://0.0.0.0:8080"


def test_address_falls_back_to_local_http_url() -> None:
    probe = ConnectionReadinessProbe(_HttpOnlyAdapter(), logger=NullLogger())

    assert probe.address() == "http://127.0.0.1:8090"


def test_address_has_safe_default() -> None:
    probe = ConnectionReadinessProbe(object(), logger=NullLogger())

    assert probe.address() == "反向 WebSocket 服务"


# ── 文案契约 ────────────────────────────────────────────────────────


def test_startup_log_does_not_say_failure_when_not_connected() -> None:
    """启动日志不能把「未连接」写成失败措辞：它是可恢复状态。"""
    text = ConnectionState(
        connected=False, waited_seconds=30.0, wait_timed_out=True, address="ws://h:1"
    ).startup_log()

    assert "无需重启" in text
    assert "失败" not in text
    assert "ws://h:1" in text


def test_startup_log_when_connected() -> None:
    text = ConnectionState(
        connected=True, waited_seconds=0.0, wait_timed_out=False, address="ws://h:1"
    ).startup_log()

    assert "已连接" in text


@pytest.mark.parametrize("wait_seconds", [-1.0, -100.0])
async def test_negative_wait_seconds_is_clamped(wait_seconds: float) -> None:
    adapter = _FakeAdapter(wait_result=False)
    probe = ConnectionReadinessProbe(
        adapter, logger=NullLogger(), wait_seconds=wait_seconds
    )

    await probe.observe()

    assert adapter.wait_calls == [None]
