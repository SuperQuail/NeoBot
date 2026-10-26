"""任务注册、提交与状态查询。"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.agent_tools.contracts import ToolContext

from .models import (
    ProblemSolverAgentConfig,
    SolveTask,
    _MAX_AGENT_ITERATIONS,
    _MODE_NOTE_NATIVE,
    _MODE_NOTE_PTC,
    _json,
)


class ProblemSolverManagerCoreMixin:
    """任务注册、提交与状态查询。"""

    def __init__(
        self,
        *,
        config: ProblemSolverAgentConfig | None = None,
        logger: Logger | None = None,
        notification_hub: Any = None,
    ) -> None:
        self._config = config or ProblemSolverAgentConfig()
        self._logger = logger or NullLogger()
        self._notification_hub = notification_hub
        self._tasks: dict[str, SolveTask] = {}
        self._bg_tasks: set[asyncio.Task] = set()
        self._notification_queues: dict[str, asyncio.Queue[str]] = {}
        self._orchestrator: Any = None
        self._agent: Any = None
        self._tool_runtime: Any = None
        self._prompt_store: Any = None
        self._closed = False

    # ── 提示词规范化：实现 agent_prompt_parts() 即被分析页自动收集 ──

    agent_name = "解题 Agent"
    agent_note = "系统提示词 + 该 Agent 自带工具；peer 描述在运行时按需装配"

    def agent_prompt_parts(self) -> list[tuple[str, str, str]]:
        from neobot_app.agents.problem_solver import _build_system_prompt
        from neobot_app.analysis.prompt_analysis import tools_to_text

        prompt = _build_system_prompt(
            self._config,
            prompt_store=self._prompt_store,
            max_iterations=_MAX_AGENT_ITERATIONS,
            mode_note=(
                _MODE_NOTE_PTC
                if getattr(self._tool_runtime, "mode", "") == "ptc"
                else (_MODE_NOTE_NATIVE if self._tool_runtime is not None else "")
            ),
        )
        parts = [("系统提示词", "system", prompt)]
        agent = getattr(self, "_agent", None)
        definitions = list(getattr(agent, "tool_definitions", []) or []) if agent else []
        if definitions:
            parts.append(
                (f"工具定义（{len(definitions)} 个）", "tools", tools_to_text(definitions))
            )
        return parts

    def set_agent(self, agent: Any) -> None:
        self._agent = agent

    def set_prompt_store(self, prompt_store: Any) -> None:
        """提供提示词存储,使分析页展示与运行时同一份提示词。"""
        self._prompt_store = prompt_store

    def set_tool_runtime(self, runtime: Any) -> None:
        self._tool_runtime = runtime
        if self._agent is not None:
            self._agent.set_tool_runtime(runtime)

    def set_orchestrator(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator
        if self._notification_hub is not None:
            self._notification_hub.set_orchestrator(orchestrator)

    def set_notification_hub(self, hub: Any) -> None:
        self._notification_hub = hub

    def _spawn_bg_task(self, coro: Any) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    def _pipeline_key(self, kind: str, conv_id: str) -> str:
        return f"{kind}:{conv_id}"

    def _get_active_task(self, pipeline_key: str) -> SolveTask | None:
        for task in self._tasks.values():
            if task.pipeline_key == pipeline_key and task.status == "solving":
                return task
        return None

    def _enforce_task_limit(self, pipeline_key: str) -> None:
        limit = self._config.max_tasks_per_pipeline
        if limit <= 0:
            return
        pipeline_tasks = [
            t for t in self._tasks.values() if t.pipeline_key == pipeline_key
        ]
        if len(pipeline_tasks) <= limit:
            return
        pipeline_tasks.sort(key=lambda t: t.created_at)
        removed = 0
        for task in pipeline_tasks:
            if len(pipeline_tasks) - removed <= limit:
                break
            if task.status == "solving":
                continue
            self._tasks.pop(task.task_id, None)
            removed += 1
            self._logger.info(
                "后台解题任务超出上限已自动销毁",
                task_id=task.task_id,
                pipeline_key=pipeline_key,
                status=task.status,
                limit=limit,
            )

    def get_pipeline_status(self, pipeline_key: str) -> dict[str, Any]:
        active = self._get_active_task(pipeline_key)
        recent: list[dict[str, Any]] = []
        for task in self._tasks.values():
            if task.pipeline_key == pipeline_key and task.status != "solving":
                recent.append(
                    {
                        "task_id": task.task_id,
                        "status": task.status,
                        "error": task.error,
                        "question": (task.question or "")[:100],
                        "created_at": task.created_at,
                    }
                )
        return {
            "solver_has_active_task": active is not None,
            "solver_active_task": {
                "task_id": active.task_id,
                "status": active.status,
                "question": (active.question or "")[:200],
            }
            if active
            else None,
            "solver_recent_tasks": recent[-5:],
        }

    async def poll_notification(self, pipeline_key: str) -> str | None:
        """轮询本地通知队列（向后兼容；通知中心已接管时通常不使用）。"""
        queue = self._notification_queues.get(pipeline_key)
        if queue is None or queue.empty():
            return None
        try:
            return queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def submit(
        self,
        *,
        pipeline_key: str,
        conversation_kind: str,
        conversation_id: str,
        question: str,
        delegate_context: str = "",
        execution_context: ToolContext | None = None,
    ) -> str:
        """提交后台解题任务。返回 JSON 状态字符串。"""
        if self._tool_runtime is not None and not isinstance(execution_context, ToolContext):
            return _json({"ok": False, "code": "CONTEXT_REQUIRED", "error": "解题工具要求可信调用上下文"})
        if self._closed:
            return _json({"ok": False, "error": "解题管理器已关闭"})
        if self._agent is None:
            return _json({"ok": False, "error": "解题 Agent 未配置"})
        if not conversation_kind or not conversation_id:
            return _json(
                {
                    "ok": False,
                    "error": f"无效的会话信息: kind={conversation_kind!r}, id={conversation_id!r}",
                }
            )

        active = self._get_active_task(pipeline_key)
        if active is not None:
            return _json(
                {
                    "ok": True,
                    "status": "busy",
                    "message": f"已有解题任务正在进行中 (task_id={active.task_id})，请等待任务完成后再提交",
                    "existing_task_id": active.task_id,
                }
            )

        if pipeline_key != f"{conversation_kind}:{conversation_id}":
            return _json({"ok": False, "error": "会话身份与pipeline_key不一致"})
        if execution_context is not None and execution_context.chat_flow_id != pipeline_key:
            return _json({"ok": False, "error": "委派上下文不属于此聊天"})
        task = SolveTask(
            task_id=f"solve_{uuid4().hex[:12]}",
            pipeline_key=pipeline_key,
            conversation_kind=conversation_kind,
            conversation_id=conversation_id,
            question=question,
            delegate_context=delegate_context,
            execution_context=execution_context,
        )
        self._tasks[task.task_id] = task
        self._enforce_task_limit(pipeline_key)

        bg = self._spawn_bg_task(self._run_solve(task))
        bg.add_done_callback(lambda _: None)

        grace = self._config.startup_grace_seconds
        await asyncio.sleep(min(grace, 3.0))
        if task.status == "failed":
            return _json({"ok": False, "error": task.error or "解题任务启动失败"})

        self._logger.info(
            "后台解题任务已启动",
            task_id=task.task_id,
            pipeline_key=pipeline_key,
            question=question[:80],
        )
        return _json(
            {
                "ok": True,
                "status": "solving",
                "task_id": task.task_id,
                "message": "正在解题，已加入后台解题任务，完成后会通知你",
            }
        )

