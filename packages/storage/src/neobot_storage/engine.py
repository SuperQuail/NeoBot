"""异步引擎工厂。"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine as _create


def create_engine(db_url: str, **kwargs) -> AsyncEngine:
    """创建异步 SQLAlchemy 引擎。

    对 SQLite，传入形如 ``sqlite+aiosqlite:///path/to/db.sqlite3`` 的 URL。

    当后端为 SQLite 时，自动启用 WAL 日志模式与 5 秒 busy_timeout，
    以减少并发异步任务访问时的 "database is locked" 错误。
    """
    engine = _create(db_url, **kwargs)
    _enable_wal_if_sqlite(engine)
    return engine


def _enable_wal_if_sqlite(engine: AsyncEngine) -> None:
    """当引擎面向 SQLite 时启用 WAL 模式与 busy_timeout。"""
    if engine.url.get_backend_name() != "sqlite":
        return

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
    """根据文件系统路径构建规范化的 sqlite+aiosqlite URL。"""
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
