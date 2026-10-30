"""ToolPermissions 自动审查：allow / deny / 凭据覆盖 / 回退。"""

from __future__ import annotations

import json

import pytest

from neobot_app.agent_tools.contracts import AgentToolError, ToolContext
from neobot_app.agent_tools.permissions import ToolPermissions


class _Credentials:
    def __init__(self, allowed: bool = False) -> None:
        self.allowed = allowed
        self.calls: list[tuple[str, str, bool]] = []

    def consume(self, *, chat_flow: str, action: str, commit: bool = True):
        self.calls.append((chat_flow, action, commit))
        return object() if self.allowed else None


class _Reviewer:
    def __init__(self, decision: str = "allow", *, error: Exception | None = None) -> None:
        self.decision = decision
        self.error = error
        self.calls: list[list[dict]] = []

    async def chat(self, messages: list[dict]) -> dict:
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return {"content": json.dumps({"decision": self.decision, "reason": "审查原因"}, ensure_ascii=False)}


def _context() -> ToolContext:
    return ToolContext(owner="owner", chat_flow_id="group:1")


@pytest.mark.asyncio
async def test_authorize_review_allow() -> None:
    credentials = _Credentials()
    reviewer = _Reviewer("allow")
    permissions = ToolPermissions(credentials, reviewer=reviewer)

    await permissions.authorize(
        _context(), "agent_execute", tool_name="run_code", arguments={"code": "print(1)"}
    )

    assert len(reviewer.calls) == 1
    assert credentials.calls == [("group:1", "agent_execute", True)]


@pytest.mark.asyncio
async def test_authorize_review_deny_offers_credential() -> None:
    reviewer = _Reviewer("deny")
    permissions = ToolPermissions(_Credentials(), reviewer=reviewer)

    with pytest.raises(AgentToolError) as exc:
        await permissions.authorize(_context(), "agent_execute", tool_name="run_code", arguments={})

    assert exc.value.code == "AUTO_REVIEW_DENIED"
    assert exc.value.details["request_tool"] == "credential__request"
    assert exc.value.details["request_args"]["action"] == "agent_execute"


@pytest.mark.asyncio
async def test_authorize_credential_override_skips_reviewer() -> None:
    reviewer = _Reviewer("deny")
    permissions = ToolPermissions(_Credentials(allowed=True), reviewer=reviewer)

    await permissions.authorize(_context(), "agent_execute", tool_name="run_code", arguments={})
    assert reviewer.calls == []


@pytest.mark.asyncio
async def test_authorize_reviewer_unavailable_falls_back_to_credentials() -> None:
    reviewer = _Reviewer(error=RuntimeError("provider down"))
    permissions = ToolPermissions(_Credentials(), reviewer=reviewer)

    with pytest.raises(AgentToolError) as exc:
        await permissions.authorize(_context(), "agent_shared_write", tool_name="write_file", arguments={})

    assert exc.value.code == "CREDENTIAL_REQUIRED"


@pytest.mark.asyncio
async def test_authorize_can_disable_auto_review() -> None:
    reviewer = _Reviewer("allow")
    permissions = ToolPermissions(_Credentials(), reviewer=reviewer, auto_review=False)

    with pytest.raises(AgentToolError) as exc:
        await permissions.authorize(_context(), "agent_execute", tool_name="run_code", arguments={})

    assert exc.value.code == "CREDENTIAL_REQUIRED"
    assert reviewer.calls == []


class _AdminCredentials(_Credentials):
    def __init__(self, admins: set[int]) -> None:
        super().__init__(False)
        self.admins = set(admins)

    def is_super_admin(self, user_id) -> bool:
        try:
            return int(user_id) in self.admins
        except (TypeError, ValueError):
            return False


def _admin_context(
    user_id: int = 2234503375, flow: str = "private:2234503375"
) -> ToolContext:
    return ToolContext(owner="owner", chat_flow_id=flow, user_id=user_id)


