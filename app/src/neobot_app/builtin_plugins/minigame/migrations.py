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


async def add_profile_user_name(connection) -> None:
    """v2：mg_profile 增加 user_name（issue #85）。

    排行榜对全群可见：有昵称就显示昵称，没有昵称回落掩码，**不再下发完整 QQ 号**。
    SQLite 的 ADD COLUMN 带 NOT NULL DEFAULT 时对既有行安全（都拿空串）。
    """
    await connection.execute(
        text(
            "ALTER TABLE mg_profile "
            "ADD COLUMN user_name VARCHAR(128) NOT NULL DEFAULT ''"
        )
    )


#: v3 重建表要搬运的列（按 v3 新表的列顺序写）。
#: 必须显式列清单：v2 的 ALTER TABLE 把 user_name 追加在 mg_profile 末尾，而 v3
#: 新表把它放在第二列；SELECT * 会按位置搬运，导致 score/user_name/best_score
#: 等整体错位（DATETIME 列甚至可能拿到人名）。
_V3_COPY_COLUMNS = {
    "mg_profile": "user_id, user_name, score, best_score, plays, wins, updated_at",
    "mg_bottle": (
        "id, sender_id, sender_name, sender_avatar, content, anonymous, "
        "created_at, picked_at, picked_by, status, meta"
    ),
    "mg_daily": "user_id, game_id, day, plays",
    "mg_checkin": "user_id, day, score, streak, created_at",
    "mg_fortune": "user_id, day, result_key, result_text, drawn_at",
    "mg_record": "id, user_id, game_id, score, conversation_id, created_at",
}

#: v4 要改写的（表, 列）：这些列存本地用户 ID。
_LEGACY_USER_ID_COLUMNS = (
    ("mg_profile", "user_id"),
    ("mg_bottle", "sender_id"),
    ("mg_bottle", "picked_by"),
    ("mg_daily", "user_id"),
    ("mg_checkin", "user_id"),
    ("mg_fortune", "user_id"),
    ("mg_record", "user_id"),
)


async def widen_user_ids(connection) -> None:
    """v3：用户/会话 ID 列加宽到 128，容纳官方通道的 openid 字符串。

    SQLite 不强制 VARCHAR 长度，但列声明要与 models 一致，同时给「对外能力
    接受 openid」一个明确的库结构版本。重建表必须按 :data:`_V3_COPY_COLUMNS`
    的显式列清单搬运，不能用 SELECT *（v2 追加的 user_name 在旧表末尾）。
    """
    tables = {
        "mg_profile": """
            CREATE TABLE mg_profile_v3 (
                user_id VARCHAR(128) NOT NULL PRIMARY KEY,
                user_name VARCHAR(128) NOT NULL DEFAULT '',
                score INTEGER NOT NULL DEFAULT 0,
                best_score INTEGER NOT NULL DEFAULT 0,
                plays INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME NOT NULL
            )
        """,
        "mg_bottle": """
            CREATE TABLE mg_bottle_v3 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id VARCHAR(128) NOT NULL DEFAULT '',
                sender_name VARCHAR(128) NOT NULL DEFAULT '',
                sender_avatar TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL DEFAULT '',
                anonymous BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                picked_at DATETIME,
                picked_by VARCHAR(128) NOT NULL DEFAULT '',
                status VARCHAR(16) NOT NULL DEFAULT 'pooled',
                meta JSON
            )
        """,
        "mg_daily": """
            CREATE TABLE mg_daily_v3 (
                user_id VARCHAR(128) NOT NULL,
                game_id VARCHAR(32) NOT NULL,
                day VARCHAR(10) NOT NULL,
                plays INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, game_id, day)
            )
        """,
        "mg_checkin": """
            CREATE TABLE mg_checkin_v3 (
                user_id VARCHAR(128) NOT NULL,
                day VARCHAR(10) NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                streak INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                PRIMARY KEY (user_id, day)
            )
        """,
        "mg_fortune": """
            CREATE TABLE mg_fortune_v3 (
                user_id VARCHAR(128) NOT NULL,
                day VARCHAR(10) NOT NULL,
                result_key VARCHAR(32) NOT NULL DEFAULT '',
                result_text TEXT NOT NULL DEFAULT '',
                drawn_at DATETIME NOT NULL,
                PRIMARY KEY (user_id, day)
            )
        """,
        "mg_record": """
            CREATE TABLE mg_record_v3 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(128) NOT NULL DEFAULT '',
                game_id VARCHAR(32) NOT NULL DEFAULT '',
                score INTEGER NOT NULL DEFAULT 0,
                conversation_id VARCHAR(128) NOT NULL DEFAULT '',
                created_at DATETIME NOT NULL
            )
        """,
    }
    for table, create_sql in tables.items():
        columns = _V3_COPY_COLUMNS[table]
        await connection.execute(text(create_sql))
        await connection.execute(
            text(f"INSERT INTO {table}_v3 ({columns}) SELECT {columns} FROM {table}")
        )
        await connection.execute(text(f"DROP TABLE {table}"))
        await connection.execute(text(f"ALTER TABLE {table}_v3 RENAME TO {table}"))
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
        text("CREATE INDEX IF NOT EXISTS ix_mg_record_rank ON mg_record (game_id, score DESC)")
    )
    await connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_mg_record_created ON mg_record (created_at)")
    )


