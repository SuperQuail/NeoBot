from __future__ import annotations

import asyncio
import time

import pytest

from neobot_app.runtime.browser_lifecycle import BrowserLifecycleManager


def _aged_manager(idle_timeout_minutes: int = 10, age_seconds: float = 9999.0) -> BrowserLifecycleManager:
    """构造管理器并将指定流老化，使其超过闲置阈值。"""
    manager = BrowserLifecycleManager(idle_timeout_minutes=idle_timeout_minutes)
    manager.track_tab_open("flow-1", "tab-1")
    state = manager._flows["flow-1"]
    state.last_access = time.time() - age_seconds
    return manager


def test_held_flow_is_not_reported_idle() -> None:
    """流被 hold 后即使长时间未访问，也不应被闲置检测选中关闭。"""
    # Arrange
    manager = _aged_manager()
    manager.hold("flow-1", minutes=30)

    # Act
    idle_flows = manager._get_idle_flows()

    # Assert
    assert idle_flows == []
    assert manager.is_held("flow-1") is True


def test_release_restores_idle_detection() -> None:
    """释放 hold 后，超时未访问的流恢复被闲置检测选中。"""
    # Arrange
    manager = _aged_manager()
    manager.hold("flow-1", minutes=30)

    # Act
    released = manager.release("flow-1")
    manager._flows["flow-1"].last_access = time.time() - 9999
    idle_flows = manager._get_idle_flows()

    # Assert
    assert released is True
    assert manager.is_held("flow-1") is False
    assert idle_flows == [("flow-1", {"tab-1"})]


@pytest.mark.asyncio
async def test_concurrent_hold_on_multiple_flows() -> None:
    """多个聊天流并发 hold 互不阻塞，各自成功且状态一致。"""
    # Arrange
    manager = BrowserLifecycleManager()
    manager.track_tab_open("flow-a", "tab-a")
    manager.track_tab_open("flow-b", "tab-b")

    async def hold_flow(chat_flow_id: str) -> bool:
        await asyncio.sleep(0)
        return manager.hold(chat_flow_id, minutes=60)

    # Act
    results = await asyncio.gather(hold_flow("flow-a"), hold_flow("flow-b"))

    # Assert
    assert results == [True, True]
    assert manager.is_held("flow-a") is True
    assert manager.is_held("flow-b") is True
    assert manager.active_flow_count == 2


def test_stale_flow_without_tabs_is_reclaimed() -> None:
    """标签页关光后剩下的空流状态必须能被回收，否则长期运行会无限堆积。"""
    manager = BrowserLifecycleManager(idle_timeout_minutes=10)
    manager.track_tab_open("flow-1", "tab-1")
    manager.track_tab_close("flow-1", "tab-1")
    manager.touch("flow-2")
    for cid in ("flow-1", "flow-2"):
        manager._flows[cid].last_access = time.time() - 9999

    stale = manager._get_stale_flow_ids()

    assert sorted(stale) == ["flow-1", "flow-2"]
    # 没有标签页的流不会被闲置关闭流程选中（它只负责关页面）
    assert manager._get_idle_flows() == []


def test_stale_reclaim_keeps_live_and_held_flows() -> None:
    manager = BrowserLifecycleManager(idle_timeout_minutes=10)
    manager.track_tab_open("live", "tab-1")
    manager.track_tab_close("live", "tab-1")
    manager.touch("fresh")
    manager.hold("held", minutes=30)
    manager._flows["live"].last_access = time.time() - 9999
    manager._flows["held"].last_access = time.time() - 9999

    stale = manager._get_stale_flow_ids()

    assert stale == ["live"]
    assert manager.is_held("held") is True
