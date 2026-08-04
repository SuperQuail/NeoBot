"""针对 SQLite 瞬时锁错误的重试辅助工具。"""

from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, Iterator, TypeVar

T = TypeVar("T")

# SQLite returns this error code / message when it cannot acquire a write lock
_LOCKED_MESSAGES = (
    "database is locked",
    "database table is locked",
    "locking protocol",
    "deadlock",
)


def _iter_exception_chain(exc: BaseException) -> Iterator[BaseException]:
    """按顺序产出 *exc* 及其 ``__cause__``/``__context__`` 异常链，循环安全。"""
    seen: set[int] = set()
    link: BaseException | None = exc
    while link is not None and id(link) not in seen:
        seen.add(id(link))
        yield link
        link = link.__cause__ or link.__context__


def _is_locked_error(exc: Exception) -> bool:
    # PendingRollbackError 的 message 内嵌原始 flush 异常
    # （"Original exception was: ... database is locked"），
    # 沿 __cause__/__context__ 链匹配可覆盖该场景，且不会对
    # 普通含 "rolled back" 字样的错误过度匹配。
    for link in _iter_exception_chain(exc):
        msg = str(link).casefold()
        if any(pattern in msg for pattern in _LOCKED_MESSAGES):
            return True
    return False


async def retry_on_lock(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    on_retry: Callable[[], Awaitable[None]] | None = None,
) -> T:
    """执行 *coro_factory*，当 SQLite 报告数据库被锁定时，
    按指数退避 + 随机抖动重试。

    Parameters
    ----------
    coro_factory : callable returning awaitable
        每次调用都返回新协程的工厂函数（以便重试）。
    max_retries : int
        重试次数上限，超过后抛出最后一次异常。
    base_delay : float
        初始延迟（秒），每次重试翻倍。
    max_delay : float
        延迟上限。
    on_retry : optional callable returning awaitable
        每次重试尝试前（退避延迟之后）调用。失败的 flush
        会让 SQLAlchemy 会话处于已回滚状态，可传入类似
        ``session.rollback`` 的调用以恢复会话；重试的事务体
        将在全新事务上重新执行。

    Raises
    ------
    重试全部耗尽时抛出最后遇到的异常。
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if not _is_locked_error(exc):
                raise
            if attempt >= max_retries:
                break
            delay = min(base_delay * (2**attempt), max_delay)
            jitter = random.uniform(0, delay * 0.25)
            await asyncio.sleep(delay + jitter)
            if on_retry is not None:
                await on_retry()

    # All retries exhausted
    raise last_exc  # type: ignore[misc]
