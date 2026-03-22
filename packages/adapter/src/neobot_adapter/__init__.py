"""NeoBot 适配器公开入口"""

from .adapter import OneBotAdapter, Subscription
from .mapping import map_to_incoming_message
from .receiver import AdapterCore
from .request.websocket import WebSocketAPI

__all__ = [
    "OneBotAdapter",
    "Subscription",
    "map_to_incoming_message",
    "AdapterCore",
    "WebSocketAPI",
]
