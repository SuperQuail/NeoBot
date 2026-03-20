"""Storage 装配"""

from __future__ import annotations

from neobot_storage import create_engine, make_uow_factory
from neobot_storage.uow import SqlAlchemyUnitOfWork


def build_storage(db_url: str = "sqlite+aiosqlite:///neobot.db"):
    """创建异步引擎和 UoW 工厂"""
    engine = create_engine(db_url)
    uow_factory = make_uow_factory(engine)
    return engine, uow_factory
