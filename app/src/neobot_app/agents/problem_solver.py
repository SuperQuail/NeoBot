"""Problem Solver agent and background task manager.

Receives complex reasoning problems from the main agent, runs them as background
tasks, converts the solution to a Markdown image, and notifies the main agent.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import dataclass, field
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
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.statistics.tracker import (
    CURRENT_CONVERSATION_ID,
    CURRENT_CONVERSATION_KIND,
    CURRENT_USAGE_MODULE,
    get_usage_tracker,
)
from neobot_app.time_context import monotonic_seconds

if TYPE_CHECKING:
    pass

EXPOSED_TO_MAIN_AGENT_NAME = "problem_solver"
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = (
    "复杂问题解题。处理需要深度推理的数学、编程算法、科学计算、"
    "逻辑推理等问题。解题为后台任务，提交后立即返回状态，"
    "完成后会通过通知告知主Agent，届时主Agent可调用 send_long_reply 发送解题结果图片。"
    "涉及复杂推理问题时必须委托本 agent，不要自行处理。"
)

PEER_AGENT_DESCRIPTIONS = (
    "同级 sub agent 及其职责：\n"
    "- memory: 读写长期记忆档案、查询用户资料/好友备注/聊天记录、解析用户头像、调整好感度。\n"
    "- chat_interaction: 聊天互动、群管理、好友管理、发送表情包。\n"
    "- creator: 绘图与图片资产管理、图库管理、表情包管理。\n"
    "- image_parse: 按需求解析图片内容。\n"
    "- scheduled_task: 定时提醒、生日记录与祝福。\n"
    "- willingness: 调整回复意愿。\n"
    "如果收到的任务明显属于其他 agent 的职责，直接告知主Agent该委托给对应的 agent，不要越权处理。"
)

_SOLVER_CHAT_CONTEXT: ContextVar[str] = ContextVar("solver_chat_context", default="")
_SOLUTION_RESULT: ContextVar[str] = ContextVar("solution_result", default="")


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


class ProblemSolverAgentConfig:
    """解题 Agent 配置。"""

    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout_seconds: float = 600.0,
        max_tokens: int = 20480,
        notification_retry_seconds: int = 30,
        max_retries: int = 1,
        startup_grace_seconds: float = 3.0,
        max_tasks_per_pipeline: int = 5,
        reasoning_effort: str = "max",
    ) -> None:
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.notification_retry_seconds = notification_retry_seconds
        self.max_retries = max_retries
        self.startup_grace_seconds = startup_grace_seconds
        self.max_tasks_per_pipeline = max_tasks_per_pipeline
        self.reasoning_effort = reasoning_effort

    @classmethod
    def from_schema(cls, config: Any | None) -> "ProblemSolverAgentConfig":
        if config is None:
            return cls()
        return cls(
            enabled=bool(getattr(config, "enabled", True)),
            timeout_seconds=float(getattr(config, "timeout_seconds", 600) or 600),
            max_tokens=int(getattr(config, "max_tokens", 20480) or 20480),
            notification_retry_seconds=int(getattr(config, "notification_retry_seconds", 30) or 30),
            max_retries=int(getattr(config, "max_retries", 1) or 0),
            startup_grace_seconds=float(getattr(config, "startup_grace_seconds", 3.0) or 3.0),
            max_tasks_per_pipeline=int(getattr(config, "max_tasks_per_pipeline", 5) or 5),
            reasoning_effort=str(getattr(config, "reasoning_effort", "max") or "max"),
        )


@dataclass
class SolveTask:
    """后台解题任务记录。"""

    task_id: str
    pipeline_key: str
    conversation_kind: str
    conversation_id: str
    question: str
    delegate_context: str = ""
    status: str = "solving"  # solving | completed | failed | timeout
    markdown_solution: str | None = None
    image_path: str | None = None
    error: str | None = None
    notification_count: int = 0
    notified: bool = False
    created_at: float = field(default_factory=monotonic_seconds)


class ProblemSolverManager:
    """管理后台解题任务的提交、通知与重试。"""

    def __init__(
        self,
        *,
        config: ProblemSolverAgentConfig | None = None,
        logger: Logger | None = None,
        notification_hub: Any = None,
        markdown_image_converter: Any = None,
    ) -> None:
        self._config = config or ProblemSolverAgentConfig()
        self._logger = logger or NullLogger()
        self._notification_hub = notification_hub
        self._markdown_image_converter = markdown_image_converter
        self._tasks: dict[str, SolveTask] = {}
        self._notification_queues: dict[str, asyncio.Queue[str]] = {}
        self._orchestrator: Any = None
        self._agent: Any = None

    def set_agent(self, agent: Any) -> None:
        self._agent = agent

    def set_orchestrator(self, orchestrator: Any) -> None:
        self._orchestrator = orchestrator

    def set_markdown_converter(self, converter: Any) -> None:
        self._markdown_image_converter = converter

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
            t for t in self._tasks.values()
            if t.pipeline_key == pipeline_key
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
                recent.append({
                    "task_id": task.task_id,
                    "status": task.status,
                    "error": task.error,
                    "question": (task.question or "")[:100],
                    "created_at": task.created_at,
                })
        return {
            "solver_has_active_task": active is not None,
            "solver_active_task": {
                "task_id": active.task_id,
                "status": active.status,
            } if active else None,
            "solver_recent_tasks": recent[-5:],
        }

    async def submit(
        self,
        *,
        pipeline_key: str,
        conversation_kind: str,
        conversation_id: str,
        question: str,
        delegate_context: str = "",
    ) -> str:
        """提交后台解题任务。返回 JSON 状态字符串。"""
        if self._agent is None:
            return _json({"ok": False, "error": "解题 Agent 未配置"})

        active = self._get_active_task(pipeline_key)
        if active is not None:
            return _json({
                "ok": True,
                "status": "busy",
                "message": f"已有解题任务正在进行中 (task_id={active.task_id})，请等待任务完成后再提交",
                "existing_task_id": active.task_id,
            })

        task = SolveTask(
            task_id=f"solve_{uuid4().hex[:12]}",
            pipeline_key=pipeline_key,
            conversation_kind=conversation_kind,
            conversation_id=conversation_id,
            question=question,
            delegate_context=delegate_context,
        )
        self._tasks[task.task_id] = task
        self._enforce_task_limit(pipeline_key)

        bg = asyncio.create_task(self._run_solve(task))
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
        return _json({
            "ok": True,
            "status": "solving",
            "task_id": task.task_id,
            "message": "正在解题，已加入后台解题任务，完成后会通知你",
        })

    async def _run_solve(self, task: SolveTask) -> None:
        """后台执行解题。"""
        try:
            state: State = {
                "messages": [{"role": "user", "content": task.question}],
                "_delegate_context": task.delegate_context,
            }
            result_state = await asyncio.wait_for(
                self._agent.invoke(state),
                timeout=self._config.timeout_seconds,
            )

            solution = _SOLUTION_RESULT.get("")
            if not solution:
                # 尝试从结果消息中提取
                messages = result_state.get("messages", [])
                for msg in reversed(messages):
                    if msg.get("role") == "assistant" and msg.get("content"):
                        solution = str(msg["content"])
                        break

            if not solution:
                raise RuntimeError("解题 Agent 未提交解答内容")

            task.markdown_solution = solution
            task.status = "completed"

            if self._markdown_image_converter is not None:
                try:
                    image_path = await self._markdown_image_converter.convert(
                        solution,
                        filename=f"solve_{task.task_id}",
                    )
                    task.image_path = str(image_path)
                except Exception as exc:
                    self._logger.warning(
                        "解题结果 Markdown 转图片失败，仅保留文本",
                        task_id=task.task_id,
                        error=str(exc),
                    )

            self._logger.info(
                "后台解题任务完成",
                task_id=task.task_id,
                solution_length=len(solution),
                has_image=task.image_path is not None,
            )
            await self._on_completed(task)

        except asyncio.TimeoutError:
            task.status = "timeout"
            task.error = f"解题超时 ({self._config.timeout_seconds}s)"
            self._logger.warning("后台解题任务超时", task_id=task.task_id)
            await self._on_failed(task)
        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            self._logger.warning(
                "后台解题任务失败",
                task_id=task.task_id,
                error=str(exc),
            )
            await self._on_failed(task)

    async def _on_completed(self, task: SolveTask) -> None:
        question_preview = task.question[:200]
        image_info = (
            f"\n图片路径: {task.image_path}\n"
            f"解答已自动转为图片保存，你必须调用 send_long_reply 工具发送。"
            if task.image_path else
            f"\n注意：markdown 转图片失败，解答仅保留文本（{len(task.markdown_solution or '')} 字符）。"
        )
        notification = (
            "<这是新的必须要回答的内容>\n"
            f"解题任务完成通知\n\n"
            f"任务ID: {task.task_id}\n"
            f"原始问题: {question_preview}\n"
            f"解答Markdown长度: {len(task.markdown_solution or '')} 字符\n"
            f"{image_info}\n\n"
            "请立即将解答结果发送给用户。如果解答有图片，使用 send_long_reply 工具发送。\n"
            "注意：这不是一个新的解题请求，而是已完成的结果通知。\n"
            "</这是新的必须要回答的内容>"
        )
        self._logger.info(
            "推送解题完成通知",
            task_id=task.task_id,
            pipeline_key=task.pipeline_key,
        )
        await self._push_notification(task, notification)

    async def _on_failed(self, task: SolveTask) -> None:
        error_text = task.error or "未知错误"
        question_preview = task.question[:200]
        notification = (
            "<这是新的必须要回答的内容>\n"
            f"解题任务失败通知\n\n"
            f"任务ID: {task.task_id}\n"
            f"状态: {task.status}\n"
            f"错误原因: {error_text}\n"
            f"原始问题: {question_preview}\n\n"
            "你必须立即告知用户解题失败及其原因，询问是否重试或提供更多信息。\n"
            "</这是新的必须要回答的内容>"
        )
        self._logger.info(
            "推送解题失败通知",
            task_id=task.task_id,
            pipeline_key=task.pipeline_key,
            status=task.status,
        )
        await self._push_notification(task, notification)

    async def _push_notification(self, task: SolveTask, notification: str) -> None:
        if self._notification_hub is not None:
            started = await self._publish_hub_notification(task, notification)
            self._logger.info(
                "解题通知已交给统一通知中心",
                task_id=task.task_id,
                pipeline_key=task.pipeline_key,
                started_pipeline=started,
            )
            if not started and not task.notified and task.notification_count == 0:
                asyncio.create_task(self._retry_notification(task))
            return

        if self._orchestrator is None:
            self._logger.warning("通知推送失败：orchestrator 为空", task_id=task.task_id)
            return

        pipeline_active = self._orchestrator.is_pipeline_key_active(task.pipeline_key)
        if not pipeline_active:
            try:
                result = self._orchestrator.start_background_reply(
                    kind=task.conversation_kind,
                    conversation_id=task.conversation_id,
                    content=notification,
                )
                if result is not None:
                    task.notified = True
                    return
            except Exception as exc:
                self._logger.warning(
                    "启动后台回复管线失败",
                    task_id=task.task_id,
                    error=str(exc),
                )

        queue = self._notification_queues.setdefault(task.pipeline_key, asyncio.Queue())
        await queue.put(notification)

        if not task.notified and task.notification_count == 0:
            asyncio.create_task(self._retry_notification(task))

    async def _publish_hub_notification(
        self, task: SolveTask, notification: str
    ) -> bool:
        """通过 BackgroundNotificationHub 发布通知。返回是否启动了新管线。"""
        if self._notification_hub is None:
            return False

        def _on_consumed(n: Any) -> None:
            task.notified = True

        try:
            return await self._notification_hub.publish(
                source="problem_solver",
                kind=task.conversation_kind,
                conversation_id=task.conversation_id,
                content=notification,
                manager_name="problem_solver",
                reasons=["problem solving result"],
                metadata={
                    "task_id": task.task_id,
                    "status": task.status,
                },
                on_consumed=_on_consumed,
            )
        except Exception:
            return False

    async def _retry_notification(self, task: SolveTask) -> None:
        max_attempts = self._config.max_retries + 1
        while task.notification_count < max_attempts and not task.notified:
            await asyncio.sleep(self._config.notification_retry_seconds)
            if task.notified:
                break
            task.notification_count += 1
            if task.notified:
                break
            self._logger.info(
                "解题通知重试",
                task_id=task.task_id,
                attempt=task.notification_count,
                max_attempts=max_attempts,
            )
            notification_text = self._build_retry_content(task)
            if self._notification_hub is not None:
                await self._publish_hub_notification(task, notification_text)

    def _build_retry_content(self, task: SolveTask) -> str:
        if task.status == "completed":
            return (
                "<这是新的必须要回答的内容>\n"
                f"解题任务（{task.task_id}）已完成但未被消费，请检查并发送结果。\n"
                f"原始问题: {task.question[:200]}\n"
                "</这是新的必须要回答的内容>"
            )
        return (
            "<这是新的必须要回答的内容>\n"
            f"解题任务（{task.task_id}）已{task.status}但未被处理。\n"
            f"错误: {task.error}\n"
            "</这是新的必须要回答的内容>"
        )

    async def shutdown(self) -> None:
        for task in list(self._tasks.values()):
            if task.status == "solving":
                task.status = "failed"
                task.error = "系统关闭，任务被取消"
        self._tasks.clear()
        self._notification_queues.clear()


class ProblemSolverToolExecutor(ToolExecutor):
    """解题 Agent 的工具执行器。"""

    def __init__(
        self,
        *,
        logger: Logger | None = None,
    ) -> None:
        self._logger = logger or NullLogger()

    def definitions(self) -> list[ToolDefinition]:
        return [
            _tool_def(
                "get_chat_context",
                "读取主Agent本轮看到的聊天上下文和消息编号映射，"
                "用于理解问题背景和对话环境。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "submit_solution",
                "提交解题结果。将完整的解题过程以 Markdown 格式提交。"
                "支持代码块、表格、公式等标准 Markdown 语法。"
                "提交后解题任务视为完成。",
                {
                    "properties": {
                        "solution": {
                            "type": "string",
                            "description": "完整的解题过程，使用 Markdown 格式。",
                        },
                    },
                    "required": ["solution"],
                },
            ),
        ]

    async def execute(self, name: str, args: dict) -> str:
        if name == "get_chat_context":
            context = _SOLVER_CHAT_CONTEXT.get("")
            if not context:
                return "无聊天上下文可用（可能未通过主Agent委托调用）"
            return context
        if name == "submit_solution":
            solution = str(args.get("solution") or "").strip()
            if not solution:
                return "错误：solution 不能为空"
            _SOLUTION_RESULT.set(solution)
            return "解题结果已提交"
        return f"未知工具: {name}"


def _build_system_prompt(config: ProblemSolverAgentConfig | None) -> str:
    cfg = config or ProblemSolverAgentConfig()
    return (
        "你是解题 Agent，专门处理需要深度推理和复杂计算的数学、编程、逻辑、科学问题。\n"
        "收到问题后，请：\n"
        "1. 先用 get_chat_context 获取问题背景（如果问题来自聊天群/私聊）\n"
        "2. 仔细分析问题，逐步推理，不要跳步\n"
        "3. 给出完整、清晰的解答过程，使用 Markdown 格式\n"
        "4. 使用 submit_solution 工具提交最终解答\n\n"
        "交互规则：\n"
        "- 如果缺少关键信息无法解答，通过 submit_solution 返回说明，指出缺失什么信息\n"
        "- 如果问题不属于你的能力范围，直接声明无法处理\n\n"
        "格式要求：\n"
        "- 解答应包含完整的推理步骤，使用合适的 Markdown 格式（代码块、表格等）\n"
        "- 对于数学问题，使用标准的数学符号和步骤编号\n"
        "- 对于编程问题，提供可运行的代码及其解释\n"
        f"- 最终解答必须通过 submit_solution 提交，不要直接在对话中输出全部解答\n"
        f"- 超时时间: {cfg.timeout_seconds} 秒\n"
    )


def build_problem_solver_toolset(
    *,
    config: ProblemSolverAgentConfig | None = None,
    logger: Logger | None = None,
    policy: ToolAccessPolicy | None = None,
) -> Toolset:
    executor = ProblemSolverToolExecutor(logger=logger)
    specs = [
        ToolSpec(definition=d, access_resolver=_default_resolver)
        for d in executor.definitions()
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())


class ProblemSolverAgent:
    """LLM-backed agent dedicated to complex problem solving."""

    def __init__(
        self,
        provider: Provider,
        *,
        config: ProblemSolverAgentConfig | None = None,
        logger: Logger | None = None,
    ) -> None:
        cfg = config or ProblemSolverAgentConfig()
        self.description = EXPOSED_TO_MAIN_AGENT_DESCRIPTION
        self._toolset = build_problem_solver_toolset(config=cfg, logger=logger)
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
            system_prompt=_build_system_prompt(cfg),
            on_model_usage=_record_usage,
            max_iterations=20,
            command_timeout=cfg.timeout_seconds,
            logger=logger or NullLogger(),
        )

    async def invoke(self, state: State) -> State:
        token = _SOLVER_CHAT_CONTEXT.set(str(state.get("_delegate_context") or ""))
        token_m = CURRENT_USAGE_MODULE.set("agent:problem_solver")
        try:
            return await self._agent.invoke(state)
        finally:
            _SOLVER_CHAT_CONTEXT.reset(token)
            CURRENT_USAGE_MODULE.reset(token_m)

    async def stream_invoke(self, state: State) -> AsyncIterator[ChatChunk]:
        token = _SOLVER_CHAT_CONTEXT.set(str(state.get("_delegate_context") or ""))
        token_m = CURRENT_USAGE_MODULE.set("agent:problem_solver")
        try:
            async for chunk in self._agent.stream_invoke(state):
                yield chunk
        finally:
            _SOLVER_CHAT_CONTEXT.reset(token)
            CURRENT_USAGE_MODULE.reset(token_m)

    async def close(self) -> None:
        await self._agent.close()


def build_problem_solver_agent(
    provider: Provider,
    *,
    config: ProblemSolverAgentConfig | Any = None,
    logger: Logger | None = None,
    manager: ProblemSolverManager | None = None,
) -> ProblemSolverAgent:
    """构建解题 Agent 并关联到 Manager。"""
    cfg = (
        config if isinstance(config, ProblemSolverAgentConfig)
        else ProblemSolverAgentConfig.from_schema(config)
    )
    agent = ProblemSolverAgent(provider=provider, config=cfg, logger=logger)
    if manager is not None:
        manager.set_agent(agent)
    return agent
