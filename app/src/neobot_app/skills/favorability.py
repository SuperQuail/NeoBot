"""FavorabilitySkill — 好感度调整。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class FavorabilitySkill(SkillModule):
    """好感度 Skill — 调整用户好感度。"""

    @property
    def name(self) -> str:
        return "favorability"

    @property
    def description(self) -> str:
        return "好感度管理：调整用户好感度，幅度有上限"

    @property
    def instructions(self) -> str:
        return (
            "好感度 Skill 提供以下能力：\n\n"
            "  update_favorability — 调整用户好感度，每次变更幅度有限制。"
            "根据近期聊天中用户表现出的态度、行为、互动质量等综合判断，适当调整好感度。"
        )

    def __init__(
        self,
        profile_service: Any = None,
        max_change: int = 5,
        min_value: int = -1000,
        max_value: int = 1000,
    ) -> None:
        self._profile_service = profile_service
        self._max_change = max_change
        self._min_value = min_value
        self._max_value = max_value

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        if self._profile_service is None or self._max_change <= 0:
            return []
        return [
            self._tool_def(
                "update_favorability",
                f"调整用户好感度。每次变更幅度限制在 ±{self._max_change} 以内，"
                f"范围 {self._min_value} 到 {self._max_value}。"
                "根据近期聊天中用户表现出的态度、行为、互动质量等综合判断，适当调整好感度。"
                "正向互动增加好感度，负向互动减少好感度。",
                {
                    "properties": {
                        "user_id": {"type": "string", "description": "目标QQ号"},
                        "change": {
                            "type": "integer",
                            "description": f"好感度变更量，范围 [{-self._max_change}, {self._max_change}]",
                        },
                        "reason": {"type": "string", "description": "可选，变更原因简述"},
                    },
                    "required": ["user_id", "change"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown favorability tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_update_favorability(self: FavorabilitySkill, args: dict) -> str:
    if self._profile_service is None:
        return _json({"ok": False, "error": "profile_service 未配置"})
    user_id = str(args.get("user_id", "")).strip()
    change = int(args.get("change", 0))
    reason = str(args.get("reason", "")).strip()
    if not user_id or change == 0:
        return _json({"ok": False, "error": "缺少必要参数或变更量为0"})
    try:
        result = await self._profile_service.update_favorability(
            user_id, change, reason=reason,
            max_change=self._max_change, min_value=self._min_value, max_value=self._max_value,
        )
        return _json({"ok": True, "result": result})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


_HANDLERS = {
    "update_favorability": _handle_update_favorability,
}
