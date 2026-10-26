"""agent 循环内跨工具回调共享的可变状态。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentLoopState:
    """一次 agent 回复管线中，工具回调与主循环共同维护的可变字段。"""

    reply_sent: bool = False
    cancelled: bool = False
    time_block_full_sent: bool = False
    is_group: bool = False
    rendered_user_ids: set[str] = field(default_factory=set)
    previous_entries: list[Any] = field(default_factory=list)
