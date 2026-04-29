"""领域模型"""

from __future__ import annotations

from neobot_contracts.models.base import ConversationRef, IncomingMessage, MemoryRecord
from neobot_contracts.models.memory import (
    ArchiveMemory,
    CreatorImageRecord,
    ImageAnalysis,
    TopicNode,
)
from neobot_contracts.models.scheduled_task import (
    CompletedScheduledTaskRecord,
    ScheduledTaskRecord,
    ScheduledTaskRecurrence,
    ScheduledTaskState,
)
from neobot_contracts.models.trigger import KeywordConfig, TriggerResult

__all__ = [
    "ConversationRef",
    "IncomingMessage",
    "MemoryRecord",
    "ArchiveMemory",
    "CreatorImageRecord",
    "ImageAnalysis",
    "TopicNode",
    "CompletedScheduledTaskRecord",
    "ScheduledTaskRecord",
    "ScheduledTaskRecurrence",
    "ScheduledTaskState",
    "KeywordConfig",
    "TriggerResult",
]
