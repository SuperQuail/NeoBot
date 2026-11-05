"""Reuse the bot's chat-bound administrator credential workflow."""
from __future__ import annotations

from typing import Any

from neobot_app.agent_tools.contracts import AgentToolError, ToolContext
from neobot_app.agent_tools.review import review_action


class ToolPermissions:
    def __init__(
        self,
        credential_manager: Any = None,
        *,
        reviewer: Any = None,
        auto_review: bool = True,
        review_timeout_seconds: float = 30.0,
        admin_self_authorize: bool = False,
        admin_self_authorize_chats: Any = None,
    ) -> None:
        self.manager = credential_manager
        self.reviewer = reviewer
        self.auto_review = bool(auto_review)
        self.review_timeout = max(1.0, float(review_timeout_seconds or 30.0))
        self.admin_self_authorize = bool(admin_self_authorize)
        self.admin_self_authorize_chats = frozenset(
            str(item) for item in (admin_self_authorize_chats or ()) if str(item).strip()
        )

    def _admin_self_authorized(self, context: ToolContext) -> bool:
        """管理员本人发起的请求视为已授权：不用再申请凭据或走自动审查。

        默认只信任「与超管的私聊」：私聊里只有他能发话，不存在别人插话
        搭同一条回复管线的问题；群聊要放行必须显式列入
        ``admin_self_authorize_chats``（受信群），并自行承担群成员在 wait
        期间插话也会搭上这条管线的风险。
        """
        if not self.admin_self_authorize or self.manager is None:
            return False
        flow = str(getattr(context, "chat_flow_id", "") or "")
        if not flow:
            return False
        if not flow.startswith("private:") and flow not in self.admin_self_authorize_chats:
            return False
        checker = getattr(self.manager, "is_super_admin", None)
        if not callable(checker):
            return False
        try:
            return bool(checker(getattr(context, "user_id", None)))
        except Exception:
            return False

    async def authorize(
        self,
        context: ToolContext,
        action: str,
        *,
        tool_name: str = "",
        arguments: dict[str, Any] | None = None,
    ) -> None:
        """自动审查优先；审查拒绝/不可用回退凭据；凭据=人工覆盖。"""
        if not isinstance(context, ToolContext):
            raise AgentToolError("CONTEXT_REQUIRED", "Trusted invocation context required")
        if self._admin_self_authorized(context):
            return
        if self.manager is not None and self.manager.consume(
            chat_flow=context.chat_flow_id, action=action, commit=True
        ) is not None:
            return
        if not self.auto_review or self.reviewer is None:
            self.require(context, action)
            return
        allowed, reason, code = await review_action(
            self.reviewer,
            action=action,
            tool_name=tool_name,
            params=arguments,
            timeout=self.review_timeout,
            domain="agent tool / host execution",
        )
        if allowed:
            return
        if code == "AUTO_REVIEW_UNAVAILABLE":
            self.require(context, action)
            return
        if self.manager is None:
            raise AgentToolError(
                "CREDENTIAL_UNAVAILABLE",
                f"动作 {action} 被自动审查拒绝（{reason}），当前没有管理员凭据可覆盖。",
                details={"action": action, "tool": tool_name, "safety": "review"},
            )
        raise AgentToolError(
            "AUTO_REVIEW_DENIED",
            f"动作 {action} 被自动审查拒绝：{reason}。若认为审查器误判，可申请管理员凭据覆盖："
            f"先调用 credential__request(action='{action}')，签发后重试。",
            details={
                "action": action,
                "tool": tool_name,
                "reason": reason,
                "request_tool": "credential__request",
                "request_args": {"action": action, "credential_type": "one_time"},
            },
        )

    def require(self, context: ToolContext, action: str) -> None:
        """Consume immediately before a sensitive operation; never grant from model text."""
        if not isinstance(context, ToolContext):
            raise AgentToolError("CONTEXT_REQUIRED", "Trusted invocation context required")
        if self._admin_self_authorized(context):
            return
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
