"""自修复 Agent 的常量、配置与任务记录。"""

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



EXPOSED_TO_MAIN_AGENT_NAME = "self_heal"
EXPOSED_TO_MAIN_AGENT_DESCRIPTION = (
    "系统自修复诊断。仅由系统在累积异常时自动唤起，不直接面向用户聊天。"
    "诊断 Bot 自身运行时异常、尝试安全修复、产出调试报告并通过通知系统告知管理员。"
)

# Source names used when publishing to BackgroundNotificationHub
START_SOURCE = "self_heal_start"
RESULT_SOURCE = "self_heal_result"

# Module-name prefix used by loguru sink for selfheal-internal loggers.
# The sink filters these out to avoid self-excitation loops.
LOGGER_PREFIX = "app.self_heal"

# ContextVar carrying the HealTask that the current LLM invocation belongs to,
# used by tool executor to read the error snapshot + chat_flow_id.
_HEAL_TASK: ContextVar["HealTask | None"] = ContextVar("self_heal_task", default=None)


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




class SelfHealAgentConfig:
    """自修复 Agent 的运行时配置（来自 BotConfig.agent.self_healing）。"""

    def __init__(
        self,
        *,
        enabled: bool = True,
        admin_account: str = "",
        traceback_threshold: int = 3,
        rate_threshold: int = 10,
        rate_window_seconds: int = 60,
        min_interval_seconds: int = 300,
        buffer_size: int = 200,
        daily_limit: int = 5,
        timeout_seconds: float = 300.0,
        max_tokens: int = 8192,
        reasoning_effort: str = "high",
        sandbox_debug_dir: str = "debug/self_heal",
    ) -> None:
        self.enabled = enabled
        self.admin_account = admin_account.strip() if admin_account else ""
        self.traceback_threshold = max(1, int(traceback_threshold))
        self.rate_threshold = max(1, int(rate_threshold))
        self.rate_window_seconds = max(1, int(rate_window_seconds))
        self.min_interval_seconds = max(0, int(min_interval_seconds))
        self.buffer_size = max(10, int(buffer_size))
        self.daily_limit = max(1, int(daily_limit))
        self.timeout_seconds = float(timeout_seconds)
        self.max_tokens = int(max_tokens)
        self.reasoning_effort = str(reasoning_effort)
        self.sandbox_debug_dir = (
            str(sandbox_debug_dir).strip().lstrip("/") or "debug/self_heal"
        )

    @classmethod
    def from_schema(cls, config: Any | None) -> "SelfHealAgentConfig":
        if config is None:
            return cls()
        admin = getattr(config, "admin_account", "") or ""
        return cls(
            enabled=bool(getattr(config, "enabled", True)),
            admin_account=str(admin),
            traceback_threshold=int(getattr(config, "traceback_threshold", 3) or 3),
            rate_threshold=int(getattr(config, "rate_threshold", 10) or 10),
            rate_window_seconds=int(getattr(config, "rate_window_seconds", 60) or 60),
            min_interval_seconds=int(
                getattr(config, "min_interval_seconds", 300) or 300
            ),
            buffer_size=int(getattr(config, "buffer_size", 200) or 200),
            daily_limit=int(getattr(config, "daily_limit", 5) or 5),
            timeout_seconds=float(getattr(config, "timeout_seconds", 300) or 300),
            max_tokens=int(getattr(config, "max_tokens", 8192) or 8192),
            reasoning_effort=str(getattr(config, "reasoning_effort", "high") or "high"),
            sandbox_debug_dir=str(
                getattr(config, "sandbox_debug_dir", "debug/self_heal")
                or "debug/self_heal"
            ),
        )


@dataclass
class HealTask:
    """一次正在进行的自修复调用记录。"""

    task_id: str
    admin_account: str
    trigger_reason: str
    error_snapshot: list[dict[str, Any]] = field(default_factory=list)
    first_error_time: str = ""
    last_error_time: str = ""
    status: str = "healing"  # healing | completed | failed | timeout
    summary: str | None = None
    root_cause: str | None = None
    debug_file: str | None = None
    repaired: bool = False
    notified_final: bool = False
    created_at: float = field(default_factory=monotonic_seconds)
