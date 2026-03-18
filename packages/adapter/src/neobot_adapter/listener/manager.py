"""
监听器管理器

负责管理事件处理器，从适配器核心消费事件并分发给注册的处理器。
"""
import asyncio
import threading
import queue
from typing import Dict, List, Callable, Any, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
import time
import functools

from neobot_adapter.utils.logger import get_module_logger

logger = get_module_logger("adapter_listener")


class HandlerType(Enum):
    """处理器类型"""
    SYNC = "sync"
    ASYNC = "async"


@dataclass
class EventFilter:
    """事件过滤器
    
    用于过滤特定类型的事件。
    """
    post_type: Optional[str] = None
    message_type: Optional[str] = None
    notice_type: Optional[str] = None
    request_type: Optional[str] = None
    meta_event_type: Optional[str] = None
    sub_type: Optional[str] = None
    
    def match(self, event: Dict[str, Any]) -> bool:
        """检查事件是否匹配过滤条件
        
        Args:
            event: 事件字典
            
        Returns:
            如果事件匹配所有过滤条件返回 True，否则返回 False
        """
        # 检查 post_type
        if self.post_type and event.get("post_type") != self.post_type:
            return False
        
        # 检查消息类型
        if self.message_type and event.get("message_type") != self.message_type:
            return False
        
        # 检查通知类型
        if self.notice_type and event.get("notice_type") != self.notice_type:
            return False
        
        # 检查请求类型
        if self.request_type and event.get("request_type") != self.request_type:
            return False
        
        # 检查元事件类型
        if self.meta_event_type and event.get("meta_event_type") != self.meta_event_type:
            return False
        
        # 检查子类型
        if self.sub_type and event.get("sub_type") != self.sub_type:
            return False
        
        return True
    
    @classmethod
    def from_kwargs(cls, **kwargs) -> 'EventFilter':
        """从关键字参数创建过滤器
        
        Args:
            **kwargs: 过滤条件
            
        Returns:
            事件过滤器实例
        """
        return cls(**kwargs)


@dataclass
class EventHandler:
    """事件处理器
    
    封装事件处理函数及其配置。
    """
    func: Callable
    filter: EventFilter
    is_async: bool
    priority: int = 0
    enabled: bool = True
    
    def __post_init__(self):
        """后初始化处理"""
        # 为同步函数添加错误处理
        if not self.is_async:
            original_func = self.func
            @functools.wraps(original_func)
            def wrapper(event):
                try:
                    return original_func(event)
                except Exception as e:
                    logger.error(f"事件处理器执行失败: {e}", exc_info=True)
            self.func = wrapper
        else:
            # 为异步函数添加错误处理
            original_func = self.func
            @functools.wraps(original_func)
            async def wrapper(event):
                try:
                    return await original_func(event)
                except Exception as e:
                    logger.error(f"异步事件处理器执行失败: {e}", exc_info=True)
            self.func = wrapper


