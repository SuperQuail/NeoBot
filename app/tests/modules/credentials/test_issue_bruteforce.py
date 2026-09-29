"""凭据码强度与防爆破的回归测试（fix(12) §4.3）。

旧实现两个问题：
1. 凭据码用 `random.choices`（进程内全局 MT19937）生成 —— 输出可观测后理论上可被
   恢复并预测后续码，而凭据码等价于"管理员对该动作的授权"；
2. `try_issue` 无失败计数：群聊里任何人都能无限次猜测 6 位码（约 29.6 bit）。

修复后：改用 `secrets.choice`；同一会话连续未命中 5 次进入 5 分钟冷却，
冷却期内即使"猜中"也不签发（否则只是限速而非阻断）。
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from neobot_app.credentials.model import CRED_TYPE_ONE_TIME
from neobot_app.credentials.service import (
    _CODE_CHARS,
    _ISSUE_BLOCK_SECONDS,
    _ISSUE_MAX_FAILURES,
    CredentialManager,
)

SUPER = 1
NORMAL = 2


def _manager() -> CredentialManager:
    permissions = SimpleNamespace(
        can=lambda user_id, level: user_id == SUPER or level <= 0
    )
    return CredentialManager(permissions=permissions)


def _new_credential(manager: CredentialManager, *, chat_flow: str = "group:1"):
    return manager.create(
        chat_flow=chat_flow,
        action="kick_member",
        requester_id=NORMAL,
        cred_type=CRED_TYPE_ONE_TIME,
    )


def test_code_charset_and_length() -> None:
    manager = _manager()
    credential = _new_credential(manager)
    assert len(credential.code) == 6
    assert set(credential.code) <= set(_CODE_CHARS)


def test_code_generation_does_not_use_global_random(monkeypatch) -> None:
    """生成必须走 secrets（旧实现用 random.choices，MT19937 可被预测）。"""
    import neobot_app.credentials.service as service

    calls: list[str] = []
    original = service.secrets.choice

    def _spy(alphabet: str) -> str:
        calls.append(alphabet)
        return original(alphabet)

    monkeypatch.setattr(service.secrets, "choice", _spy)
    # 同时把 random.choices 换成必须失败：一旦回退到旧实现，用例立刻报错
    monkeypatch.setattr(
        service, "random", SimpleNamespace(choices=lambda *a, **k: pytest.fail("不得使用 random"))
    ) if hasattr(service, "random") else None

    manager = _manager()
    _new_credential(manager)
    assert calls, "凭据码未通过 secrets.choice 生成"


def test_repeated_not_found_enters_cooldown() -> None:
    manager = _manager()
    for _ in range(_ISSUE_MAX_FAILURES):
        result = manager.try_issue(chat_flow="group:1", code="zzzzzz", issuer_id=SUPER)
        assert result.ok is False
        assert result.error == "not_found"

    assert manager.is_issue_blocked("group:1") is True
    blocked = manager.try_issue(chat_flow="group:1", code="zzzzzz", issuer_id=SUPER)
    assert blocked.ok is False
    assert blocked.error == "rate_limited"


def test_cooldown_blocks_even_a_correct_code() -> None:
    """冷却期内真实凭据也不签发 —— 否则爆破只是被限速。"""
    manager = _manager()
    credential = _new_credential(manager)
    for _ in range(_ISSUE_MAX_FAILURES):
        manager.try_issue(chat_flow="group:1", code="zzzzzz", issuer_id=SUPER)

    result = manager.try_issue(chat_flow="group:1", code=credential.code, issuer_id=SUPER)
    assert result.ok is False
    assert result.error == "rate_limited"


def test_successful_issue_clears_failure_counter() -> None:
    manager = _manager()
    credential = _new_credential(manager)
    for _ in range(_ISSUE_MAX_FAILURES - 1):
        manager.try_issue(chat_flow="group:1", code="zzzzzz", issuer_id=SUPER)

    issued = manager.try_issue(chat_flow="group:1", code=credential.code, issuer_id=SUPER)
    assert issued.ok is True
    assert manager.is_issue_blocked("group:1") is False

    # 计数已清零：再猜 _ISSUE_MAX_FAILURES - 1 次仍不应触发冷却
    for _ in range(_ISSUE_MAX_FAILURES - 1):
        manager.try_issue(chat_flow="group:1", code="zzzzzz", issuer_id=SUPER)
    assert manager.is_issue_blocked("group:1") is False


def test_failures_are_per_chat_flow() -> None:
    manager = _manager()
    for _ in range(_ISSUE_MAX_FAILURES):
        manager.try_issue(chat_flow="group:1", code="zzzzzz", issuer_id=SUPER)

    assert manager.is_issue_blocked("group:1") is True
    assert manager.is_issue_blocked("group:2") is False


def test_cleanup_releases_expired_cooldown(monkeypatch) -> None:
    manager = _manager()
    for _ in range(_ISSUE_MAX_FAILURES):
        manager.try_issue(chat_flow="group:1", code="zzzzzz", issuer_id=SUPER)
    assert manager.is_issue_blocked("group:1") is True

    real_time = time.time
    monkeypatch.setattr(
        "neobot_app.credentials.service.time.time",
        lambda: real_time() + _ISSUE_BLOCK_SECONDS + 1,
    )
    manager.cleanup()

    assert manager.is_issue_blocked("group:1") is False
    assert "group:1" not in manager._issue_failures
