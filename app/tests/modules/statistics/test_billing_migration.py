"""spec(4) Part A：迁移 0025（A5 存量行自动填充 + upgrade/downgrade 往返）。"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from neobot_storage.engine import create_engine, sqlite_url


def _alembic_config(url: str):
    from alembic.config import Config

    from neobot_storage import engine as storage_engine

    pkg_dir = Path(storage_engine.__file__).resolve().parent
    cfg = Config(str(pkg_dir / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option("script_location", str(pkg_dir / "alembic"))
    return cfg


def _columns(db: Path) -> set[str]:
    import sqlite3

    connection = sqlite3.connect(str(db))
    try:
        rows = connection.execute("PRAGMA table_info(model_usage_records)").fetchall()
    finally:
        connection.close()
    return {str(row[1]) for row in rows}


async def test_migration_0025_backfills_builtin(tmp_path):
    """A5：升级前插入的存量行自动填充 cost_source='builtin'、cost_detail=NULL。"""
    from alembic import command

    db = tmp_path / "billing.db"
    url = sqlite_url(db)
    cfg = _alembic_config(url)
    command.upgrade(cfg, "0024")

    engine = create_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO model_usage_records "
                    "(module_name, model_name, provider_name, input_tokens, output_tokens, "
                    " cache_hit_tokens, cache_miss_tokens, cost_cny, created_at) "
                    "VALUES ('reply_agent', 'deepseek-flash', 'DeepSeek', 10, 20, 0, 0, 0.5, "
                    " '2026-09-12 00:00:00.000000')"
                )
            )
    finally:
        await engine.dispose()

    assert "cost_source" not in _columns(db)
    command.upgrade(cfg, "head")
    assert {"cost_source", "cost_detail"} <= _columns(db)

    engine = create_engine(url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT cost_source, cost_detail, cost_cny FROM model_usage_records")
                )
            ).one()
    finally:
        await engine.dispose()
    assert row[0] == "builtin"
    assert row[1] is None
    assert row[2] == 0.5

    # 往返：downgrade 必须干净地移除两列，再 upgrade 能恢复
    command.downgrade(cfg, "0024")
    assert not ({"cost_source", "cost_detail"} & _columns(db))
    command.upgrade(cfg, "head")
    assert {"cost_source", "cost_detail"} <= _columns(db)


async def test_migration_0025_round_trip_keeps_rows(tmp_path):
    """A5：downgrade / upgrade 往返不丢行（0025 只加列）。"""
    from alembic import command

    db = tmp_path / "billing_roundtrip.db"
    url = sqlite_url(db)
    cfg = _alembic_config(url)
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO model_usage_records "
                    "(module_name, model_name, provider_name, input_tokens, output_tokens, "
                    " cache_hit_tokens, cache_miss_tokens, cost_cny, created_at, cost_source) "
                    "VALUES ('reply_common', 'deepseek-flash', 'DeepSeek', 1, 2, 0, 0, -0.25, "
                    " '2026-09-12 00:00:00.000000', 'script:per_call')"
                )
            )
    finally:
        await engine.dispose()

    command.downgrade(cfg, "0024")
    command.upgrade(cfg, "head")

    engine = create_engine(url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT cost_cny, cost_source FROM model_usage_records")
                )
            ).one()
    finally:
        await engine.dispose()
    assert row[0] == -0.25
    assert row[1] == "builtin"
