"""凭据管理器与凭据 Skill 单元测试。"""

from __future__ import annotations

import json
from types import SimpleNamespace


from neobot_app.commands.model import PERM_SUPER_ADMIN
from neobot_app.commands.permissions import PermissionManager
from neobot_app.credentials.model import (
    CRED_STATUS_ACTIVE,
    CRED_STATUS_PENDING,
    CRED_STATUS_USED,
    CRED_TYPE_ONE_TIME,
    CRED_TYPE_TIMED,
)
from neobot_app.credentials.service import CredentialManager
from neobot_app.skills.credential_skill import CredentialSkill
from neobot_app.skills.group_management import GroupManagementSkill

BOT = 88888
SUPER = 10000
SUB = 30000
NORMAL = 99999


def _permissions() -> PermissionManager:
    chat = SimpleNamespace(admin_accounts=[SUPER], sub_admin_accounts=[SUB])
    bot = SimpleNamespace(account=BOT)
    return PermissionManager(SimpleNamespace(chat=chat, bot=bot))


def _manager() -> CredentialManager:
    return CredentialManager(_permissions())


# ── 创建 ──


def test_create_one_time_credential() -> None:
    manager = _manager()
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=BOT,
        cred_type=CRED_TYPE_ONE_TIME,
    )
    assert credential.status == CRED_STATUS_PENDING
    assert credential.code and len(credential.code) == 6
    assert credential.action == "kick"
    assert credential.cred_type == CRED_TYPE_ONE_TIME
    assert credential.required_level == PERM_SUPER_ADMIN  # kick 需超管


def test_create_reuses_pending_credential() -> None:
    manager = _manager()
    first = manager.create(
        chat_flow="group:123", action="kick", requester_id=BOT, cred_type=CRED_TYPE_ONE_TIME
    )
    second = manager.create(
        chat_flow="group:123", action="kick", requester_id=BOT, cred_type=CRED_TYPE_ONE_TIME
    )
    assert first.code == second.code  # 同会话同动作复用


def test_create_duration_clamped() -> None:
    manager = _manager()
    credential = manager.create(
        chat_flow="group:1", action="kick", requester_id=BOT,
        cred_type=CRED_TYPE_TIMED, duration_minutes=999,
    )
    assert credential.duration_minutes == 30  # 钳制到最长
    credential2 = manager.create(
        chat_flow="group:2", action="kick", requester_id=BOT,
        cred_type=CRED_TYPE_TIMED, duration_minutes=0,
    )
    assert credential2.duration_minutes == 1  # 至少 1 分钟
    credential3 = manager.create(
        chat_flow="group:3", action="kick", requester_id=BOT,
        cred_type=CRED_TYPE_TIMED,
    )
    assert credential3.duration_minutes == 5  # 默认 5 分钟


# ── 签发 ──


def test_issue_by_super_admin() -> None:
    manager = _manager()
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=BOT, cred_type=CRED_TYPE_ONE_TIME
    )
    result = manager.try_issue(chat_flow="group:123", code=credential.code, issuer_id=SUPER)
    assert result.ok
    assert credential.status == CRED_STATUS_ACTIVE
    assert credential.issuer_id == SUPER
    # timed 凭据设置过期时间
    manager2 = _manager()
    timed = manager2.create(
        chat_flow="group:9", action="kick", requester_id=BOT, cred_type=CRED_TYPE_TIMED
    )
    manager2.try_issue(chat_flow="group:9", code=timed.code, issuer_id=SUPER)
    assert timed.expires_at is not None


def test_issue_denied_for_normal_user() -> None:
    manager = _manager()
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=BOT, cred_type=CRED_TYPE_ONE_TIME
    )
    result = manager.try_issue(chat_flow="group:123", code=credential.code, issuer_id=NORMAL)
    assert not result.ok
    assert result.error == "permission_denied"
    assert credential.status == CRED_STATUS_PENDING


def test_issue_denied_for_sub_admin_on_super_action() -> None:
    manager = _manager()
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=BOT, cred_type=CRED_TYPE_ONE_TIME
    )
    result = manager.try_issue(chat_flow="group:123", code=credential.code, issuer_id=SUB)
    assert not result.ok
    assert result.error == "permission_denied"


def test_issue_wrong_chat_flow() -> None:
    manager = _manager()
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=BOT, cred_type=CRED_TYPE_ONE_TIME
    )
    result = manager.try_issue(chat_flow="group:999", code=credential.code, issuer_id=SUPER)
    assert not result.ok
    assert result.error == "not_found"


def test_issue_idempotent() -> None:
    manager = _manager()
    credential = manager.create(
        chat_flow="group:1", action="kick", requester_id=BOT, cred_type=CRED_TYPE_ONE_TIME
    )
    assert manager.try_issue(chat_flow="group:1", code=credential.code, issuer_id=SUPER).ok
    assert manager.try_issue(chat_flow="group:1", code=credential.code, issuer_id=SUPER).ok


# ── 消费 ──


def test_consume_one_time() -> None:
    manager = _manager()
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=BOT, cred_type=CRED_TYPE_ONE_TIME
    )
    manager.try_issue(chat_flow="group:123", code=credential.code, issuer_id=SUPER)
    consumed = manager.consume(chat_flow="group:123", action="kick")
    assert consumed is not None
    assert credential.status == CRED_STATUS_USED
    # 二次消费失败
    assert manager.consume(chat_flow="group:123", action="kick") is None


