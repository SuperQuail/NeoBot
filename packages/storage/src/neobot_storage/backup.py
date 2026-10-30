"""SQLite 数据库备份。

用于在 alembic 迁移**之前**留一份可回滚的快照：迁移里存在不可逆操作
（例如 0021 的去重 DELETE），而原实现升级前不做任何备份。
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
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
        target = _create_backup(source, target_dir)
    except Exception as exc:
        log.warning(f"数据库备份失败（迁移将继续）: {exc}")
        return None

    _prune_backups(target_dir, source.stem, max_backups, log)
    return target


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S") + f"_{int(time.time() * 1000) % 1000:03d}"


def _create_backup(source: Path, target_dir: Path) -> Path:
    prefix = f".{source.stem}_{_timestamp()}_"
    for _ in range(100):
        descriptor, filename = tempfile.mkstemp(dir=target_dir, prefix=prefix, suffix=".db")
        staged = Path(filename)
        target = staged.with_name(staged.name[1:])
        try:
            os.close(descriptor)
            _copy_database(source, staged)
            try:
                _publish_backup(staged, target)
            except FileExistsError:
                continue
            return target
        finally:
            # 隐藏暂存不参与保留策略，失败或碰撞也不能留下空库/半成品。
            staged.unlink(missing_ok=True)
    raise FileExistsError("无法分配未占用的数据库备份路径")


def _publish_backup(staged: Path, target: Path) -> None:
    # 先独占预留目标，不能用 replace 直接覆盖仅凭随机后缀假定不存在的路径。
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    published = False
    try:
        os.close(descriptor)
        os.replace(staged, target)
        published = True
    finally:
        if not published:
            target.unlink(missing_ok=True)


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


def _prune_backups(backup_dir: Path, stem: str, max_backups: int, logger: Logger) -> None:
    if max_backups <= 0:
        return
    try:
        snapshots = []
        for item in backup_dir.glob(f"{stem}_*.db"):
            try:
                metadata = item.stat()
            except FileNotFoundError:
                # 另一备份调用可能已经清理掉同一旧快照，继续检查其余文件。
                continue
            # SQLite backup 即使源库为空也生成非空数据库。零字节只可能是
            # 发布前的独占占位，不能由其他调用的保留策略删除。
            if metadata.st_size == 0:
                continue
            snapshots.append((metadata.st_mtime_ns, item.name, item))
        backups = [item for _, _, item in sorted(snapshots)]
    except OSError as exc:
        logger.warning(f"清理旧数据库备份失败: {exc}")
        return
    if len(backups) <= max_backups:
        return
    for stale in backups[: len(backups) - max_backups]:
        try:
            stale.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            logger.warning(f"删除旧数据库备份失败 ({stale.name}): {exc}")
