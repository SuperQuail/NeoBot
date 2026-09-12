"""Reuse the bot's chat-bound administrator credential workflow."""
from __future__ import annotations

from typing import Any

from neobot_app.agent_tools.contracts import AgentToolError, ToolContext


class ToolPermissions:
    def __init__(self, credential_manager: Any = None) -> None:
        self.manager = credential_manager

    def require(self, context: ToolContext, action: str) -> None:
        """Consume immediately before a sensitive operation; never grant from model text."""
        if not isinstance(context, ToolContext):
            raise AgentToolError("CONTEXT_REQUIRED", "Trusted invocation context required")
        if self.manager is not None and self.manager.consume(
            chat_flow=context.chat_flow_id, action=action, commit=True
        ) is not None:
            return
        details: dict[str, Any] = {
            "action": action, "request_tool": "credential__request",
            "request_args": {"action": action, "credential_type": "one_time"},
        }
        raise AgentToolError(
            "CREDENTIAL_REQUIRED",
            f"需要当前聊天的管理员凭据：先调用 credential__request(action='{action}')，"
            "由管理员发送返回的确认文本，签发后重试。凭据不等于操作系统沙箱。"
            "注意：拿到凭据之前重复调用本工具每次都会以同样的原因失败，不要重试；"
            "若只是读写文件，改用 sandbox_manager__* 工具。",
            details=details,
        )
