"""Storage 装配"""

from __future__ import annotations

from pathlib import Path

from neobot_storage import create_engine, make_uow_factory, sqlite_url


def build_storage(db_url: str | None = None, *, db_path: str | Path | None = None):
    """创建异步引擎和 UoW 工厂"""
    if db_url is None:
        db_url = sqlite_url(db_path or "neobot.db")
    engine = create_engine(db_url)
    uow_factory = make_uow_factory(engine)
    return engine, uow_factory
