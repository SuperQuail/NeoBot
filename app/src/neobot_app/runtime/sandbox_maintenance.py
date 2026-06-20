"""SandboxMaintenanceManager — 沙箱持久化文件定时维护。

每 N 秒扫描 sandbox/ 下的持久化目录（tools/、docs/、assets/），
整理文件命名和位置，删除冗余文件，更新 文件存储.md。
清理根目录和 tmp/ 中的不当文件，清除空目录。
如果自上次维护以来无非 temp 文件变更，则跳过。
"""

from __future__ import annotations

import asyncio
import os
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


class SandboxMaintenanceManager:
    """沙箱持久化文件定时维护管理器。"""

    def __init__(
        self,
        sandbox_root: str | Path,
        *,
        interval_seconds: int = 10800,
        enabled: bool = True,
        notification_hub: Any = None,
        sandbox_service: Any = None,
        logger: Logger | None = None,
    ) -> None:
        self._root = Path(sandbox_root).resolve()
        self._interval = interval_seconds
        self._enabled = enabled
        self._notification_hub = notification_hub
        self._sandbox = sandbox_service
        self._logger = logger or NullLogger()
        self._runner: asyncio.Task | None = None
        self._stopping = asyncio.Event()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def root(self) -> Path:
        return self._root

    def set_notification_hub(self, hub: Any) -> None:
        self._notification_hub = hub

    def start(self) -> None:
        if not self._enabled:
            self._logger.info("SandboxMaintenanceManager 已禁用")
            return
        if self._runner is not None and not self._runner.done():
            return
        self._stopping.clear()
        self._runner = asyncio.create_task(self._run_loop())
        self._logger.info(
            f"SandboxMaintenanceManager 已启动: interval={self._interval}s"
        )

    async def stop(self) -> None:
        self._stopping.set()
        if self._runner is not None:
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass
            self._runner = None
        self._logger.info("SandboxMaintenanceManager 已停止")

    async def _run_loop(self) -> None:
        # 首次启动后等待 60 秒再开始第一次检查
        await asyncio.sleep(60)
        while not self._stopping.is_set():
            try:
                await self._maintenance_cycle()
            except Exception as exc:
                self._logger.warning(f"维护异常: {exc}")
            try:
                await asyncio.wait_for(
                    self._stopping.wait(), timeout=self._interval
                )
                break
            except asyncio.TimeoutError:
                pass

    async def run_once(self, *, force: bool = False) -> dict[str, Any]:
        """手动触发一次维护，返回结果摘要。force=True 时跳过变更检查强制执行。"""
        return await self._maintenance_cycle(force=force)

    async def _maintenance_cycle(self, *, force: bool = False) -> dict[str, Any]:
        """执行一次完整的维护周期。force=True 时跳过变更检查强制执行。"""
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
            "todo_processed": False,
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

        # 4. 尝试处理 TODO
        await self._process_todo(result)

        # 5. 刷新容量信息（清理后）
        result["capacity"] = self._get_capacity_info()

        # 6. 更新维护标记
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
                    # chat_flow 目录应放在 temp/ 下
                    target = self._root / "temp" / name
                    try:
                        if not target.exists():
                            shutil.move(str(entry), str(target))
                        else:
                            # 目标存在 → 合并文件
                            self._merge_dir(entry, target)
                            shutil.rmtree(str(entry))
                        result["moved"].append(f"{name} -> temp/{name}")
                        self._logger.debug(f"移动 chat_flow 目录: {name} -> temp/")
                    except OSError as e:
                        self._logger.warning(f"移动目录失败 {name}: {e}")
                else:
                    # 非 chat_flow 非已知目录 → 移到 docs/
                    target = self._root / "docs" / name
                    try:
                        if not target.exists():
                            shutil.move(str(entry), str(target))
                            result["moved"].append(f"{name} -> docs/{name}")
                            self._logger.debug(f"移动未知目录: {name} -> docs/")
                    except OSError as e:
                        self._logger.warning(f"移动目录失败 {name}: {e}")
            elif entry.is_file():
                # 保留文件不移动
                if name in self._KEPT_FILES:
                    continue
                # 根目录下的孤立文件 → 移到 docs/
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
        """检查文件命名规范（统一 snake_case）。"""
        name = file_path.name
        # 跳过特殊文件（如 .gitkeep、prepared 等标记文件）
        if name.startswith(".") or name in ("prepared",):
            return
        # 检查是否已经是 snake_case（允许数字和中划线在 snake_case 中）
        stem = file_path.stem
        if re.match(r"^[a-z][a-z0-9_\-]*$", stem):
            return
        # 尝试转换为 snake_case
        new_stem = _to_snake_case(stem)
        if new_stem == stem:
            return
        new_name = new_stem + file_path.suffix
        new_path = file_path.parent / new_name
        if not new_path.exists():
            try:
                file_path.rename(new_path)
                result["renamed"].append(
                    f"{section}/{file_path.name} -> {new_name}"
                )
                self._logger.debug(f"重命名: {file_path.name} -> {new_name}")
            except OSError:
                pass

    def _check_redundant_file(
        self, file_path: Path, section: str, result: dict
    ) -> None:
        """检查并删除明显冗余的文件。"""
        name = file_path.name
        # 删除临时/备份文件
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

        # 扫描所有目录，删除垃圾目录
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
            # 清理空目录（已经在上面 rglob 中，通过 reverse 自底向上）
            if entry.name not in self._KNOWN_DIRS and entry != self._root:
                try:
                    if not any(entry.iterdir()):
                        entry.rmdir()
                        cleaned_dirs += 1
                except OSError:
                    pass

        # 扫描垃圾文件
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

        if cleaned_dirs > 0:
            result["removed"].append(f"垃圾目录 x{cleaned_dirs}")
        if cleaned_files > 0:
            result["removed"].append(f"垃圾文件 x{cleaned_files}")

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

        # 只有当内容变化时才写入
        old_content = ""
        if doc_path.is_file():
            old_content = doc_path.read_text("utf-8")

        if old_content.strip() != new_content.strip():
            doc_path.write_text(new_content, "utf-8")
            result["doc_updated"] = True
            self._logger.debug("文件存储.md 已更新")

    async def _process_todo(self, result: dict) -> None:
        """检查 TODO.md，如有待实现项则尝试处理。"""
        todo_path = self._root / _TODO_DOC
        if not todo_path.is_file():
            return

        content = todo_path.read_text("utf-8")
        pending_items = _extract_pending_todos(content)
        if not pending_items:
            return

        # 通过 notification_hub 发布 TODO 处理通知
        if self._notification_hub is not None:
            todo_list = "\n".join(f"- {item}" for item in pending_items)
            cap = self._get_capacity_info()
            cap_line = (
                f"沙箱容量：已用 {cap['total_mb']}MB / 上限 {cap['max_mb']}MB "
                f"（{cap['usage_percent']}%）"
                if cap.get("available", True)
                else "沙箱容量：不可用"
            )
            try:
                await self._notification_hub.publish(
                    source="sandbox_maintenance",
                    kind="group",
                    conversation_id="admin",
                    content=(
                        "<新的必须回复内容>\n"
                        "这是一条沙箱定时维护通知。\n"
                        f"{cap_line}\n\n"
                        "以下是 TODO.md 中的待实现工具，请在 sandbox/tools/ 目录下逐一实现：\n\n"
                        f"{todo_list}\n\n"
                        "实现要求：\n"
                        "1. 每个工具创建后必须运行测试验证可用\n"
                        "2. 测试通过后调用 file_storage__update_storage_doc 更新文件索引\n"
                        "3. 调用 file_storage__update_todo action=complete 将实现完成的项标记为完成\n"
                        "4. 所有工具完成后调用 sandbox_maintenance__get_maintenance_status 确认状态\n"
                        "5. 注意及时清理沙箱中的垃圾文件，保持空间充足\n"
                        "</新的必须回复内容>"
                    ),
                    manager_name="sandbox_maintenance",
                    reasons=["sandbox maintenance TODO processing"],
                    metadata={
                        "pending_count": len(pending_items),
                        "capacity": cap,
                    },
                )
                result["todo_processed"] = True
                self._logger.info(
                    f"已发布 TODO 处理通知，待实现: {len(pending_items)} 项"
                )
            except Exception as exc:
                self._logger.warning(f"发布 TODO 通知失败: {exc}")

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
            "interval_seconds": self._interval,
            "last_maintenance": (
                time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(last_time))
                if last_time else None
            ),
            "persistent_dirs": _PERSISTENT_DIRS,
            "pending_todo_count": pending_count,
            "capacity": self._get_capacity_info(),
        }


def _to_snake_case(name: str) -> str:
    """将 CamelCase 或 mixedCase 转为 snake_case。"""
    # 插入下划线
    s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s2 = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s1)
    # 处理连续非字母数字
    s3 = re.sub(r"[^a-zA-Z0-9]+", "_", s2)
    return s3.lower().strip("_")


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
            # 提取条目文本（去掉 checkbox）
            item_text = re.sub(r"^-\s*\[ \]\s*", "", stripped)
            if item_text:
                items.append(item_text)
    return items