def test_consume_timed_multiple_times() -> None:
    manager = _manager()
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=BOT, cred_type=CRED_TYPE_TIMED
    )
    manager.try_issue(chat_flow="group:123", code=credential.code, issuer_id=SUPER)
    assert manager.consume(chat_flow="group:123", action="kick") is not None
    assert manager.consume(chat_flow="group:123", action="kick") is not None  # timed 不消费
    assert credential.status == CRED_STATUS_ACTIVE


def test_consume_requires_matching_action_and_flow() -> None:
    manager = _manager()
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=BOT, cred_type=CRED_TYPE_ONE_TIME
    )
    manager.try_issue(chat_flow="group:123", code=credential.code, issuer_id=SUPER)
    assert manager.consume(chat_flow="group:123", action="quit_group") is None
    assert manager.consume(chat_flow="group:999", action="kick") is None


def test_consume_none_without_credential() -> None:
    manager = _manager()
    assert manager.consume(chat_flow="group:123", action="kick") is None


# ── 过期清理 ──


def test_timed_expires() -> None:
    manager = _manager()
    credential = manager.create(
        chat_flow="group:1", action="kick", requester_id=BOT, cred_type=CRED_TYPE_TIMED
    )
    manager.try_issue(chat_flow="group:1", code=credential.code, issuer_id=SUPER)
    # 模拟过期
    credential.expires_at = 0
    assert credential.is_expired()
    assert manager.consume(chat_flow="group:1", action="kick") is None


def test_cleanup_removes_stale() -> None:
    manager = _manager()
    used = manager.create(
        chat_flow="group:1", action="kick", requester_id=BOT, cred_type=CRED_TYPE_ONE_TIME
    )
    manager.try_issue(chat_flow="group:1", code=used.code, issuer_id=SUPER)
    manager.consume(chat_flow="group:1", action="kick")
    removed = manager.cleanup()
    assert removed >= 1
    assert manager.get(used.code) is None


# ── 凭据 Skill ──


def _skill(manager: CredentialManager) -> CredentialSkill:
    return CredentialSkill(credential_manager=manager)


async def test_skill_request_generates_code() -> None:
    manager = _manager()
    skill = _skill(manager)
    result = json.loads(await skill.execute(
        "request",
        {"action": "kick", "pipeline_key": "group:123", "user_id": BOT},
    ))
    assert result["ok"] is True
    assert result["code"]
    assert "发送" in result["message"]


async def test_skill_request_requires_pipeline() -> None:
    skill = _skill(_manager())
    result = json.loads(await skill.execute("request", {"action": "kick"}))
    assert result["ok"] is False
    assert "pipeline_key" in result["error"]


async def test_skill_check_lists_credentials() -> None:
    manager = _manager()
    manager.create(
        chat_flow="group:123", action="kick", requester_id=BOT, cred_type=CRED_TYPE_ONE_TIME
    )
    skill = _skill(manager)
    result = json.loads(await skill.execute("check", {"pipeline_key": "group:123"}))
    assert result["ok"] is True
    assert len(result["items"]) == 1


# ── 群管理接入 ──


class _FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def call_api(self, api: str, params: dict) -> str:
        self.calls.append((api, params))
        return f"ok:{api}"


async def test_kick_without_credential_rejected() -> None:
    manager = _manager()
    adapter = _FakeAdapter()
    skill = GroupManagementSkill(adapter=adapter, credential_manager=manager)
    result = json.loads(await skill.execute(
        "manage_group",
        {"action": "kick", "group_id": 123, "user_id": 999},
    ))
    assert result["ok"] is False
    assert "凭据" in result["error"]
    assert "credential__request" in result["error"]
    assert adapter.calls == []  # 未执行


async def test_kick_with_credential_executes() -> None:
    manager = _manager()
    credential = manager.create(
        chat_flow="group:123", action="kick", requester_id=BOT, cred_type=CRED_TYPE_ONE_TIME
    )
    manager.try_issue(chat_flow="group:123", code=credential.code, issuer_id=SUPER)
    adapter = _FakeAdapter()
    skill = GroupManagementSkill(adapter=adapter, credential_manager=manager)
    result = json.loads(await skill.execute(
        "manage_group",
        {"action": "kick", "group_id": 123, "user_id": 999},
    ))
    assert result["ok"] is True
    assert adapter.calls[0][0] == "set_group_kick"
    assert adapter.calls[0][1]["user_id"] == 999


async def test_quit_group_with_credential() -> None:
    manager = _manager()
    credential = manager.create(
        chat_flow="group:123", action="quit_group", requester_id=BOT, cred_type=CRED_TYPE_ONE_TIME
    )
    manager.try_issue(chat_flow="group:123", code=credential.code, issuer_id=SUPER)
    adapter = _FakeAdapter()
    skill = GroupManagementSkill(adapter=adapter, credential_manager=manager)
    result = json.loads(await skill.execute(
        "manage_group", {"action": "quit_group", "group_id": 123}
    ))
    assert result["ok"] is True
    assert adapter.calls[0][0] == "set_group_leave"


async def test_non_credential_action_no_check() -> None:
    manager = _manager()
    adapter = _FakeAdapter()
    skill = GroupManagementSkill(adapter=adapter, credential_manager=manager)
    result = json.loads(await skill.execute(
        "manage_group",
        {"action": "set_ban", "group_id": 123, "user_id": 999, "duration": 60},
    ))
    assert result["ok"] is True
    assert adapter.calls[0][0] == "set_group_ban"
