"""星舰插件数据库迁移。"""

from __future__ import annotations

from sqlalchemy import text


async def create_initial_schema(connection) -> None:
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS starship_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game VARCHAR(64) NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                player VARCHAR(64) NOT NULL DEFAULT '',
                user_id VARCHAR(32) NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL
            )
            """
        )
    )
    await connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_starship_scores_game ON starship_scores (game)")
    )
    await connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_starship_scores_created "
            "ON starship_scores (created_at)"
        )
    )
    await connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS starship_achievements (
                key VARCHAR(64) PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0,
                first_at DATETIME NOT NULL,
                last_at DATETIME NOT NULL,
                detail TEXT NOT NULL DEFAULT ''
            )
            """
        )
    )


async def add_score_detail_index(connection) -> None:
    await connection.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_starship_scores_rank "
            "ON starship_scores (game, score DESC)"
        )
    )