async def _rewrite_legacy_ids(connection, table: str, column: str, resolve) -> None:
    """逐列把旧合成号改写成 openid；目标行已存在时跳过（保留旧数据）。"""
    result = await connection.execute(text(f"SELECT DISTINCT {column} FROM {table}"))
    for (value,) in result:
        legacy = str(value or "")
        openid = resolve(legacy)
        if not openid or openid == legacy:
            continue
        await connection.execute(
            text(f"UPDATE OR IGNORE {table} SET {column}=:openid WHERE {column}=:legacy"),
            {"openid": openid, "legacy": legacy},
        )


async def rewrite_legacy_user_ids(connection) -> None:
    """v4：把旧 13 位合成号本地 ID 改写成官方 openid。

    本体数据库的启动迁移只覆盖本体表；插件库是独立 SQLite，升级后旧积分/
    签到/运势/榜单行在官方通道按 openid 查不到。这里借本体 user_identity 的
    只读映射（bootstrap 在加载插件前已 bind DATA_DIR）做一次显式 UPDATE：
    无 identities.json / 非合成号 / 无映射时原样保留；目标 openid 行已存在时
    跳过该行，不删除旧数据。
    """
    from neobot_app.user_identity import openid_for_legacy_id

    for table, column in _LEGACY_USER_ID_COLUMNS:
        await _rewrite_legacy_ids(
            connection, table, column, lambda value: openid_for_legacy_id("user", value)
        )
    # 会话 ID 可能是群也可能是用户，两种映射依次尝试（命中一种即用）。
    await _rewrite_legacy_ids(
        connection,
        "mg_record",
        "conversation_id",
        lambda value: openid_for_legacy_id("group", value) or openid_for_legacy_id("user", value),
    )


#: 旧 v3（用 SELECT * 按位置搬运 mg_profile）的校验和。
#: 该版本只在 #305 的开发快照中出现过，未随任何发布版本发布；跑过它的开发库
#: 记录的是这个校验和，命中后由 v5 修复错位数据。
LEGACY_V3_CHECKSUMS = ("5af7f0a52a7b97ebe0aaef6d87e27d070b4985b2ab6a8602f32c9d7f9e8e134e",)


async def repair_v3_profile_copy_order(connection) -> None:
    """v5：修复旧 v3 用 SELECT * 搬运 mg_profile 造成的列错位。

    旧 v3 只在 #305 的开发快照里存在过（未发布）。旧表列顺序是
    user_id/score/best_score/plays/wins/updated_at/user_name，新表是
    user_id/user_name/score/best_score/plays/wins/updated_at，按位置拷贝后
    user_name<-score、score<-best_score、best_score<-plays、plays<-wins、
    wins<-updated_at、updated_at<-user_name。这里按原映射反推；错位行的 wins
    一定是文本（DATETIME），正常行是整数，只改错位行，正常库 no-op。
    """
    await connection.execute(
        text(
            """
            UPDATE mg_profile SET
                user_name = CAST(updated_at AS TEXT),
                updated_at = CAST(wins AS TEXT),
                score = CAST(user_name AS INTEGER),
                best_score = score,
                plays = best_score,
                wins = plays
            WHERE typeof(wins) = 'text'
            """
        )
    )


def build_migrations() -> tuple[Migration, ...]:
    """本插件数据库的迁移列表（新增结构时追加 version）。"""
    return (
        Migration(version=1, name="initial-schema", upgrade=create_initial_schema),
        Migration(version=2, name="profile-user-name", upgrade=add_profile_user_name),
        Migration(
            version=3,
            name="widen-user-ids",
            upgrade=widen_user_ids,
            legacy_checksums=LEGACY_V3_CHECKSUMS,
        ),
        Migration(version=4, name="legacy-ids-to-openid", upgrade=rewrite_legacy_user_ids),
        Migration(
            version=5,
            name="repair-v3-profile-copy-order",
            upgrade=repair_v3_profile_copy_order,
        ),
    )


__all__ = [
    "DATABASE_FILENAME",
    "add_profile_user_name",
    "build_migrations",
    "create_initial_schema",
    "repair_v3_profile_copy_order",
    "rewrite_legacy_user_ids",
    "widen_user_ids",
]
