"""领域事件基类（预留）"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """所有领域事件的基类"""

    occurred_at: datetime
