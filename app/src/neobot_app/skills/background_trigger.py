"""BackgroundTriggerSkill — 后台问题求解触发（problem_solver）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class BackgroundTriggerSkill(SkillModule):
    """后台问题求解 Skill — 提交深度推理任务，查询状态与结果。"""

    @property
    def name(self) -> str:
        return "background_trigger"

    @property
    def description(self) -> str:
        return "后台深度推理：提交复杂问题（数学/编程/科学）到后台 agent 进行深度推理"

    @property
    def instructions(self) -> str:
        return (
            "后台推理 Skill 提供后台深度推理能力。\n\n"
            "## 重要: 提交问题后的行为规范\n"
            "调用 submit_problem 提交后台任务后，你必须：\n"
            "  1. 立即结束本轮回复（使用 send_reply 告知用户「已提交解题任务，请稍候」或 cancel）\n"
            "  2. 不要轮询 get_solver_status 或 get_solution\n"
            "  3. 不要使用 wait 等待\n"
            "  4. 系统会在解题完成后通过通知自动唤醒你，届时携带结果\n\n"
            "## submit_problem\n"
            "提交复杂问题到后台进行深度推理解题。适用场景：\n"
            "  - 高难度数学证明与计算\n"
            "  - 复杂编程算法设计与实现\n"
            "  - 深度科学推理与计算\n"
            "  - 需要多步骤推演的逻辑问题\n"
            "  - 多网页信息收集与综合分析\n"
            "  - 文档编写与报告生成\n\n"
            "提交后立即返回 task_id。解题完成后系统将通过后台通知携带结果唤醒你。\n"
            "解题完成后可将结果保存到沙箱并返回路径。\n"
            "返回内容不限于文本，可以是文件路径、图片路径等任意形式。\n\n"
            "## get_solution\n"
            "查询已完成的解题结果。仅在收到解题完成通知后调用。\n\n"
            "## get_solver_status\n"
            "查询当前管线的解题状态。仅在需要决策是否提交新问题时调用。\n"
            "有活跃任务时请勿轮询，等待通知即可。\n\n"
            "注意：简单问答、常识性问题、日常聊天、普通信息查询不应使用本 skill。"
        )

    def __init__(self, manager: Any = None, config: Any = None) -> None:
        self._manager = manager
        self._config = config

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "submit_problem",
                "提交复杂问题到后台进行深度推理解题。提交后立即返回，完成后会通知主Agent。"
                "仅在问题非常复杂、需要长时间深度推理时才使用。",
                {
                    "properties": {
                        "question": {"type": "string", "description": "需要深度推理的复杂问题描述"},
                        "context": {
                            "type": "string",
                            "description": "可选，补充上下文信息，如已知条件、相关代码等",
                        },
                    },
                    "required": ["question"],
                },
            ),
            self._tool_def(
                "get_solution",
                "查询已完成的解题结果。返回解题结果（文本、文件路径、图片路径等）。"
                "【注意】仅在收到解题完成通知后调用，不要在解题进行中轮询此工具。",
                {
                    "properties": {
                        "task_id": {"type": "string", "description": "submit_problem 返回的任务 ID"},
                    },
                    "required": ["task_id"],
                },
            ),
            self._tool_def(
                "get_solver_status",
                "查询当前会话管线的解题状态（是否有活跃任务、近期完成的任务等）。"
                "【注意】有活跃任务时请勿轮询，等待通知即可。仅在需要决策是否提交新问题时查询。",
                {
                    "properties": {},
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown background_trigger tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_submit_problem(self: BackgroundTriggerSkill, args: dict) -> str:
    if self._manager is None:
        return _json({"ok": False, "error": "solver_manager 未配置"})
    question = str(args.get("question", "")).strip()
    if not question:
        return _json({"ok": False, "error": "question 不能为空"})
    try:
        pipeline_key = str(args.get("pipeline_key", "")).strip()
        parts = pipeline_key.split("_", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return _json({"ok": False, "error": f"无效的 pipeline_key: {pipeline_key}（缺少聊天流信息）"})
        conversation_kind, conversation_id = parts
        result = await self._manager.submit(
            pipeline_key=pipeline_key,
            conversation_kind=conversation_kind,
            conversation_id=conversation_id,
            question=question,
            delegate_context=str(args.get("context", "")),
        )
        return result
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_get_solution(self: BackgroundTriggerSkill, args: dict) -> str:
    if self._manager is None:
        return _json({"ok": False, "error": "solver_manager 未配置"})
    task_id = str(args.get("task_id", "")).strip()
    task = getattr(self._manager, "_tasks", {}).get(task_id) if hasattr(self._manager, "_tasks") else None
    if task is None:
        return _json({"ok": False, "error": f"任务不存在: {task_id}"})
    return _json({
        "ok": True,
        "task_id": task_id,
        "status": task.status,
        "result": getattr(task, "result", None),
        "error": getattr(task, "error", None),
    })

async def _handle_get_solver_status(self: BackgroundTriggerSkill, args: dict) -> str:
    if self._manager is None:
        return _json({"ok": False, "error": "solver_manager 未配置"})
    pipeline_key = args.get("pipeline_key", "")
    status = self._manager.get_pipeline_status(pipeline_key) if pipeline_key else {}
    result: dict[str, Any] = {"ok": True, "status": status}
    if status.get("solver_has_active_task"):
        result["_hint"] = "【有活跃任务进行中，请结束本轮回复等待通知，无需轮询】"
    return _json(result)


_HANDLERS = {
    "submit_problem": _handle_submit_problem,
    "get_solution": _handle_get_solution,
    "get_solver_status": _handle_get_solver_status,
}
