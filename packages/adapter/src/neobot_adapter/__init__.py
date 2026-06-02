"""NeoBot 适配器公开入口"""

from .factory import AdapterSettings, create_adapter
from .interfaces import CoreLike, RuntimeAdapter
from .local import LocalAdapter
from .mapping import map_to_incoming_message
from .onebot import AdapterCore, OneBotAdapter, Subscription
from .request.websocket import WebSocketAPI

__all__ = [
    "OneBotAdapter",
    "LocalAdapter",
    "Subscription",
    "AdapterSettings",
    "create_adapter",
    "CoreLike",
    "RuntimeAdapter",
    "map_to_incoming_message",
    "AdapterCore",
    "WebSocketAPI",
]
