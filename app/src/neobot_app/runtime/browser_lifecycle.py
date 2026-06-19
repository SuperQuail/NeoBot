"""BrowserLifecycleManager — 浏览器生命周期管理。

管理浏览器页面的自动关闭与保活（hold）机制。
"""

from __future__ import annotations

import time
from typing import Any


class BrowserLifecycleManager:
    """浏览器生命周期管理器。

    跟踪当前打开的浏览器页面，管理 hold 保活机制。
    当没有任何 hold 页面且浏览器空闲时，自动触发关闭。
    """

    def __init__(self, hold_max_minutes: int = 30) -> None:
        self._hold_max_seconds = hold_max_minutes * 60
        self._page_count: int = 0
        self._held_pages: dict[str, float] = {}  # page_id -> expiry_timestamp
        self._browser_instance: Any = None

    @property
    def page_count(self) -> int:
        return self._page_count

    @property
    def has_held_pages(self) -> bool:
        """是否有任何保活中的页面。"""
        self._purge_expired()
        return len(self._held_pages) > 0

    @property
    def held_pages(self) -> list[str]:
        self._purge_expired()
        return list(self._held_pages.keys())

    def set_browser_instance(self, browser: Any) -> None:
        """关联浏览器实例。"""
        self._browser_instance = browser

    def track_page_open(self, count: int = 1) -> None:
        """追踪页面打开。"""
        self._page_count += count

    def track_page_close(self, count: int = 1) -> None:
        """追踪页面关闭。"""
        self._page_count = max(0, self._page_count - count)

    def hold(self, page_id: str, minutes: int | None = None) -> bool:
        """保活一个页面。

        Args:
            page_id: 页面标识。
            minutes: 保活分钟数，默认使用配置的最大值。

        Returns:
            True 表示成功保活。
        """
        duration = min(
            minutes or self._hold_max_seconds / 60,
            self._hold_max_seconds / 60,
        )
        expiry = time.time() + duration * 60
        self._held_pages[page_id] = expiry
        return True

    def release(self, page_id: str) -> bool:
        """释放一个页面的保活状态。"""
        return self._held_pages.pop(page_id, None) is not None

    def should_auto_close(self) -> bool:
        """检查是否应该自动关闭所有浏览器页面。

        条件：无任何保活页面。
        """
        return not self.has_held_pages

    def _purge_expired(self) -> None:
        """清理过期的保活记录。"""
        now = time.time()
        expired = [pid for pid, exp in self._held_pages.items() if exp <= now]
        for pid in expired:
            self._held_pages.pop(pid, None)

    def reset(self) -> None:
        """重置所有状态（新会话时调用）。"""
        self._page_count = 0
        self._held_pages.clear()
        self._browser_instance = None
