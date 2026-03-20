"""NeoBot 适配器公开入口"""

from .adapter import OneBotAdapter, Subscription
from .gateway import OneBotGateway
from .mapping import map_to_incoming_message
from .receiver import AdapterCore
from .request.websocket import WebSocketAPI

__all__ = [
    "OneBotAdapter",
    "Subscription",
    "OneBotGateway",
    "map_to_incoming_message",
    "AdapterCore",
    "WebSocketAPI",
]
