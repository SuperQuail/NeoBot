"""将 src/data/ 中的源文件同步到运行时 data/ 目录，基于 SHA256 哈希校验。"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from neobot_contracts.ports.logging import Logger, NullLogger


def _sha256(path: Path) -> str:
    """计算文件的 SHA256 哈希值。"""
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


def sync_data_files(
    src_dir: Path,
    dest_dir: Path,
    logger: Logger | None = None,
) -> None:
    """将 src_dir 中的文件同步到 dest_dir。

    - 目标文件不存在 → 复制
    - 目标文件存在但哈希不匹配 → 覆盖
    - 目标文件存在且哈希匹配 → 跳过
    """
    log = logger or NullLogger()
    if not src_dir.is_dir():
        log.warning(f"源数据目录不存在，跳过同步: {src_dir}")
        return

    dest_dir.mkdir(parents=True, exist_ok=True)

    for src_file in src_dir.rglob("*"):
        if not src_file.is_file():
            continue
        rel_path = src_file.relative_to(src_dir)
        dest_file = dest_dir / rel_path

        if not dest_file.exists():
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)
            log.info(f"数据文件已复制: {rel_path}")
        else:
            src_hash = _sha256(src_file)
            dest_hash = _sha256(dest_file)
            if src_hash != dest_hash:
                shutil.copy2(src_file, dest_file)
                log.info(f"数据文件已覆盖 (哈希不匹配): {rel_path}")
