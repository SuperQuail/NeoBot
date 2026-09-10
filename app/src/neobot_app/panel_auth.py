"""网页面板登录密码的存储与校验。

设计：
- 密码用 PBKDF2-HMAC-SHA256 + 随机盐保存（不落明文），文件权限 0600。
- 未配置密码时面板不允许外网访问：本机访问会进入「设置密码」流程，
  超级管理员也可以在 QQ 私聊中执行 /set_password 直接设置。
- 每次修改密码都会递增 revision，面板用它立即失效所有已登录会话。

本模块属于本体核心设施：官方 dashboard 插件负责校验，命令系统负责设置，
两边共用同一个存储实例（同进程内共享，跨进程按文件 mtime 自动重载）。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 240_000
SALT_BYTES = 16
STATE_VERSION = 1
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
GENERATED_PASSWORD_BYTES = 12


class PasswordPolicyError(ValueError):
    """密码不符合策略。"""


def validate_password(password: Any) -> str:
    """校验并返回密码明文；不合规抛出 PasswordPolicyError。"""
    if not isinstance(password, str):
        raise PasswordPolicyError("密码必须是字符串")
    value = password
    if value != value.strip():
        raise PasswordPolicyError("密码首尾不能包含空白字符")
    if len(value) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"密码至少 {MIN_PASSWORD_LENGTH} 个字符")
    if len(value) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"密码最多 {MAX_PASSWORD_LENGTH} 个字符")
    if not any(char.isalnum() for char in value):
        raise PasswordPolicyError("密码至少包含一个字母或数字")
    return value


def generate_password() -> str:
    """生成一个满足策略的随机密码。"""
    while True:
        candidate = secrets.token_urlsafe(GENERATED_PASSWORD_BYTES)
        try:
            return validate_password(candidate)
        except PasswordPolicyError:
            continue


def _hash_password(password: str, *, salt: bytes, iterations: int) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    ).hex()


def default_auth_path() -> Path:
    """面板密码文件默认位置（插件数据目录内）。"""
    from neobot_app.core import DATA_DIR

    return Path(DATA_DIR) / "plugins_data" / "dashboard" / "auth.json"


class PanelPasswordStore:
    """面板密码存储。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()
        self._loaded = False
        self._configured = False
        self._revision = 0
        self._iterations = PBKDF2_ITERATIONS
        self._salt = b""
        self._digest = ""
        self._signature: tuple[int, int] | None = None

    # ------------------------------------------------------------------

    @property
    def configured(self) -> bool:
        with self._lock:
            self._load_if_changed()
            return self._configured

    @property
    def revision(self) -> int:
        """密码版本号；修改密码后递增，用于失效旧会话。"""
        with self._lock:
            self._load_if_changed()
            return self._revision

    def verify(self, password: Any) -> bool:
        with self._lock:
            self._load_if_changed()
            if not self._configured:
                return False
            if not isinstance(password, str) or not password:
                return False
            candidate = _hash_password(
                password, salt=self._salt, iterations=self._iterations
            )
            return hmac.compare_digest(candidate, self._digest)

    def set_password(self, password: Any) -> int:
        """设置/重置密码，返回新的 revision。"""
        value = validate_password(password)
        with self._lock:
            self._load_if_changed()
            salt = os.urandom(SALT_BYTES)
            payload = {
                "version": STATE_VERSION,
                "algorithm": ALGORITHM,
                "iterations": PBKDF2_ITERATIONS,
                "salt": salt.hex(),
                "hash": _hash_password(
                    value, salt=salt, iterations=PBKDF2_ITERATIONS
                ),
                "revision": self._revision + 1,
                "updated_at": int(time.time()),
            }
            self._write(payload)
            self._apply(payload)
            self._signature = self._stat_signature()
            return self._revision

    def clear(self) -> None:
        """清除密码（下一次访问将重新进入设置流程）。"""
        with self._lock:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
            self._configured = False
            self._salt = b""
            self._digest = ""
            self._iterations = PBKDF2_ITERATIONS
            self._revision += 1
            self._signature = None
            self._loaded = True

    # ------------------------------------------------------------------

    def _stat_signature(self) -> tuple[int, int] | None:
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _load_if_changed(self) -> None:
        signature = self._stat_signature()
        if self._loaded and signature == self._signature:
            return
        self._loaded = True
        self._signature = signature
        self._configured = False
        self._salt = b""
        self._digest = ""
        if signature is None:
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except Exception:
            return
        if isinstance(payload, dict):
            self._apply(payload)

    def _apply(self, payload: dict[str, Any]) -> None:
        try:
            salt = bytes.fromhex(str(payload.get("salt") or ""))
            digest = str(payload.get("hash") or "")
            iterations = int(payload.get("iterations") or PBKDF2_ITERATIONS)
        except (TypeError, ValueError):
            return
        if (
            str(payload.get("algorithm") or "") != ALGORITHM
            or not salt
            or not digest
            or iterations < 10_000
        ):
            return
        self._configured = True
        self._salt = salt
        self._digest = digest
        self._iterations = iterations
        self._revision = int(payload.get("revision") or 1)

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".auth-", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temp_name, 0o600)
            except OSError:
                pass
            os.replace(temp_name, self.path)
        except BaseException:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise


_STORES: dict[str, PanelPasswordStore] = {}
_STORES_LOCK = threading.Lock()


def get_panel_password_store(path: Path | None = None) -> PanelPasswordStore:
    """获取（并按路径缓存）面板密码存储实例。"""
    resolved = Path(path) if path is not None else default_auth_path()
    key = str(resolved.resolve())
    with _STORES_LOCK:
        store = _STORES.get(key)
        if store is None:
            store = PanelPasswordStore(resolved)
            _STORES[key] = store
        return store
