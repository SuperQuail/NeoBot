"""官方 dashboard 插件：延迟探针门控与空闲停止的行为回归。

背景（bugfixes/feat(2)）：探针原本在 load() 里无条件常驻、固定 15s 发一次 get_status，
与有没有人看面板无关，实测 5760 次/天、占 packets 行数 70.8%。

本文件守住改造后的三条核心语义：
1. 无活跃会话时不探测（idle=0），且**绝不能退出循环**（退出即永久停摆，坑 5）；
2. 有活跃会话时按 interval 探测；活跃窗口外不算"有人看"；
3. 门控必须只读会话（不能 touch 造成自我续期）。
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from types import SimpleNamespace
from typing import Any

import pytest

from neobot_app.builtin_plugins import dashboard as dashboard_module
from neobot_app.builtin_plugins.dashboard import DashboardPlugin
from neobot_app.builtin_plugins.dashboard.security import SessionStore


class _FakeMetrics:
    def __init__(self) -> None:
        self.stale_after: float | None = None
        self.capacity: int | None = None

    def set_latency_stale_after(self, seconds: float) -> None:
        self.stale_after = float(seconds)

    def set_latency_capacity(self, samples: int) -> None:
        self.capacity = int(samples)


class _CountingServer:
    """计数 fake：只关心 probe_latency 被调用了多少次。"""

    def __init__(self, sessions: Any) -> None:
        self.sessions = sessions
        self.metrics = _FakeMetrics()
        self.probe_count = 0

    async def probe_latency(self) -> None:
        self.probe_count += 1


def _config(**overrides: Any) -> SimpleNamespace:
    values: dict[str, Any] = {
        "latency_probe_interval_seconds": 0.02,
        "latency_probe_idle_seconds": 0,
        "latency_probe_active_window_seconds": 120,
        "latency_probe_gate_check_seconds": 0.02,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def _drive(plugin: DashboardPlugin, *, seconds: float = 0.15) -> None:
    task = asyncio.create_task(plugin._latency_loop())
    try:
        await asyncio.sleep(seconds)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@pytest.fixture(autouse=True)
def _fast_warmup(monkeypatch: pytest.MonkeyPatch) -> None:
    """跳过 3 秒启动预热，让单测能在毫秒级驱动循环。"""
    monkeypatch.setattr(dashboard_module, "PROBE_WARMUP_SECONDS", 0.0)


async def test_no_session_never_probes() -> None:
    """用例 1：没有任何会话 → 空闲且 idle=0 → probe_count == 0。"""
    sessions = SessionStore(timeout_seconds=720 * 60)
    plugin = DashboardPlugin()
    plugin.config = _config()
    server = _CountingServer(sessions)
    plugin.server = server

    await _drive(plugin)

    assert server.probe_count == 0


async def test_active_session_probes_on_interval() -> None:
    """用例 2：有活跃会话 → 按 interval 计次（至少 2 次，且不会失控）。"""
    sessions = SessionStore(timeout_seconds=720 * 60)
    sessions.create(ip="127.0.0.1")
    plugin = DashboardPlugin()
    plugin.config = _config()
    server = _CountingServer(sessions)
    plugin.server = server

    await _drive(plugin, seconds=0.2)

    assert server.probe_count >= 2
    assert server.probe_count < 40


async def test_session_outside_active_window_is_idle() -> None:
    """用例 3：会话 last_seen_at 落在活跃窗口之外 → 按空闲处理，不探测。"""
    sessions = SessionStore(timeout_seconds=720 * 60)
    session = sessions.create(ip="127.0.0.1")
    session.last_seen_at = time.time() - 121

    plugin = DashboardPlugin()
    plugin.config = _config(latency_probe_active_window_seconds=120)
    server = _CountingServer(sessions)
    plugin.server = server

    await _drive(plugin)

    assert server.probe_count == 0


async def test_has_recent_activity_is_read_only() -> None:
    """用例 4：门控必须只读——调用前后 last_seen_at 不变（否则会话自我续期）。"""
    sessions = SessionStore(timeout_seconds=720 * 60)
    sessions.create(ip="127.0.0.1")
    before = next(iter(sessions._sessions.values())).last_seen_at

    assert sessions.has_recent_activity(120) is True
    after = next(iter(sessions._sessions.values())).last_seen_at

    assert before == after


async def test_zero_interval_disables_probe() -> None:
    """用例 5：latency_probe_interval_seconds=0 → 用户明确关闭，循环返回。"""
    sessions = SessionStore(timeout_seconds=720 * 60)
    sessions.create(ip="127.0.0.1")
    plugin = DashboardPlugin()
    plugin.config = _config(latency_probe_interval_seconds=0)
    server = _CountingServer(sessions)
    plugin.server = server

    task = asyncio.create_task(plugin._latency_loop())
    await asyncio.sleep(0.05)

    assert task.done()
    assert server.probe_count == 0


async def test_probe_recovers_after_idle_period() -> None:
    """用例 6（坑 5 专项回归）：空闲停止后**不能**永久停摆——有人重新打开面板要能恢复探测。"""
    sessions = SessionStore(timeout_seconds=720 * 60)
    plugin = DashboardPlugin()
    plugin.config = _config()
    server = _CountingServer(sessions)
    plugin.server = server

    task = asyncio.create_task(plugin._latency_loop())
    try:
        await asyncio.sleep(0.1)
        assert server.probe_count == 0, "空闲期不应产生任何探测"
        assert not task.done(), "空闲期不允许退出循环，否则探针永久停摆"
        assert plugin._probe_state == "idle"

        sessions.create(ip="127.0.0.1")
        await asyncio.sleep(0.15)

        assert server.probe_count >= 2, "有人重新打开面板后必须恢复探测"
        assert plugin._probe_state == "probing"
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def test_idle_interval_probes_at_low_rate() -> None:
    """用例 7：idle > 0 → 空闲时按 idle 间隔低频探测（不再是常驻高频）。"""
    sessions = SessionStore(timeout_seconds=720 * 60)
    plugin = DashboardPlugin()
    plugin.config = _config(
        latency_probe_interval_seconds=0.02, latency_probe_idle_seconds=0.05
    )
    server = _CountingServer(sessions)
    plugin.server = server

    await _drive(plugin, seconds=0.3)

    assert server.probe_count >= 1
    # 空闲采样间隔明显大于活跃间隔：同样的窗口内次数应显著少于活跃分支
    assert server.probe_count <= 12


async def test_restarting_probe_leaves_single_task() -> None:
    """用例 8：重复启动探针只保留一个任务（load(); load() 回归）。"""
    sessions = SessionStore(timeout_seconds=720 * 60)
    plugin = DashboardPlugin()
    plugin.config = _config()
    server = _CountingServer(sessions)
    plugin.server = server

    await plugin._start_latency_task()
    first = plugin._latency_task
    assert first is not None

    await plugin._start_latency_task()
    second = plugin._latency_task
    assert second is not None and second is not first
    assert first.cancelled() or first.done()

    await plugin._cancel_latency_task()
    assert plugin._latency_task is None
    assert second.cancelled() or second.done()


async def test_stale_threshold_follows_interval() -> None:
    """附带：探针循环会把「样本陈旧阈值」与「样本容量」同步给指标（P1-①②）。"""
    sessions = SessionStore(timeout_seconds=720 * 60)
    sessions.create(ip="127.0.0.1")
    plugin = DashboardPlugin()
    plugin.config = _config(latency_probe_interval_seconds=0.02)
    server = _CountingServer(sessions)
    plugin.server = server

    await _drive(plugin, seconds=0.1)

    assert server.metrics.stale_after == pytest.approx(0.1)
    assert server.metrics.capacity is not None and server.metrics.capacity >= 60
