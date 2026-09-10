"""creator_images 图库固定编号: 分配、保持、查询与迁移回填。"""

from __future__ import annotations

from pathlib import Path

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from neobot_storage.engine import create_engine, sqlite_url
from neobot_storage.models import Base
from neobot_storage.repositories.creator_image import SqlAlchemyCreatorImageAccess


@pytest_asyncio.fixture
async def engine(tmp_path):
    """每用例独立的临时 sqlite 引擎。"""
    eng = create_engine(sqlite_url(tmp_path / "creator_images.db"))
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _set(
    repo,
    image_id: str,
    *,
    source: str = "gallery",
    gallery_no: int | None = None,
    description: str | None = None,
):
    return await repo.set(
        image_id,
        source=source,
        file_hash="h" * 64,
        file_path=f"/tmp/{image_id}.png",
        description=description,
        gallery_no=gallery_no,
    )


async def test_next_gallery_no_starts_at_one_and_skips_used(session_factory):
    """编号从 1 开始，并且永远取当前最大编号 +1。"""

    async with session_factory() as session:
        repo = SqlAlchemyCreatorImageAccess(session)
        assert await repo.next_gallery_no() == 1

        await _set(repo, "g_a", gallery_no=await repo.next_gallery_no())
        await _set(repo, "g_b", gallery_no=await repo.next_gallery_no())

        assert await repo.next_gallery_no() == 3
        await session.commit()


async def test_gallery_no_is_written_once_and_survives_updates(session_factory):
    """更新已有记录不得改写已分配的编号。"""

    async with session_factory() as session:
        repo = SqlAlchemyCreatorImageAccess(session)
        created = await _set(repo, "g_a", gallery_no=1)
        assert created.gallery_no == 1

        # 更新时即使传入更大的编号，也必须保持 1
        updated = await _set(repo, "g_a", gallery_no=99, description="改描述")
        assert updated.gallery_no == 1

        fetched = await repo.get("g_a")
        assert fetched.gallery_no == 1
        await session.commit()


async def test_get_by_gallery_no_returns_matching_record(session_factory):
    """按编号查询必须命中唯一记录，未分配编号的记录查不到。"""

    async with session_factory() as session:
        repo = SqlAlchemyCreatorImageAccess(session)
        await _set(repo, "g_a", gallery_no=7)
        await _set(repo, "tmp_a", source="tmp")

        found = await repo.get_by_gallery_no(7)
        assert found is not None and found.image_id == "g_a"
        assert await repo.get_by_gallery_no(8) is None
        assert await repo.get_by_gallery_no(1) is None
        await session.commit()


async def test_tmp_records_keep_null_gallery_no(session_factory):
    """暂存区记录不参与图库编号。"""

    async with session_factory() as session:
        repo = SqlAlchemyCreatorImageAccess(session)
        record = await _set(repo, "tmp_a", source="tmp")
        assert record.gallery_no is None
        await session.commit()


async def test_migration_backfills_gallery_numbers_by_created_at(tmp_path):
    """迁移 0023 必须给历史图库记录按入库顺序回填 1..N，暂存记录保持为空。"""

    # Arrange: 先停在 0022，插入没有编号的历史数据
    from alembic import command
    from alembic.config import Config

    from neobot_storage import engine as storage_engine

    db = tmp_path / "backfill.db"
    url = sqlite_url(db)
    pkg_dir = Path(storage_engine.__file__).resolve().parent
    cfg = Config(str(pkg_dir / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(pkg_dir / "alembic"))
    command.upgrade(cfg, "0022")

    engine = create_engine(url)
    try:
        async with engine.begin() as conn:
            for index, (image_id, source, created_at) in enumerate(
                [
                    ("g_second", "gallery", "2026-01-02 00:00:00.000000"),
                    ("g_first", "gallery", "2026-01-01 00:00:00.000000"),
                    ("tmp_only", "tmp", "2026-01-03 00:00:00.000000"),
                ]
            ):
                await conn.execute(
                    text(
                        "INSERT INTO creator_images "
                        "(image_id, source, file_hash, file_path, created_at, updated_at, version) "
                        "VALUES (:image_id, :source, :file_hash, :file_path, :created_at, :created_at, 1)"
                    ),
                    {
                        "image_id": image_id,
                        "source": source,
                        "file_hash": f"{index}" * 64,
                        "file_path": f"/tmp/{image_id}.png",
                        "created_at": created_at,
                    },
                )
    finally:
        await engine.dispose()

    # Act
    command.upgrade(cfg, "head")

    # Assert
    engine = create_engine(url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text("SELECT image_id, gallery_no FROM creator_images ORDER BY id")
                )
            ).all()
    finally:
        await engine.dispose()

    # 先入库的 g_first（created_at 更早）拿 1 号，与插入顺序无关；暂存记录不编号
    assert dict(rows) == {"g_first": 1, "g_second": 2, "tmp_only": None}
