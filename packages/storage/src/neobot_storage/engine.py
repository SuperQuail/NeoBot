"""Async engine factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine as _create


def create_engine(db_url: str, **kwargs) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    For SQLite, pass a URL like ``sqlite+aiosqlite:///path/to/db.sqlite3``.
    """
    return _create(db_url, **kwargs)