class ListenerManager:
    """监听器管理器（单例）
    
    负责管理所有事件处理器，并提供事件分发功能。
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialize()
            return cls._instance
    
    def _initialize(self):
        """初始化管理器状态"""
        self._handlers: List[EventHandler] = []
        self._handlers_lock = threading.RLock()
        self._core = None
        self._running = False
        self._dispatch_thread = None
        self._stop_event = threading.Event()
    
    @property
    def core(self):
        """获取关联的适配器核心实例"""
        return self._core
    
    @core.setter
    def core(self, value):
        """设置适配器核心实例"""
        if self._core is not None and self._running:
            self.stop()
        self._core = value
    
    def register(self, handler: EventHandler) -> None:
        """注册事件处理器
        
        Args:
            handler: 事件处理器
        """
        with self._handlers_lock:
            self._handlers.append(handler)
            # 按优先级排序（优先级高的在前）
            self._handlers.sort(key=lambda h: h.priority, reverse=True)
            logger.debug(f"注册事件处理器: {handler.func.__name__}, 优先级: {handler.priority}")
    
    def unregister(self, func: Callable) -> bool:
        """注销事件处理器
        
        Args:
            func: 要注销的处理函数
            
        Returns:
            如果成功注销返回 True，否则返回 False
        """
        with self._handlers_lock:
            initial_count = len(self._handlers)
            self._handlers = [h for h in self._handlers if h.func != func]
            removed = len(self._handlers) < initial_count
            if removed:
                logger.debug(f"注销事件处理器: {func.__name__}")
            return removed
    
    def get_handlers_for_event(self, event: Dict[str, Any]) -> List[EventHandler]:
        """获取匹配指定事件的所有处理器
        
        Args:
            event: 事件字典
            
        Returns:
            匹配的事件处理器列表
        """
        with self._handlers_lock:
            return [h for h in self._handlers if h.enabled and h.filter.match(event)]
    
    async def _dispatch_async(self, event: Dict[str, Any]) -> None:
        """异步分发事件到所有匹配的处理器
        
        Args:
            event: 事件字典
        """
        handlers = self.get_handlers_for_event(event)
        
        for handler in handlers:
            if handler.is_async:
                # 异步处理器
                await handler.func(event)
            else:
                # 同步处理器在默认线程池中执行
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, handler.func, event)
    
    def _dispatch_sync(self, event: Dict[str, Any]) -> None:
        """同步分发事件到所有匹配的处理器
        
        Args:
            event: 事件字典
        """
        handlers = self.get_handlers_for_event(event)
        
        for handler in handlers:
            if handler.is_async:
                # 异步处理器需要在事件循环中调度
                if self._core and self._core.loop and self._core.loop.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        handler.func(event), 
                        self._core.loop
                    )
                    # 不等待结果，避免阻塞
                    future.add_done_callback(lambda f: f.exception() if f.exception() else None)
                else:
                    logger.warning(f"无法执行异步处理器 {handler.func.__name__}，事件循环不可用")
            else:
                # 同步处理器直接调用
                try:
                    handler.func(event)
                except Exception as e:
                    logger.error(f"同步处理器执行失败: {e}", exc_info=True)
    
    def _dispatch_loop(self) -> None:
        """事件分发循环（在独立线程中运行）"""
        logger.info("事件分发线程启动")
        
        while not self._stop_event.is_set():
            if not self._core:
                time.sleep(0.1)
                continue
            
            try:
                # 从核心的消息队列获取事件（非阻塞）
                event = self._core.get_message(block=False, timeout=0.1)
                if event:
                    self._dispatch_sync(event)
                else:
                    time.sleep(0.01)  # 避免忙等待
            except Exception as e:
                logger.error(f"事件分发失败: {e}", exc_info=True)
                time.sleep(0.1)
        
        logger.info("事件分发线程停止")
    
    def start(self) -> None:
        """启动事件监听器
        
        开始从适配器核心消费事件并分发给注册的处理器。
        """
        if self._running:
            logger.warning("监听器已经在运行")
            return
        
        if not self._core:
            raise RuntimeError("请先设置适配器核心实例 (通过 setup_listeners() 或直接设置 core 属性)")
        
        self._stop_event.clear()
        self._running = True
        self._dispatch_thread = threading.Thread(
            target=self._dispatch_loop,
            name="EventDispatcher",
            daemon=True
        )
        self._dispatch_thread.start()
        logger.info("事件监听器已启动")
    
    def stop(self) -> None:
        """停止事件监听器"""
        if not self._running:
            return
        
        self._running = False
        self._stop_event.set()
        
        if self._dispatch_thread:
            self._dispatch_thread.join(timeout=5)
            self._dispatch_thread = None
        
        logger.info("事件监听器已停止")
    
    def clear(self) -> None:
        """清除所有事件处理器"""
        with self._handlers_lock:
            self._handlers.clear()
        logger.info("所有事件处理器已清除")


# 全局单例实例
_listener_manager = None
_listener_manager_lock = threading.Lock()

def get_listener_manager() -> ListenerManager:
    """获取全局监听器管理器实例
    
    Returns:
        监听器管理器实例
    """
    global _listener_manager
    with _listener_manager_lock:
        if _listener_manager is None:
            _listener_manager = ListenerManager()
        return _listener_manager


def setup_listeners(core = None) -> ListenerManager:
    """设置事件监听器
    
    Args:
        core: 适配器核心实例，如果为 None 则尝试使用全局核心实例
        
    Returns:
        监听器管理器实例
        
    Raises:
        RuntimeError: 如果无法获取适配器核心实例
    """
    if core is None:
        from neobot_adapter.receiver import get_core
        try:
            core = get_core()
        except RuntimeError as e:
            raise RuntimeError(
                "无法获取适配器核心实例，请先初始化适配器核心或显式提供核心实例"
            ) from e
    
    manager = get_listener_manager()
    manager.core = core
    manager.start()
    return manager


def stop_listening() -> None:
    """停止事件监听"""
    manager = get_listener_manager()
    manager.stop()