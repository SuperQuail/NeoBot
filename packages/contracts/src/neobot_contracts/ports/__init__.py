"""Port 接口集合"""

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.output import CapturingOutput, NullOutput, OutputMessage, OutputPort
from neobot_contracts.ports.runtime_event import RuntimeEnvelope, RuntimeInterceptionRegistry
from neobot_contracts.ports.clock import Clock, SystemClock, now_utc
from neobot_contracts.ports.event_source import EventSource, Subscription
from neobot_contracts.ports.plugin import (
    Plugin,
    PluginCapability,
    PluginHandle,
    PluginLoader,
    PluginManager,
    PluginRegistry,
    PluginState,
    RuntimePluginContext,
)
from neobot_contracts.ports.repository import MemoryRepository, MessageRepository, ProfileRepository
from neobot_contracts.ports.provider import Provider
from neobot_contracts.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from neobot_contracts.ports.creator_image_access import CreatorImageAccess
from neobot_contracts.ports.archive_memory_access import (
    ArchiveMemoryAccess,
    ArchiveMemoryAccessWrapper,
    ensure_optional_str,
    ensure_str,
)
from neobot_contracts.ports.image_analysis_access import ImageAnalysisAccess
from neobot_contracts.ports.host import (
    CapabilityRegistry,
    CapabilitySpec,
    CommandRegistry,
    CommandSpec,
    HostRuntimeFacade,
    LifecycleHooks,
    QueryRegistry,
    QuerySpec,
)
from neobot_contracts.ports.scheduled_task_access import ScheduledTaskAccess

__all__ = [
    "Logger",
    "NullLogger",
    "OutputMessage",
    "OutputPort",
    "NullOutput",
    "CapturingOutput",
    "RuntimeEnvelope",
    "RuntimeInterceptionRegistry",
    "Clock",
    "SystemClock",
    "now_utc",
    "EventSource",
    "Subscription",
    "Plugin",
    "PluginCapability",
    "PluginHandle",
    "PluginLoader",
    "PluginManager",
    "PluginRegistry",
    "PluginState",
    "RuntimePluginContext",
    "MemoryRepository",
    "MessageRepository",
    "ProfileRepository",
    "Provider",
    "UnitOfWork",
    "UnitOfWorkFactory",
    "CreatorImageAccess",
    "ArchiveMemoryAccess",
    "ArchiveMemoryAccessWrapper",
    "ensure_optional_str",
    "ensure_str",
    "ImageAnalysisAccess",
    "ScheduledTaskAccess",
    "CapabilityRegistry",
    "CapabilitySpec",
    "CommandRegistry",
    "CommandSpec",
    "HostRuntimeFacade",
    "LifecycleHooks",
    "QueryRegistry",
    "QuerySpec",
]
