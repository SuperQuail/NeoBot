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
            "后台任务 Skill — 这是你生成文件、运行代码、深度推理的唯一途径。\n\n"
            "=== 必须使用本 skill 的场景 ===\n"
            "以下任何场景都必须通过 submit_problem 提交，你自身没有能力完成：\n"
            "  文件生成：PDF、图片、Word/Excel/PPT、图表、代码文件、数据报表等一切文件\n"
            "  代码执行：任何需要运行 Python/Shell 的操作（计算、绘图、数据处理、格式转换）\n"
            "  深度推理：复杂数学、多步逻辑推演、多网页综合调研\n"
            "  网页搜索：需要联网获取实时信息的任务\n\n"
            "=== 文件生成的标准流程 ===\n"
            "用户要文件 → submit_problem(question=\"生成xxx文件，格式为...，内容包含...\")\n"
            "           → 返回 task_id，立即结束本轮回复（告知用户稍候）\n"
            "           → 收到后台通知（含文件路径）\n"
            "           → sandbox_manager__send_chat_file 或 send_file 发送给用户\n\n"
            "=== 提交后的行为规范 ===\n"
            "1. 立即用 send_reply 告知用户「已提交后台任务，请稍候」，然后结束\n"
            "2. 禁止轮询 get_solver_status 或 get_solution\n"
            "3. 禁止使用 wait 等待结果\n"
            "4. 系统会在任务完成后通过通知自动唤醒你，届时携带结果\n\n"
            "=== 工具说明 ===\n"
            "submit_problem(question, context) — 提交任务。question 写清楚要什么文件/什么格式/什么内容\n"
            "get_solution(task_id) — 仅在收到完成通知后调用，获取结果\n"
            "get_solver_status() — 仅在需要判断是否提交新任务时调用\n\n"
            "注意：简单问答、日常聊天、已知信息的查询不应使用本 skill。"
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
                "【生成文件/运行代码/深度推理的唯一途径】"
                "将任务提交到后台 Agent 执行。后台 Agent 可以运行 Python 代码生成 PDF、图片、"
                "Word/Excel/PPT、图表、代码文件等任意文件，也可以进行复杂计算、网页搜索、数据分析。"
                "这是你唯一能完成文件生成和代码执行的方式——不要用 sandbox_manager__write_file 或 write_file_base64 替代。"
                "提交后立即结束本轮回复，等待系统通知唤醒。"
                "完成后用 sandbox_manager__send_chat_file 将生成的文件发送到聊天。"
                "适用：生成任何文件、复杂计算、数据分析、多步推理、网页调研。",
                {
                    "properties": {
                        "question": {"type": "string", "description": "任务描述。如果是文件生成，请明确说明文件格式、内容和要求。"},
                        "context": {
                            "type": "string",
                            "description": "可选，补充上下文信息（聊天记录摘要、相关数据、格式要求等）",
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
        parts = pipeline_key.split(":", 1)
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
