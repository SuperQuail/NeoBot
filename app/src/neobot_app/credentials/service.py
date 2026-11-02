"""CredentialManager:凭据的创建/签发/消费/过期清理。"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any

from neobot_app.credentials.model import (
    ACTION_REQUIRED_LEVEL,
    CRED_STATUS_ACTIVE,
    CRED_STATUS_EXPIRED,
    CRED_STATUS_PENDING,
    CRED_STATUS_USED,
    CRED_TYPE_ONE_TIME,
    CRED_TYPE_TIMED,
    DEFAULT_REQUIRED_LEVEL,
    Credential,
)

# 易读字符集(去掉易混淆的 0/O/1/l/I)
_CODE_CHARS = "abcdefghjkmnpqrstuvwxyz23456789"

#: 凭据签发尝试的防爆破阈值：同一会话连续未命中达到此数量后进入冷却
_ISSUE_MAX_FAILURES = 5
#: 冷却时长（秒）：期间即使猜中也不签发，避免"低速无限次猜测"
_ISSUE_BLOCK_SECONDS = 300.0


@dataclass
class CredentialIssueResult:
    """签发结果。"""

    ok: bool
    credential: Credential | None = None
    error: str = ""
    newly_issued: bool = False  # 是否本次从 pending → active(首次签发)


class CredentialManager:
    """凭据管理器(进程内)。"""

    def __init__(
        self,
        permissions: Any,
        *,
        code_length: int = 6,
        default_duration_minutes: int = 5,
        max_duration_minutes: int = 30,
    ) -> None:
        self._permissions = permissions
        self._code_length = code_length
        self._default_duration = default_duration_minutes
        self._max_duration = max_duration_minutes
        self._credentials: dict[str, Credential] = {}
        # 群聊里任何人都能发消息，凭据码只能靠"猜不中"来抵御爆破。
        # 按会话记录连续未命中的次数，超限后冷却，避免无限次尝试。
        self._issue_failures: dict[str, int] = {}
        self._issue_blocked_until: dict[str, float] = {}
        # 冷却窗口内已提示过「太频繁」的会话：每窗口只提醒一次，避免任意成员
        # 反复发像码的文本放大回执，也避免通过回执探测会话是否在冷却。
        self._rate_limit_notified: set[str] = set()

    def is_super_admin(self, user_id: Any) -> bool:
        """该用户是否为超级管理员。

        管理员本人直接发起的请求视为已授权：无需再申请凭据。其他人的请求
        仍然需要管理员签发凭据，本方法只用于区分「谁在发起」。
        """
        permissions = getattr(self, "_permissions", None)
        if permissions is None or user_id in (None, "", 0, "0"):
            return False
        try:
            return bool(permissions.is_super_admin(int(user_id)))
        except (TypeError, ValueError, AttributeError):
            return False

    # ── 查询 ──

    def get(self, code: str) -> Credential | None:
        return self._credentials.get(code)

    def list(self, *, chat_flow: str | None = None) -> list[Credential]:
        result = [
            credential
            for credential in self._credentials.values()
            if chat_flow is None or credential.chat_flow == chat_flow
        ]
        result.sort(key=lambda credential: credential.created_at)
        return result

    def has_pending_or_active(self, *, chat_flow: str) -> bool:
        """该会话是否有待签发或可用凭据（轻量遍历，不排序）。"""
        return any(
            credential.chat_flow == chat_flow
            and credential.status in (CRED_STATUS_PENDING, CRED_STATUS_ACTIVE)
            for credential in self._credentials.values()
        )

    def can_issue_pending(self, *, chat_flow: str, issuer_id: int) -> bool:
        """该发送者是否有权限签发本会话任一待签发凭据。

        失败计数与冷却提示都用它做权限门：没有签发权限的人即使猜中也会
        `permission_denied`，对他的猜测计数没有安全收益，反而让普通成员能用
        闲聊把签发挡住。
        """
        return any(
            credential.chat_flow == chat_flow
            and credential.status == CRED_STATUS_PENDING
            and self._permissions.can(issuer_id, credential.required_level)
            for credential in self._credentials.values()
        )

    def take_rate_limit_notice(self, chat_flow: str) -> bool:
        """冷却窗口内每会话只提示一次；返回本次是否应当提示。"""
        if chat_flow in self._rate_limit_notified:
            return False
        self._rate_limit_notified.add(chat_flow)
        return True

    def has_active(self, *, chat_flow: str, action: str) -> bool:
        return self.consume(chat_flow=chat_flow, action=action, commit=False) is not None

    # ── 创建(申请) ──

    def create(
        self,
        *,
        chat_flow: str,
        action: str,
        requester_id: int,
        cred_type: str,
        duration_minutes: int | None = None,
    ) -> Credential:
        cred_type = (cred_type or "").strip().lower()
        if cred_type not in (CRED_TYPE_ONE_TIME, CRED_TYPE_TIMED):
            raise ValueError(f"凭据类型无效: {cred_type}")
        duration = self._clamp_duration(duration_minutes)

        # 同会话同动作已有可用凭据:直接复用(避免垃圾凭据堆积)
        for credential in self._credentials.values():
            if (
                credential.chat_flow == chat_flow
                and credential.action == action
                and credential.status in (CRED_STATUS_PENDING, CRED_STATUS_ACTIVE)
            ):
                if credential.is_expired():
                    credential.status = CRED_STATUS_EXPIRED
                    continue
                return credential

        code = self._generate_code()
        required_level = ACTION_REQUIRED_LEVEL.get(action, DEFAULT_REQUIRED_LEVEL)
        credential = Credential(
            code=code,
            chat_flow=chat_flow,
            action=action,
            cred_type=cred_type,
            duration_minutes=duration,
            required_level=required_level,
            requester_id=requester_id,
        )
        self._credentials[code] = credential
        return credential

    def _clamp_duration(self, duration_minutes: int | None) -> int:
        if duration_minutes is None:
            return self._default_duration
        try:
            value = max(1, min(int(duration_minutes), self._max_duration))
        except (TypeError, ValueError, OverflowError):
            return self._default_duration
        return value

    def _generate_code(self) -> str:
        # 必须用 secrets：random 是进程内全局 MT19937，输出可观测后理论上可被
        # 恢复并预测后续凭据码，而凭据码等价于"管理员对该动作的授权"。
        while True:
            code = "".join(secrets.choice(_CODE_CHARS) for _ in range(self._code_length))
            if code not in self._credentials:
                return code

    def looks_like_code(self, text: str) -> bool:
        """文本是否「长得像凭据码」：长度与字符集都要和凭据码一致。

        `_try_issue_credential` 对每条群消息都会调用 `try_issue`，若把普通闲聊
        也记成一次「没猜中」，活跃群聊五句话就能把会话打进 5 分钟冷却，而冷却期
        内正确凭据码同样被拒（rate_limited），凭据功能等于不可用。所以只有格式
        与凭据码一致的文本才算一次猜测尝试，防爆破强度不变。
        """
        candidate = text.strip().lower()
        if len(candidate) != self._code_length:
            return False
        return all(char in _CODE_CHARS for char in candidate)

    def _record_issue_failure(self, chat_flow: str, now: float) -> None:
        """记录一次"没猜中"；达到阈值后进入冷却。"""
        failures = self._issue_failures.get(chat_flow, 0) + 1
        self._issue_failures[chat_flow] = failures
        if failures >= _ISSUE_MAX_FAILURES:
            self._issue_blocked_until[chat_flow] = now + _ISSUE_BLOCK_SECONDS
            self._issue_failures[chat_flow] = 0
            # 新冷却窗口：允许再提示一次
            self._rate_limit_notified.discard(chat_flow)

    def _clear_issue_failures(self, chat_flow: str) -> None:
        self._issue_failures.pop(chat_flow, None)
        self._issue_blocked_until.pop(chat_flow, None)
        self._rate_limit_notified.discard(chat_flow)

    def is_issue_blocked(self, chat_flow: str) -> bool:
        """该会话是否正处于签发冷却期（供上层给出明确提示）。"""
        return self._issue_blocked_until.get(chat_flow, 0.0) > time.time()

    # ── 签发(管理员发送凭据文本) ──

    def try_issue(self, *, chat_flow: str, code: str, issuer_id: int) -> CredentialIssueResult:
        now = time.time()
        # 冷却期内一律拒绝：此时连"猜中"也不签发，否则爆破只是被限速而非被阻断。
        blocked_until = self._issue_blocked_until.get(chat_flow, 0.0)
        if blocked_until > now:
            return CredentialIssueResult(ok=False, error="rate_limited")

        credential = self._credentials.get(code.strip().lower())
        if credential is None or credential.chat_flow != chat_flow:
            # 只有「本来就能签发」的人发来的、格式合法的文本才算一次猜测尝试：
            # 普通聊天不计数，无签发权限的成员也不计数（他们猜中同样会被拒）。
            if self.looks_like_code(code) and self.can_issue_pending(
                chat_flow=chat_flow, issuer_id=issuer_id
            ):
                self._record_issue_failure(chat_flow, now)
            return CredentialIssueResult(ok=False, error="not_found")
        if credential.is_expired():
            credential.status = CRED_STATUS_EXPIRED
            return CredentialIssueResult(ok=False, error="expired")
        if credential.status == CRED_STATUS_ACTIVE:
            # 已签发:重发需具备签发权限(防任意成员重复触发);
            # 与首次签发者一致时幂等返回
            if self._permissions.can(issuer_id, credential.required_level):
                return CredentialIssueResult(ok=True, credential=credential, newly_issued=False)
            return CredentialIssueResult(
                ok=False, error="permission_denied", credential=credential
            )
        if credential.status != CRED_STATUS_PENDING:
            return CredentialIssueResult(
                ok=False, error="invalid_status", credential=credential
            )

        if not self._permissions.can(issuer_id, credential.required_level):
            return CredentialIssueResult(
                ok=False,
                error="permission_denied",
                credential=credential,
            )

        credential.status = CRED_STATUS_ACTIVE
        credential.issuer_id = issuer_id
        if credential.cred_type == CRED_TYPE_TIMED:
            credential.expires_at = time.time() + credential.duration_minutes * 60
        self._clear_issue_failures(chat_flow)
        return CredentialIssueResult(ok=True, credential=credential, newly_issued=True)

    # ── 消费(风险操作执行前) ──

    def consume(
        self, *, chat_flow: str, action: str, commit: bool = True
    ) -> Credential | None:
        """查找并消费指定会话+动作的可用凭据。

        commit=False 仅检查不消费(has_active 用)。
        返回 None 表示无可用凭据(操作应被拒绝)。
        """
        now = time.time()
        candidates: list[Credential] = []
        for credential in self._credentials.values():
            if credential.chat_flow != chat_flow or credential.action != action:
                continue
            if credential.is_expired(now):
                credential.status = CRED_STATUS_EXPIRED
                continue
            if credential.status == CRED_STATUS_ACTIVE:
                candidates.append(credential)
        if not candidates:
            return None
        candidates.sort(key=lambda credential: credential.created_at)
        credential = candidates[0]
        if commit:
            if credential.cred_type == CRED_TYPE_ONE_TIME:
                credential.status = CRED_STATUS_USED
                credential.used_at = now
            # timed 凭据持续有效,不消费
        return credential

    # ── 管理 ──

    def revoke(self, code: str) -> bool:
        credential = self._credentials.get(code)
        if credential is None:
            return False
        if credential.status in (CRED_STATUS_PENDING, CRED_STATUS_ACTIVE):
            credential.status = CRED_STATUS_EXPIRED
            return True
        return False

    def cleanup(self) -> int:
        """清理过期凭据,返回清理数量。"""
        now = time.time()
        removed = 0
        # 冷却已过的会话把计数一并回收，避免长期运行下字典无界增长
        for flow, blocked_until in list(self._issue_blocked_until.items()):
            if blocked_until <= now:
                self._issue_blocked_until.pop(flow, None)
                self._issue_failures.pop(flow, None)
                self._rate_limit_notified.discard(flow)
        for code, credential in list(self._credentials.items()):
            if credential.status == CRED_STATUS_PENDING:
                # pending 超时(10 分钟未签发)也清理,避免堆积
                if now - credential.created_at > 600:
                    self._credentials.pop(code, None)
                    removed += 1
                continue
            if credential.is_expired(now) or credential.status in (
                CRED_STATUS_USED,
                CRED_STATUS_EXPIRED,
            ):
                self._credentials.pop(code, None)
                removed += 1
        return removed

    def required_level_for(self, action: str) -> int:
        return ACTION_REQUIRED_LEVEL.get(action, DEFAULT_REQUIRED_LEVEL)
