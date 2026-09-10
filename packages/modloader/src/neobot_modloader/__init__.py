from __future__ import annotations

from neobot_modloader.agent import AgentRequest
from neobot_modloader.bot import Bot
from neobot_modloader.database import (
    Migration,
    PluginDatabase,
    PluginDatabaseClosedError,
    PluginDatabaseError,
    PluginDatabaseNotReadyError,
    PluginMigrationConflictError,
    PluginMigrationError,
)
from neobot_modloader.dependencies import PythonDependencyInstaller
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.host import DefaultServiceRegistry, PluginHostFacade
from neobot_modloader.installer import (
    PROXY_MODES,
    PluginInstallError,
    PluginInstallResult,
    PluginInstaller,
    PluginUpdateCheck,
    ProxySettings,
    RepoSpec,
    compare_versions,
)
from neobot_modloader.loader import DiscoveredPlugin, FilesystemPluginLoader
from neobot_modloader.loading.models import OFFICIAL_SOURCE, THIRD_PARTY_SOURCE
from neobot_modloader.management import PluginControlFacade, PluginOperationResult, PluginSnapshot
from neobot_modloader.state import PluginStateEntry, PluginStateStore
from neobot_modloader.manager import DefaultPluginManager
from neobot_modloader.message import AtSegment, ImageSegment, Message, MessageChain, MessageSegment, at, image, text
from neobot_modloader.plugin import Plugin
from neobot_modloader.reply import Reply
from neobot_modloader.runtime import PluginRuntime
from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.users import UserDirectory, UserProfile
from neobot_contracts.ports.screenshot import (
    FontFace,
    FontFormat,
    FontLoadError,
    ImageFormat,
    InvalidScreenshotOptions,
    RenderOptions,
    ScreenshotError,
    ScreenshotMode,
    ScreenshotOptions,
    ScreenshotPort,
    ScreenshotResult,
    ScreenshotTargetNotFound,
    ScreenshotTimeout,
    ScreenshotUnavailable,
)

__all__ = [
    "AgentRequest",
    "AtSegment",
    "Bot",
    "DefaultPluginManager",
    "DefaultServiceRegistry",
    "DiscoveredPlugin",
    "FilesystemPluginLoader",
    "OFFICIAL_SOURCE",
    "PROXY_MODES",
    "PluginInstallError",
    "PluginInstallResult",
    "PluginInstaller",
    "PluginStateEntry",
    "PluginStateStore",
    "PluginUpdateCheck",
    "ProxySettings",
    "RepoSpec",
    "THIRD_PARTY_SOURCE",
    "compare_versions",
    "ImageSegment",
    "Message",
    "MessageChain",
    "MessageSegment",
    "Migration",
    "Plugin",
    "PluginControlFacade",
    "PluginDatabase",
    "PluginDatabaseClosedError",
    "PluginDatabaseError",
    "PluginDatabaseNotReadyError",
    "PluginHookBus",
    "PluginHostFacade",
    "PluginMigrationConflictError",
    "PluginMigrationError",
    "PluginOperationResult",
    "PluginRuntime",
    "PluginSnapshot",
    "PythonDependencyInstaller",
    "Reply",
    "RuntimePluginContext",
    "UserDirectory",
    "UserProfile",
    "at",
    "image",
    "text",
    "FontFace",
    "FontFormat",
    "FontLoadError",
    "ImageFormat",
    "InvalidScreenshotOptions",
    "RenderOptions",
    "ScreenshotError",
    "ScreenshotMode",
    "ScreenshotOptions",
    "ScreenshotPort",
    "ScreenshotResult",
    "ScreenshotTargetNotFound",
    "ScreenshotTimeout",
    "ScreenshotUnavailable",
]
