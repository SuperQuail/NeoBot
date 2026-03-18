"""
事件分发器

提供高级API用于事件分发和管理。
"""
from typing import Dict, Any, Callable, Optional
from .manager import get_listener_manager, EventHandler, EventFilter


class EventDispatcher:
    """事件分发器（高级包装类）
    
    提供更友好的API用于事件处理。
    """
    
    def __init__(self, core=None):
        """初始化事件分发器
        
        Args:
            core: 适配器核心实例，如果为 None 则稍后需要手动设置
        """
        self._manager = get_listener_manager()
        if core:
            self._manager.core = core
    
    @property
    def core(self):
        """获取关联的适配器核心实例"""
        return self._manager.core
    
    @core.setter
    def core(self, value):
        """设置适配器核心实例"""
        self._manager.core = value
    
    def start(self):
        """启动事件分发"""
        self._manager.start()
    
    def stop(self):
        """停止事件分发"""
        self._manager.stop()
    
    def register_handler(
        self,
        func: Callable,
        post_type: Optional[str] = None,
        message_type: Optional[str] = None,
        notice_type: Optional[str] = None,
        request_type: Optional[str] = None,
        meta_event_type: Optional[str] = None,
        sub_type: Optional[str] = None,
        priority: int = 0
    ) -> EventHandler:
        """注册事件处理器
        
        Args:
            func: 处理函数（同步或异步）
            post_type: 事件类型
            message_type: 消息类型
            notice_type: 通知类型
            request_type: 请求类型
            meta_event_type: 元事件类型
            sub_type: 子类型
            priority: 处理器优先级
            
        Returns:
            注册的事件处理器
        """
        import inspect
        is_async = inspect.iscoroutinefunction(func)
        
        filter = EventFilter(
            post_type=post_type,
            message_type=message_type,
            notice_type=notice_type,
            request_type=request_type,
            meta_event_type=meta_event_type,
            sub_type=sub_type
        )
        
        handler = EventHandler(
            func=func,
            filter=filter,
            is_async=is_async,
            priority=priority
        )
        
        self._manager.register(handler)
        return handler
    
    def unregister_handler(self, func: Callable) -> bool:
        """注销事件处理器
        
        Args:
            func: 要注销的处理函数
            
        Returns:
            如果成功注销返回 True，否则返回 False
        """
        return self._manager.unregister(func)
    
    def clear_handlers(self):
        """清除所有事件处理器"""
        self._manager.clear()
    
    def handle_message(
        self,
        message_type: Optional[str] = None,
        sub_type: Optional[str] = None,
        priority: int = 0
    ):
        """消息事件处理装饰器
        
        Args:
            message_type: 消息类型
            sub_type: 子类型
            priority: 处理器优先级
            
        Returns:
            装饰器函数
        """
        def decorator(func: Callable):
            self.register_handler(
                func=func,
                post_type="message",
                message_type=message_type,
                sub_type=sub_type,
                priority=priority
            )
            return func
        return decorator
    
    def handle_notice(
        self,
        notice_type: Optional[str] = None,
        sub_type: Optional[str] = None,
        priority: int = 0
    ):
        """通知事件处理装饰器
        
        Args:
            notice_type: 通知类型
            sub_type: 子类型
            priority: 处理器优先级
            
        Returns:
            装饰器函数
        """
        def decorator(func: Callable):
            self.register_handler(
                func=func,
                post_type="notice_data",
                notice_type=notice_type,
                sub_type=sub_type,
                priority=priority
            )
            return func
        return decorator
    
    def handle_request(
        self,
        request_type: Optional[str] = None,
        sub_type: Optional[str] = None,
        priority: int = 0
    ):
        """请求事件处理装饰器
        
        Args:
            request_type: 请求类型
            sub_type: 子类型
            priority: 处理器优先级
            
        Returns:
            装饰器函数
        """
        def decorator(func: Callable):
            self.register_handler(
                func=func,
                post_type="request",
                request_type=request_type,
                sub_type=sub_type,
                priority=priority
            )
            return func
        return decorator
    
    def handle_event(
        self,
        post_type: str,
        **filter_kwargs
    ):
        """通用事件处理装饰器
        
        Args:
            post_type: 事件类型
            **filter_kwargs: 过滤条件
            
        Returns:
            装饰器函数
        """
        def decorator(func: Callable):
            self.register_handler(
                func=func,
                post_type=post_type,
                **filter_kwargs
            )
            return func
        return decorator
    
    def dispatch(self, event: Dict[str, Any]) -> None:
        """立即分发事件
        
        Args:
            event: 事件字典
        """
        self._manager._dispatch_sync(event)