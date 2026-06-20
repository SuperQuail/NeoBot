"""BirthdaySkill — 生日记录管理。"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4

from neobot_contracts.models import ConversationRef
from neobot_contracts.models.scheduled_task import ScheduledTaskRecurrence
from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _parse_pipeline_key(pipeline_key: str) -> tuple[str, str]:
    if ":" in pipeline_key:
        return tuple(pipeline_key.split(":", 1))  # type: ignore
    return "", ""


def _resolve_bindings(args: dict) -> list[ConversationRef]:
    raw = args.get("bindings")
    if isinstance(raw, list):
        result: list[ConversationRef] = []
        for item in raw:
            if isinstance(item, dict):
                kind = str(item.get("kind", "") or "").strip()
                conv_id = str(item.get("id", "") or "").strip()
                if kind and conv_id:
                    result.append(ConversationRef(kind=kind, id=conv_id))
        if result:
            return result
    pipeline_key = str(args.get("pipeline_key", "") or "")
    kind, conv_id = _parse_pipeline_key(pipeline_key)
    if kind and conv_id:
        return [ConversationRef(kind=kind, id=conv_id)]
    return []


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

    person_name = str(args.get("person_name", "")).strip()
    if not person_name:
        return _json({"ok": False, "error": "person_name 不能为空"})

    birthday_raw = str(args.get("birthday", "")).strip()
    try:
        if len(birthday_raw) == 5 and birthday_raw[2] == "-":
            birthday_date = date(datetime.now().year, int(birthday_raw[:2]), int(birthday_raw[3:]))
        elif len(birthday_raw) == 10:
            birthday_date = date.fromisoformat(birthday_raw)
        else:
            return _json({"ok": False, "error": f"birthday 格式错误: {birthday_raw}，需为 YYYY-MM-DD 或 MM-DD"})
    except (ValueError, IndexError):
        return _json({"ok": False, "error": f"无法解析生日日期: {birthday_raw}"})

    start_time_str = str(args.get("start_time", "06:00")).strip()
    end_time_str = str(args.get("end_time", "22:00")).strip()
    try:
        start_h, start_m = map(int, start_time_str.split(":"))
        end_h, end_m = map(int, end_time_str.split(":"))
    except (ValueError, AttributeError):
        return _json({"ok": False, "error": "start_time/end_time 格式错误，需为 HH:MM"})

    this_year = datetime.now().year
    year = this_year if birthday_date.month > datetime.now().month or (
        birthday_date.month == datetime.now().month and birthday_date.day >= datetime.now().day
    ) else this_year + 1

    start_at = datetime(year, birthday_date.month, birthday_date.day, start_h, start_m)
    end_at = start_at + timedelta(days=1)

    bindings = _resolve_bindings(args)
    if not bindings:
        return _json({"ok": False, "error": "bindings 为空，需提供绑定聊天流或当前 pipeline 上下文"})

    celebration_style = str(args.get("celebration_style", "")).strip()
    relationship = str(args.get("relationship_context", "")).strip()
    detail_parts = [f"{person_name}的生日"]
    if celebration_style:
        detail_parts.append(f"庆祝方式：{celebration_style}")
    if relationship:
        detail_parts.append(f"关系背景：{relationship}")
    detail = "；".join(detail_parts)

    title = f"{person_name}的生日"
    metadata = {
        "type": "birthday",
        "person_name": person_name,
        "birthday": f"{birthday_date.month:02d}-{birthday_date.day:02d}",
        "celebration_style": celebration_style,
        "relationship_context": relationship,
    }

    task_uuid = str(uuid4())
    try:
        async with self._uow_factory() as uow:
            record = await uow.scheduled_tasks.create(
                task_uuid=task_uuid,
                title=title,
                detail=detail,
                recurrence=ScheduledTaskRecurrence.YEARLY,
                start_at=start_at,
                end_at=end_at,
                bindings=tuple(bindings),
                metadata=metadata,
            )
        return _json({"ok": True, "status": "birthday_task_created", "task": {
            "task_uuid": record.task_uuid,
            "title": record.title,
            "person_name": person_name,
            "birthday": f"{birthday_date.month:02d}-{birthday_date.day:02d}",
            "next_occurrence": start_at.isoformat(),
        }})
    except Exception as exc:
        return _json({"ok": False, "error": str(exc)})


_HANDLERS = {
    "create_birthday_task": _handle_create_birthday_task,
}
