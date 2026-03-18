"""
事件监听器模块

提供装饰器风格的接口用于注册事件处理器。

使用示例：

    from neobot_adapter.listener import on_message, on_notice, on_request, setup_listeners

    @on_message(message_type="private")
    def handle_private_message(event):
        print(f"收到私聊消息: {event}")

    @on_notice(notice_type="group_increase")
    def handle_group_increase(event):
        print(f"群成员增加: {event}")

    @on_request(request_type="friend")
    async def handle_friend_request(event):
        print(f"好友请求: {event}")

    # 设置监听器（需要适配器核心实例）
    from neobot_adapter.receiver import get_core
    setup_listeners(get_core())

或者使用全局快捷方式：

    from neobot_adapter import setup_listeners
    from neobot_adapter.receiver import start_core

    setup_listeners()
    start_core()
"""
from .decorators import (
    on_message,
    on_notice,
    on_request,
    on_event,
    on_meta_event
)
from .manager import setup_listeners, get_listener_manager, stop_listening
from .dispatcher import EventDispatcher

__all__ = [
    'on_message',
    'on_notice',
    'on_request',
    'on_event',
    'on_meta_event',
    'setup_listeners',
    'get_listener_manager',
    'stop_listening',
    'EventDispatcher'
]