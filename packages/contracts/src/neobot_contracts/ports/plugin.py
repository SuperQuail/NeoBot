"""Plugin Ports — 插件系统抽象"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from neobot_contracts.models import ConversationRef


class PluginState(Enum):
    """插件状态"""

    UNLOADED = "unloaded"
    LOADED = "loaded"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@runtime_checkable
class PluginAgentRegistrar(Protocol):
    """插件 Agent 注册接口"""

    @property
    def names(self) -> list[str]: ...

    def register(self, name: str, agent: Any) -> str: ...

    def snapshot(self) -> list[dict[str, str]]: ...

    def list_agents(self, name: str | None = None) -> str: ...


@runtime_checkable
class PluginContext(Protocol):
    """插件上下文接口"""

    @property
    def plugin_name(self) -> str: ...

    @property
    def plugin_dir(self) -> Path: ...

    @property
    def data_dir(self) -> Path: ...

    @property
    def config(self) -> Mapping[str, Any]: ...

    @property
    def logger(self) -> Any: ...

    @property
    def on(self) -> Any: ...

    @property
    def agents(self) -> PluginAgentRegistrar: ...

    async def send_private(self, user_id: int, message: str | list[dict[str, Any]]) -> Any: ...

    async def send_group(self, group_id: int, message: str | list[dict[str, Any]]) -> Any: ...

    async def send(self, conversation: ConversationRef, message: str | list[dict[str, Any]]) -> Any: ...

    async def reply(self, event: dict[str, Any] | Any, message: str | list[dict[str, Any]]) -> Any: ...

    def message_text(self, event: dict[str, Any] | Any) -> str: ...

    def conversation_from_event(self, event: dict[str, Any] | Any) -> ConversationRef: ...

    def require_config(self, key: str) -> Any: ...


@runtime_checkable
class Plugin(Protocol):
    """插件接口"""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    async def on_load(self, ctx: PluginContext) -> None: ...

    async def on_start(self) -> None: ...

    async def on_stop(self) -> None: ...


@runtime_checkable
class PluginLoader(Protocol):
    """插件加载器接口"""

    def scan_plugins(self, path: str) -> list[str]: ...

    def load_plugin(self, module_name: str) -> Plugin: ...


@runtime_checkable
class PluginManager(Protocol):
    """插件管理器接口"""

    def register(self, plugin: Plugin) -> None: ...

    def get_plugin(self, name: str) -> Optional[Plugin]: ...

    def get_state(self, name: str) -> PluginState: ...

    async def start_plugin(self, name: str) -> None: ...

    async def stop_plugin(self, name: str) -> None: ...
