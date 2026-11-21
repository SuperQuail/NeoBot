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

from neobot_app.prompt.assets import raw_text as _raw_text
from neobot_app.time_context import monotonic_seconds
from neobot_app.agent_tools.contracts import ToolContext



_MAX_AGENT_ITERATIONS = 20

# 提示词文本在 prompt/templates/prompts.toml（数据文件），这里只保留兼容导出名。
# 任务模式说明:绑定工具运行时后按模式写入 [problem_solver.runtime] 的 {mode_note}
_MODE_NOTE_PTC = _raw_text("problem_solver", "runtime.mode_note_ptc")
_MODE_NOTE_NATIVE = _raw_text("problem_solver", "runtime.mode_note_native")

EXPOSED_TO_MAIN_AGENT_NAME = "problem_solver"
# TOML 里 description 按行折行保存；导出常量沿用旧的单行拼接（逐字兼容）。
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = _raw_text("problem_solver", "description").replace("\n", "")
EXPOSED_TO_MAIN_AGENT_SHORT_DESCRIPTION = _raw_text("problem_solver", "short_description")


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
