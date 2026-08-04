"""neobot_app.console.security 凭据存储与登录限流测试。"""

from __future__ import annotations

import json
from pathlib import Path

import neobot_app.console.security as security_module
from neobot_app.console.security import (
    CredentialStore,
    LoginLimiter,
    SessionStore,
    is_loopback,
    mask_secret,
)


def test_credential_store_roundtrip_verifies_correct_and_wrong_password(tmp_path: Path) -> None:
    """Arrange: 设置密码后；Act: 用正确/错误密码校验；Assert: 正确为 True、错误为 False。"""
    store = CredentialStore(tmp_path / "console" / "auth.json")

    store.set_password("正确密码-42")

    assert store.verify("正确密码-42") is True
    assert store.verify("错误密码") is False
    assert store.configured is True


def test_credential_store_never_stores_plaintext_and_randomizes_salt(tmp_path: Path) -> None:
    """Arrange: 两次设置相同密码；Act: 读取文件内容；Assert: 无明文且两次盐/摘要不同。"""
    store = CredentialStore(tmp_path / "console" / "auth.json")

    store.set_password("same-password")
    first = json.loads(store.path.read_text(encoding="utf-8"))
    store.set_password("same-password")
    second = json.loads(store.path.read_text(encoding="utf-8"))

    assert "same-password" not in store.path.read_text(encoding="utf-8")
    assert first["salt"] != second["salt"]
    assert first["digest"] != second["digest"]


def test_credential_store_uses_scrypt_parameters(tmp_path: Path) -> None:
    """Arrange: 设置密码；Act: 解析落盘文件；Assert: 算法为 scrypt 且 n/r/p 符合约定。"""
    store = CredentialStore(tmp_path / "console" / "auth.json")

    store.set_password("pw")

    payload = json.loads(store.path.read_text(encoding="utf-8"))
    assert payload["algorithm"] == "scrypt"
    assert payload["version"] == 1
    assert payload["n"] == 2**15
    assert payload["r"] == 8
    assert payload["p"] == 1


def test_credential_store_verify_missing_file_returns_false(tmp_path: Path) -> None:
    """Arrange: 凭据文件不存在；Act: verify；Assert: 返回 False 且不抛错（异常路径）。"""
    store = CredentialStore(tmp_path / "console" / "auth.json")

    assert store.verify("any") is False
    assert store.configured is False


def test_credential_store_verify_corrupt_file_returns_false(tmp_path: Path) -> None:
    """Arrange: 凭据文件损坏/字段缺失；Act: verify；Assert: 返回 False 不抛错（异常路径）。"""
    store = CredentialStore(tmp_path / "console" / "auth.json")
    store.path.parent.mkdir(parents=True)
    store.path.write_text("{not-json", encoding="utf-8")
    assert store.verify("pw") is False

    store.path.write_text(json.dumps({"version": 1}), encoding="utf-8")
    assert store.verify("pw") is False


def test_login_limiter_counts_failures_within_window(monkeypatch) -> None:
    """Arrange: 同一客户端 3 次失败（上限 3）；Act: retry_after；Assert: 返回 >0 的等待秒数。"""
    now = [1000.0]
    monkeypatch.setattr(security_module.time, "time", lambda: now[0])
    limiter = LoginLimiter(attempts=3, window_seconds=300)

    limiter.record_failure("client-a")
    limiter.record_failure("client-a")
    limiter.record_failure("client-a")

    assert limiter.retry_after("client-a") > 0
    assert limiter.retry_after("client-b") == 0


def test_login_limiter_recovers_after_window_elapses(monkeypatch) -> None:
    """Arrange: 窗口内的失败在 300 秒后过期；Act: retry_after；Assert: 重新允许登录。"""
    now = [1000.0]
    monkeypatch.setattr(security_module.time, "time", lambda: now[0])
    limiter = LoginLimiter(attempts=2, window_seconds=300)

    limiter.record_failure("client-a")
    limiter.record_failure("client-a")
    assert limiter.retry_after("client-a") > 0

    now[0] += 301
    assert limiter.retry_after("client-a") == 0


def test_login_limiter_success_resets_bucket(monkeypatch) -> None:
    """Arrange: 客户端已有失败记录；Act: record_success 后 retry_after；Assert: 限流清零。"""
    now = [1000.0]
    monkeypatch.setattr(security_module.time, "time", lambda: now[0])
    limiter = LoginLimiter(attempts=1, window_seconds=300)

    limiter.record_failure("client-a")
    assert limiter.retry_after("client-a") > 0

    limiter.record_success("client-a")

    assert limiter.retry_after("client-a") == 0


def test_login_limiter_at_boundary_attempts() -> None:
    """Arrange: attempts=5 时只失败 4 次；Act: retry_after；Assert: 未达上限返回 0（边界）。"""
    limiter = LoginLimiter(attempts=5, window_seconds=300)

    for _ in range(4):
        limiter.record_failure("client-a")

    assert limiter.retry_after("client-a") == 0


def test_session_store_touch_updates_last_seen(monkeypatch) -> None:
    """Arrange: 会话接近超时；Act: get(touch=True)；Assert: 触碰后延长存活期。"""
    now = [1000.0]
    monkeypatch.setattr(security_module.time, "time", lambda: now[0])
    sessions = SessionStore(timeout_seconds=300)
    token, _session = sessions.create()

    now[0] += 299
    assert sessions.get(token) is not None

    now[0] += 299
    assert sessions.get(token) is not None
    assert sessions.get(token, touch=False) is not None


def test_session_store_expires_without_touch(monkeypatch) -> None:
    """Arrange: 会话未触碰超时；Act: get(touch=False)；Assert: 返回 None。"""
    now = [1000.0]
    monkeypatch.setattr(security_module.time, "time", lambda: now[0])
    sessions = SessionStore(timeout_seconds=300)
    token, _session = sessions.create()

    now[0] += 301
    assert sessions.get(token, touch=False) is None


def test_is_loopback_recognition() -> None:
    """Arrange: 各类 IP 字符串；Act: is_loopback；Assert: 仅回环地址为 True。"""
    assert is_loopback("127.0.0.1") is True
    assert is_loopback("localhost") is True
    assert is_loopback("::1") is True
    assert is_loopback("127.0.0.1%eth0") is True
    assert is_loopback("8.8.8.8") is False
    assert is_loopback("192.168.1.1") is False
    assert is_loopback(None) is False
    assert is_loopback("not-an-ip") is False


def test_mask_secret_short_and_long_values() -> None:
    """Arrange: 短/长敏感值；Act: mask_secret；Assert: 短值全掩码、长值保留首尾。"""
    assert mask_secret("abc") == "••••••••"
    assert mask_secret("") == ""
    assert mask_secret(None) == ""
    assert mask_secret("abcdefghijklmnop") == "abc••••••nop"
