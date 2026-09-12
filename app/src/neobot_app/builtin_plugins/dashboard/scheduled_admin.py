"""网页面板「定时任务」页的后端逻辑。

读:走 ScheduledTaskManager 的只读投影(含已停用任务、绑定列表、下次触发时间);
写:全部转发给 reminder skill —— 面板与主 Agent 因此共享同一套校验、
循环任务配额与创建锁,不存在第二套写路径。
"""

from __future__ import annotations

import json
from typing import Any

#: 提供定时任务 CRUD 的内置技能名
REMINDER_SKILL_NAME = "reminder"

#: 面板动作 -> reminder skill 工具名
ACTION_TOOL = {
    "create": "create_scheduled_task",
    "update": "update_scheduled_task",
    "set_state": "set_scheduled_task_state",
    "set_notification_policy": "set_scheduled_task_notification_policy",
    "delete": "delete_scheduled_task",
}

#: 面板请求里允许透传给 skill 的字段
ACTION_FIELDS = (
    "task_uuid",
    "title",
    "detail",
    "recurrence",
    "start_at",
    "end_at",
    "bindings",
    "metadata",
    "one_shot_notification",
    "state",
)


def find_reminder_skill(skill_manager: Any) -> Any | None:
    """从 SkillManager 里找出 reminder 技能实例;找不到返回 None。"""
    if skill_manager is None:
        return None
    lister = getattr(skill_manager, "all_skills", None)
    if not callable(lister):
        return None
    try:
        modules = lister()
    except Exception:
        return None
    for module in modules or []:
        if str(getattr(module, "name", "")) == REMINDER_SKILL_NAME:
            return module
    return None


def build_action_args(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    """把面板请求体裁剪成 skill 参数(未知字段直接丢弃)。"""
    args: dict[str, Any] = {}
    for field in ACTION_FIELDS:
        if field in payload and payload[field] is not None:
            args[field] = payload[field]
    if action == "set_state" and "state" not in args:
        raise ValueError("缺少 state(active/disabled)")
    if action == "set_notification_policy" and "one_shot_notification" not in args:
        raise ValueError("缺少 one_shot_notification")
    if action in {"update", "set_state", "set_notification_policy", "delete"}:
        if not str(args.get("task_uuid") or "").strip():
            raise ValueError("缺少 task_uuid")
    return args


async def execute_action(
    skill_manager: Any, action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """执行一次面板写操作,返回 skill 的 JSON 结果(已解析)。

    未配置技能/未知动作时抛 ValueError,由面板转成 400。
    """
    tool = ACTION_TOOL.get(str(action or "").strip())
    if tool is None:
        raise ValueError(f"未知操作: {action}")
    skill = find_reminder_skill(skill_manager)
    if skill is None:
        raise RuntimeError("reminder skill 未加载,无法管理定时任务")
    args = build_action_args(str(action).strip(), payload or {})
    raw = await skill.execute(tool, args)
    try:
        result = json.loads(raw)
    except (TypeError, ValueError):
        return {"ok": False, "error": str(raw)}
    return result if isinstance(result, dict) else {"ok": False, "error": "技能返回格式异常"}


async def read_managed_tasks(
    scheduled_task_manager: Any, *, include_disabled: bool = True, limit: int = 200
) -> dict[str, Any]:
    """读取定时任务列表;未配置管理器时返回 available=False。"""
    if scheduled_task_manager is None:
        return {"available": False, "tasks": [], "error": "定时任务管理器未启用"}
    reader = getattr(scheduled_task_manager, "list_managed_tasks", None)
    if not callable(reader):
        return {"available": False, "tasks": [], "error": "定时任务管理器不提供管理接口"}
    try:
        tasks = await reader(include_disabled=include_disabled, limit=limit)
    except Exception as exc:
        return {"available": True, "tasks": [], "error": str(exc)}
    return {"available": True, "tasks": list(tasks or []), "error": None}
