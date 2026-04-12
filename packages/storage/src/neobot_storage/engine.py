"""Async engine factory."""

from __future__ import annotations

from pathlib import Path
from typing import Union

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine as _create


def create_engine(db_url: str, **kwargs) -> AsyncEngine:
    """Create an async SQLAlchemy engine.

    For SQLite, pass a URL like ``sqlite+aiosqlite:///path/to/db.sqlite3``.
    """
    return _create(db_url, **kwargs)


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
