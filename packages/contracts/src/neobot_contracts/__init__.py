"""NeoBot 跨模块共享的领域模型与 Port 接口"""

from neobot_contracts.models import ConversationRef, IncomingMessage, MemoryRecord
from neobot_contracts.errors import NeoBotError
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.clock import Clock, SystemClock
from neobot_contracts.ports.event_source import EventSource, Subscription
from neobot_contracts.ports.repository import MemoryRepository, MessageRepository
from neobot_contracts.ports.provider import Provider
from neobot_contracts.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory

__all__ = [
    # Models
    "ConversationRef",
    "IncomingMessage",
    "MemoryRecord",
    # Errors
    "NeoBotError",
    # Ports
    "Logger",
    "NullLogger",
    "Clock",
    "SystemClock",
    "Subscription",
    "EventSource",
    "MemoryRepository",
    "MessageRepository",
    "Provider",
    "UnitOfWork",
    "UnitOfWorkFactory",
]
