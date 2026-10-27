"""网页面板密码存储（panel_auth）单元测试。"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from neobot_app.panel_auth import (
    MIN_PASSWORD_LENGTH,
    PanelPasswordStore,
    PasswordPolicyError,
    PasswordRevisionError,
    PasswordVerificationError,
    generate_password,
    get_panel_password_store,
    validate_password,
)

PASSWORD = "NeoBot-Panel-2026"


def test_validate_password_policy() -> None:
    assert validate_password(PASSWORD) == PASSWORD
    with pytest.raises(PasswordPolicyError):
        validate_password("short")
    with pytest.raises(PasswordPolicyError):
        validate_password("x" * 200)
    with pytest.raises(PasswordPolicyError):
        validate_password("  spaced123  ")
    with pytest.raises(PasswordPolicyError):
        validate_password("!!!!!!!!")
    with pytest.raises(PasswordPolicyError):
        validate_password(12345678)


def test_generate_password_meets_policy() -> None:
    for _ in range(5):
        candidate = generate_password()
        assert validate_password(candidate) == candidate
        assert len(candidate) >= MIN_PASSWORD_LENGTH


def test_store_set_and_verify(tmp_path: Path) -> None:
    store = PanelPasswordStore(tmp_path / "auth.json")
    assert store.configured is False
    assert store.verify(PASSWORD) is False

    revision = store.set_password(PASSWORD)

    assert store.configured is True
    assert revision == 1
    assert store.verify(PASSWORD) is True
    assert store.verify("wrong-password") is False
    assert store.verify("") is False


def test_store_never_writes_plaintext(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    store = PanelPasswordStore(path)
    store.set_password(PASSWORD)

    raw = path.read_text(encoding="utf-8")
    assert PASSWORD not in raw
    payload = json.loads(raw)
    assert payload["algorithm"] == "pbkdf2_sha256"
    assert payload["iterations"] >= 10_000
    assert payload["salt"] and payload["hash"]


def test_store_reloads_when_file_changes(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    first = PanelPasswordStore(path)
    first.set_password(PASSWORD)

    second = PanelPasswordStore(path)
    assert second.configured is True
    assert second.verify(PASSWORD) is True

    revision = second.set_password("Another-Password-1")
    assert revision == 2
    # 第一个实例应通过 mtime 感知变化，旧密码失效
    assert first.verify(PASSWORD) is False
    assert first.verify("Another-Password-1") is True
    assert first.revision == 2


def test_store_clear(tmp_path: Path) -> None:
    store = PanelPasswordStore(tmp_path / "auth.json")
    store.set_password(PASSWORD)

    store.clear()

    assert store.configured is False
    assert store.verify(PASSWORD) is False
    assert not (tmp_path / "auth.json").exists()


def test_store_tolerates_corrupt_file(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text("{ not json", encoding="utf-8")
    store = PanelPasswordStore(path)

    assert store.configured is False
    assert store.verify(PASSWORD) is False

    store.set_password(PASSWORD)
    assert store.verify(PASSWORD) is True


def test_store_rejects_foreign_algorithm(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "algorithm": "plain",
                "iterations": 1,
                "salt": "00" * 16,
                "hash": "deadbeef",
            }
        ),
        encoding="utf-8",
    )
    store = PanelPasswordStore(path)

    assert store.configured is False
    assert store.verify("whatever") is False


def test_get_panel_password_store_is_cached_per_path(tmp_path: Path) -> None:
    path = tmp_path / "auth.json"
    assert get_panel_password_store(path) is get_panel_password_store(path)
    assert get_panel_password_store(path) is not get_panel_password_store(
        tmp_path / "other.json"
    )


def test_change_password_verifies_current_and_preserves_state_on_failure(tmp_path: Path) -> None:
    store = PanelPasswordStore(tmp_path / "auth.json")
    revision = store.set_password(PASSWORD)
    original = store.path.read_bytes()
    with pytest.raises(PasswordVerificationError, match="当前密码不正确"):
        store.change_password("wrong-password", "Next-Password-2026", expected_revision=revision)
    with pytest.raises(PasswordPolicyError):
        store.change_password(PASSWORD, "short", expected_revision=revision)
    assert store.path.read_bytes() == original
    assert store.revision == revision
    assert store.verify(PASSWORD)


def test_change_password_rejects_stale_session_after_reset(tmp_path: Path) -> None:
    store = PanelPasswordStore(tmp_path / "auth.json")
    revision = store.set_password(PASSWORD)
    current_revision = store.set_password("Reset-Password-2026")
    with pytest.raises(PasswordRevisionError):
        store.change_password("Reset-Password-2026", "Next-Password-2026", expected_revision=revision)
    assert store.revision == current_revision
    assert store.verify("Reset-Password-2026")


def test_change_password_concurrent_requests_cannot_overwrite_each_other(tmp_path: Path) -> None:
    store = PanelPasswordStore(tmp_path / "auth.json")
    revision = store.set_password(PASSWORD)

    def attempt(password: str) -> str | None:
        try:
            store.change_password(PASSWORD, password, expected_revision=revision)
            return password
        except PasswordRevisionError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, ["First-Password-2026", "Second-Password-2026"]))
    winners = [value for value in results if value is not None]
    assert len(winners) == 1
    assert store.revision == revision + 1
    assert store.verify(winners[0])
    assert not store.verify(PASSWORD)
    assert winners[0] not in store.path.read_text(encoding="utf-8")


def test_change_password_write_failure_keeps_original_password(tmp_path: Path, monkeypatch) -> None:
    store = PanelPasswordStore(tmp_path / "auth.json")
    revision = store.set_password(PASSWORD)
    original = store.path.read_bytes()

    def fail_write(_payload) -> None:
        raise OSError("test disk full")

    monkeypatch.setattr(store, "_write", fail_write)
    with pytest.raises(OSError):
        store.change_password(PASSWORD, "Next-Password-2026", expected_revision=revision)
    assert store.path.read_bytes() == original
    assert store.revision == revision
    assert store.verify(PASSWORD)
