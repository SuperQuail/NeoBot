"""图片引用索引：迁移 0028 往返 + image_refs 读写与保留期清理（issue #80）。

为什么单独一张表：解析结果按内容哈希存在 `images`，而拉不到的图片算不出哈希，
只能按「引用摘要」冗余存一份描述，供过期时回显。
"""

from __future__ import annotations

import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest_asyncio

from neobot_contracts.time_context import now_utc
from neobot_storage.uow import make_uow_factory

from .archive_test_utils import create_memory_engine, create_schema

IMAGE_REF_COLUMNS = {"source_ref", "analysis_text", "updated_at"}


def _alembic_config(url: str):
    from alembic.config import Config

    from neobot_storage import engine as storage_engine

    pkg_dir = Path(storage_engine.__file__).resolve().parent
    cfg = Config(str(pkg_dir / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(pkg_dir / "alembic"))
    return cfg


def _tables(db: Path) -> set[str]:
    connection = sqlite3.connect(str(db))
    try:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    finally:
        connection.close()
    return {str(row[0]) for row in rows}


def test_migration_0028_round_trip(tmp_path: Path) -> None:
    """0028 建表 / 删表往返正常，且不动既有 images 数据。"""
    from alembic import command

    from neobot_storage.engine import sqlite_url

    db = tmp_path / "image_refs.db"
    cfg = _alembic_config(sqlite_url(db))

    command.upgrade(cfg, "0027")
    assert "image_refs" not in _tables(db), "0027 之前不该有 image_refs"

    command.upgrade(cfg, "head")
    assert "image_refs" in _tables(db)

    info = {row[1]: row for row in sqlite3.connect(str(db)).execute("PRAGMA table_info(image_refs)")}
    assert set(info) == IMAGE_REF_COLUMNS
    assert info["source_ref"][3] == 1, "source_ref 必须非空（主键）"
    assert info["analysis_text"][3] == 1, "analysis_text 必须非空"
    assert info["updated_at"][3] == 1, "updated_at 必须非空"
    indexes = {row[1] for row in sqlite3.connect(str(db)).execute("PRAGMA index_list(image_refs)")}
    assert "ix_image_refs_updated_at" in indexes

    connection = sqlite3.connect(str(db))
    try:
        connection.execute(
            "INSERT INTO image_refs (source_ref, analysis_text, updated_at) "
            "VALUES ('digest-1', '一只橘猫', '2026-01-01 00:00:00.000000')"
        )
        connection.commit()
    finally:
        connection.close()

    command.downgrade(cfg, "0027")
    assert "image_refs" not in _tables(db)
    # images 表与里面的档案数据不受影响
    assert "images" in _tables(db)

    command.upgrade(cfg, "head")
    assert "image_refs" in _tables(db)


@pytest_asyncio.fixture
async def engine():
    eng = create_memory_engine()
    await create_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def uow_factory(engine):
    return make_uow_factory(engine)


async def test_remember_ref_round_trip(uow_factory) -> None:
    async with uow_factory() as uow:
        await uow.images.remember_ref("digest-1", "一只橘猫趴在键盘上")
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.images.get_ref_text("digest-1") == "一只橘猫趴在键盘上"
        assert await uow.images.get_ref_text("digest-missing") is None
        assert await uow.images.get_ref_text("") is None


async def test_remember_ref_keeps_latest_and_prunes_expired(uow_factory, engine) -> None:
    async with uow_factory() as uow:
        await uow.images.remember_ref("digest-1", "旧描述")
        await uow.commit()
    async with uow_factory() as uow:
        await uow.images.remember_ref("digest-1", "新描述")
        await uow.commit()

    # 超出保留期的记录在下一次写入时被清掉（表不会无界增长）
    from sqlalchemy.ext.asyncio import AsyncSession

    from neobot_storage.models import ImageRefData

    async with AsyncSession(engine) as session:
        session.add(
            ImageRefData(
                source_ref="digest-old",
                analysis_text="很久以前",
                updated_at=now_utc() - timedelta(days=400),
            )
        )
        await session.commit()
    async with uow_factory() as uow:
        await uow.images.remember_ref("digest-2", "另一张图")
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.images.get_ref_text("digest-1") == "新描述"
        assert await uow.images.get_ref_text("digest-old") is None
        assert await uow.images.get_ref_text("digest-2") == "另一张图"


async def test_remember_ref_ignores_empty_values(uow_factory) -> None:
    async with uow_factory() as uow:
        await uow.images.remember_ref("", "无引用")
        await uow.images.remember_ref("digest-1", "")
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.images.get_ref_text("digest-1") is None
