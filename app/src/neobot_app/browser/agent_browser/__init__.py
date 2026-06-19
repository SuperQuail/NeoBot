"""agent-browser — AI 代理浏览器（DrissionPage 实现）"""

from .actions import AgentBrowser
from .manager import BrowserManager
from .snapshot import snapshot_page, format_snapshot

__all__ = [
    "AgentBrowser",
    "BrowserManager",
    "snapshot_page",
    "format_snapshot",
]
