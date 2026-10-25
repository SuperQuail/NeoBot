"""B站集成层的兼容小工具。

BilibiliClient（bili-core）是**同步**请求封装，BilibiliService 是异步门面；
本层同时接受两者：调用时协程就 await，普通函数丢线程池，避免阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import inspect
from collections import deque
from typing import Any


async def call_client(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """调用客户端/服务方法：协程函数 await，同步函数 asyncio.to_thread。"""
    if inspect.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    result = await asyncio.to_thread(fn, *args, **kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


def get_field(obj: Any, name: str, default: Any = None) -> Any:
    """同时兼容 dict 与 dataclass/对象（bili-core 的返回结构尚未冻结）。"""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def resolve_client(obj: Any) -> Any | None:
    """接受 BilibiliClient 或 BilibiliService，返回当前可用的同步 client。

    BilibiliService 登录状态运行期会变（二维码登录/dormant），因此调用方
    每轮都重新 resolve，而不是在构造时缓存。休眠的 service（available 为
    False）返回 None：绝不回退成 service 本身，否则调用方拿到的是缺方法的
    门面，异常被吞成空结果（"没通知"而不是"没登录"）。
    """
    if obj is None:
        return None
    if getattr(obj, "available", True) is False:
        return None
    inner = getattr(obj, "client", None)
    if inner is not None:
        return inner
    return obj


def bilibili_config(config: Any) -> Any | None:
    """接受 BotConfig 或 config.bilibili，返回 Bilibili 配置对象。"""
    if config is None:
        return None
    inner = getattr(config, "bilibili", None)
    return inner if inner is not None else config


class RecentIds:
    """有界去重集合：FIFO 淘汰，防止长时间轮询后无界增长。"""

    def __init__(self, maxlen: int = 2000) -> None:
        self._items: deque[str] = deque()
        self._seen: set[str] = set()
        self._maxlen = max(1, int(maxlen))

    def add(self, key: str) -> bool:
        """记录 key；返回 False 表示之前已见过。"""
        if key in self._seen:
            return False
        if len(self._items) >= self._maxlen:
            self._seen.discard(self._items.popleft())
        self._items.append(key)
        self._seen.add(key)
        return True

    def keys(self) -> list[str]:
        """按插入顺序返回当前保留的 key（持久化 restore 用）。"""
        return list(self._items)

    def __contains__(self, key: str) -> bool:
        return key in self._seen
