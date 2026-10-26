"""解题 Agent 的常量、上下文变量、配置与任务记录。"""

from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from neobot_chat.schema.types import (
    ToolAccessPolicy,
    ToolAccessRule,
    ToolDefinition,
    ToolGuardContext,
)

from neobot_app.time_context import monotonic_seconds
from neobot_app.agent_tools.contracts import ToolContext



_MAX_AGENT_ITERATIONS = 20

# 任务模式说明:绑定工具运行时后按模式写入 [problem_solver.runtime] 的 {mode_note}
_MODE_NOTE_PTC = (
    "当前任务模式为PTC，只能调用 run_code；业务 get_chat_context / submit_solution "
    "也在程序内调用。新版文件工具使用 read/write/edit/glob/grep，搜索使用 "
    "web_search/web_fetch，图片使用 read_image；旧同类别名不再提供。"
)
_MODE_NOTE_NATIVE = (
    "当前任务模式为普通模式，直接调用精简工具；复杂编排仅在PTC模式提供。"
    "新版文件工具使用 read/write/edit/glob/grep，搜索使用 web_search/web_fetch，"
    "图片使用 read_image；旧同类别名不再提供。"
)

EXPOSED_TO_MAIN_AGENT_NAME = "problem_solver"
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = (
    "复杂问题解题。仅在问题非常复杂、需要长时间深度推理时才使用本 agent。"
    "适用场景：高难度数学证明与计算、复杂编程算法设计与实现、"
    "深度科学推理与计算、需要多步骤推演的逻辑问题。"
    "解题为后台任务，提交后立即返回状态，"
    "完成后会通过通知将解答结果（文本/文件路径等）告知主Agent，由主Agent决定如何回复。"
    "注意：简单问答、常识性问题、日常聊天、普通信息查询/搜索等不应委托本 agent。"
    "简单搜索查询请使用联网搜索工具包(先 unlock web_search)自行完成。"
    "只有确认问题需要深度推理（非简单搜索能解决）时才使用本 agent。"
)
EXPOSED_TO_MAIN_AGENT_SHORT_DESCRIPTION = "复杂问题解题（数学/编程/科学推理），仅高难度深度推理时使用。简单搜索/信息查询请使用联网搜索工具包，不要委托本agent"


_SOLVER_CHAT_CONTEXT: ContextVar[str] = ContextVar("solver_chat_context", default="")
_SOLUTION_RESULT: ContextVar[str] = ContextVar("solution_result", default="")
_CHAT_FLOW_ID: ContextVar[str] = ContextVar("solver_chat_flow_id", default="")
_TOOL_CONTEXT: ContextVar[ToolContext | None] = ContextVar("solver_tool_context", default=None)


def _tool_def(
    name: str, description: str, parameters: dict[str, Any]
) -> ToolDefinition:
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
            notification_retry_seconds=int(
                getattr(config, "notification_retry_seconds", 30) or 30
            ),
            max_retries=int(getattr(config, "max_retries", 1) or 0),
            startup_grace_seconds=float(
                getattr(config, "startup_grace_seconds", 3.0) or 3.0
            ),
            max_tasks_per_pipeline=int(
                getattr(config, "max_tasks_per_pipeline", 5) or 5
            ),
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
    execution_context: ToolContext | None = None
    status: str = "solving"  # solving | completed | failed | timeout
    markdown_solution: str | None = None
    error: str | None = None
    notification_count: int = 0
    notified: bool = False
    created_at: float = field(default_factory=monotonic_seconds)
