"""SandboxMaintenanceSkill — 沙箱维护 Skill（AI 驱动）。

允许 agent 检查沙箱状态、清理临时文件、触发持久化文件维护。
AI 自行决策何时清理、清理什么。
"""

from __future__ import annotations

import asyncio
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
            "沙箱维护 Skill 用于检查和管理 sandbox/ 下的文件，不自动执行维护。\n\n"
            "## 操作流程\n"
            "1. 清理前先阅读 sandbox/文件存储.md；不存在时先检查目录结构。\n"
            "2. 使用 get_maintenance_status、check_capacity 或 scan_temp_files 只读检查，"
            "确认确有维护需要后再调用写入工具。\n"
            "3. trigger_maintenance 会移动错放文件、清理垃圾文件和缓存目录、整理持久化文件，"
            "并自动重建 文件存储.md；它不是只读扫描，也不只处理 tools/。\n"
            "4. 检查返回的 skipped、renamed、moved、removed、doc_updated，"
            "如有重命名或移动，核对依赖旧路径的引用；需要补充索引说明时再更新存储文档。\n\n"
            "## 文件命名安全规则\n"
            "- tools/、docs/、assets/ 的直属文件才参与命名整理，不递归重命名。\n"
            "- 中文名保留原样；含中文、其他 Unicode 字符或中英混合的文件名整体保留，"
            "不删除字符、不转拼音，也不修改其扩展名。\n"
            "- 仅纯 ASCII 文件名参与 snake_case 规范化，保留扩展名；"
            "空主名、点开头文件及符号链接不执行命名转换，目标名称已被占用时跳过。\n"
            "- 已被旧版本改名为 .html 等名称的文件不会自动恢复；"
            "须根据维护记录或备份确认原名，不能猜测改名或覆盖其他文件。\n\n"
            "## 默认存储规范\n"
            "- tools/ — 可复用的工具脚本、程序\n"
            "- docs/ — 文档、参考资料、说明文件\n"
            "- assets/ — 静态资源（图片、字体、模板等）\n"
            "- temp/ — 按 chat_flow_id 分子目录的临时文件，先扫描再清理\n"
            "- gift/ — 礼物文件，由 gift skill 管理，勿手动编辑\n"
            "- 根目录文档保留 文件存储.md、TODO.md\n\n"
            "## 工具列表\n"
            "  scan_temp_files — 只读扫描临时目录\n"
            "  clean_temp_files — 清理过期文件、修复临时目录嵌套、清理空目录\n"
            "  trigger_maintenance — 执行持久化维护并更新索引，无变更时跳过\n"
            "  get_maintenance_status — 只读查询维护状态\n"
            "  check_capacity — 只读查询容量"
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
                "执行沙箱维护（会移动、重命名和删除文件，并自动更新存储索引），无文件变更时跳过。"
                "仅规范化 tools/docs/assets 直属文件的纯 ASCII 名称；中文及中英混合等 Unicode 文件名"
                "保留原样，不生成空主名，目标名称已占用时跳过。",
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
            # TempCleaner 是同步实现（整树扫描/删除），必须离开事件循环
            status = await asyncio.to_thread(self._temp_cleaner.get_status)
            return _json(status)
        except Exception as e:
            return _json({"ok": False, "error": str(e)})

    async def _handle_clean_temp(self, args: dict) -> str:
        if self._temp_cleaner is None:
            return _json({"ok": False, "error": "temp_cleaner 未配置"})
        try:
            result = await asyncio.to_thread(self._temp_cleaner.run_once)
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
