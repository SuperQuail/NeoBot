"""适配器接收器模块，提供 WebSocket 反向连接功能。"""

from .core import (
    AdapterCore,
    initialize_core,
    get_core,
    is_core_initialized,
    start_core,
    stop_core,
    restart_core,
)

__all__ = [
    "AdapterCore",
    "initialize_core",
    "get_core",
    "is_core_initialized",
    "start_core",
    "stop_core",
    "restart_core",
]
