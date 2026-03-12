"""
事件监听装饰器

提供装饰器风格的接口用于注册事件处理器，支持同步和异步函数。
"""
import inspect
from functools import wraps
from typing import Optional, Callable, Union, Any, Dict
import asyncio

from .manager import get_listener_manager


def on_message(
    message_type: Optional[str] = None,
    sub_type: Optional[str] = None,
    priority: int = 0
):
    """
    消息事件装饰器

    用于处理消息事件（post_type = "message"）。

    Args:
        message_type: 消息类型，如 "private"（私聊）或 "group"（群聊）
        sub_type: 消息子类型，如 "friend"（好友消息）、"normal"（正常群聊）等
        priority: 处理器优先级，数字越大优先级越高

    Example:
        @on_message(message_type="private")
        def handle_private_msg(event):
            print(f"私聊消息: {event}")

        @on_message(message_type="group", sub_type="normal")
        async def handle_group_normal_msg(event):
            print(f"普通群消息: {event}")
    """
    def decorator(func: Callable):
        is_async = inspect.iscoroutinefunction(func)
        
        @wraps(func)
        def wrapper(event: Dict[str, Any]) -> Any:
            return func(event)
        
        @wraps(func)
        async def async_wrapper(event: Dict[str, Any]) -> Any:
            return await func(event)
        
        # 注册到监听器管理器
        from .manager import EventHandler, EventFilter
        filter = EventFilter(
            post_type='message',
            message_type=message_type,
            sub_type=sub_type
        )
        handler = EventHandler(
            func=async_wrapper if is_async else wrapper,
            filter=filter,
            is_async=is_async,
            priority=priority
        )
        
        get_listener_manager().register(handler)
        return async_wrapper if is_async else wrapper
    return decorator


def on_notice(
    notice_type: Optional[str] = None,
    sub_type: Optional[str] = None,
    priority: int = 0
):
    """
    通知事件装饰器

    用于处理通知事件（post_type = "notice"）。

    Args:
        notice_type: 通知类型，如 "group_increase"（群成员增加）、"friend_add"（好友添加）等
        sub_type: 通知子类型，如 "invite"（邀请）、"approve"（管理员同意）等
        priority: 处理器优先级，数字越大优先级越高

    Example:
        @on_notice(notice_type="group_increase")
        def handle_group_increase(event):
            print(f"群成员增加: {event}")

        @on_notice(notice_type="friend_add")
        async def handle_friend_add(event):
            print(f"好友添加: {event}")
    """
    def decorator(func: Callable):
        is_async = inspect.iscoroutinefunction(func)
        
        @wraps(func)
        def wrapper(event: Dict[str, Any]) -> Any:
            return func(event)
        
        @wraps(func)
        async def async_wrapper(event: Dict[str, Any]) -> Any:
            return await func(event)
        
        from .manager import EventHandler, EventFilter
        filter = EventFilter(
            post_type='notice',
            notice_type=notice_type,
            sub_type=sub_type
        )
        handler = EventHandler(
            func=async_wrapper if is_async else wrapper,
            filter=filter,
            is_async=is_async,
            priority=priority
        )
        
        get_listener_manager().register(handler)
        return async_wrapper if is_async else wrapper
    return decorator


def on_request(
    request_type: Optional[str] = None,
    sub_type: Optional[str] = None,
    priority: int = 0
):
    """
    请求事件装饰器

    用于处理请求事件（post_type = "request"）。

    Args:
        request_type: 请求类型，如 "friend"（好友请求）或 "group"（群请求）
        sub_type: 请求子类型，如 "add"（加群）、"invite"（邀请）等
        priority: 处理器优先级，数字越大优先级越高

    Example:
        @on_request(request_type="friend")
        def handle_friend_request(event):
            print(f"好友请求: {event}")

        @on_request(request_type="group", sub_type="add")
        async def handle_group_join_request(event):
            print(f"加群请求: {event}")
    """
    def decorator(func: Callable):
        is_async = inspect.iscoroutinefunction(func)
        
        @wraps(func)
        def wrapper(event: Dict[str, Any]) -> Any:
            return func(event)
        
        @wraps(func)
        async def async_wrapper(event: Dict[str, Any]) -> Any:
            return await func(event)
        
        from .manager import EventHandler, EventFilter
        filter = EventFilter(
            post_type='request',
            request_type=request_type,
            sub_type=sub_type
        )
        handler = EventHandler(
            func=async_wrapper if is_async else wrapper,
            filter=filter,
            is_async=is_async,
            priority=priority
        )
        
        get_listener_manager().register(handler)
        return async_wrapper if is_async else wrapper
    return decorator


def on_event(
    post_type: Optional[str] = None,
    **filter_kwargs
):
    """
    通用事件装饰器

    用于处理任意类型的事件。

    Args:
        post_type: 事件类型，如 "message"、"notice"、"request"、"meta_event"，
                  如果为 None 则匹配所有类型的事件
        **filter_kwargs: 过滤条件，如 message_type="private"、notice_type="group_increase" 等

    Example:
        @on_event(post_type="message", message_type="private")
        def handle_private_message(event):
            print(f"私聊消息: {event}")

        @on_event()
        def handle_all_events(event):
            print(f"所有事件: {event}")
    """
    def decorator(func: Callable):
        is_async = inspect.iscoroutinefunction(func)
        
        @wraps(func)
        def wrapper(event: Dict[str, Any]) -> Any:
            return func(event)
        
        @wraps(func)
        async def async_wrapper(event: Dict[str, Any]) -> Any:
            return await func(event)
        
        from .manager import EventHandler, EventFilter
        filter_kwargs['post_type'] = post_type
        filter = EventFilter(**filter_kwargs)
        handler = EventHandler(
            func=async_wrapper if is_async else wrapper,
            filter=filter,
            is_async=is_async,
            priority=0
        )
        
        get_listener_manager().register(handler)
        return async_wrapper if is_async else wrapper
    return decorator


def on_meta_event(
    meta_event_type: Optional[str] = None,
    priority: int = 0
):
    """
    元事件装饰器

    用于处理元事件（post_type = "meta_event"）。

    Args:
        meta_event_type: 元事件类型，如 "heartbeat"（心跳）或 "lifecycle"（生命周期）
        priority: 处理器优先级，数字越大优先级越高

    Example:
        @on_meta_event(meta_event_type="heartbeat")
        def handle_heartbeat(event):
            print(f"心跳: {event}")
    """
    def decorator(func: Callable):
        is_async = inspect.iscoroutinefunction(func)
        
        @wraps(func)
        def wrapper(event: Dict[str, Any]) -> Any:
            return func(event)
        
        @wraps(func)
        async def async_wrapper(event: Dict[str, Any]) -> Any:
            return await func(event)
        
        from .manager import EventHandler, EventFilter
        filter = EventFilter(
            post_type='meta_event',
            meta_event_type=meta_event_type
        )
        handler = EventHandler(
            func=async_wrapper if is_async else wrapper,
            filter=filter,
            is_async=is_async,
            priority=priority
        )
        
        get_listener_manager().register(handler)
        return async_wrapper if is_async else wrapper
    return decorator