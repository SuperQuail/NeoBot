"""SandboxMaintenanceManager — 沙箱持久化文件维护（工具类，由 AI 或 CLI 按需调用）。"""

from __future__ import annotations

import asyncio
import re
import shutil
import time
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

_PERSISTENT_DIRS = ["tools", "docs", "assets"]
_STORAGE_DOC = "文件存储.md"
_TODO_DOC = "TODO.md"
_MAINTENANCE_MARKER = ".last_maintenance"

#: 原子写的临时文件前缀（sandbox_service.atomic_write / 复制时的 mkstemp）。
#: 正常路径在 finally 里清理，进程被强杀时才会留在原地。
_WRITE_TEMP_PREFIX = ".neobot-write-"
#: 超过这个年龄的临时文件才算孤儿：正在进行的写入只有毫秒级寿命。
_ORPHAN_TEMP_MAX_AGE_SECONDS = 3600


class SandboxMaintenanceManager:
    """沙箱持久化文件维护管理器。

    不自动运行，由 AI agent 通过 trigger_maintenance 工具调用，
    或通过 CLI sandbox_CP 命令执行。
    """

    def __init__(
        self,
        sandbox_root: str | Path,
        *,
        enabled: bool = True,
        sandbox_service: Any = None,
        logger: Logger | None = None,
    ) -> None:
        self._root = Path(sandbox_root).resolve()
        self._enabled = enabled
        self._sandbox = sandbox_service
        self._logger = logger or NullLogger()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def root(self) -> Path:
        return self._root

    async def run_once(self, *, force: bool = False) -> dict[str, Any]:
        """手动触发一次维护，返回结果摘要。force=True 时跳过变更检查强制执行。"""
        return await self._maintenance_cycle(force=force)

    async def _maintenance_cycle(self, *, force: bool = False) -> dict[str, Any]:
        """执行一次完整的维护周期。force=True 时跳过变更检查强制执行。

        整个周期都是同步文件系统操作（整树 rglob、rmtree、move），必须放进工作
        线程：它由后台协程每 3 小时自动触发一次，直接跑在事件循环上会让整个 Bot
        （所有会话、通知、心跳）停顿数秒。
        """
        return await asyncio.to_thread(self._maintenance_cycle_sync, force=force)

    def _maintenance_cycle_sync(self, *, force: bool = False) -> dict[str, Any]:
        if not force and not self._has_changes_since_last():
            self._logger.debug("无文件变更，跳过维护")
            return {"ok": True, "skipped": True, "reason": "无文件变更"}

        result: dict[str, Any] = {
            "ok": True,
            "skipped": False,
            "renamed": [],
            "removed": [],
            "moved": [],
            "doc_updated": False,
            "junk_cleaned": False,
            "capacity": self._get_capacity_info(),
        }

        # 确保目录存在
        for d in _PERSISTENT_DIRS:
            (self._root / d).mkdir(parents=True, exist_ok=True)

        # 0. 清理根目录和 tmp/ 中的不当文件
        self._clean_misplaced_files(result)

        # 1. 清理垃圾文件
        self._clean_junk_files(result)
        result["junk_cleaned"] = True

        # 2. 扫描并整理文件
        self._organize_files(result)

        # 3. 更新 文件存储.md
        self._update_storage_doc(result)

        # 4. 刷新容量信息（清理后）
        result["capacity"] = self._get_capacity_info()

        # 5. 更新维护标记
        self._touch_maintenance_marker()

        return result

    def _has_changes_since_last(self) -> bool:
        """检查自上次维护以来是否有非 temp 文件变更。"""
        marker = self._root / _MAINTENANCE_MARKER
        if not marker.exists():
            return True  # 首次运行

        last_mtime = marker.stat().st_mtime
        for d in _PERSISTENT_DIRS:
            dir_path = self._root / d
            if not dir_path.is_dir():
                continue
            for entry in dir_path.rglob("*"):
                if entry.is_file() and entry.stat().st_mtime > last_mtime:
                    return True

        # 也检查 文件存储.md 和 TODO.md
        for doc_name in [_STORAGE_DOC, _TODO_DOC]:
            doc_path = self._root / doc_name
            if doc_path.is_file() and doc_path.stat().st_mtime > last_mtime:
                return True

        return False

    # ── 已知的按 chat_flow_id 命名的目录前缀 ──
    _CHAT_FLOW_PREFIXES = ("Group_", "Private_", "Friend_", "Channel_")

    # 已知的持久化目录名（不会被误清理）
    _KNOWN_DIRS = frozenset(
        _PERSISTENT_DIRS + ["temp", "tmp", "gift", "__pycache__"]
    )
    # 根目录保留文件（不被移动到 docs/）
    _KEPT_FILES = frozenset({".last_maintenance", "文件存储.md", "TODO.md"})

    def _is_chat_flow_dir(self, name: str) -> bool:
        return name.startswith(self._CHAT_FLOW_PREFIXES)

    def _clean_misplaced_files(self, result: dict) -> None:
        """清理根目录和 tmp/ 中不当放置的文件和目录。

        - 根目录下的 chat_flow 目录 → 移到 temp/
        - 根目录下的孤立文件 → 移到 docs/ 或删除
        - tmp/ 下的内容 → 移到 temp/，删除 tmp/
        """
        # 根目录清理
        for entry in sorted(self._root.iterdir()):
            name = entry.name
            if name in self._KNOWN_DIRS or name.startswith("."):
                continue

            if entry.is_dir():
                if self._is_chat_flow_dir(name):
                    target = self._root / "temp" / name
                    try:
                        if not target.exists():
                            shutil.move(str(entry), str(target))
                        else:
                            self._merge_dir(entry, target)
                            shutil.rmtree(str(entry))
                        result["moved"].append(f"{name} -> temp/{name}")
                        self._logger.debug(f"移动 chat_flow 目录: {name} -> temp/")
                    except OSError as e:
                        self._logger.warning(f"移动目录失败 {name}: {e}")
                else:
                    target = self._root / "docs" / name
                    try:
                        if not target.exists():
                            shutil.move(str(entry), str(target))
                            result["moved"].append(f"{name} -> docs/{name}")
                            self._logger.debug(f"移动未知目录: {name} -> docs/")
                    except OSError as e:
                        self._logger.warning(f"移动目录失败 {name}: {e}")
            elif entry.is_file():
                if name in self._KEPT_FILES:
                    continue
                target = self._root / "docs" / name
                try:
                    shutil.move(str(entry), str(target))
                    result["moved"].append(f"{name} -> docs/{name}")
                    self._logger.debug(f"移动根目录文件: {name} -> docs/")
                except OSError as e:
                    self._logger.warning(f"移动文件失败 {name}: {e}")

        # 清理残留的 tmp/ 目录（旧版本遗留，已无代码使用）
        tmp_dir = self._root / "tmp"
        if tmp_dir.is_dir():
            temp_base = self._root / "temp"
            temp_base.mkdir(parents=True, exist_ok=True)
            for entry in sorted(tmp_dir.iterdir()):
                target = temp_base / entry.name
                try:
                    if not target.exists():
                        shutil.move(str(entry), str(target))
                    else:
                        if entry.is_dir():
                            self._merge_dir(entry, target)
                        shutil.rmtree(str(entry))
                    result["moved"].append(f"tmp/{entry.name} -> temp/{entry.name}")
                except OSError as e:
                    self._logger.warning(f"tmp/ 迁移失败 {entry.name}: {e}")
            try:
                shutil.rmtree(str(tmp_dir))
                result["removed"].append("tmp/ (已废弃)")
                self._logger.info("已清理废弃的 tmp/ 目录")
            except OSError as e:
                self._logger.warning(f"删除 tmp/ 失败: {e}")

    @staticmethod
    def _merge_dir(src: Path, dst: Path) -> None:
        """将 src 目录中的文件合并到 dst 目录。"""
        dst.mkdir(parents=True, exist_ok=True)
        for item in src.rglob("*"):
            if item.is_file():
                rel = item.relative_to(src)
                target = dst / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    try:
                        shutil.move(str(item), str(target))
                    except OSError:
                        pass

    def _organize_files(self, result: dict) -> None:
        """整理持久化目录中的文件。"""
        for d in _PERSISTENT_DIRS:
            dir_path = self._root / d
            if not dir_path.is_dir():
                continue
            for entry in sorted(dir_path.iterdir()):
                if entry.is_file():
                    self._check_file_naming(entry, d, result)
                    self._check_redundant_file(entry, d, result)

    def _check_file_naming(
        self, file_path: Path, section: str, result: dict
    ) -> None:
        """仅规范化纯 ASCII 文件名；中文等 Unicode 文件名完整保留。"""
        name = file_path.name
        if (
            not name.isascii()
            or name.startswith(".")
            or name == "prepared"
            or file_path.is_symlink()
        ):
            return
        stem = file_path.stem
        if re.fullmatch(r"[a-z][a-z0-9_\-]*", stem):
            return
        new_stem = _to_snake_case(stem)
        # 转换不得生成空主名、隐藏文件或路径；即使转换函数变更也保持保护。
        if (
            not new_stem
            or new_stem == stem
            or not re.fullmatch(r"[a-z0-9][a-z0-9_\-]*", new_stem)
        ):
            return
        new_name = new_stem + file_path.suffix
        new_path = file_path.parent / new_name
        # 断开的符号链接也占用目标名称，不能仅用 exists() 判断。
        if new_path.exists() or new_path.is_symlink():
            return
        try:
            file_path.rename(new_path)
            result["renamed"].append(f"{section}/{name} -> {new_name}")
            self._logger.debug(f"重命名: {name} -> {new_name}")
        except OSError as exc:
            self._logger.warning(f"重命名失败，保留原文件 {section}/{name}: {exc}")

    def _check_redundant_file(
        self, file_path: Path, section: str, result: dict
    ) -> None:
        """检查并删除明显冗余的文件。"""
        name = file_path.name
        if name.endswith((".tmp", ".bak", ".swp", "~")) or name.startswith("~"):
            try:
                file_path.unlink()
                result["removed"].append(f"{section}/{name}")
                self._logger.debug(f"删除冗余文件: {section}/{name}")
            except OSError:
                pass

    def _clean_junk_files(self, result: dict) -> None:
        """扫描整个沙箱，删除垃圾文件（缓存、临时文件、空目录等）。"""
        junk_patterns = [
            "__pycache__",
            ".cache",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "node_modules",
        ]
        junk_suffixes = (
            ".tmp", ".bak", ".swp", ".pyc", ".pyo", ".log",
        )
        junk_names = frozenset({
            ".DS_Store", "Thumbs.db", ".directory",
            "desktop.ini",
        })

        cleaned_dirs = 0
        cleaned_files = 0

        for entry in sorted(self._root.rglob("*"), reverse=True):
            if not entry.is_dir():
                continue
            if entry.name in junk_patterns:
                try:
                    shutil.rmtree(str(entry))
                    cleaned_dirs += 1
                    self._logger.debug(f"清理垃圾目录: {entry.relative_to(self._root)}")
                except OSError:
                    pass
                continue
            if entry.name not in self._KNOWN_DIRS and entry != self._root:
                try:
                    if not any(entry.iterdir()):
                        entry.rmdir()
                        cleaned_dirs += 1
                except OSError:
                    pass

        for entry in self._root.rglob("*"):
            if not entry.is_file():
                continue
            name = entry.name
            should_delete = False

            if name in junk_names:
                should_delete = True
            elif name.endswith(junk_suffixes) or name.startswith("~") or name.endswith("~"):
                should_delete = True

            if should_delete:
                try:
                    entry.unlink()
                    cleaned_files += 1
                    self._logger.debug(f"清理垃圾文件: {entry.relative_to(self._root)}")
                except OSError:
                    pass

        cleaned_files += self._clean_orphan_write_temps()

        if cleaned_dirs > 0:
            result["removed"].append(f"垃圾目录 x{cleaned_dirs}")
        if cleaned_files > 0:
            result["removed"].append(f"垃圾文件 x{cleaned_files}")

    def _clean_orphan_write_temps(self) -> int:
        """清理原子写残留的 ``.neobot-write-*`` 临时文件。

        sandbox_service 写文件时先写同目录临时文件再 os.replace，正常路径会在
        finally 里删除；进程被强杀（崩溃 / 任务管理器结束）才会留下孤儿。这些
        文件以 "." 开头、没有扩展名，既不会被垃圾后缀规则命中，也不会出现在
        目录索引里，只能靠年龄判断。仍在进行中的写入寿命只有毫秒级，
        因此只清理超过一小时的。
        """
        cutoff = time.time() - _ORPHAN_TEMP_MAX_AGE_SECONDS
        cleaned = 0
        for entry in sorted(self._root.rglob(f"{_WRITE_TEMP_PREFIX}*"), reverse=True):
            try:
                if not entry.is_file() or entry.stat().st_mtime > cutoff:
                    continue
                entry.unlink()
                cleaned += 1
                self._logger.debug(f"清理原子写残留: {entry.relative_to(self._root)}")
            except OSError:
                continue
        return cleaned

    def _get_capacity_info(self) -> dict[str, Any]:
        """获取当前沙箱容量信息。"""
        if self._sandbox is None:
            return {"available": False, "reason": "sandbox_service 未配置"}
        total = self._sandbox.get_total_size()
        max_size = self._sandbox.max_total_size
        remaining = max_size - total
        return {
            "total_bytes": total,
            "max_bytes": max_size,
            "remaining_bytes": remaining,
            "total_mb": round(total / (1024 * 1024), 1),
            "max_mb": round(max_size / (1024 * 1024), 1),
            "remaining_mb": round(remaining / (1024 * 1024), 1),
            "usage_percent": round(total / max_size * 100, 1) if max_size > 0 else 0,
        }

    def _update_storage_doc(self, result: dict) -> None:
        """根据实际文件状态更新 文件存储.md。"""
        doc_path = self._root / _STORAGE_DOC
        sections: dict[str, list[str]] = {}

        for d in _PERSISTENT_DIRS:
            dir_path = self._root / d
            if not dir_path.is_dir():
                sections[d] = []
                continue
            items = []
            for entry in sorted(dir_path.iterdir()):
                if entry.is_file() and not entry.name.startswith("."):
                    items.append(f"- `{entry.name}` — ")
            sections[d] = items

        new_content = "# 沙箱文件存储\n\n"
        for d in _PERSISTENT_DIRS:
            new_content += f"## {d}/\n"
            if sections[d]:
                for item in sections[d]:
                    new_content += item + "\n"
            else:
                new_content += "（暂无）\n"
            new_content += "\n"
        new_content += "## gift/\n（由 gift skill 管理，勿手动编辑）\n"

        old_content = ""
        if doc_path.is_file():
            old_content = doc_path.read_text("utf-8")

        if old_content.strip() != new_content.strip():
            doc_path.write_text(new_content, "utf-8")
            result["doc_updated"] = True
            self._logger.debug("文件存储.md 已更新")

    def _touch_maintenance_marker(self) -> None:
        """更新维护时间标记。"""
        marker = self._root / _MAINTENANCE_MARKER
        marker.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))

    def get_last_maintenance_time(self) -> float | None:
        """返回上次维护的时间戳。"""
        marker = self._root / _MAINTENANCE_MARKER
        if marker.is_file():
            return marker.stat().st_mtime
        return None

    def get_status(self) -> dict[str, Any]:
        """返回当前维护状态（含容量信息）。"""
        last_time = self.get_last_maintenance_time()
        pending_count = 0
        todo_path = self._root / _TODO_DOC
        if todo_path.is_file():
            pending_count = len(_extract_pending_todos(todo_path.read_text("utf-8")))

        return {
            "enabled": self._enabled,
            "last_maintenance": (
                time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(last_time))
                if last_time else None
            ),
            "persistent_dirs": _PERSISTENT_DIRS,
            "pending_todo_count": pending_count,
            "capacity": self._get_capacity_info(),
        }


def _to_snake_case(name: str) -> str:
    """规范化 ASCII 名称；Unicode 或转换后无有效字符的名称保留原样。"""
    if not name.isascii():
        return name
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s2 = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s1)
    s3 = re.sub(r"[^a-zA-Z0-9]+", "_", s2)
    return s3.lower().strip("_") or name


def _extract_pending_todos(content: str) -> list[str]:
    """从 TODO.md 内容中提取 Pending 区域的条目描述文本。"""
    items: list[str] = []
    in_pending = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("## Pending"):
            in_pending = True
            continue
        if stripped.startswith("## "):
            in_pending = False
            continue
        if in_pending and stripped.startswith("- [ ]"):
            item_text = re.sub(r"^-\s*\[ \]\s*", "", stripped)
            if item_text:
                items.append(item_text)
    return items
