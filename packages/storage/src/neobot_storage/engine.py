"""Async engine factory."""

from __future__ import annotations

from pathlib import Path
from typing import Union

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine as _create


def create_engine(db_url: str, **kwargs) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    For SQLite, pass a URL like ``sqlite+aiosqlite:///path/to/db.sqlite3``.

    When the backend is SQLite, WAL journal mode and a 5-second busy timeout
    are automatically enabled to reduce "database is locked" errors under
    concurrent async task access.
    """
    engine = _create(db_url, **kwargs)
    _enable_wal_if_sqlite(engine)
    return engine


def _enable_wal_if_sqlite(engine: AsyncEngine) -> None:
    """Enable WAL mode + busy_timeout when the engine targets SQLite."""
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass
        try:
            cursor.execute("PRAGMA busy_timeout=5000")
        except Exception:
            pass
        cursor.close()


def sqlite_url(path: Union[str, Path]) -> str:
    """Build a normalized sqlite+aiosqlite URL from a filesystem path."""
    resolved = Path(path).expanduser().resolve()
    return f"sqlite+aiosqlite:///{resolved.as_posix()}"


def run_migrations(db_url: str) -> None:
    """使用 Alembic 自动迁移到最新版本"""
    from alembic import command
    from alembic.config import Config

    alembic_dir = Path(__file__).resolve().parent.parent.parent / "alembic"
    ini_path = alembic_dir.parent / "alembic.ini"

    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.set_main_option("script_location", str(alembic_dir))
    command.upgrade(cfg, "head")
