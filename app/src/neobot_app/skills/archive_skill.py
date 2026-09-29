"""ArchiveSkill — 文件压缩与解压 Skill。

纯 Python 标准库实现（zipfile + tarfile），无外部依赖。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


#: 形如 "C:" 的 Windows 盘符前缀；成员名/链接目标出现即为绝对路径。
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")

#: extractall(..., filter=) 的支持情况按运行时签名探测：
#: tarfile 从 3.12 起有 filter=（本仓要求 3.13），zipfile 到 CPython 3.13 仍无
#: （实测 TypeError: ZipFile.extractall() got an unexpected keyword argument 'filter'）。
_ZIP_EXTRACT_FILTER_SUPPORTED = (
    "filter" in inspect.signature(zipfile.ZipFile.extractall).parameters
)


def _is_absolute_member(name: str) -> bool:
    """成员名/链接目标是否写成绝对路径（POSIX 根、Windows 盘符或 UNC）。"""
    return name.startswith(("/", "\\")) or bool(_DRIVE_PREFIX.match(name))


def _unsafe_member_reason(dest_root: Path, name: str, linkname: str = "") -> str | None:
    """按路径语义校验归档成员（及链接目标）是否落在 dest 内。

    返回拒绝原因，None 表示安全。注意：
    - dest_root 必须是 resolve() 之后的目录；
    - 边界判定用 Path.is_relative_to，不能用字符串 startswith —— 后者会被
      「兄弟目录名以 dest 名为前缀」的成员绕过（dest=uploads 时 ../uploads_evil/a.txt）；
    - resolve() 会跟随 dest 内既有的符号链接，因此穿过既有链接的成员同样被拒。
    """
    raw = str(name or "")
    if not raw.strip():
        return "成员名为空"
    if _is_absolute_member(raw):
        return "绝对路径"
    parts = PurePosixPath(raw.replace("\\", "/")).parts
    if ".." in parts:
        return "包含 .. 的路径"
    target = dest_root.joinpath(*parts)
    try:
        resolved = target.resolve()
    except OSError:
        return "路径无法解析"
    if not resolved.is_relative_to(dest_root):
        return "路径解析后逃出目标目录"

    link = str(linkname or "")
    if not link.strip():
        return None
    if _is_absolute_member(link):
        return "链接目标为绝对路径"
    link_parts = PurePosixPath(link.replace("\\", "/")).parts
    if ".." in link_parts:
        return "链接目标包含 .."
    try:
        link_resolved = target.parent.joinpath(*link_parts).resolve()
    except OSError:
        return "链接目标无法解析"
    if not link_resolved.is_relative_to(dest_root):
        return "链接目标逃出目标目录"
    return None


def _is_zip_symlink(member: zipfile.ZipInfo) -> bool:
    """zip 成员是否声明为符号链接（外部属性高 16 位是 Unix mode）。"""
    return stat.S_ISLNK((member.external_attr >> 16) & 0xFFFF)


class ArchiveSkill(SkillModule):
    """文件压缩/解压 Skill。"""

    def __init__(self, sandbox_service: Any = None) -> None:
        self._sandbox = sandbox_service

    @property
    def name(self) -> str:
        return "archive"

    @property
    def description(self) -> str:
        return "文件压缩与解压：支持 zip / tar / tar.gz / tar.bz2 / tar.xz 格式"

    @property
    def instructions(self) -> str:
        return (
            "文件压缩与解压 Skill，支持常见归档格式。\n\n"
            "## 压缩\n"
            "  将多个文件或目录打包压缩。paths 为待压缩的路径列表（相对于沙箱根目录），"
            "output 为输出归档文件名（如 backup.zip / data.tar.gz）。\n"
            "  格式由 output 后缀自动判断：.zip / .tar / .tar.gz / .tgz / .tar.bz2 / .tar.xz。\n\n"
            "## 解压\n"
            "  解压归档文件。archive 为归档文件路径，dest 为目标目录（可选，默认解压到归档所在目录）。\n"
            "  格式同样由后缀自动判断。\n\n"
            "## 工具列表\n"
            "  archive_compress — 压缩文件/目录\n"
            "  archive_decompress — 解压归档文件"
        )

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "archive_compress",
                "将多个文件或目录压缩打包。paths 为待压缩路径列表，output 为输出文件名。"
                "格式由 output 后缀决定：.zip / .tar / .tar.gz(.tgz) / .tar.bz2 / .tar.xz。",
                {
                    "properties": {
                        "paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "待压缩的文件/目录路径列表（相对于沙箱根目录）",
                        },
                        "output": {
                            "type": "string",
                            "description": "输出归档文件名，如 backup.zip 或 data.tar.gz。后缀决定压缩格式。",
                        },
                    },
                    "required": ["paths", "output"],
                },
            ),
            self._tool_def(
                "archive_decompress",
                "解压归档文件。archive 为归档路径，dest 为目标目录（可选，默认解压到归档所在目录）。"
                "支持 .zip / .tar / .tar.gz(.tgz) / .tar.bz2 / .tar.xz。",
                {
                    "properties": {
                        "archive": {
                            "type": "string",
                            "description": "归档文件路径（相对于沙箱根目录）",
                        },
                        "dest": {
                            "type": "string",
                            "description": "解压目标目录（可选，默认解压到归档所在目录）",
                        },
                    },
                    "required": ["archive"],
                },
            ),
        ]

    def _resolve(self, path: str) -> Path:
        if self._sandbox is not None:
            return self._sandbox.resolve_path(path)
        return Path(path)

    # ── execute ──

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        try:
            if tool_name == "archive_compress":
                return await self._compress(args)
            if tool_name == "archive_decompress":
                return await self._decompress(args)
            return _json({"ok": False, "error": f"unknown archive tool: {tool_name}"})
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

    # ── 压缩 ──

    async def _compress(self, args: dict[str, Any]) -> str:
        paths = args.get("paths", [])
        output = str(args.get("output", ""))
        if not paths:
            return _json({"ok": False, "error": "paths 不能为空"})
        if not output:
            return _json({"ok": False, "error": "output 不能为空"})

        output_path = self._resolve(output)
        output_lower = output.lower()

        source_paths = [self._resolve(str(p)) for p in paths]

        # 检查所有源路径是否存在
        missing = [str(p) for p in source_paths if not p.exists()]
        if missing:
            return _json({"ok": False, "error": f"路径不存在: {missing}"})

        if output_lower.endswith(".zip"):
            return await self._compress_zip(source_paths, output_path)
        elif output_lower.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
            return await self._compress_tar(source_paths, output_path)
        else:
            return _json({
                "ok": False,
                "error": f"不支持的压缩格式: {output}，支持 .zip / .tar / .tar.gz / .tar.bz2 / .tar.xz",
            })

    async def _compress_zip(self, sources: list[Path], output: Path) -> str:
        # 压缩是 CPU+磁盘密集工作：放进工作线程，避免卡住事件循环
        return await asyncio.to_thread(self._compress_zip_sync, sources, output)

    def _compress_zip_sync(self, sources: list[Path], output: Path) -> str:
        count = 0
        total_size = 0
        with zipfile.ZipFile(str(output), "w", zipfile.ZIP_DEFLATED) as zf:
            for src in sources:
                if src.is_file():
                    zf.write(str(src), src.name)
                    count += 1
                    total_size += src.stat().st_size
                elif src.is_dir():
                    for root, _, files in os.walk(str(src)):
                        for f in files:
                            fp = Path(root) / f
                            arcname = str(fp.relative_to(src.parent))
                            zf.write(str(fp), arcname)
                            count += 1
                            total_size += fp.stat().st_size
        output_size = output.stat().st_size
        return _json({
            "ok": True,
            "format": "zip",
            "output": str(output.relative_to(self._resolve("."))),
            "file_count": count,
            "uncompressed_size": total_size,
            "compressed_size": output_size,
            "ratio": f"{output_size / total_size * 100:.1f}%" if total_size > 0 else "0%",
        })

    async def _compress_tar(self, sources: list[Path], output: Path) -> str:
        return await asyncio.to_thread(self._compress_tar_sync, sources, output)

    def _compress_tar_sync(self, sources: list[Path], output: Path) -> str:
        mode_map = {
            ".tar": "w",
            ".tar.gz": "w:gz",
            ".tgz": "w:gz",
            ".tar.bz2": "w:bz2",
            ".tar.xz": "w:xz",
        }
        # 处理双重后缀如 .tar.gz
        output_str = str(output).lower()
        mode = "w:gz"
        for ext, m in mode_map.items():
            if output_str.endswith(ext):
                mode = m
                break

        count = 0
        total_size = 0
        with tarfile.open(str(output), mode) as tf:
            for src in sources:
                arcname = src.name
                tf.add(str(src), arcname=arcname)
                if src.is_file():
                    count += 1
                    total_size += src.stat().st_size
                elif src.is_dir():
                    for root, _, files in os.walk(str(src)):
                        for f in files:
                            fp = Path(root) / f
                            count += 1
                            total_size += fp.stat().st_size

        output_size = output.stat().st_size
        fmt = output_str.rsplit(".", 1)[-1] if "." in output_str else output_str
        return _json({
            "ok": True,
            "format": output.suffix.lstrip(".") if output.suffix else fmt,
            "output": str(output.relative_to(self._resolve("."))),
            "file_count": count,
            "uncompressed_size": total_size,
            "compressed_size": output_size,
            "ratio": f"{output_size / total_size * 100:.1f}%" if total_size > 0 else "0%",
        })

    # ── 解压 ──

    async def _decompress(self, args: dict[str, Any]) -> str:
        archive = str(args.get("archive", ""))
        if not archive:
            return _json({"ok": False, "error": "archive 不能为空"})

        archive_path = self._resolve(archive)
        if not archive_path.exists():
            return _json({"ok": False, "error": f"归档文件不存在: {archive}"})

        dest_arg = args.get("dest")
        if dest_arg:
            dest = self._resolve(str(dest_arg))
        else:
            dest = archive_path.parent
        dest.mkdir(parents=True, exist_ok=True)

        archive_lower = str(archive).lower()

        if archive_lower.endswith(".zip"):
            return await self._decompress_zip(archive_path, dest)
        elif archive_lower.endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
            return await self._decompress_tar(archive_path, dest)
        else:
            return _json({
                "ok": False,
                "error": f"不支持的归档格式: {archive}，支持 .zip / .tar / .tar.gz / .tar.bz2 / .tar.xz",
            })

    async def _decompress_zip(self, archive: Path, dest: Path) -> str:
        return await asyncio.to_thread(self._decompress_zip_sync, archive, dest)

    def _decompress_zip_sync(self, archive: Path, dest: Path) -> str:
        count = 0
        total_size = 0
        with zipfile.ZipFile(str(archive), "r") as zf:
            members = zf.infolist()
            # 安全检查：防止 Zip Slip 攻击
            for m in members:
                member_path = (dest / m.filename).resolve()
                if not str(member_path).startswith(str(dest.resolve())):
                    return _json({"ok": False, "error": f"安全拒绝：{m.filename} 试图解压到目标目录之外"})
            zf.extractall(str(dest))
            count = len(members)
            total_size = sum(m.file_size for m in members)
        return _json({
            "ok": True,
            "format": "zip",
            "dest": str(dest.relative_to(self._resolve("."))),
            "file_count": count,
            "uncompressed_size": total_size,
        })

    async def _decompress_tar(self, archive: Path, dest: Path) -> str:
        return await asyncio.to_thread(self._decompress_tar_sync, archive, dest)

    def _decompress_tar_sync(self, archive: Path, dest: Path) -> str:
        mode_map = {
            ".tar": "r",
            ".tar.gz": "r:gz",
            ".tgz": "r:gz",
            ".tar.bz2": "r:bz2",
            ".tar.xz": "r:xz",
        }
        archive_lower = str(archive).lower()
        mode = "r:gz"
        for ext, m in mode_map.items():
            if archive_lower.endswith(ext):
                mode = m
                break

        count = 0
        total_size = 0
        dest_root = dest.resolve()
        with tarfile.open(str(archive), mode) as tf:
            members = tf.getmembers()
            # 安全检查必须在解压前完成：extractall 会先建符号链接、再穿链接写文件，
            # 事后检查落盘路径已经晚了。链接/设备成员一律拒绝（不看 linkname 是否"看起来"安全，
            # 硬链接还能指向 dest 外已存在的文件）。
            for m in members:
                if (
                    m.issym()
                    or m.islnk()
                    or m.ischr()
                    or m.isblk()
                    or m.isfifo()
                    or m.isdev()
                ):
                    return _json({
                        "ok": False,
                        "error": f"安全拒绝：{m.name} 是不允许的链接/设备成员",
                    })
                reason = _unsafe_member_reason(dest_root, m.name, m.linkname)
                if reason is not None:
                    return _json({"ok": False, "error": f"安全拒绝：{m.name} {reason}"})
            # filter="data" 是第二层兜底：即使上面的白名单漏了某种成员，tarfile 也会
            # 拒绝绝对路径/越界链接并清掉 setuid 等高危位。
            tf.extractall(str(dest), filter="data")
            count = sum(1 for m in members if m.isfile())
            total_size = sum(m.size for m in members if m.isfile())
        return _json({
            "ok": True,
            "format": archive.suffix.lstrip(".") if archive.suffix else archive_lower.rsplit(".", 1)[-1],
            "dest": str(dest.relative_to(self._resolve("."))),
            "file_count": count,
            "uncompressed_size": total_size,
        })
