"""Retry helpers for transient SQLite locking errors."""

from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

# SQLite returns this error code / message when it cannot acquire a write lock
_LOCKED_MESSAGES = (
    "database is locked",
    "database table is locked",
    "locking protocol",
    "deadlock",
)


def _is_locked_error(exc: Exception) -> bool:
    msg = str(exc).casefold()
    return any(pattern in msg for pattern in _LOCKED_MESSAGES)


async def retry_on_lock(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
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

    # All retries exhausted
    raise last_exc  # type: ignore[misc]
