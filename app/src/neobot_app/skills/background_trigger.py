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
            "后台推理 Skill 提供后台深度推理能力：\n\n"
            "## submit_problem\n"
            "提交复杂问题到后台进行深度推理解题。适用场景：\n"
            "  - 高难度数学证明与计算\n"
            "  - 复杂编程算法设计与实现\n"
            "  - 深度科学推理与计算\n"
            "  - 需要多步骤推演的逻辑问题\n"
            "  - 多网页信息收集与综合分析\n"
            "  - 文档编写与报告生成\n\n"
            "解题为后台任务，提交后立即返回 task_id，完成后会通过通知告知主Agent。\n"
            "解题完成后可将结果保存到沙箱并返回路径。\n"
            "返回内容不限于文本，可以是文件路径、图片路径等任意形式。\n\n"
            "## get_solution\n"
            "查询已完成的解题结果。\n\n"
            "## get_solver_status\n"
            "查询当前管线的解题状态。\n\n"
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
                        "pipeline_key": {
                            "type": "string",
                            "description": "可选，聊天流标识如 Group_12345。不传则由主 agent 自动填充",
                        },
                    },
                    "required": ["question"],
                },
            ),
            self._tool_def(
                "get_solution",
                "查询已完成的解题结果。返回解题结果（文本、文件路径、图片路径等）。",
                {
                    "properties": {
                        "task_id": {"type": "string", "description": "submit_problem 返回的任务 ID"},
                    },
                    "required": ["task_id"],
                },
            ),
            self._tool_def(
                "get_solver_status",
                "查询当前会话管线的解题状态（是否有活跃任务、近期完成的任务等）。",
                {
                    "properties": {
                        "pipeline_key": {"type": "string", "description": "可选，管线标识"},
                    },
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
        pipeline_key = str(args.get("pipeline_key", "")).strip() or "default"
        result = await self._manager.submit(
            pipeline_key=pipeline_key,
            conversation_kind=pipeline_key.split("_")[0] if "_" in pipeline_key else "",
            conversation_id=pipeline_key.split("_", 1)[1] if "_" in pipeline_key else "",
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
    return _json({"ok": True, "status": status})


_HANDLERS = {
    "submit_problem": _handle_submit_problem,
    "get_solution": _handle_get_solution,
    "get_solver_status": _handle_get_solver_status,
}
