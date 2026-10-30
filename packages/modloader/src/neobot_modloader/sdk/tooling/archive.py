"""将已校验的静态工程打成确定性 ZIP，不隐式执行 export。"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from neobot_modloader.installer import MAX_ARCHIVE_BYTES
from neobot_modloader.loading.manifest import read_manifest

from .files import project_files, safe_file
from .models import ToolingError, ToolReport
from .validation import check_project


def package_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_package(path: Path, output: Path) -> ToolReport:
    """固定条目顺序、时间戳和权限，产物验证后再原子替换目标文件。"""
    root = Path(path).resolve()
    destination = Path(output).absolute()
    temporary: Path | None = None
    checks: tuple[str, ...] = ()
    try:
        if destination.suffix.casefold() != ".zip" or destination.is_symlink() or destination.is_dir():
            raise ToolingError("output 必须是普通 ZIP 文件路径")
        report = check_project(root, output=destination)
        checks = report.checks
        if not report.ok:
            return ToolReport("build", False, checks, report.errors, str(destination))
        metadata = read_manifest(root / "plugin.toml")
        if not metadata:
            raise ToolingError("打包需要非空 plugin.toml，请先将旧单文件插件整理成目录工程")
        name = metadata.get("name") or root.name
        files = project_files(root, output=destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, filename = tempfile.mkstemp(prefix=".neobot-package-", suffix=".zip", dir=destination.parent)
        os.close(descriptor)
        temporary = Path(filename)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for path in files:
                relative = path.relative_to(root).as_posix()
                safe_file(root, relative, label=relative)
                before = path.stat()
                entry = zipfile.ZipInfo(f"{name}/{relative}", date_time=(1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.compress_level = 9
                with path.open("rb") as source, bundle.open(entry, "w") as target:
                    shutil.copyfileobj(source, target, length=64 * 1024)
                after = path.stat()
                if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
                    raise ToolingError(f"{relative}: 打包期间文件发生变化，请重试")
        if temporary.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ToolingError("ZIP 超过安装器允许的压缩体积")
        digest = package_digest(temporary)
        temporary.replace(destination)
        return ToolReport("build", True, (*checks, "archive"), path=str(destination), sha256=digest)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        return ToolReport("build", False, checks, (str(exc),), str(destination))
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
