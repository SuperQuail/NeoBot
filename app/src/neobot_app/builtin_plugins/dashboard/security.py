"""面板安全：登录令牌、会话、限速与脱敏。

设计要点：
- 令牌来源优先级：config.access_token > 数据目录 access_token.txt > 自动生成并落盘（0600）。
- 会话使用内存随机 token + HttpOnly Cookie，并绑定 CSRF token；写操作必须带 X-CSRF-Token。
- 登录按 IP 限速，超过阈值临时锁定，防公网暴力破解。
- 所有对外输出都经过脱敏，避免把 API Key 写进日志/接口响应。
"""

from __future__ import annotations

import hmac
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SENSITIVE_KEY_RE = re.compile(r"(?i)(api[_-]?key|token|password|secret|credential|authorization)")
_REDACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(
        r"(?i)\b(api[_-]?key|access[_-]?token|token|password|secret|authorization)"
        r"\b\s*[=:]\s*(?:(?:bearer|token)\s+)?[^\s,;]+"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"),
)


def redact(text: Any) -> str:
    """把文本中的密钥类内容替换为 ***。"""
    value = str(text if text is not None else "")
    for pattern in _REDACTION_PATTERNS:
        value = pattern.sub("***", value)
    return value


def is_sensitive_key(key: str) -> bool:
    return bool(SENSITIVE_KEY_RE.search(str(key or "")))


def mask_secret(value: str, *, keep: int = 4) -> str:
    """保留首尾少量字符用于辨认，其余打码。"""
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= keep * 2:
        return "*" * len(text)
    return f"{text[:keep]}{'*' * 8}{text[-keep:]}"


def secrets_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(str(left or ""), str(right or ""))


def client_ip(request: Any, *, trust_proxy: bool = False) -> str:
    """解析客户端地址；仅在显式信任代理时使用转发头。"""
    if trust_proxy:
        for header in ("X-Forwarded-For", "X-Real-IP"):
            raw = request.headers.get(header)
            if raw:
                candidate = raw.split(",")[0].strip()
                if candidate:
                    return candidate
    peer = request.transport.get_extra_info("peername") if request.transport else None
    if isinstance(peer, (tuple, list)) and peer:
        return str(peer[0])
    return str(request.remote or "")


def is_loopback(ip: str) -> bool:
    normalized = str(ip or "").strip()
    if normalized in {"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1"}:
        return True
    return normalized.startswith("127.")


@dataclass(slots=True)
class Session:
    token: str
    csrf_token: str
    created_at: float
    last_seen_at: float
    ip: str = ""
    user_agent: str = ""

    def touch(self, *, timeout_seconds: float) -> bool:
        now = time.time()
        if now - self.last_seen_at > timeout_seconds:
            return False
        self.last_seen_at = now
        return True

    def to_payload(self, *, timeout_seconds: float) -> dict[str, Any]:
        return {
            "ip": self.ip,
            "user_agent": self.user_agent,
            "created_at": self.created_at,
            "last_seen_at": self.last_seen_at,
            "expires_in": max(0, int(timeout_seconds - (time.time() - self.last_seen_at))),
        }


class SessionStore:
    """内存会话表（重启即失效，令牌仍是唯一长期凭据）。"""

    def __init__(self, *, timeout_seconds: float, max_sessions: int = 64) -> None:
        self._timeout = float(timeout_seconds)
        self._max_sessions = int(max_sessions)
        self._sessions: dict[str, Session] = {}

    @property
    def timeout_seconds(self) -> float:
        return self._timeout

    def create(self, *, ip: str = "", user_agent: str = "") -> Session:
        self.prune()
        if len(self._sessions) >= self._max_sessions:
            oldest = min(self._sessions.values(), key=lambda item: item.last_seen_at)
            self._sessions.pop(oldest.token, None)
        now = time.time()
        session = Session(
            token=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(24),
            created_at=now,
            last_seen_at=now,
            ip=ip,
            user_agent=user_agent[:200],
        )
        self._sessions[session.token] = session
        return session

    def get(self, token: str | None) -> Session | None:
        if not token:
            return None
        session = self._sessions.get(token)
        if session is None:
            return None
        if not session.touch(timeout_seconds=self._timeout):
            self._sessions.pop(token, None)
            return None
        return session

    def revoke(self, token: str | None) -> bool:
        if not token:
            return False
        return self._sessions.pop(token, None) is not None

    def revoke_all(self) -> int:
        count = len(self._sessions)
        self._sessions.clear()
        return count

    def prune(self) -> None:
        now = time.time()
        for token in [
            token
            for token, session in self._sessions.items()
            if now - session.last_seen_at > self._timeout
        ]:
            self._sessions.pop(token, None)

    def describe(self) -> list[dict[str, Any]]:
        self.prune()
        return [
            {"token": session.token[:6] + "…", **session.to_payload(timeout_seconds=self._timeout)}
            for session in sorted(
                self._sessions.values(), key=lambda item: item.last_seen_at, reverse=True
            )
        ]


@dataclass(slots=True)
class LoginLimiter:
    """按 IP 统计登录失败次数，超限后临时锁定。"""

    max_failures: int = 5
    window_seconds: float = 600.0
    _failures: dict[str, list[float]] = field(default_factory=dict)

    def _recent(self, ip: str, now: float) -> list[float]:
        stamps = [item for item in self._failures.get(ip, []) if now - item < self.window_seconds]
        if stamps:
            self._failures[ip] = stamps
        else:
            self._failures.pop(ip, None)
        return stamps

    def is_locked(self, ip: str) -> tuple[bool, int]:
        now = time.time()
        stamps = self._recent(ip, now)
        if len(stamps) < self.max_failures:
            return False, 0
        remaining = int(self.window_seconds - (now - min(stamps))) + 1
        return True, max(1, remaining)

    def record_failure(self, ip: str) -> None:
        now = time.time()
        stamps = self._recent(ip, now)
        stamps.append(now)
        self._failures[ip] = stamps

    def reset(self, ip: str) -> None:
        self._failures.pop(ip, None)


class TokenStore:
    """登录令牌的读取/生成与持久化。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def resolve(self, configured: str) -> tuple[str, str]:
        """返回 (token, source)；source 取值 config / file / auto。"""
        candidate = str(configured or "").strip()
        if candidate:
            return candidate, "config"
        if self.path.is_file():
            try:
                stored = self.path.read_text(encoding="utf-8").strip()
            except OSError:
                stored = ""
            if stored:
                return stored, "file"
        token = secrets.token_urlsafe(32)
        self.persist(token)
        return token, "auto"

    def persist(self, token: str) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(token, encoding="utf-8")
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
            return True
        except OSError:
            return False
