"""SandboxMaintenanceSkill — 沙箱维护 Skill（AI 驱动）。

允许 agent 检查沙箱状态、清理临时文件、触发持久化文件维护。
AI 自行决策何时清理、清理什么。
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

class SandboxMaintenanceSkill(SkillModule):
    """沙箱维护 Skill — 检查状态、清理临时文件、触发维护。"""

    @property
    def name(self) -> str:
        return "sandbox_maintenance"

    @property
    def description(self) -> str:
        return "沙箱维护：检查临时文件状态、清理过期文件、触发持久化文件整理"

    @property
    def instructions(self) -> str:
        return (
            "沙箱维护 Skill 用于检查和管理 sandbox/ 下的文件。\n\n"
            "## 核心规则\n"
            "**清理前必须先阅读 sandbox/文件存储.md 了解当前存储规范。**\n"
            "如文件存储.md 不存在，先检查 sandbox/ 目录结构，按默认规范创建文件存储.md\n"
            "后再执行清理。**清理完成后必须调用 file_storage__update_storage_doc 更新索引。**\n\n"
            "## 默认存储规范（文件存储.md 不存在时参考）\n"
            "- tools/ — 可复用的工具脚本、程序\n"
            "- docs/ — 文档、参考资料、说明文件\n"
            "- assets/ — 静态资源（图片、字体、模板等）\n"
            "- temp/ — 临时文件，按 chat_flow_id 分子目录，可随时清理\n"
            "- gift/ — 礼物文件，由 gift skill 管理，勿手动编辑\n"
            "- 文件命名统一使用 snake_case，中文名保留原样\n"
            "- 根目录只保留 文件存储.md、TODO.md 和持久化目录\n\n"
            "## 维护模式\n"
            "系统不再自动执行维护，由你主动检查并决定是否需要清理。\n"
            "收到维护提醒通知时，或在文件操作前，先检查沙箱状态。\n\n"
            "## 工具列表\n"
            "  scan_temp_files — 扫描临时目录，查看过期文件、嵌套、空目录（只读）\n"
            "  clean_temp_files — 执行临时文件清理（删除过期文件、修复嵌套、清理空目录）\n"
            "  trigger_maintenance — 触发一次完整的持久化文件维护\n"
            "  get_maintenance_status — 查询上次维护时间和当前状态\n"
            "  check_capacity — 检查沙箱当前容量使用情况"
        )

    def __init__(
        self,
        maintenance_manager: Any = None,
        sandbox_service: Any = None,
        temp_cleaner: Any = None,
    ) -> None:
        self._maintenance = maintenance_manager
        self._sandbox = sandbox_service
        self._temp_cleaner = temp_cleaner

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "scan_temp_files",
                "只读扫描沙箱 temp/ 目录，返回过期文件列表、嵌套目录、空目录统计。"
                "用于在清理前评估需要清理的内容。",
                {"properties": {}, "required": []},
            ),
            self._tool_def(
                "clean_temp_files",
                "执行临时文件清理：删除过期文件（默认超过30分钟未修改）、"
                "修复递归嵌套目录、删除空目录。返回清理数量统计。",
                {"properties": {}, "required": []},
            ),
            self._tool_def(
                "trigger_maintenance",
                "手动触发一次沙箱持久化文件维护。包括文件整理、冗余清理、垃圾清理、文档更新。"
                "如无文件变更则跳过。",
                {"properties": {}, "required": []},
            ),
            self._tool_def(
                "get_maintenance_status",
                "查询沙箱维护系统的当前状态，包括上次维护时间、待处理 TODO 数量、容量信息等。",
                {"properties": {}, "required": []},
            ),
            self._tool_def(
                "check_capacity",
                "检查沙箱当前容量使用情况：已用/上限/剩余（MB），使用百分比。"
                "当空间不足时应清理垃圾文件或触发维护。",
                {"properties": {}, "required": []},
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "scan_temp_files":
            return await self._handle_scan_temp(args)
        if tool_name == "clean_temp_files":
            return await self._handle_clean_temp(args)
        if tool_name == "trigger_maintenance":
            return await self._handle_trigger(args)
        if tool_name == "get_maintenance_status":
            return await self._handle_status(args)
        if tool_name == "check_capacity":
            return await self._handle_capacity(args)
        return _json({"ok": False, "error": f"unknown sandbox_maintenance tool: {tool_name}"})

    async def _handle_scan_temp(self, args: dict) -> str:
        if self._temp_cleaner is None:
            return _json({"ok": False, "error": "temp_cleaner 未配置"})
        try:
            status = self._temp_cleaner.get_status()
            return _json(status)
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

    async def _handle_clean_temp(self, args: dict) -> str:
        if self._temp_cleaner is None:
            return _json({"ok": False, "error": "temp_cleaner 未配置"})
        try:
            result = self._temp_cleaner.run_once()
            return _json(result)
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

    async def _handle_trigger(self, args: dict) -> str:
        if self._maintenance is None:
            return _json({"ok": False, "error": "maintenance_manager 未配置"})
        try:
            result = await self._maintenance.run_once()
            return _json(result)
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

    async def _handle_status(self, args: dict) -> str:
        if self._maintenance is None:
            return _json({"ok": False, "error": "maintenance_manager 未配置"})
        try:
            status = self._maintenance.get_status()
            return _json({"ok": True, **status})
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

    async def _handle_capacity(self, args: dict) -> str:
        """直接查询沙箱容量（也可通过 maintenance_manager 获取）。"""
        cap = None
        if self._maintenance is not None:
            cap = self._maintenance._get_capacity_info()
        if cap is None or not cap.get("available", False):
            if self._sandbox is not None:
                total = self._sandbox.get_total_size()
                max_size = self._sandbox.max_total_size
                remaining = max_size - total
                cap = {
                    "total_bytes": total,
                    "max_bytes": max_size,
                    "remaining_bytes": remaining,
                    "total_mb": round(total / (1024 * 1024), 1),
                    "max_mb": round(max_size / (1024 * 1024), 1),
                    "remaining_mb": round(remaining / (1024 * 1024), 1),
                    "usage_percent": round(total / max_size * 100, 1) if max_size > 0 else 0,
                }
        if cap is None:
            return _json({"ok": False, "error": "sandbox_service 未配置，无法获取容量"})
        return _json({"ok": True, **cap})
