"""迁移前数据库备份测试。"""

from __future__ import annotations

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

import pytest

from neobot_storage import backup as backup_module

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


def test_keeps_only_recent_backups(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backup_module, "_timestamp", lambda: "20261030_123456_789")
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


@pytest.fixture
def fixed_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backup_module, "_timestamp", lambda: "20261030_123456_789")


def _set_value(path: Path, value: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("DELETE FROM t")
        conn.execute("INSERT INTO t (value) VALUES (?)", (value,))
        conn.commit()
    finally:
        conn.close()


def test_same_timestamp_preserves_each_backup_snapshot(tmp_path: Path, fixed_timestamp) -> None:
    db = tmp_path / "neobot.db"
    _make_db(db).close()
    backup_dir = tmp_path / "db_backup"
    targets = []
    for index in range(4):
        _set_value(db, str(index))
        target = backup_sqlite_database(db, backup_dir, max_backups=0)
        assert target is not None
        targets.append(target)

    assert len(set(targets)) == 4
    assert [_read_values(target) for target in targets] == [[str(index)] for index in range(4)]
    assert set(backup_dir.iterdir()) == set(targets)


def test_concurrent_same_timestamp_backups_keep_distinct_snapshots(
    tmp_path: Path, fixed_timestamp, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = []
    for index in range(4):
        parent = tmp_path / str(index)
        parent.mkdir()
        db = parent / "neobot.db"
        _make_db(db).close()
        _set_value(db, str(index))
        sources.append(db)
    barrier = Barrier(len(sources), timeout=10)
    copy_database = backup_module._copy_database

    def synchronized_copy(source: Path, target: Path) -> None:
        barrier.wait()
        copy_database(source, target)

    monkeypatch.setattr(backup_module, "_copy_database", synchronized_copy)
    backup_dir = tmp_path / "db_backup"
    with ThreadPoolExecutor(max_workers=len(sources)) as executor:
        futures = [executor.submit(backup_sqlite_database, source, backup_dir, max_backups=0) for source in sources]
        targets = [future.result(timeout=15) for future in futures]

    assert all(target is not None for target in targets)
    assert len(set(targets)) == len(sources)
    assert [_read_values(target) for target in targets] == [[str(index)] for index in range(4)]
    assert set(backup_dir.iterdir()) == set(targets)


def test_pruning_cannot_remove_a_backup_still_being_copied(
    tmp_path: Path, fixed_timestamp, monkeypatch: pytest.MonkeyPatch
) -> None:
    slow_dir = tmp_path / "slow"
    fast_dir = tmp_path / "fast"
    slow_dir.mkdir()
    fast_dir.mkdir()
    slow_db, fast_db = slow_dir / "neobot.db", fast_dir / "neobot.db"
    for db, value in ((slow_db, "slow"), (fast_db, "fast")):
        _make_db(db).close()
        _set_value(db, value)
    copied, release = Event(), Event()
    pending = []
    copy_database = backup_module._copy_database

    def copy_then_pause(source: Path, target: Path) -> None:
        copy_database(source, target)
        if source == slow_db:
            pending.append(target)
            copied.set()
            assert release.wait(10), "in-flight backup was never released"

    monkeypatch.setattr(backup_module, "_copy_database", copy_then_pause)
    backup_dir = tmp_path / "db_backup"
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(backup_sqlite_database, slow_db, backup_dir, max_backups=0)
        try:
            assert copied.wait(10), "in-flight backup never reached the copy barrier"
            fast = backup_sqlite_database(fast_db, backup_dir, max_backups=1)
            assert fast is not None
            assert pending[0].is_file()
            assert pending[0] not in backup_dir.glob("neobot_*.db")
            assert list(backup_dir.glob("neobot_*.db")) == [fast]
            assert _read_values(fast) == ["fast"]
        finally:
            release.set()
        slow = future.result(timeout=10)

    assert slow is not None and slow != fast
    assert _read_values(slow) == ["slow"]
    assert _read_values(fast) == ["fast"]
    assert not pending[0].exists()
    assert set(backup_dir.iterdir()) == {slow, fast}


def test_failed_partial_copy_leaves_existing_backup_untouched(
    tmp_path: Path, fixed_timestamp, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "neobot.db"
    _make_db(db).close()
    _set_value(db, "preserved")
    backup_dir = tmp_path / "db_backup"
    existing = backup_sqlite_database(db, backup_dir, max_backups=0)
    assert existing is not None

    def partial_copy(source: Path, target: Path) -> None:
        target.write_bytes(b"unfinished backup")
        raise OSError("injected copy failure")

    monkeypatch.setattr(backup_module, "_copy_database", partial_copy)
    assert backup_sqlite_database(db, backup_dir, max_backups=1) is None
    assert _read_values(existing) == ["preserved"]
    assert set(backup_dir.iterdir()) == {existing}


def test_publish_collision_preserves_existing_file_and_retries(
    tmp_path: Path, fixed_timestamp, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "neobot.db"
    _make_db(db).close()
    _set_value(db, "new")
    previous = tmp_path / "previous.db"
    _make_db(previous).close()
    _set_value(previous, "previous")
    original_publish = backup_module._publish_backup
    collisions = []

    def collide_once(source: Path, target: Path) -> None:
        if not collisions:
            target = Path(target)
            target.write_bytes(previous.read_bytes())
            collisions.append(target)
        original_publish(source, target)

    monkeypatch.setattr(backup_module, "_publish_backup", collide_once)
    backup_dir = tmp_path / "db_backup"
    target = backup_sqlite_database(db, backup_dir, max_backups=0)
    assert target is not None
    assert len(collisions) == 1 and target != collisions[0]
    assert _read_values(target) == ["new"]
    assert _read_values(collisions[0]) == ["previous"]
    assert set(backup_dir.iterdir()) == {target, collisions[0]}


def test_pruning_equal_mtimes_uses_stable_filename_order(tmp_path: Path, fixed_timestamp) -> None:
    db = tmp_path / "neobot.db"
    _make_db(db).close()
    backup_dir = tmp_path / "db_backup"
    backup_dir.mkdir()
    # 故意按非字典顺序创建，不能靠文件系统枚举顺序打破时间戳平局。
    for suffix in ("c", "a", "b"):
        path = backup_dir / f"neobot_{suffix}.db"
        path.write_bytes(db.read_bytes())
        os.utime(path, ns=(1_000_000_000, 1_000_000_000))

    target = backup_sqlite_database(db, backup_dir, max_backups=2)
    assert target is not None
    assert set(backup_dir.iterdir()) == {backup_dir / "neobot_c.db", target}


def test_pruning_skips_a_file_removed_by_another_cleanup(
    tmp_path: Path, fixed_timestamp, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "neobot.db"
    _make_db(db).close()
    backup_dir = tmp_path / "db_backup"
    backup_dir.mkdir()
    for index in range(3):
        path = backup_dir / f"neobot_{index}.db"
        path.write_bytes(db.read_bytes())
        os.utime(path, ns=((index + 1) * 1_000_000_000, (index + 1) * 1_000_000_000))
    missing = backup_dir / "neobot_0.db"
    original_stat = Path.stat
    removed = []

    def disappear_during_stat(path: Path, *args, **kwargs):
        if path == missing and not removed:
            path.unlink()
            removed.append(path)
            raise FileNotFoundError(str(path))
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", disappear_during_stat)
    target = backup_sqlite_database(db, backup_dir, max_backups=2)
    assert target is not None
    assert removed == [missing]
    assert set(backup_dir.iterdir()) == {backup_dir / "neobot_2.db", target}


def test_publish_failure_removes_staging_and_preserves_existing_backup(
    tmp_path: Path, fixed_timestamp, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "neobot.db"
    _make_db(db).close()
    _set_value(db, "preserved")
    backup_dir = tmp_path / "db_backup"
    existing = backup_sqlite_database(db, backup_dir, max_backups=0)
    assert existing is not None

    placeholders = []

    def failed_replace(source, target):
        target = Path(target)
        assert target.is_file() and target.stat().st_size == 0
        placeholders.append(target)
        raise OSError("injected publication failure")

    monkeypatch.setattr(os, "replace", failed_replace)
    assert backup_sqlite_database(db, backup_dir, max_backups=1) is None
    assert len(placeholders) == 1
    assert _read_values(existing) == ["preserved"]
    assert set(backup_dir.iterdir()) == {existing}


def test_backup_succeeds_when_filesystem_hard_links_are_unavailable(
    tmp_path: Path, fixed_timestamp, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "neobot.db"
    _make_db(db).close()
    _set_value(db, "portable")
    link_attempts = []

    def unsupported_link(*args, **kwargs):
        link_attempts.append(args)
        raise OSError("hard links are unsupported on this filesystem")

    monkeypatch.setattr(os, "link", unsupported_link)
    backup_dir = tmp_path / "db_backup"
    target = backup_sqlite_database(db, backup_dir)
    assert target is not None
    assert _read_values(target) == ["portable"]
    assert set(backup_dir.iterdir()) == {target}
    assert not link_attempts


def test_pruning_preserves_reserved_destination_until_atomic_publication(
    tmp_path: Path, fixed_timestamp, monkeypatch: pytest.MonkeyPatch
) -> None:
    slow_dir, fast_dir = tmp_path / "slow", tmp_path / "fast"
    slow_dir.mkdir()
    fast_dir.mkdir()
    slow_db, fast_db = slow_dir / "neobot.db", fast_dir / "neobot.db"
    for db, value in ((slow_db, "slow"), (fast_db, "fast")):
        _make_db(db).close()
        _set_value(db, value)
    reserved, release = Event(), Event()
    destinations = []
    original_replace = os.replace

    def replace_after_release(source, target):
        if _read_values(Path(source)) == ["slow"]:
            target = Path(target)
            assert target.is_file() and target.stat().st_size == 0
            destinations.append(target)
            reserved.set()
            assert release.wait(10), "reserved backup destination was never released"
        return original_replace(source, target)

    monkeypatch.setattr(os, "replace", replace_after_release)
    backup_dir = tmp_path / "db_backup"
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(backup_sqlite_database, slow_db, backup_dir, max_backups=0)
        try:
            assert reserved.wait(10), "backup never reserved its destination"
            placeholder = destinations[0]
            fast = backup_sqlite_database(fast_db, backup_dir, max_backups=1)
            assert fast is not None
            assert placeholder.is_file() and placeholder.stat().st_size == 0
            assert set(backup_dir.glob("neobot_*.db")) == {placeholder, fast}
            assert _read_values(fast) == ["fast"]
        finally:
            release.set()
        slow = future.result(timeout=10)

    assert slow == placeholder and slow != fast
    assert _read_values(slow) == ["slow"]
    assert _read_values(fast) == ["fast"]
    assert set(backup_dir.iterdir()) == {slow, fast}


def test_empty_sqlite_database_publishes_nonempty_snapshots_and_is_pruned(tmp_path: Path, fixed_timestamp) -> None:
    db = tmp_path / "neobot.db"
    sqlite3.connect(db).close()
    assert db.stat().st_size == 0
    backup_dir = tmp_path / "db_backup"
    targets = []
    for _ in range(4):
        target = backup_sqlite_database(db, backup_dir, max_backups=2)
        assert target is not None and target.stat().st_size > 0
        with sqlite3.connect(target) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert connection.execute("SELECT count(*) FROM sqlite_master").fetchone() == (0,)
        targets.append(target)

    assert len(set(targets)) == 4
    assert len(list(backup_dir.glob("neobot_*.db"))) == 2
    assert len(list(backup_dir.iterdir())) == 2
