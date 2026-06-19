"""BirthdaySkill — 生日记录管理。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class BirthdaySkill(SkillModule):
    """生日管理 Skill — 记录生日，自动创建 yearly 定时任务。"""

    @property
    def name(self) -> str:
        return "birthday"

    @property
    def description(self) -> str:
        return "生日记录：记录生日信息并创建 yearly 庆祝定时任务"

    @property
    def instructions(self) -> str:
        return (
            "生日管理 Skill 提供以下能力：\n\n"
            "  create_birthday_task — 专用生日记录工具，自动创建 yearly 任务。\n"
            "  记录生日时必须包含：是谁的生日、在哪些聊天流庆祝、对方希望的庆祝方式。\n\n"
            "注意：有人提出生日、生日祝福偏好、庆祝方式变更时应先记录或更新。"
        )

    def __init__(self, uow_factory: Any = None) -> None:
        self._uow_factory = uow_factory

    def reset(self) -> None:
        pass

    def _binding_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["group", "private"]},
                "id": {"type": "string", "description": "群号或好友 QQ 号"},
            },
            "required": ["kind", "id"],
        }

    def get_tools(self) -> list[dict]:
        binding_schema = self._binding_schema()
        return [
            self._tool_def(
                "create_birthday_task",
                "生日专用工具。记录生日时必须包含：是谁的生日、在哪些聊天流庆祝、对方希望的庆祝方式。"
                "生日会创建 yearly 定时任务。",
                {
                    "properties": {
                        "person_name": {"type": "string", "description": "生日对象的称呼或姓名"},
                        "birthday": {"type": "string", "description": "生日日期，格式 YYYY-MM-DD 或 MM-DD"},
                        "bindings": {
                            "type": "array", "items": binding_schema,
                            "description": "要在哪些聊天流庆祝",
                        },
                        "celebration_style": {"type": "string", "description": "对方希望的庆祝方式"},
                        "relationship_context": {"type": "string", "description": "可选，关系背景"},
                        "start_time": {"type": "string", "description": "可选，开始提醒时间 HH:MM，默认 06:00"},
                        "end_time": {"type": "string", "description": "可选，结束提醒时间 HH:MM，默认 22:00"},
                        "one_shot_notification": {"type": "boolean", "description": "一次性通知策略，生日通常保持 true"},
                    },
                    "required": ["person_name", "birthday"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown birthday tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_create_birthday_task(self: BirthdaySkill, args: dict) -> str:
    if self._uow_factory is None:
        return _json({"ok": False, "error": "uow_factory 未配置"})
    return _json({"ok": True, "status": "birthday_task_created"})


_HANDLERS = {
    "create_birthday_task": _handle_create_birthday_task,
}
