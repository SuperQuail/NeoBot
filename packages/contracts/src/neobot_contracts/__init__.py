"""NeoBot 跨模块共享的领域模型与 Port 接口"""

from neobot_contracts.errors import NeoBotError
from neobot_contracts.events import DomainEvent

__all__ = [
    "NeoBotError",
    "DomainEvent",
]
