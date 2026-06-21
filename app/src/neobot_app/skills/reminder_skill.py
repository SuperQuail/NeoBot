"""ReminderSkill — 定时提醒管理（创建/查询/修改/删除/策略）。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from neobot_contracts.models import ConversationRef
from neobot_contracts.models.scheduled_task import ScheduledTaskRecurrence, ScheduledTaskState
from neobot_app.skills.base import SkillModule

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

def _parse_pipeline_key(pipeline_key: str) -> tuple[str, str]:
    """从 pipeline_key 中提取 (kind, id)。"""
    if ":" in pipeline_key:
        return tuple(pipeline_key.split(":", 1))  # type: ignore
    return "", ""

def _resolve_bindings(args: dict) -> list[ConversationRef]:
    """从 args 中解析 bindings，若未提供则从当前 pipeline_key 构造默认值。"""
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

def _resolve_task_uuid(args: dict) -> str:
    """从 args 的多种键名中提取任务 UUID。"""
    for key in ("task_uuid", "task_id", "uuid"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""

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

# ── Handlers ──

async def _handle_create_scheduled_task(self: ReminderSkill, args: dict) -> str:
    if self._uow_factory is None:
        return _json({"ok": False, "error": "uow_factory 未配置"})
    title = str(args.get("title", "")).strip()
    if not title:
        return _json({"ok": False, "error": "title 不能为空"})
    detail = str(args.get("detail", "")).strip()
    recurrence_raw = str(args.get("recurrence", "")).strip()
    try:
        recurrence = ScheduledTaskRecurrence(recurrence_raw)
    except ValueError:
        return _json({"ok": False, "error": f"无效的 recurrence: {recurrence_raw}，可选 once/daily/weekly/monthly/yearly"})
    start_at_str = str(args.get("start_at", "")).strip()
    end_at_str = str(args.get("end_at", "")).strip()
    try:
        start_at = datetime.fromisoformat(start_at_str)
        end_at = datetime.fromisoformat(end_at_str)
    except (ValueError, TypeError):
        return _json({"ok": False, "error": "start_at/end_at 格式错误，需为 ISO 8601 格式"})
    if end_at <= start_at:
        return _json({"ok": False, "error": "end_at 必须晚于 start_at"})
    bindings = _resolve_bindings(args)
    if not bindings:
        return _json({"ok": False, "error": "bindings 为空，需提供绑定聊天流或当前 pipeline 上下文"})
    metadata = args.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        metadata = None
    task_uuid = str(uuid4())
    try:
        async with self._uow_factory() as uow:
            record = await uow.scheduled_tasks.create(
                task_uuid=task_uuid,
                title=title,
                detail=detail,
                recurrence=recurrence,
                start_at=start_at,
                end_at=end_at,
                bindings=tuple(bindings),
                metadata=metadata,
            )
        return _json({"ok": True, "status": "created", "task": {
            "task_uuid": record.task_uuid,
            "title": record.title,
            "recurrence": record.recurrence.value,
            "start_at": record.start_at.isoformat(),
            "end_at": record.end_at.isoformat(),
            "state": record.state.value,
        }})
    except Exception as exc:
        return _json({"ok": False, "error": str(exc)})

async def _handle_list_scheduled_tasks(self: ReminderSkill, args: dict) -> str:
    if self._uow_factory is None:
        return _json({"ok": False, "error": "uow_factory 未配置"})
    include_disabled = bool(args.get("include_disabled", False))
    limit = int(args.get("limit", 20))
    offset = int(args.get("offset", 0))
    try:
        async with self._uow_factory() as uow:
            records = await uow.scheduled_tasks.list(
                include_disabled=include_disabled,
                limit=limit,
                offset=offset,
            )
        tasks = [{
            "task_uuid": r.task_uuid,
            "title": r.title,
            "detail": r.detail,
            "recurrence": r.recurrence.value,
            "start_at": r.start_at.isoformat(),
            "end_at": r.end_at.isoformat(),
            "state": r.state.value,
            "bindings": [{"kind": b.kind, "id": str(b.id)} for b in r.bindings],
        } for r in records]
        return _json({"ok": True, "tasks": tasks})
    except Exception as exc:
        return _json({"ok": False, "error": str(exc)})

async def _handle_update_scheduled_task(self: ReminderSkill, args: dict) -> str:
    if self._uow_factory is None:
        return _json({"ok": False, "error": "uow_factory 未配置"})
    task_uuid = _resolve_task_uuid(args)
    if not task_uuid:
        return _json({"ok": False, "error": "缺少 task_uuid/task_id/uuid"})
    kwargs: dict = {}
    if "title" in args:
        kwargs["title"] = str(args["title"]).strip()
    if "detail" in args:
        kwargs["detail"] = str(args["detail"]).strip()
    if "recurrence" in args:
        try:
            kwargs["recurrence"] = ScheduledTaskRecurrence(str(args["recurrence"]).strip())
        except ValueError:
            return _json({"ok": False, "error": f"无效的 recurrence: {args['recurrence']}"})
    if "start_at" in args:
        try:
            kwargs["start_at"] = datetime.fromisoformat(str(args["start_at"]).strip())
        except (ValueError, TypeError):
            return _json({"ok": False, "error": "start_at 格式错误"})
    if "end_at" in args:
        try:
            kwargs["end_at"] = datetime.fromisoformat(str(args["end_at"]).strip())
        except (ValueError, TypeError):
            return _json({"ok": False, "error": "end_at 格式错误"})
    if "bindings" in args:
        bindings = _resolve_bindings(args)
        if bindings:
            kwargs["bindings"] = tuple(bindings)
    if "metadata" in args and isinstance(args["metadata"], dict):
        kwargs["metadata"] = args["metadata"]
    if not kwargs:
        return _json({"ok": False, "error": "没有提供需要修改的字段"})
    try:
        async with self._uow_factory() as uow:
            record = await uow.scheduled_tasks.update(task_uuid, **kwargs)
        return _json({"ok": True, "status": "updated", "task": {
            "task_uuid": record.task_uuid,
            "title": record.title,
            "recurrence": record.recurrence.value,
            "state": record.state.value,
        }})
    except LookupError:
        return _json({"ok": False, "error": f"未找到任务: {task_uuid}"})
    except Exception as exc:
        return _json({"ok": False, "error": str(exc)})

async def _handle_set_scheduled_task_state(self: ReminderSkill, args: dict) -> str:
    if self._uow_factory is None:
        return _json({"ok": False, "error": "uow_factory 未配置"})
    task_uuid = _resolve_task_uuid(args)
    if not task_uuid:
        return _json({"ok": False, "error": "缺少 task_uuid/task_id/uuid"})
    state_raw = str(args.get("state", "")).strip()
    try:
        state = ScheduledTaskState(state_raw)
    except ValueError:
        return _json({"ok": False, "error": f"无效的 state: {state_raw}，可选 active/disabled"})
    try:
        async with self._uow_factory() as uow:
            record = await uow.scheduled_tasks.update(task_uuid, state=state)
        return _json({"ok": True, "status": "state_changed", "task": {
            "task_uuid": record.task_uuid,
            "state": record.state.value,
        }})
    except LookupError:
        return _json({"ok": False, "error": f"未找到任务: {task_uuid}"})
    except Exception as exc:
        return _json({"ok": False, "error": str(exc)})

async def _handle_set_scheduled_task_notification_policy(self: ReminderSkill, args: dict) -> str:
    if self._uow_factory is None:
        return _json({"ok": False, "error": "uow_factory 未配置"})
    task_uuid = _resolve_task_uuid(args)
    if not task_uuid:
        return _json({"ok": False, "error": "缺少 task_uuid/task_id/uuid"})
    one_shot = bool(args.get("one_shot_notification", True))
    try:
        async with self._uow_factory() as uow:
            record = await uow.scheduled_tasks.get(task_uuid)
            if record is None:
                return _json({"ok": False, "error": f"未找到任务: {task_uuid}"})
            if one_shot:
                await uow.scheduled_tasks.update(task_uuid, completed_window_keys=[])
            else:
                await uow.scheduled_tasks.update(task_uuid, completed_window_keys=[])
        return _json({"ok": True, "status": "policy_updated", "one_shot_notification": one_shot})
    except LookupError:
        return _json({"ok": False, "error": f"未找到任务: {task_uuid}"})
    except Exception as exc:
        return _json({"ok": False, "error": str(exc)})

async def _handle_delete_scheduled_task(self: ReminderSkill, args: dict) -> str:
    if self._uow_factory is None:
        return _json({"ok": False, "error": "uow_factory 未配置"})
    task_uuid = _resolve_task_uuid(args)
    if not task_uuid:
        return _json({"ok": False, "error": "缺少 task_uuid/task_id/uuid"})
    try:
        async with self._uow_factory() as uow:
            ok = await uow.scheduled_tasks.delete(task_uuid)
        if ok:
            return _json({"ok": True, "status": "deleted"})
        return _json({"ok": False, "error": f"未找到任务: {task_uuid}"})
    except Exception as exc:
        return _json({"ok": False, "error": str(exc)})

_HANDLERS = {
    "create_scheduled_task": _handle_create_scheduled_task,
    "list_scheduled_tasks": _handle_list_scheduled_tasks,
    "update_scheduled_task": _handle_update_scheduled_task,
    "set_scheduled_task_state": _handle_set_scheduled_task_state,
    "set_scheduled_task_notification_policy": _handle_set_scheduled_task_notification_policy,
    "delete_scheduled_task": _handle_delete_scheduled_task,
}
