"""
NeoBot 适配器

提供与 OneBot 协议兼容的 WebSocket 适配器，支持事件监听和 API 调用。

主要功能：
1. WebSocket 反向连接
2. 事件接收和处理
3. API 调用
4. 事件监听装饰器

使用示例：

    # 初始化适配器
    from neobot_adapter.receiver import initialize_core, start_core
    from neobot_adapter.listener import setup_listeners
    from neobot_adapter.listener import on_message, on_notice, on_request

    # 初始化核心
    core = initialize_core()

    # 注册事件处理器
    @on_message(message_type="private")
    def handle_private_msg(event):
        print(f"私聊消息: {event}")

    @on_notice(notice_type="group_increase")
    async def handle_group_increase(event):
        print(f"群成员增加: {event}")

    # 启动适配器和监听器
    setup_listeners()
    start_core()
"""

from .receiver import (
    AdapterCore,
    initialize_core,
    get_core,
    start_core,
    stop_core,
    restart_core,
    is_core_initialized
)

from .listener import (
    on_message,
    on_notice,
    on_request,
    on_event,
    on_meta_event,
    setup_listeners,
    get_listener_manager,
    stop_listening,
    EventDispatcher
)

from .request.websocket import WebSocketAPI, get_default_api

__all__ = [
    # 核心功能
    'AdapterCore',
    'initialize_core',
    'get_core',
    'start_core',
    'stop_core',
    'restart_core',
    'is_core_initialized',

    # 事件监听
    'on_message',
    'on_notice',
    'on_request',
    'on_event',
    'on_meta_event',
    'setup_listeners',
    'get_listener_manager',
    'stop_listening',
    'EventDispatcher',

    # API
    'WebSocketAPI',
    'get_default_api'
]

def hello() -> str:
    return "Hello from adapter!"
