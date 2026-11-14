"""a10→a11 全量回滚重建：快照选择、marker、抗失败与迁移时机。"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from neobot_app.database.identity_repair import auto_rebuild_if_a10_migration


def _db(path: Path, value: str, *, migration_table: bool = False) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("CREATE TABLE IF NOT EXISTS core_value (v TEXT);" + ("CREATE TABLE identity_migration_backup (old_key TEXT, new_key TEXT, payload TEXT);" if migration_table else ""))
    conn.execute("DELETE FROM core_value")
    conn.execute("INSERT INTO core_value VALUES (?)", (value,))
    conn.commit()
    conn.close()


def _fixture(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    backup = data / "db_backup"
    (data / "agent_tools" / "state").mkdir(parents=True)
    backup.mkdir(parents=True)
    current = data / "neobot.db"
    _db(current, "a10-after", migration_table=True)
    conn = sqlite3.connect(current)
    conn.executemany(
        "INSERT INTO identity_migration_backup (old_key, new_key, payload) VALUES (?, ?, ?)",
        [("1111111111", "BAD_OPENID", "{}"), ("2222222222", "BAD_OPENID", "{}")],
    )
    conn.commit()
    conn.close()
    old = backup / "neobot_old.db"
    _db(old, "pre-a10")
    now = time.time()
    os.utime(old, (now - 100, now - 100))
    agent = data / "agent_tools" / "state" / "agent_state.sqlite3"
    _db(agent, "agent-a11")
    old_agent = backup / "identity_agent_state_old.db"
    _db(old_agent, "agent-pre")
    new_agent = backup / "identity_agent_state_new.db"
    _db(new_agent, "agent-after")
    os.utime(old_agent, (now - 100, now - 100))
    os.utime(new_agent, (now - 50, now - 50))
    (data / "user_qq_map.json").write_text(json.dumps({"version": 3, "aliases": {"user:official:X": {"qq": 1, "trusted": True}}}), encoding="utf-8")
    return data


def _value(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("SELECT v FROM core_value").fetchone()[0]
    finally:
        conn.close()


def _tables(path: Path) -> set[str]:
    conn = sqlite3.connect(path)
    try:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_rebuild_restores_pre_a10_core_and_earliest_aux_and_clears_aliases(tmp_path: Path) -> None:
    data = _fixture(tmp_path)
    assert auto_rebuild_if_a10_migration(data, apply=True) is True
    assert _value(data / "neobot.db") == "pre-a10"
    assert "identity_migration_backup" not in _tables(data / "neobot.db")
    assert _value(data / "agent_tools" / "state" / "agent_state.sqlite3") == "agent-pre"
    assert json.loads((data / "user_qq_map.json").read_text(encoding="utf-8"))["aliases"] == {}
    assert (data / ".neobot" / "identity_rebuild_a11.done").is_file()
    assert list((data / "db_backup").glob("pre-rebuild_*/neobot.db"))


def test_rebuild_is_one_shot_unless_forced(tmp_path: Path) -> None:
    data = _fixture(tmp_path)
    assert auto_rebuild_if_a10_migration(data, apply=True) is True
    _db(data / "neobot.db", "a11-user-data", migration_table=True)
    assert auto_rebuild_if_a10_migration(data, apply=True) is False
    assert _value(data / "neobot.db") == "a11-user-data"
    assert auto_rebuild_if_a10_migration(data, apply=True, force=True) is True
    assert _value(data / "neobot.db") == "pre-a10"


def test_rebuild_dry_run_and_no_marker_when_not_a10(tmp_path: Path) -> None:
    data = _fixture(tmp_path)
    assert auto_rebuild_if_a10_migration(data, apply=False) is True
    assert _value(data / "neobot.db") == "a10-after"
    assert not (data / ".neobot" / "identity_rebuild_a11.done").exists()
    (data / "neobot.db").unlink()
    _db(data / "neobot.db", "healthy")
    assert auto_rebuild_if_a10_migration(data, apply=True) is False


def test_rebuild_failure_restores_current_core_and_aliases(tmp_path: Path, monkeypatch) -> None:
    import neobot_app.database.identity_repair as ir

    data = _fixture(tmp_path)
    original_aliases = (data / "user_qq_map.json").read_text(encoding="utf-8")
    real_backup = ir._backup

    def failing_backup(src: Path, dst: Path) -> None:
        if Path(dst).name == "neobot.db" and Path(src).name == "neobot_old.db":
            raise RuntimeError("simulated write failure")
        real_backup(src, dst)

    monkeypatch.setattr(ir, "_backup", failing_backup)
    assert ir.auto_rebuild_if_a10_migration(data, apply=True) is False
    assert _value(data / "neobot.db") == "a10-after"
    assert _value(data / "agent_tools" / "state" / "agent_state.sqlite3") == "agent-a11"
    assert json.loads((data / "user_qq_map.json").read_text(encoding="utf-8"))["aliases"] == json.loads(original_aliases)["aliases"]
    assert not (data / ".neobot" / "identity_rebuild_a11.done").exists()




def test_rebuild_skips_healthy_migration_table(tmp_path: Path) -> None:
    data = _fixture(tmp_path)
    current = data / "neobot.db"
    current.unlink()
    _db(current, "healthy", migration_table=True)
    conn = sqlite3.connect(current)
    conn.executemany(
        "INSERT INTO identity_migration_backup (old_key, new_key, payload) VALUES (?, ?, ?)",
        [("9000000000001", "OPENID", "{}"), ("3331347593", "OPENID", "{}")],
    )
    conn.commit()
    conn.close()
    assert auto_rebuild_if_a10_migration(data, apply=True) is False
    assert _value(current) == "healthy"
    assert not (data / ".neobot" / "identity_rebuild_a11.done").exists()


def test_rebuild_skips_empty_migration_table(tmp_path: Path) -> None:
    data = _fixture(tmp_path)
    current = data / "neobot.db"
    current.unlink()
    _db(current, "empty-table", migration_table=True)
    assert auto_rebuild_if_a10_migration(data, apply=True) is False
    assert _value(current) == "empty-table"


def test_rebuild_without_snapshot_quarantines_aliases(tmp_path: Path) -> None:
    data = _fixture(tmp_path)
    for snap in (data / "db_backup").glob("neobot_*.db"):
        snap.unlink()
    assert auto_rebuild_if_a10_migration(data, apply=True) is False
    assert json.loads((data / "user_qq_map.json").read_text(encoding="utf-8"))["aliases"] == {}
    assert (data / ".neobot" / "identity_rebuild_a11.done").is_file()
    assert list((data / "db_backup").glob("pre-rebuild_*/user_qq_map.a10.json"))
