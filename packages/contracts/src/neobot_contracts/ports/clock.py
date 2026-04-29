"""Clock Port — 时间抽象"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from neobot_contracts.time_context import now_utc


@runtime_checkable
class Clock(Protocol):
    """时钟接口，便于测试时替换"""

    def now(self) -> datetime: ...


class SystemClock:
    """系统时钟默认实现"""

    def now(self) -> datetime:
        return now_utc()
