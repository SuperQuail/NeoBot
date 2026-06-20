"""SandboxMaintenanceSkill — 沙箱定时维护 Skill。

允许 agent 手动触发维护或查询维护状态。
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

class SandboxMaintenanceSkill(SkillModule):
    """沙箱维护 Skill — 手动触发维护、查询状态、检查容量。"""

    @property
    def name(self) -> str:
        return "sandbox_maintenance"

    @property
    def description(self) -> str:
        return "沙箱维护：手动触发文件整理、查询维护状态、检查沙箱容量"

    @property
    def instructions(self) -> str:
        return (
            "沙箱维护 Skill 用于管理 sandbox/ 下持久化文件的定期整理和维护。\n\n"
            "## 维护系统说明\n"
            "系统默认每 3 小时自动触发一次维护（仅在检测到非 temp 文件变更时）。\n"
            "维护内容包括：\n"
            "  1. 清理根目录和 tmp/ 中不当放置的文件\n"
            "  2. 清理垃圾文件（__pycache__/、.DS_Store、.tmp/.bak 等）\n"
            "  3. 整理文件命名（统一 snake_case）\n"
            "  4. 检查文件位置合理性，删除冗余文件\n"
            "  5. 更新 文件存储.md 与实际文件一致\n"
            "  6. 发布 TODO 项处理通知（含容量信息）\n\n"
            "## 工具列表\n"
            "  trigger_maintenance — 手动触发一次完整的维护流程\n"
            "  get_maintenance_status — 查询上次维护时间和当前状态（含容量信息）\n"
            "  check_capacity — 检查沙箱当前容量使用情况"
        )

    def __init__(
        self,
        maintenance_manager: Any = None,
        sandbox_service: Any = None,
    ) -> None:
        self._maintenance = maintenance_manager
        self._sandbox = sandbox_service

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "trigger_maintenance",
                "手动触发一次沙箱持久化文件维护。包括文件整理、冗余清理、垃圾清理、文档更新、TODO 处理。",
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
        if tool_name == "trigger_maintenance":
            return await self._handle_trigger(args)
        if tool_name == "get_maintenance_status":
            return await self._handle_status(args)
        if tool_name == "check_capacity":
            return await self._handle_capacity(args)
        return _json({"ok": False, "error": f"unknown sandbox_maintenance tool: {tool_name}"})

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

