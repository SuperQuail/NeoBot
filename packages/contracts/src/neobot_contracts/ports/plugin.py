"""Plugin Ports — 插件系统抽象"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.output import OutputPort


class PluginState(Enum):
    """插件状态"""

    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
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
class PluginCapability(Protocol):
    """插件显式导出的能力接口"""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...


@runtime_checkable
class PluginHandle(Protocol):
    """受限插件句柄，不暴露插件实例"""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def state(self) -> PluginState: ...

    @property
    def capabilities(self) -> tuple[str, ...]: ...

    async def call(self, capability: str, payload: Mapping[str, Any] | None = None) -> Any: ...


@runtime_checkable
class PluginRegistry(Protocol):
    """插件查询接口"""

    def names(self) -> list[str]: ...

    def has(self, name: str) -> bool: ...

    def get(self, name: str) -> PluginHandle | None: ...

    def list(self) -> list[PluginHandle]: ...


@runtime_checkable
class RuntimePluginContext(Protocol):
    """Internal runtime context passed to plugin objects by the loader."""

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
    def agents(self) -> PluginAgentRegistrar: ...

    @property
    def plugins(self) -> PluginRegistry: ...

    @property
    def plugin_control(self) -> Any: ...

    @property
    def output(self) -> OutputPort: ...

    async def send_private(self, user_id: int, message: str | list[dict[str, Any]]) -> Any: ...

    async def send_group(self, group_id: int, message: str | list[dict[str, Any]]) -> Any: ...

    async def send(self, conversation: ConversationRef, message: str | list[dict[str, Any]]) -> Any: ...

    async def send_image(
        self,
        conversation: ConversationRef,
        *,
        path: Path | None = None,
        data: bytes | None = None,
        filename: str | None = None,
    ) -> Any: ...

    async def send_audio(
        self,
        conversation: ConversationRef,
        *,
        path: Path,
    ) -> Any: ...

    async def reply(self, event: dict[str, Any] | Any, message: str | list[dict[str, Any]]) -> Any: ...

    def conversation_from_event(self, event: dict[str, Any] | Any) -> ConversationRef: ...


@runtime_checkable
class Plugin(Protocol):
    """插件接口"""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    async def on_load(self, ctx: RuntimePluginContext) -> None: ...

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
