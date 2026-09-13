"""小游戏插件数据库迁移（插件独立库，不动本体迁移）。

DDL 与 :mod:`.models` 的声明必须一致（有结构一致性测试守住）。
"""

from __future__ import annotations

from sqlalchemy import text

from neobot_modloader import Migration

#: 插件数据库文件名（plugins_data/minigame/databases/minigame.db）
DATABASE_FILENAME = "minigame.db"


async def create_initial_schema(connection) -> None:
    """v1：六张表 + 索引。"""
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS mg_profile (
                user_id VARCHAR(32) NOT NULL PRIMARY KEY,
                score INTEGER NOT NULL DEFAULT 0,
                best_score INTEGER NOT NULL DEFAULT 0,
                plays INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME NOT NULL
            )
            """
        )
    )
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS mg_bottle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id VARCHAR(32) NOT NULL DEFAULT '',
                sender_name VARCHAR(128) NOT NULL DEFAULT '',
                sender_avatar TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                anonymous BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                picked_at DATETIME,
                picked_by VARCHAR(32) NOT NULL DEFAULT '',
                status VARCHAR(16) NOT NULL DEFAULT 'pooled',
                meta JSON
            )
            """
        )
    )
    await connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_mg_bottle_pool ON mg_bottle (status, sender_id)")
    )
    await connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_mg_bottle_picked_by "
            "ON mg_bottle (picked_by, picked_at)"
        )
    )
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS mg_daily (
                user_id VARCHAR(32) NOT NULL,
                game_id VARCHAR(32) NOT NULL,
                day VARCHAR(10) NOT NULL,
                plays INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, game_id, day)
            )
            """
        )
    )
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS mg_checkin (
                user_id VARCHAR(32) NOT NULL,
                day VARCHAR(10) NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                streak INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                PRIMARY KEY (user_id, day)
            )
            """
        )
    )
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS mg_fortune (
                user_id VARCHAR(32) NOT NULL,
                day VARCHAR(10) NOT NULL,
                result_key VARCHAR(32) NOT NULL DEFAULT '',
                result_text TEXT NOT NULL DEFAULT '',
                drawn_at DATETIME NOT NULL,
                PRIMARY KEY (user_id, day)
            )
            """
        )
    )
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS mg_record (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(32) NOT NULL DEFAULT '',
                game_id VARCHAR(32) NOT NULL DEFAULT '',
                score INTEGER NOT NULL DEFAULT 0,
                conversation_id VARCHAR(64) NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL
            )
            """
        )
    )
    await connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_mg_record_rank ON mg_record (game_id, score DESC)")
    )
    await connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_mg_record_created ON mg_record (created_at)")
    )


def build_migrations() -> tuple[Migration, ...]:
    """本插件数据库的迁移列表（新增结构时追加 version）。"""
    return (
        Migration(version=1, name="initial-schema", upgrade=create_initial_schema),
    )


__all__ = ["DATABASE_FILENAME", "build_migrations", "create_initial_schema"]
