"""内置控制台的认证与请求安全基础组件。"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|authorization|password|secret)"
)
_INLINE_SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|authorization|password|secret)"
    r"\b(\s*[:=]\s*)([^\s,;]+)"
)


@dataclass
class Session:
    csrf_token: str
    created_at: float
    last_seen: float


class CredentialStore:
    """仅持久化加盐 scrypt 校验值；明文密码永不落盘。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def configured(self) -> bool:
        return self.path.is_file()

    def set_password(self, password: str) -> None:
        salt = secrets.token_bytes(32)
        digest = _derive_password(password, salt)
        payload = {
            "version": 1,
            "algorithm": "scrypt",
            "n": _SCRYPT_N,
            "r": _SCRYPT_R,
            "p": _SCRYPT_P,
            "salt": salt.hex(),
            "digest": digest.hex(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.path)

    def verify(self, password: str) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            salt = bytes.fromhex(str(payload["salt"]))
            expected = bytes.fromhex(str(payload["digest"]))
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=int(payload["n"]),
                r=int(payload["r"]),
                p=int(payload["p"]),
                maxmem=_SCRYPT_MAXMEM,
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return False
        return hmac.compare_digest(actual, expected)


class SessionStore:
    def __init__(self, timeout_seconds: int) -> None:
        self.timeout_seconds = max(300, timeout_seconds)
        self._sessions: dict[str, Session] = {}

    def create(self) -> tuple[str, Session]:
        now = time.time()
        token = secrets.token_urlsafe(48)
        session = Session(
            csrf_token=secrets.token_urlsafe(32),
            created_at=now,
            last_seen=now,
        )
        self._sessions[token] = session
        self.prune()
        return token, session

    def get(self, token: str | None, *, touch: bool = True) -> Session | None:
        if not token:
            return None
        session = self._sessions.get(token)
        if session is None:
            return None
        now = time.time()
        if now - session.last_seen > self.timeout_seconds:
            self._sessions.pop(token, None)
            return None
        if touch:
            session.last_seen = now
        return session

    def revoke(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def revoke_all(self) -> None:
        self._sessions.clear()

    def prune(self) -> None:
        now = time.time()
        expired = [
            token
            for token, session in self._sessions.items()
            if now - session.last_seen > self.timeout_seconds
        ]
        for token in expired:
            self._sessions.pop(token, None)


class LoginLimiter:
    """针对密码尝试的内存滑动窗口限流器。"""

    def __init__(self, attempts: int = 5, window_seconds: int = 300) -> None:
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def retry_after(self, client: str) -> int:
        now = time.time()
        bucket = self._attempts[client]
        while bucket and now - bucket[0] >= self.window_seconds:
            bucket.popleft()
        if len(bucket) < self.attempts:
            return 0
        return max(1, int(self.window_seconds - (now - bucket[0])))

    def record_failure(self, client: str) -> None:
        self._attempts[client].append(time.time())

    def record_success(self, client: str) -> None:
        self._attempts.pop(client, None)


def is_loopback(value: str | None) -> bool:
    if not value:
        return False
    address = value.strip().split("%", 1)[0]
    if address.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


def redact(value: Any, key: str = "") -> Any:
    """递归脱敏常见凭据字段及行内密钥值。"""

    if _SECRET_PATTERN.search(key):
        return mask_secret(value)
    if isinstance(value, dict):
        return {str(item_key): redact(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _INLINE_SECRET_PATTERN.sub(r"\1\2••••••••", value)
    return value


def mask_secret(value: Any) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""
    if len(text) <= 8:
        return "••••••••"
    return f"{text[:3]}••••••{text[-3:]}"


def _derive_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        maxmem=_SCRYPT_MAXMEM,
    )
