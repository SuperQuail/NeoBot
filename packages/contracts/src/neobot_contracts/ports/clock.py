"""Clock Port — 时间抽象"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """时钟协议，便于测试时替换"""

    def now(self) -> datetime: ...


class SystemClock:
    """系统时钟默认实现"""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)
