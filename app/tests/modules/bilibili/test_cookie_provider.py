"""Cookie 持久化：保存/读取/损坏容忍/清除。"""

from __future__ import annotations

import json

import pytest

from neobot_app.bilibili.cookie_provider import BilibiliCookieStore

_COOKIES = {
    "SESSDATA": "sess-value",
    "bili_jct": "jct-value",
    "DedeUserID": "12345",
    "buvid3": "buvid-value",
}


def test_save_then_load_roundtrip(tmp_path) -> None:
    path = tmp_path / "bilibili" / "cookies.json"
    store = BilibiliCookieStore(path)
    store.save(_COOKIES, refresh_token="refresh-token")

    assert path.is_file()
    loaded = store.load()
    assert loaded is not None
    assert {key: loaded[key] for key in _COOKIES} == _COOKIES
    assert loaded["refresh_token"] == "refresh-token"
    assert loaded["saved_at"].isdigit()

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["saved_at"].isdigit()
    assert raw["DedeUserID"] == "12345"


def test_load_missing_file_returns_none(tmp_path) -> None:
    assert BilibiliCookieStore(tmp_path / "cookies.json").load() is None


def test_load_corrupt_json_returns_none(tmp_path) -> None:
    path = tmp_path / "cookies.json"
    path.write_text("{not json", encoding="utf-8")
    assert BilibiliCookieStore(path).load() is None


def test_load_without_required_cookies_returns_none(tmp_path) -> None:
    path = tmp_path / "cookies.json"
    path.write_text(json.dumps({"SESSDATA": "only-sessdata"}), encoding="utf-8")
    assert BilibiliCookieStore(path).load() is None


def test_save_requires_sessdata_and_bili_jct(tmp_path) -> None:
    store = BilibiliCookieStore(tmp_path / "cookies.json")
    with pytest.raises(ValueError):
        store.save({"SESSDATA": "s"})
    assert not (tmp_path / "cookies.json").exists()


def test_clear_removes_file(tmp_path) -> None:
    path = tmp_path / "cookies.json"
    store = BilibiliCookieStore(path)
    store.save(_COOKIES)
    store.clear()
    assert not path.exists()
    store.clear()  # 重复清除不抛错

def test_save_failure_raises_with_real_path_and_no_partial_file(
    tmp_path, monkeypatch
) -> None:
    """原子写失败时直接抛（不再直写兜底）：异常带真实路径，也不留半个文件。"""
    import neobot_app.bilibili.cookie_provider as module

    calls: list[str] = []

    def failing_atomic(path, text, **kwargs):
        calls.append(str(path))
        raise OSError(2, "No such file or directory", str(path))

    monkeypatch.setattr(module, "atomic_write_text", failing_atomic)
    path = tmp_path / "bilibili" / "cookies.json"
    store = BilibiliCookieStore(path)

    with pytest.raises(OSError) as excinfo:
        store.save(_COOKIES)

    assert str(path) in str(excinfo.value)
    assert calls == [str(path)]  # 只调一次原子写：外层不再重试、也不再直写
    assert not path.exists()
    assert store.load() is None


def test_save_error_mentions_real_path(tmp_path, monkeypatch) -> None:
    """两种写法都失败时，异常里要有真实 cookie 路径，而不是随机 tmp 名。"""
    import neobot_app.bilibili.cookie_provider as module

    def failing_atomic(path, text, **kwargs):
        raise OSError(2, "No such file or directory", str(path))

    monkeypatch.setattr(module, "atomic_write_text", failing_atomic)
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    path = blocker / "cookies.json"

    with pytest.raises(OSError) as excinfo:
        BilibiliCookieStore(path).save(_COOKIES)
    assert str(path) in str(excinfo.value)
