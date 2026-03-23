"""Plugin Ports — 插件系统抽象"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable
from enum import Enum


class PluginState(Enum):
    """插件状态"""
    UNLOADED = "unloaded"
    LOADED = "loaded"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@runtime_checkable
class Plugin(Protocol):
    """插件协议"""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    async def on_load(self) -> None: ...

    async def on_start(self) -> None: ...

    async def on_stop(self) -> None: ...


@runtime_checkable
class PluginLoader(Protocol):
    """插件加载器协议"""

    def scan_plugins(self, path: str) -> list[str]: ...

    def load_plugin(self, module_name: str) -> Plugin: ...


@runtime_checkable
class PluginManager(Protocol):
    """插件管理器协议"""

    def register(self, plugin: Plugin) -> None: ...

    def get_plugin(self, name: str) -> Optional[Plugin]: ...

    def get_state(self, name: str) -> PluginState: ...

    async def start_plugin(self, name: str) -> None: ...

    async def stop_plugin(self, name: str) -> None: ...
