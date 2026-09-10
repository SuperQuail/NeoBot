"""SQLite 数据库备份。

用于在 alembic 迁移**之前**留一份可回滚的快照：迁移里存在不可逆操作
（例如 0021 的去重 DELETE），而原实现升级前不做任何备份。
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from neobot_contracts.ports.logging import Logger, NullLogger

#: 默认保留的最近备份份数
DEFAULT_MAX_BACKUPS = 5


def backup_sqlite_database(
    db_path: str | Path,
    backup_dir: str | Path,
    *,
    max_backups: int = DEFAULT_MAX_BACKUPS,
    logger: Logger | None = None,
) -> Path | None:
    """用 SQLite 在线备份 API 复制数据库，返回备份文件路径。

    使用 ``sqlite3.Connection.backup`` 而不是直接拷文件：WAL 模式下已提交但
    尚未 checkpoint 的数据只存在于 ``-wal`` 文件里，裸拷贝主库文件会丢数据。

    库不存在（首次启动）返回 None；备份失败只记录告警并返回 None——
    迁移本身仍会继续，由迁移自己的错误处理决定后续行为。
    """
    log = logger or NullLogger()
    source = Path(db_path)
    if not source.is_file():
        return None

    target_dir = Path(backup_dir)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / f"{source.stem}_{_timestamp()}.db"
        _copy_database(source, target)
    except Exception as exc:
        log.warning(f"数据库备份失败（迁移将继续）: {exc}")
        return None

    _prune_backups(target_dir, source.stem, max_backups, log)
    return target


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"


def _copy_database(source: Path, target: Path) -> None:
    source_conn = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    try:
        target_conn = sqlite3.connect(target)
        try:
            source_conn.backup(target_conn)
        finally:
            target_conn.close()
    finally:
        source_conn.close()


def _prune_backups(
    backup_dir: Path, stem: str, max_backups: int, logger: Logger
) -> None:
    if max_backups <= 0:
        return
    try:
        backups = sorted(
            backup_dir.glob(f"{stem}_*.db"),
            key=lambda item: item.stat().st_mtime,
        )
    except OSError as exc:
        logger.warning(f"清理旧数据库备份失败: {exc}")
        return
    if len(backups) <= max_backups:
        return
    for stale in backups[: len(backups) - max_backups]:
        try:
            stale.unlink()
        except OSError as exc:
            logger.warning(f"删除旧数据库备份失败 ({stale.name}): {exc}")
