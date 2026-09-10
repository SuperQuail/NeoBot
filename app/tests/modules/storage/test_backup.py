"""迁移前数据库备份测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from neobot_storage.backup import backup_sqlite_database


def _make_db(path: Path, *, wal: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    if wal:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, value TEXT)")
    conn.commit()
    return conn


def _read_values(path: Path) -> list[str]:
    conn = sqlite3.connect(path)
    try:
        return [row[0] for row in conn.execute("SELECT value FROM t ORDER BY id")]
    finally:
        conn.close()


def test_missing_database_returns_none(tmp_path: Path) -> None:
    assert backup_sqlite_database(tmp_path / "nope.db", tmp_path / "bk") is None


def test_backup_copies_data(tmp_path: Path) -> None:
    db = tmp_path / "neobot.db"
    conn = _make_db(db)
    conn.execute("INSERT INTO t (value) VALUES ('hello')")
    conn.commit()
    conn.close()

    target = backup_sqlite_database(db, tmp_path / "db_backup")

    assert target is not None and target.is_file()
    assert _read_values(target) == ["hello"]
    # 备份不应影响源库
    assert _read_values(db) == ["hello"]


def test_backup_includes_uncheckpointed_wal_data(tmp_path: Path) -> None:
    """WAL 中尚未 checkpoint 的已提交数据必须出现在备份里（裸拷主库会丢）。"""
    db = tmp_path / "neobot.db"
    conn = _make_db(db, wal=True)
    conn.execute("INSERT INTO t (value) VALUES ('in-wal')")
    conn.commit()
    # 刻意不 checkpoint、不关闭连接
    try:
        target = backup_sqlite_database(db, tmp_path / "db_backup")
        assert target is not None
        assert _read_values(target) == ["in-wal"]
    finally:
        conn.close()


def test_keeps_only_recent_backups(tmp_path: Path) -> None:
    db = tmp_path / "neobot.db"
    _make_db(db).close()
    backup_dir = tmp_path / "db_backup"

    for _ in range(4):
        backup_sqlite_database(db, backup_dir, max_backups=2)

    remaining = sorted(backup_dir.glob("neobot_*.db"))
    assert len(remaining) == 2


def test_backup_failure_does_not_raise(tmp_path: Path) -> None:
    """损坏的库文件不能让启动流程崩掉。"""
    db = tmp_path / "neobot.db"
    db.write_bytes(b"this is not a sqlite database at all" * 4)

    assert backup_sqlite_database(db, tmp_path / "db_backup") is None
