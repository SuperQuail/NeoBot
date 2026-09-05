"""CredentialManager:凭据的创建/签发/消费/过期清理。"""

from __future__ import annotations

import random
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
        while True:
            code = "".join(random.choices(_CODE_CHARS, k=self._code_length))
            if code not in self._credentials:
                return code

    # ── 签发(管理员发送凭据文本) ──

    def try_issue(self, *, chat_flow: str, code: str, issuer_id: int) -> CredentialIssueResult:
        credential = self._credentials.get(code.strip().lower())
        if credential is None or credential.chat_flow != chat_flow:
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
