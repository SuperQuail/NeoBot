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
    _new_credential(manager)
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
    _new_credential(manager)
    for _ in range(_ISSUE_MAX_FAILURES):
        manager.try_issue(chat_flow="group:1", code="zzzzzz", issuer_id=SUPER)

    assert manager.is_issue_blocked("group:1") is True
    assert manager.is_issue_blocked("group:2") is False


def test_cleanup_releases_expired_cooldown(monkeypatch) -> None:
    manager = _manager()
    _new_credential(manager)
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


def test_chitchat_does_not_trigger_cooldown() -> None:
    """普通聊天不能被算成「猜码失败」。

    管线对每条群消息都会调 try_issue；若把闲聊也计入失败次数，活跃群聊五句话
    就能把会话打进 5 分钟冷却，冷却期内正确凭据码同样被拒（rate_limited），
    线上表现就是「管理员发了码，凭据一直 pending」。
    """
    manager = _manager()
    credential = _new_credential(manager)
    for text in ("今天天气不错", "在吗", "哈哈哈哈", "晚安喵", "好耶", "诶嘿"):
        result = manager.try_issue(chat_flow="group:1", code=text, issuer_id=SUPER)
        assert result.ok is False
        assert result.error == "not_found"

    assert manager.is_issue_blocked("group:1") is False
    issued = manager.try_issue(chat_flow="group:1", code=credential.code, issuer_id=SUPER)
    assert issued.ok is True
    assert issued.newly_issued is True


def test_code_shaped_guesses_still_count() -> None:
    """格式与凭据码一致的猜测仍然计入失败次数（防爆破强度不变）。"""
    manager = _manager()
    credential = _new_credential(manager)
    wrong = "z" * len(credential.code)
    assert manager.looks_like_code(wrong) is True
    assert manager.looks_like_code("在吗") is False

    for _ in range(_ISSUE_MAX_FAILURES):
        manager.try_issue(chat_flow="group:1", code=wrong, issuer_id=SUPER)
    assert manager.is_issue_blocked("group:1") is True

    blocked = manager.try_issue(chat_flow="group:1", code=credential.code, issuer_id=SUPER)
    assert blocked.error == "rate_limited"


def test_normal_member_guesses_do_not_trigger_cooldown() -> None:
    """无签发权限的成员发「像码」的文本也不计数。

    他们猜中同样会被 permission_denied，计他们的数没有安全收益；反过来，
    「hahaha」「233333」这类日常词恰好满足长度+字符集，计入会让普通成员用
    闲聊把签发挡住。
    """
    manager = _manager()
    credential = _new_credential(manager)
    for text in ("hahaha", "233333", "666666", "thanks", "zzzzzz"):
        assert manager.looks_like_code(text) is True
        result = manager.try_issue(chat_flow="group:1", code=text, issuer_id=NORMAL)
        assert result.ok is False
        assert result.error == "not_found"

    assert manager.is_issue_blocked("group:1") is False
    issued = manager.try_issue(chat_flow="group:1", code=credential.code, issuer_id=SUPER)
    assert issued.ok is True
    assert issued.newly_issued is True


def test_rate_limit_notice_is_once_per_cooldown() -> None:
    """冷却窗口内每会话只允许提示一次，窗口结束后可再次提示。"""
    manager = _manager()
    _new_credential(manager)
    assert manager.take_rate_limit_notice("group:1") is True
    assert manager.take_rate_limit_notice("group:1") is False

    # 重新进入冷却（成功签发会清掉窗口标记，这里直接走 _record_issue_failure）
    for _ in range(_ISSUE_MAX_FAILURES):
        manager.try_issue(chat_flow="group:1", code="zzzzzz", issuer_id=SUPER)
    assert manager.is_issue_blocked("group:1") is True
    assert manager.take_rate_limit_notice("group:1") is True
