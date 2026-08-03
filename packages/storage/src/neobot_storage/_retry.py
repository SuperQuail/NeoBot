"""Retry helpers for transient SQLite locking errors."""

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
    """Yield *exc* and its ``__cause__``/``__context__`` chain, cycle-safe."""
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
    """Execute *coro_factory* and retry with exponential backoff + jitter
    when SQLite reports a locked-database error.

    Parameters
    ----------
    coro_factory : callable returning awaitable
        A thunk that returns a new coroutine each call (so we can retry).
    max_retries : int
        How many times to retry before re-raising the last error.
    base_delay : float
        Initial delay in seconds (doubled each retry).
    max_delay : float
        Upper bound for delay.
    on_retry : optional callable returning awaitable
        Invoked right before each retry attempt (after the backoff delay).
        A failed flush leaves the SQLAlchemy session in a rolled-back state,
        so pass something like ``session.rollback`` to restore it; the retried
        transaction body then re-executes on a fresh transaction.

    Raises
    ------
    The last encountered exception if all retries are exhausted.
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
