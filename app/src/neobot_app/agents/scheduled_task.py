"""Scheduled task management agent and tools."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from neobot_chat import Agent
from neobot_chat.providers.base import Provider
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import (
    ChatChunk,
    State,
    ToolAccessPolicy,
    ToolAccessRule,
    ToolDefinition,
    ToolGuardContext,
)
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_contracts.models import ConversationRef
from neobot_contracts.models.scheduled_task import ScheduledTaskRecurrence, ScheduledTaskState
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.unit_of_work import UnitOfWorkFactory
from neobot_app.statistics.tracker import (
    CURRENT_CONVERSATION_ID,
    CURRENT_CONVERSATION_KIND,
    CURRENT_USAGE_MODULE,
    get_usage_tracker,
)
from neobot_app.time_context import combine_local, today_local, to_local

if TYPE_CHECKING:
    from neobot_app.config.schemas.bot import ScheduledTask as ScheduledTaskSchema


EXPOSED_TO_MAIN_AGENT_NAME = "scheduled_task"
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = (
    "定时任务管理。可创建、查询、修改、删除定时提醒任务，支持一次性、每日、每周、每月、每年重复，"
    "可绑定一个或多个聊天流；也提供生日专用记录工具。有人提出生日、生日祝福偏好、庆祝方式变更时应委托它先记录或更新。"
)
EXPOSED_TO_MAIN_AGENT_SHORT_DESCRIPTION = (
    "定时提醒与生日管理（一次性/重复/生日记录）"
)

_SCHEDULED_CONTEXT: ContextVar[str] = ContextVar("scheduled_task_context", default="")
_CONV_KIND: ContextVar[str] = ContextVar("scheduled_task_conv_kind", default="")
_CONV_ID: ContextVar[str] = ContextVar("scheduled_task_conv_id", default="")
BIRTHDAY_DEFAULT_START_TIME = time(6, 0)
BIRTHDAY_DEFAULT_END_TIME = time(22, 0)
BIRTHDAY_DEFAULT_CELEBRATION_STYLE = "按当前聊天语境自然、得体地送出生日祝福；后续如果用户补充偏好再更新任务。"


@dataclass(frozen=True)
class ScheduledTaskAgentConfig:
    max_repeating_tasks: int = 15
    default_window_seconds: int = 3600
    default_one_shot_notification: bool = True

    @classmethod
    def from_schema(cls, config: "ScheduledTaskSchema | None") -> "ScheduledTaskAgentConfig":
        if config is None:
            return cls()
        return cls(
            max_repeating_tasks=max(int(getattr(config, "max_repeating_tasks", 15) or 15), 0),
            default_window_seconds=max(int(getattr(config, "default_window_seconds", 3600) or 3600), 1),
            default_one_shot_notification=bool(
                getattr(config, "default_one_shot_notification", True)
            ),
        )


def _tool_def(name: str, description: str, parameters: dict[str, Any]) -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", **parameters},
        },
    }


def _default_resolver(
    args: dict[str, Any], context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    return ToolAccessRule(action="allow")


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _parse_conv_from_context(context: str) -> tuple[str, str]:
    m = re.search(r"\[当前会话\]\s*\nkind=(\w+)\s*\nid=(\S+)", context)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"\[褰撳墠浼氳瘽\]\s*\nkind=(\w+)\s*\nid=(\S+)", context)
    if m:
        return m.group(1), m.group(2)
    return "", ""


class ScheduledTaskToolExecutor(ToolExecutor):
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        config: ScheduledTaskAgentConfig | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._config = config or ScheduledTaskAgentConfig()
        self._logger = logger or NullLogger()

    def definitions(self) -> list[ToolDefinition]:
        binding_schema = {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["group", "private"]},
                "id": {"type": "string", "description": "群号或好友 QQ 号"},
            },
            "required": ["kind", "id"],
        }
        return [
            _tool_def(
                "create_scheduled_task",
                "创建定时任务。start_at/end_at 是首次有效时间窗口；重复任务会按相同窗口每日/每周/每月/每年重复。",
                {
                    "properties": {
                        "title": {"type": "string", "description": "任务标题"},
                        "detail": {"type": "string", "description": "提醒时传给主 Agent 的具体事项"},
                        "recurrence": {
                            "type": "string",
                            "enum": ["once", "daily", "weekly", "monthly", "yearly"],
                            "description": "持续方式：once 仅一次，daily 每日，weekly 每周，monthly 每月，yearly 每年",
                        },
                        "start_at": {
                            "type": "string",
                            "description": "ISO 时间，例如 2026-05-01T09:00:00+08:00",
                        },
                        "end_at": {
                            "type": "string",
                            "description": "ISO 时间，必须晚于 start_at",
                        },
                        "bindings": {
                            "type": "array",
                            "items": binding_schema,
                            "description": "绑定的聊天流列表；不填时使用当前聊天流",
                        },
                        "metadata": {"type": "object", "description": "可选结构化补充信息"},
                        "one_shot_notification": {
                            "type": "boolean",
                            "description": "一次性通知策略。true 表示每个触发窗口只通知一次并自动完成本窗口；false 表示持续通知直到主Agent标记完成。注意这不是 recurrence=once 的一次性任务。",
                        },
                    },
                    "required": ["title", "recurrence", "start_at", "end_at"],
                },
            ),
            _tool_def(
                "create_birthday_task",
                "生日专用工具。记录生日时必须准确包含：是谁的生日、在哪些私聊/群里给 ta 庆祝、对方希望的庆祝方式。"
                "生日会创建 yearly 定时任务。只要已知生日对象和日期，就先创建任务；缺少祝福时间时默认 06:00-22:00，"
                "缺少庆祝方式时使用自然得体祝福，后续问到更多信息再 update_scheduled_task。",
                {
                    "properties": {
                        "person_name": {"type": "string", "description": "生日对象的称呼或姓名"},
                        "birthday": {
                            "type": "string",
                            "description": "生日日期，格式 YYYY-MM-DD 或 MM-DD；不知道年份时用 MM-DD",
                        },
                        "bindings": {
                            "type": "array",
                            "items": binding_schema,
                            "description": "要在哪些聊天流庆祝，例如对方私聊、指定群聊；不填时使用当前聊天流",
                        },
                        "celebration_style": {
                            "type": "string",
                            "description": "对方希望的庆祝方式，例如温柔祝福、发图、提醒买礼物、在群里低调祝福等",
                        },
                        "relationship_context": {
                            "type": "string",
                            "description": "可选，生日对象与用户/Bot 的关系、称呼偏好、禁忌等",
                        },
                        "start_time": {
                            "type": "string",
                            "description": "可选，当天开始提醒时间 HH:MM，默认 06:00",
                        },
                        "end_time": {
                            "type": "string",
                            "description": "可选，当天结束提醒时间 HH:MM，默认 22:00",
                        },
                        "one_shot_notification": {
                            "type": "boolean",
                            "description": "一次性通知策略。生日祝福通常保持 true：每年生日窗口内只通知一次；只有明确要求持续催促时才设为 false。",
                        },
                    },
                    "required": ["person_name", "birthday"],
                },
            ),
            _tool_def(
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
            _tool_def(
                "update_scheduled_task",
                "修改定时任务。只传需要修改的字段。",
                {
                    "properties": {
                        "task_uuid": {"type": "string", "description": "任务 UUID"},
                        "task_id": {"type": "string", "description": "任务 UUID 的别名；用户说任务ID时可填这里"},
                        "uuid": {"type": "string", "description": "任务 UUID 的别名"},
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                        "recurrence": {"type": "string", "enum": ["once", "daily", "weekly", "monthly", "yearly"]},
                        "start_at": {"type": "string", "description": "ISO 时间"},
                        "end_at": {"type": "string", "description": "ISO 时间"},
                        "bindings": {"type": "array", "items": binding_schema},
                        "metadata": {"type": "object"},
                        "one_shot_notification": {
                            "type": "boolean",
                            "description": "修改一次性通知策略；true 为本循环窗口只通知一次，false 为持续通知。不要和 recurrence=once 混淆。",
                        },
                    },
                    "required": [],
                    "anyOf": [
                        {"required": ["task_uuid"]},
                        {"required": ["task_id"]},
                        {"required": ["uuid"]},
                    ],
                },
            ),
            _tool_def(
                "set_scheduled_task_state",
                "启用或禁用定时任务。",
                {
                    "properties": {
                        "task_uuid": {"type": "string"},
                        "task_id": {"type": "string", "description": "任务 UUID 的别名；用户说任务ID时可填这里"},
                        "uuid": {"type": "string", "description": "任务 UUID 的别名"},
                        "state": {"type": "string", "enum": ["active", "disabled"]},
                    },
                    "required": ["state"],
                    "anyOf": [
                        {"required": ["task_uuid"]},
                        {"required": ["task_id"]},
                        {"required": ["uuid"]},
                    ],
                },
            ),
            _tool_def(
                "set_scheduled_task_notification_policy",
                "单独设置定时任务的通知策略。一次性通知表示每个触发窗口只通知一次并自动完成本窗口；持续通知表示会在窗口内按冷却重复提醒，直到主Agent标记完成。注意这不是 once 一次性任务。",
                {
                    "properties": {
                        "task_uuid": {"type": "string"},
                        "task_id": {"type": "string", "description": "任务 UUID 的别名；用户说任务ID时可填这里"},
                        "uuid": {"type": "string", "description": "任务 UUID 的别名"},
                        "one_shot_notification": {
                            "type": "boolean",
                            "description": "true=一次性通知；false=持续通知",
                        },
                    },
                    "required": ["one_shot_notification"],
                    "anyOf": [
                        {"required": ["task_uuid"]},
                        {"required": ["task_id"]},
                        {"required": ["uuid"]},
                    ],
                },
            ),
            _tool_def(
                "delete_scheduled_task",
                "删除定时任务。删除后不会再提醒。",
                {
                    "properties": {
                        "task_uuid": {"type": "string"},
                        "task_id": {"type": "string", "description": "任务 UUID 的别名；用户说任务ID时可填这里"},
                        "uuid": {"type": "string", "description": "任务 UUID 的别名"},
                    },
                    "required": [],
                    "anyOf": [
                        {"required": ["task_uuid"]},
                        {"required": ["task_id"]},
                        {"required": ["uuid"]},
                    ],
                },
            ),
        ]

    async def execute(self, name: str, args: dict) -> str:
        if name == "create_scheduled_task":
            return await self._create_scheduled_task(args)
        if name == "create_birthday_task":
            return await self._create_birthday_task(args)
        if name == "list_scheduled_tasks":
            return await self._list_scheduled_tasks(args)
        if name == "update_scheduled_task":
            return await self._update_scheduled_task(args)
        if name == "set_scheduled_task_state":
            return await self._set_scheduled_task_state(args)
        if name == "set_scheduled_task_notification_policy":
            return await self._set_scheduled_task_notification_policy(args)
        if name == "delete_scheduled_task":
            return await self._delete_scheduled_task(args)
        return _json({"ok": False, "error": f"Unknown scheduled task tool: {name}"})

    async def _create_scheduled_task(self, args: dict) -> str:
        title = str(args.get("title") or "").strip()
        if not title:
            return _json({"ok": False, "error": "title 不能为空"})
        recurrence = _parse_recurrence(args.get("recurrence"))
        if recurrence is None:
            return _json({"ok": False, "error": "recurrence 无效"})
        start_at = _parse_datetime(args.get("start_at"))
        end_at = _parse_datetime(args.get("end_at"))
        if start_at is None or end_at is None or end_at <= start_at:
            return _json({"ok": False, "error": "start_at/end_at 无效，且 end_at 必须晚于 start_at"})
        bindings = _parse_bindings(args.get("bindings"), default_current=True)
        if not bindings:
            return _json({"ok": False, "error": "bindings 不能为空，且当前会话不可用"})
        limit_error = await self._check_repeating_limit(recurrence, existing_task_uuid=None)
        if limit_error:
            return _json(limit_error)
        async with self._uow_factory() as uow:
            task = await uow.scheduled_tasks.create(
                task_uuid=str(uuid4()),
                title=title,
                detail=str(args.get("detail") or "").strip(),
                recurrence=recurrence,
                start_at=start_at,
                end_at=end_at,
                bindings=bindings,
                metadata=self._metadata_with_notification_policy(
                    _parse_metadata(args.get("metadata")),
                    args,
                    default=self._config.default_one_shot_notification,
                ),
            )
            await uow.commit()
        return _json({"ok": True, "task": _task_payload(task)})

    async def _create_birthday_task(self, args: dict) -> str:
        person_name = str(args.get("person_name") or "").strip()
        raw_celebration_style = str(args.get("celebration_style") or "").strip()
        celebration_style = raw_celebration_style or BIRTHDAY_DEFAULT_CELEBRATION_STYLE
        if not person_name:
            return _json({"ok": False, "error": "person_name 不能为空"})
        birthday = _parse_birthday_date(str(args.get("birthday") or ""))
        if birthday is None:
            return _json({"ok": False, "error": "birthday 必须是 YYYY-MM-DD 或 MM-DD"})
        explicit_start = bool(str(args.get("start_time") or "").strip())
        explicit_end = bool(str(args.get("end_time") or "").strip())
        start_clock = _parse_clock(str(args.get("start_time") or "")) or BIRTHDAY_DEFAULT_START_TIME
        end_clock = _parse_clock(str(args.get("end_time") or "")) or BIRTHDAY_DEFAULT_END_TIME
        if end_clock <= start_clock:
            return _json({"ok": False, "error": "end_time 必须晚于 start_time"})
        today = today_local()
        start_date = date(today.year, birthday.month, birthday.day)
        start_at = combine_local(start_date, start_clock)
        end_at = combine_local(start_date, end_clock)
        bindings = _parse_bindings(args.get("bindings"), default_current=True)
        if not bindings:
            return _json({"ok": False, "error": "bindings 不能为空，且当前会话不可用"})
        defaulted_fields = []
        if not raw_celebration_style:
            defaulted_fields.append("celebration_style")
        if not explicit_start:
            defaulted_fields.append("start_time")
        if not explicit_end:
            defaulted_fields.append("end_time")
        limit_error = await self._check_repeating_limit(ScheduledTaskRecurrence.YEARLY, existing_task_uuid=None)
        if limit_error:
            return _json(limit_error)
        metadata = {
            "type": "birthday",
            "person_name": person_name,
            "birthday": str(args.get("birthday") or "").strip(),
            "celebration_style": celebration_style,
            "relationship_context": str(args.get("relationship_context") or "").strip(),
            "defaulted_fields": defaulted_fields,
            "needs_followup_update": bool(defaulted_fields),
            "one_shot_notification": _coerce_bool(
                args.get("one_shot_notification"),
                default=self._config.default_one_shot_notification,
            ),
            "birthday_recording_guidance": (
                "提醒时要明确这是谁的生日、在哪个绑定聊天流庆祝、按 celebration_style 执行；"
                "如果是私聊，直接给对方祝福；如果是群聊，按用户期望的方式在群里庆祝。"
            ),
        }
        async with self._uow_factory() as uow:
            task = await uow.scheduled_tasks.create(
                task_uuid=str(uuid4()),
                title=f"{person_name}的生日",
                detail=(
                    f"今天是{person_name}的生日。庆祝方式：{celebration_style}。"
                    f"{metadata['relationship_context']}"
                ).strip(),
                recurrence=ScheduledTaskRecurrence.YEARLY,
                start_at=start_at,
                end_at=end_at,
                bindings=bindings,
                metadata=metadata,
            )
            await uow.commit()
        return _json({"ok": True, "task": _task_payload(task)})

    async def _list_scheduled_tasks(self, args: dict) -> str:
        limit = _coerce_int(args.get("limit"), default=20, minimum=1, maximum=100)
        offset = _coerce_int(args.get("offset"), default=0, minimum=0, maximum=10000)
        include_disabled = bool(args.get("include_disabled"))
        async with self._uow_factory() as uow:
            tasks = await uow.scheduled_tasks.list(
                include_disabled=include_disabled,
                limit=limit,
                offset=offset,
            )
        return _json({"ok": True, "tasks": [_task_payload(task) for task in tasks]})

    async def _update_scheduled_task(self, args: dict) -> str:
        task_uuid = _parse_task_uuid_arg(args)
        if not task_uuid:
            return _json({"ok": False, "error": "task_uuid 不能为空"})
        recurrence = _parse_recurrence(args.get("recurrence")) if "recurrence" in args else None
        start_at = _parse_datetime(args.get("start_at")) if "start_at" in args else None
        end_at = _parse_datetime(args.get("end_at")) if "end_at" in args else None
        bindings = _parse_bindings(args.get("bindings"), default_current=False) if "bindings" in args else None
        metadata = _parse_metadata(args.get("metadata")) if "metadata" in args else None
        if "recurrence" in args and recurrence is None:
            return _json({"ok": False, "error": "recurrence 无效"})
        async with self._uow_factory() as uow:
            current = await uow.scheduled_tasks.get(task_uuid)
            if current is None:
                return _json({"ok": False, "error": "任务不存在", "task_uuid": task_uuid})
            next_recurrence = recurrence or current.recurrence
            if next_recurrence != ScheduledTaskRecurrence.ONCE and current.recurrence == ScheduledTaskRecurrence.ONCE:
                count = await uow.scheduled_tasks.count_repeating_active()
                if count >= self._config.max_repeating_tasks:
                    return _json({
                        "ok": False,
                        "error": "重复定时任务数量已达上限",
                        "limit": self._config.max_repeating_tasks,
                    })
            if "one_shot_notification" in args:
                metadata = self._metadata_with_notification_policy(
                    metadata if metadata is not None else current.metadata,
                    args,
                    default=bool(
                        current.metadata.get(
                            "one_shot_notification",
                            self._config.default_one_shot_notification,
                        )
                    ),
                )
            task = await uow.scheduled_tasks.update(
                task_uuid,
                title=str(args["title"]).strip() if "title" in args else None,
                detail=str(args["detail"]).strip() if "detail" in args else None,
                recurrence=recurrence,
                start_at=start_at,
                end_at=end_at,
                bindings=bindings,
                metadata=metadata,
            )
            if task.end_at <= task.start_at:
                await uow.rollback()
                return _json({"ok": False, "error": "end_at 必须晚于 start_at"})
            await uow.commit()
        return _json({"ok": True, "task": _task_payload(task)})

    async def _set_scheduled_task_state(self, args: dict) -> str:
        task_uuid = _parse_task_uuid_arg(args)
        state = str(args.get("state") or "").strip()
        if not task_uuid:
            return _json({"ok": False, "error": "task_uuid 不能为空"})
        try:
            parsed_state = ScheduledTaskState(state)
        except ValueError:
            return _json({"ok": False, "error": "state 无效"})
        async with self._uow_factory() as uow:
            try:
                task = await uow.scheduled_tasks.update(task_uuid, state=parsed_state)
            except LookupError:
                return _json({"ok": False, "error": "任务不存在", "task_uuid": task_uuid})
            await uow.commit()
        return _json({"ok": True, "task": _task_payload(task)})

    async def _set_scheduled_task_notification_policy(self, args: dict) -> str:
        task_uuid = _parse_task_uuid_arg(args)
        if not task_uuid:
            return _json({"ok": False, "error": "task_uuid 不能为空"})
        if "one_shot_notification" not in args:
            return _json({"ok": False, "error": "one_shot_notification 不能为空"})
        async with self._uow_factory() as uow:
            current = await uow.scheduled_tasks.get(task_uuid)
            if current is None:
                return _json({"ok": False, "error": "任务不存在", "task_uuid": task_uuid})
            metadata = self._metadata_with_notification_policy(
                current.metadata,
                args,
                default=bool(
                    current.metadata.get(
                        "one_shot_notification",
                        self._config.default_one_shot_notification,
                    )
                ),
            )
            task = await uow.scheduled_tasks.update(task_uuid, metadata=metadata)
            await uow.commit()
        return _json({"ok": True, "task": _task_payload(task)})

    async def _delete_scheduled_task(self, args: dict) -> str:
        task_uuid = _parse_task_uuid_arg(args)
        if not task_uuid:
            return _json({"ok": False, "error": "task_uuid 不能为空"})
        async with self._uow_factory() as uow:
            deleted = await uow.scheduled_tasks.delete(task_uuid)
            await uow.commit()
        return _json({"ok": deleted, "task_uuid": task_uuid})

    async def _check_repeating_limit(
        self,
        recurrence: ScheduledTaskRecurrence,
        *,
        existing_task_uuid: str | None,
    ) -> dict[str, Any] | None:
        if recurrence == ScheduledTaskRecurrence.ONCE:
            return None
        async with self._uow_factory() as uow:
            count = await uow.scheduled_tasks.count_repeating_active()
            if existing_task_uuid:
                current = await uow.scheduled_tasks.get(existing_task_uuid)
                if current is not None and current.recurrence != ScheduledTaskRecurrence.ONCE:
                    count = max(0, count - 1)
        if count >= self._config.max_repeating_tasks:
            return {
                "ok": False,
                "error": "重复定时任务数量已达上限",
                "limit": self._config.max_repeating_tasks,
                "active_repeating_tasks": count,
            }
        return None

    def _metadata_with_notification_policy(
        self,
        metadata: dict[str, Any] | None,
        args: dict[str, Any],
        *,
        default: bool,
    ) -> dict[str, Any]:
        result = dict(metadata or {})
        if "one_shot_notification" in args:
            result["one_shot_notification"] = _coerce_bool(
                args.get("one_shot_notification"),
                default=default,
            )
        else:
            result.setdefault("one_shot_notification", default)
        return result


class ScheduledTaskAgent:
    def __init__(
        self,
        provider: Provider,
        *,
        uow_factory: UnitOfWorkFactory,
        config: ScheduledTaskAgentConfig | ScheduledTaskSchema | None = None,
        logger: Logger | None = None,
        peer_descriptions: str = "",
    ) -> None:
        normalized = (
            config
            if isinstance(config, ScheduledTaskAgentConfig)
            else ScheduledTaskAgentConfig.from_schema(config)
        )
        self.description = EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        self._toolset = build_scheduled_task_toolset(
            uow_factory=uow_factory,
            config=normalized,
            logger=logger,
        )
        self.tool_definitions = self._toolset.definitions()

        async def _record_usage(model_name, input_tokens, output_tokens):
            await get_usage_tracker().record(
                module=CURRENT_USAGE_MODULE.get(""),
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                conversation_kind=CURRENT_CONVERSATION_KIND.get(""),
                conversation_id=CURRENT_CONVERSATION_ID.get(""),
            )

        self._agent = Agent(
            provider,
            toolset=self._toolset,
            description=self.description,
            system_prompt=_build_system_prompt(normalized, peer_descriptions=peer_descriptions),
            on_model_usage=_record_usage,
            logger=logger or NullLogger(),
        )

    async def invoke(self, state: State) -> State:
        delegate_context = str(state.get("_delegate_context") or "")
        kind, conv_id = _parse_conv_from_context(delegate_context)
        tk = _CONV_KIND.set(kind)
        ti = _CONV_ID.set(conv_id)
        tc = _SCHEDULED_CONTEXT.set(delegate_context)
        tm = CURRENT_USAGE_MODULE.set("agent:scheduled_task")
        try:
            return await self._agent.invoke(_inject_delegate_context(state, delegate_context))
        finally:
            _SCHEDULED_CONTEXT.reset(tc)
            _CONV_ID.reset(ti)
            _CONV_KIND.reset(tk)
            CURRENT_USAGE_MODULE.reset(tm)

    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]:
        delegate_context = str(state.get("_delegate_context") or "")
        kind, conv_id = _parse_conv_from_context(delegate_context)
        tk = _CONV_KIND.set(kind)
        ti = _CONV_ID.set(conv_id)
        tc = _SCHEDULED_CONTEXT.set(delegate_context)
        tm = CURRENT_USAGE_MODULE.set("agent:scheduled_task")
        try:
            async for chunk in self._agent.stream_invoke(_inject_delegate_context(state, delegate_context)):
                yield chunk
        finally:
            _SCHEDULED_CONTEXT.reset(tc)
            _CONV_ID.reset(ti)
            _CONV_KIND.reset(tk)
            CURRENT_USAGE_MODULE.reset(tm)

    async def close(self) -> None:
        await self._agent.close()


def build_scheduled_task_toolset(
    *,
    uow_factory: UnitOfWorkFactory,
    config: ScheduledTaskAgentConfig | None = None,
    logger: Logger | None = None,
    policy: ToolAccessPolicy | None = None,
) -> Toolset:
    executor = ScheduledTaskToolExecutor(
        uow_factory=uow_factory,
        config=config,
        logger=logger,
    )
    specs = [
        ToolSpec(definition=definition, access_resolver=_default_resolver)
        for definition in executor.definitions()
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())


def build_scheduled_task_agent(
    provider: Provider,
    *,
    uow_factory: UnitOfWorkFactory,
    config: ScheduledTaskAgentConfig | ScheduledTaskSchema | None = None,
    logger: Logger | None = None,
    peer_descriptions: str = "",
) -> ScheduledTaskAgent:
    return ScheduledTaskAgent(
        provider,
        uow_factory=uow_factory,
        config=config,
        logger=logger,
        peer_descriptions=peer_descriptions,
    )


def _build_system_prompt(config: ScheduledTaskAgentConfig, *, peer_descriptions: str = "") -> str:
    return (
        "你是定时任务管理 agent。只负责创建、查询、修改、删除定时任务，不负责实际聊天回复。\n"
        "创建任务前必须确认时间窗口：start_at 是提醒窗口开始，end_at 是窗口结束，end_at 必须晚于 start_at。\n"
        f"如果用户只给了触发时间、没有给结束时间，使用默认窗口 {config.default_window_seconds} 秒生成 end_at；不要只因为缺少结束时间而追问。\n"
        "重复方式：once 仅一次；daily 每日；weekly 每周；monthly 每月；yearly 每年。\n"
        "通知策略：one_shot_notification=true 表示「一次性通知」，即每个触发窗口只通知一次并自动完成本窗口；"
        "one_shot_notification=false 表示「持续通知」，会在窗口内按冷却反复提醒直到主Agent标记完成。"
        "注意「一次性通知」不是 recurrence=once 的「一次性任务」；daily/yearly 等循环任务也可以使用一次性通知。\n"
        f"新建任务默认 one_shot_notification={'true' if config.default_one_shot_notification else 'false'}。"
        "普通提醒、早安、生日祝福等通常应使用一次性通知；只有用户明确要求持续催促/反复提醒，才设置为持续通知。\n"
        "任务必须绑定至少一个聊天流。用户没有指定聊天流时，默认绑定当前聊天流；用户指定多个群/私聊时，全部写入 bindings。\n"
        "如果用户说「这个群」「私聊我」「当前群」等上下文指代，优先使用委托上下文里的当前会话 kind/id。\n"
        "不要为了检查重复任务数量上限而先调用 list_scheduled_tasks；create_scheduled_task/create_birthday_task 会在达到上限时返回错误。\n"
        f"重复任务上限为 {config.max_repeating_tasks} 个，达到上限错误时不要继续创建重复任务。\n"
        "生日信息必须使用 create_birthday_task，并准确记录：是谁的生日、在哪个私聊或群聊庆祝、对方希望的庆祝方式。\n"
        "生日任务必须先创建，防止后续问不到补充信息导致任务丢失；只要已知生日对象和日期，就调用 create_birthday_task。\n"
        "生日祝福时间默认从早上 06:00 到下午/晚上 22:00；用户未提供祝福方式、具体聊天流或其他细节时，先使用当前会话和保守默认值创建，"
        "如果之后问到了更准确的时间、聊天流、祝福方式、称呼偏好或禁忌，再用 update_scheduled_task 修改已有任务。\n"
        "如果用户提出某人生日想要的祝福、庆祝方式、祝福场合或禁忌发生变化，先 list_scheduled_tasks 查找对应生日任务；"
        "找到后使用 update_scheduled_task 更新 detail/metadata/bindings，不要重复创建。找不到时再创建新的生日任务。"
        f"{peer_descriptions}\n"
        "如果用户只想修改通知方式，优先使用 set_scheduled_task_notification_policy。"
    )


def _inject_delegate_context(state: State, delegate_context: str) -> State:
    if not delegate_context.strip():
        return state
    context_prompt = (
        "委托上下文如下。解析聊天流绑定、当前私聊/群聊、用户提到的「这里/当前群/私聊我」等指代时必须参考它：\n"
        f"{delegate_context.strip()}"
    )
    messages = list(state.get("messages", []))
    return {
        **state,
        "messages": [{"role": "system", "content": context_prompt}, *messages],
    }


def _parse_recurrence(value: Any) -> ScheduledTaskRecurrence | None:
    try:
        return ScheduledTaskRecurrence(str(value or "").strip())
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = to_local(parsed)
    return parsed


def _parse_bindings(value: Any, *, default_current: bool) -> tuple[ConversationRef, ...] | None:
    raw_items = value if isinstance(value, list) else []
    result: list[ConversationRef] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        conv_id = str(item.get("id") or "").strip()
        if kind in {"group", "private"} and conv_id:
            ref = ConversationRef(kind=kind, id=conv_id)
            if ref not in result:
                result.append(ref)
    if not result and default_current:
        kind = _CONV_KIND.get()
        conv_id = _CONV_ID.get()
        if kind in {"group", "private"} and conv_id:
            result.append(ConversationRef(kind=kind, id=conv_id))
    return tuple(result) if result else None


def _parse_metadata(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _parse_task_uuid_arg(args: dict[str, Any]) -> str:
    for key in ("task_uuid", "task_id", "uuid", "id"):
        value = str(args.get(key) or "").strip()
        if value:
            return value
    return ""


def _parse_birthday_date(value: str) -> date | None:
    value = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    if re.fullmatch(r"\d{2}-\d{2}", value):
        try:
            month, day = (int(part) for part in value.split("-"))
            return date(2000, month, day)
        except ValueError:
            return None
    return None


def _parse_clock(value: str) -> time | None:
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", value.strip())
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    return time(hour, minute)


def _coerce_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, minimum), maximum)


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().casefold()
    if text in {"true", "1", "yes", "on", "enabled", "enable"}:
        return True
    if text in {"false", "0", "no", "off", "disabled", "disable"}:
        return False
    return default


def _task_payload(task) -> dict[str, Any]:
    return {
        "task_uuid": task.task_uuid,
        "title": task.title,
        "detail": task.detail,
        "recurrence": task.recurrence.value,
        "start_at": task.start_at.isoformat(),
        "end_at": task.end_at.isoformat(),
        "bindings": [{"kind": item.kind, "id": str(item.id)} for item in task.bindings],
        "metadata": task.metadata,
        "completed_window_keys": list(task.completed_window_keys),
        "state": task.state.value,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "version": task.version,
    }
