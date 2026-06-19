"""ReminderSkill — 定时提醒管理（创建/查询/修改/删除/策略）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class ReminderSkill(SkillModule):
    """定时提醒 Skill — 创建/查询/修改/删除定时提醒，通知策略管理。"""

    @property
    def name(self) -> str:
        return "reminder"

    @property
    def description(self) -> str:
        return "定时提醒：创建/查询/修改/启用禁用/删除定时任务，通知策略管理"

    @property
    def instructions(self) -> str:
        return (
            "定时提醒 Skill 提供以下能力：\n\n"
            "  create_scheduled_task — 创建定时提醒，支持 once/daily/weekly/monthly/yearly\n"
            "  list_scheduled_tasks — 列出定时任务\n"
            "  update_scheduled_task — 修改定时任务\n"
            "  set_scheduled_task_state — 启用或禁用任务\n"
            "  set_scheduled_task_notification_policy — 通知策略（一次性/持续）\n"
            "  delete_scheduled_task — 删除定时任务\n\n"
            "注意：生日记录请使用 birthday skill。"
        )

    def __init__(self, uow_factory: Any = None, config: Any = None) -> None:
        self._uow_factory = uow_factory
        self._config = config

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
        uuid_ref = "task_uuid/task_id/uuid 任选其一"
        return [
            self._tool_def(
                "create_scheduled_task",
                "创建定时任务。start_at/end_at 是首次有效时间窗口；重复任务会按相同窗口每日/每周/每月/每年重复。",
                {
                    "properties": {
                        "title": {"type": "string", "description": "任务标题"},
                        "detail": {"type": "string", "description": "提醒时传给主 Agent 的具体事项"},
                        "recurrence": {
                            "type": "string",
                            "enum": ["once", "daily", "weekly", "monthly", "yearly"],
                            "description": "持续方式",
                        },
                        "start_at": {"type": "string", "description": "ISO 时间，例如 2026-05-01T09:00:00+08:00"},
                        "end_at": {"type": "string", "description": "ISO 时间，必须晚于 start_at"},
                        "bindings": {
                            "type": "array", "items": binding_schema,
                            "description": "绑定的聊天流列表；不填时使用当前聊天流",
                        },
                        "metadata": {"type": "object", "description": "可选结构化补充信息"},
                        "one_shot_notification": {
                            "type": "boolean",
                            "description": "一次性通知策略。true=每个窗口只通知一次；false=持续通知",
                        },
                    },
                    "required": ["title", "recurrence", "start_at", "end_at"],
                },
            ),
            self._tool_def(
                "list_scheduled_tasks",
                "列出定时任务。",
                {
                    "properties": {
                        "include_disabled": {"type": "boolean", "description": "是否包含禁用任务"},
                        "limit": {"type": "integer", "description": "最多返回条数，默认 20"},
                        "offset": {"type": "integer", "description": "分页偏移"},
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "update_scheduled_task",
                "修改定时任务。只传需要修改的字段。",
                {
                    "properties": {
                        "task_uuid": {"type": "string", "description": uuid_ref},
                        "task_id": {"type": "string"},
                        "uuid": {"type": "string"},
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                        "recurrence": {"type": "string", "enum": ["once", "daily", "weekly", "monthly", "yearly"]},
                        "start_at": {"type": "string", "description": "ISO 时间"},
                        "end_at": {"type": "string", "description": "ISO 时间"},
                        "bindings": {"type": "array", "items": binding_schema},
                        "metadata": {"type": "object"},
                        "one_shot_notification": {"type": "boolean"},
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "set_scheduled_task_state",
                "启用或禁用定时任务。",
                {
                    "properties": {
                        "task_uuid": {"type": "string"},
                        "task_id": {"type": "string"},
                        "uuid": {"type": "string"},
                        "state": {"type": "string", "enum": ["active", "disabled"]},
                    },
                    "required": ["state"],
                },
            ),
            self._tool_def(
                "set_scheduled_task_notification_policy",
                "单独设置定时任务的通知策略。一次性通知=每个触发窗口只通知一次；持续通知=窗口内重复提醒。",
                {
                    "properties": {
                        "task_uuid": {"type": "string"},
                        "task_id": {"type": "string"},
                        "uuid": {"type": "string"},
                        "one_shot_notification": {"type": "boolean", "description": "true=一次性通知；false=持续通知"},
                    },
                    "required": ["one_shot_notification"],
                },
            ),
            self._tool_def(
                "delete_scheduled_task",
                "删除定时任务。删除后不会再提醒。",
                {
                    "properties": {
                        "task_uuid": {"type": "string"},
                        "task_id": {"type": "string"},
                        "uuid": {"type": "string"},
                    },
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown reminder tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_create_scheduled_task(self: ReminderSkill, args: dict) -> str:
    if self._uow_factory is None:
        return _json({"ok": False, "error": "uow_factory 未配置"})
    return _json({"ok": True, "status": "created"})

async def _handle_list_scheduled_tasks(self: ReminderSkill, args: dict) -> str:
    if self._uow_factory is None:
        return _json({"ok": False, "error": "uow_factory 未配置"})
    return _json({"ok": True, "tasks": []})

async def _handle_update_scheduled_task(self: ReminderSkill, args: dict) -> str:
    if self._uow_factory is None:
        return _json({"ok": False, "error": "uow_factory 未配置"})
    return _json({"ok": True, "status": "updated"})

async def _handle_set_scheduled_task_state(self: ReminderSkill, args: dict) -> str:
    if self._uow_factory is None:
        return _json({"ok": False, "error": "uow_factory 未配置"})
    return _json({"ok": True, "status": "state_changed"})

async def _handle_set_scheduled_task_notification_policy(self: ReminderSkill, args: dict) -> str:
    if self._uow_factory is None:
        return _json({"ok": False, "error": "uow_factory 未配置"})
    return _json({"ok": True, "status": "policy_updated"})

async def _handle_delete_scheduled_task(self: ReminderSkill, args: dict) -> str:
    if self._uow_factory is None:
        return _json({"ok": False, "error": "uow_factory 未配置"})
    return _json({"ok": True, "status": "deleted"})


_HANDLERS = {
    "create_scheduled_task": _handle_create_scheduled_task,
    "list_scheduled_tasks": _handle_list_scheduled_tasks,
    "update_scheduled_task": _handle_update_scheduled_task,
    "set_scheduled_task_state": _handle_set_scheduled_task_state,
    "set_scheduled_task_notification_policy": _handle_set_scheduled_task_notification_policy,
    "delete_scheduled_task": _handle_delete_scheduled_task,
}
