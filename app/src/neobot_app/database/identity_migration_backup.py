"""身份数据迁移前的 SQLite online backup 快照。

迁移会批量改写/合并历史 ID，link 触发的在线迁移没有进程启动快照可用；这里对
核心库、agent 状态库与 plugins_data 下各插件库各拍一份 WAL 安全的 sqlite 在线
备份（sqlite3.Connection.backup，见 neobot_storage.backup）：

- 文件名带 identity_ 前缀，和启动路径的 neobot_*.db 快照分开轮转，互不挤占；
- 同源库只保留最近 5 份，避免每次启动/每次 link 无限增长；
- 快照失败只记 WARNING，迁移继续（由迁移自身的错误处理决定后续）。
"""

from __future__ import annotations

import os
from pathlib import Path

from neobot_contracts.ports.logging import Logger
from neobot_storage import backup_sqlite_database

_AGENT_STATE_PATH = Path("agent_tools") / "state" / "agent_state.sqlite3"
_PLUGINS_DATA = "plugins_data"
_DB_BACKUP = "db_backup"
_SNAPSHOT_PREFIX = "identity_"
_SNAPSHOT_KEEP = 5


def agent_state_path(data_dir: Path) -> Path:
    return data_dir / _AGENT_STATE_PATH


def _aux_database_paths(data_dir: Path) -> list[Path]:
    """agent 状态库 + plugins_data/*/databases/*.db。"""
    paths = [path for path in (agent_state_path(data_dir),) if path.is_file()]
    paths.extend(sorted((data_dir / _PLUGINS_DATA).glob("*/databases/*.db")))
    return paths


def _prune_identity_snapshots(backup_dir: Path, stem: str, log: Logger) -> None:
    """identity_ 前缀的快照单独轮转，不与启动备份 neobot_*.db 互相挤占。"""
    try:
        snapshots = sorted(
            backup_dir.glob(f"{_SNAPSHOT_PREFIX}{stem}_*.db"),
            key=lambda item: item.stat().st_mtime_ns,
        )
    except OSError:
        return
    for stale in snapshots[:-_SNAPSHOT_KEEP]:
        try:
            stale.unlink()
        except OSError as exc:
            log.debug("清理身份迁移旧备份失败", path=str(stale), error=str(exc))


def _snapshot_database(source: Path, backup_dir: Path, log: Logger) -> Path | None:
    """用 SQLite online backup API 快照一个库；失败只 WARNING 不阻断迁移。"""
    if not source.is_file():
        return None
    try:
        staged = backup_sqlite_database(source, backup_dir, max_backups=0, logger=log)
        if staged is None:
            return None
        target = staged.with_name(f"{_SNAPSHOT_PREFIX}{staged.name}")
        os.replace(staged, target)
        _prune_identity_snapshots(backup_dir, source.stem, log)
        return target
    except Exception as exc:
        log.warning(
            "身份迁移前备份数据库失败（迁移将继续）", source=str(source), error=str(exc)
        )
        return None


def snapshot_migration_databases(
    db_path: Path, data_dir: Path, *, include_core: bool, log: Logger
) -> list[Path]:
    """迁移前快照：启动路径核心库已由 db_backup 覆盖，这里补 agent/插件库。

    include_core=True 供 link 后的在线迁移使用（它没有紧邻的启动快照）。
    """
    backup_dir = data_dir / _DB_BACKUP
    sources = _aux_database_paths(data_dir)
    if include_core:
        sources.insert(0, db_path)
    snapshots: list[Path] = []
    for source in sources:
        snapshot = _snapshot_database(source, backup_dir, log)
        if snapshot is not None:
            snapshots.append(snapshot)
    return snapshots