@pytest.mark.asyncio
async def test_admin_self_authorize_skips_review_and_credential() -> None:
    """与超管的私聊里，管理员本人请求视为已授权：不调审查器，也不要求凭据。"""
    credentials = _AdminCredentials({2234503375})
    reviewer = _Reviewer("deny")
    permissions = ToolPermissions(
        credentials, reviewer=reviewer, admin_self_authorize=True
    )

    await permissions.authorize(_admin_context(), "agent_execute", tool_name="bash", arguments={})
    permissions.require(_admin_context(), "agent_shared_write")

    assert reviewer.calls == []
    assert credentials.calls == []


@pytest.mark.asyncio
async def test_group_chat_needs_explicit_trusted_entry() -> None:
    """群聊默认不放行（防 wait 注入他人消息搭车），必须显式列入受信会话。"""
    credentials = _AdminCredentials({2234503375})
    reviewer = _Reviewer("allow")
    permissions = ToolPermissions(
        credentials, reviewer=reviewer, auto_review=False, admin_self_authorize=True
    )

    with pytest.raises(AgentToolError) as exc:
        await permissions.authorize(
            _admin_context(flow="group:451719631"), "agent_execute", tool_name="bash", arguments={}
        )

    assert exc.value.code == "CREDENTIAL_REQUIRED"
    assert reviewer.calls == []


@pytest.mark.asyncio
async def test_trusted_chat_allows_admin_in_group() -> None:
    """显式加入受信会话后，管理员在群聊里也免审批。"""
    reviewer = _Reviewer("deny")
    permissions = ToolPermissions(
        _AdminCredentials({2234503375}),
        reviewer=reviewer,
        admin_self_authorize=True,
        admin_self_authorize_chats=["group:451719631"],
    )

    await permissions.authorize(
        _admin_context(flow="group:451719631"), "agent_execute", tool_name="bash", arguments={}
    )

    assert reviewer.calls == []


@pytest.mark.asyncio
async def test_non_admin_still_requires_credential_when_self_authorize_enabled() -> None:
    """开关只对管理员生效：其他人发起的请求仍然要管理员签发凭据。"""
    credentials = _AdminCredentials({2234503375})
    reviewer = _Reviewer("allow")
    permissions = ToolPermissions(
        credentials, reviewer=reviewer, auto_review=False, admin_self_authorize=True
    )

    with pytest.raises(AgentToolError) as exc:
        await permissions.authorize(
            _admin_context(user_id=1111111111, flow="private:1111111111"),
            "agent_execute",
            tool_name="bash",
            arguments={},
        )

    assert exc.value.code == "CREDENTIAL_REQUIRED"
    assert reviewer.calls == []


@pytest.mark.asyncio
async def test_admin_self_authorize_is_opt_in() -> None:
    """默认关闭：即使发起人是管理员，也照旧走审查/凭据。"""
    reviewer = _Reviewer("deny")
    permissions = ToolPermissions(
        _AdminCredentials({2234503375}), reviewer=reviewer
    )

    with pytest.raises(AgentToolError) as exc:
        await permissions.authorize(_admin_context(), "agent_execute", tool_name="bash", arguments={})

    assert exc.value.code == "AUTO_REVIEW_DENIED"
    assert len(reviewer.calls) == 1


class _Perms:
    def __init__(self, admins: set[int]) -> None:
        self.admins = set(admins)

    def is_super_admin(self, user_id) -> bool:
        return int(user_id) in self.admins


def test_credential_manager_is_super_admin_guards() -> None:
    """None / 空串 / 0 这类内部身份不能误判成管理员。"""
    from neobot_app.credentials.service import CredentialManager

    manager = CredentialManager(permissions=_Perms({2234503375}))

    assert manager.is_super_admin(2234503375)
    assert manager.is_super_admin("2234503375")
    assert manager.is_super_admin(1111111111) is False
    assert manager.is_super_admin(None) is False
    assert manager.is_super_admin("") is False
    assert manager.is_super_admin(0) is False
