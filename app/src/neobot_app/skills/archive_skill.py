"""ArchiveSkill — 文件压缩与解压 Skill。

纯 Python 标准库实现（zipfile + tarfile），无外部依赖。
"""

from __future__ import annotations

import json
import os
import tarfile
import zipfile
from pathlib import Path
from typing import Any


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class ArchiveSkill:
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

    @staticmethod
    def _tool_def(name: str, description: str, parameters: dict | None = None) -> dict:
        from neobot_app.skills.base import SkillModule
        return SkillModule._tool_def(name, description, parameters)

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
        mode_map = {
            ".tar": "w",
            ".tar.gz": "w:gz",
            ".tgz": "w:gz",
            ".tar.bz2": "w:bz2",
            ".tar.xz": "w:xz",
        }
        output_lower = output.name.lower() if output.suffix else output.name.lower()
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
        with tarfile.open(str(archive), mode) as tf:
            # 安全检查
            for m in tf.getmembers():
                member_path = (dest / m.name).resolve()
                if not str(member_path).startswith(str(dest.resolve())):
                    return _json({"ok": False, "error": f"安全拒绝：{m.name} 试图解压到目标目录之外"})
            tf.extractall(str(dest))
            count = sum(1 for m in tf.getmembers() if m.isfile())
            total_size = sum(m.size for m in tf.getmembers() if m.isfile())
        return _json({
            "ok": True,
            "format": archive.suffix.lstrip(".") if archive.suffix else archive_lower.rsplit(".", 1)[-1],
            "dest": str(dest.relative_to(self._resolve("."))),
            "file_count": count,
            "uncompressed_size": total_size,
        })
