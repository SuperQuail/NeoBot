"""次级管理员列表的持久化（config.toml 的 [chat].sub_admin_accounts）。

回归背景：旧实现直接在 tomlkit 文档上写 chat["sub_admin_accounts"]，
[chat] 段不存在时 document.get("chat", {}) 返回的是**游离的 dict**，
赋值进不了文档，写回去还是原文件——而调用方收到的是"成功"。
命令因此回复"已添加次级管理员"，重启后列表却空了。
"""

from __future__ import annotations

from pathlib import Path

from neobot_app.config import chat_writer
from neobot_app.config.chat_writer import (
    ChatConfigWriteResult,
    normalize_accounts,
    read_sub_admin_accounts,
    save_sub_admin_accounts,
    write_chat_values,
)

FULL_CONFIG = """version = "0.6.0"

[bot]
account = 10001
nick_name = "bot"

[chat]
# 保留这条注释
admin_accounts = ["3331347593"]
sub_admin_accounts = []
reply_mode = "agent"
"""


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 回归：缺 [chat] 段不能再静默失败
# ---------------------------------------------------------------------------


def test_creates_chat_section_when_missing(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", 'version = "0.6.0"\n\n[bot]\naccount = 10001\n')

    result = save_sub_admin_accounts(path, [88888])

    assert result.ok is True, result.error
    assert read_sub_admin_accounts(path) == ("88888",)
    text = path.read_text(encoding="utf-8")
    assert "[chat]" in text
    assert "sub_admin_accounts" in text


def test_creates_chat_section_in_empty_file(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "")

    result = save_sub_admin_accounts(path, [88888])

    assert result.ok is True, result.error
    assert read_sub_admin_accounts(path) == ("88888",)


def test_writes_into_existing_file_without_touching_other_content(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", FULL_CONFIG)

    result = save_sub_admin_accounts(path, [88888, 77777])

    assert result.ok is True, result.error
    text = path.read_text(encoding="utf-8")
    assert "# 保留这条注释" in text
    assert 'admin_accounts = ["3331347593"]' in text
    assert 'reply_mode = "agent"' in text
    assert read_sub_admin_accounts(path) == ("77777", "88888")


def test_handles_bom_encoded_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(FULL_CONFIG, encoding="utf-8-sig")

    result = save_sub_admin_accounts(path, [88888])

    assert result.ok is True, result.error
    assert read_sub_admin_accounts(path) == ("88888",)


# ---------------------------------------------------------------------------
# 类型与规范化
# ---------------------------------------------------------------------------


def test_accounts_are_persisted_as_strings(tmp_path: Path) -> None:
    """schema 是 List[str]：写 int 会被下次启动判成类型不匹配。"""
    path = _write(tmp_path / "config.toml", FULL_CONFIG)

    assert save_sub_admin_accounts(path, [88888]).ok is True

    text = path.read_text(encoding="utf-8")
    assert 'sub_admin_accounts = ["88888"]' in text


def test_normalize_accounts_sorts_dedupes_and_rejects_garbage() -> None:
    accounts, error = normalize_accounts(["10002", 10001, "10002", " 10003 "])
    assert error == ""
    assert accounts == ("10001", "10002", "10003")

    for bad in ("abc", "10001; rm -rf /", "-1", "1234567890123456789012345"):
        accounts, error = normalize_accounts([bad])
        assert error, bad
        assert accounts == ()


def test_invalid_account_leaves_file_untouched(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", FULL_CONFIG)

    result = save_sub_admin_accounts(path, ["not-a-qq"])

    assert result.ok is False
    assert "非法" in result.error
    assert path.read_text(encoding="utf-8") == FULL_CONFIG


def test_read_returns_empty_for_missing_or_broken_file(tmp_path: Path) -> None:
    assert read_sub_admin_accounts(tmp_path / "nope.toml") == ()
    broken = _write(tmp_path / "broken.toml", "[chat\n")
    assert read_sub_admin_accounts(broken) == ()


# ---------------------------------------------------------------------------
# 失败必须如实汇报（绝不谎报成功）
# ---------------------------------------------------------------------------


def test_corrupt_config_is_rejected_without_overwriting(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", "[chat\nadmin_accounts = ")

    result = save_sub_admin_accounts(path, [88888])

    assert result.ok is False
    assert "解析失败" in result.error
    assert path.read_text(encoding="utf-8") == "[chat\nadmin_accounts = "


def test_validation_failure_blocks_write(tmp_path: Path, monkeypatch) -> None:
    path = _write(tmp_path / "config.toml", FULL_CONFIG)

    def _boom(*args, **kwargs):
        raise ValueError("schema 不接受这份配置")

    monkeypatch.setattr(chat_writer, "dict_to_dataclass", _boom)

    result = save_sub_admin_accounts(path, [88888])

    assert result.ok is False
    assert "校验失败" in result.error
    assert path.read_text(encoding="utf-8") == FULL_CONFIG


def test_roundtrip_mismatch_is_reported(tmp_path: Path, monkeypatch) -> None:
    """写盘后回读不一致时必须报错：这正是旧实现静默失败的形态。"""
    path = _write(tmp_path / "config.toml", FULL_CONFIG)
    monkeypatch.setattr(chat_writer, "read_chat_values", lambda *args, **kwargs: {})

    result = save_sub_admin_accounts(path, [88888])

    assert result.ok is False
    assert "回读不一致" in result.error


def test_write_failure_is_reported(tmp_path: Path, monkeypatch) -> None:
    path = _write(tmp_path / "config.toml", FULL_CONFIG)

    def _boom(*args, **kwargs):
        raise OSError("磁盘满了")

    monkeypatch.setattr(chat_writer, "_atomic_write", _boom)

    result = save_sub_admin_accounts(path, [88888])

    assert result.ok is False
    assert "写入配置失败" in result.error
    assert path.read_text(encoding="utf-8") == FULL_CONFIG


# ---------------------------------------------------------------------------
# 通用 chat 段写回
# ---------------------------------------------------------------------------


def test_write_chat_values_rejects_when_section_is_not_a_table(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", 'chat = "oops"\n')

    result = write_chat_values(path, {"sub_admin_accounts": ["1"]})

    assert result.ok is False
    assert "不是表" in result.error


def test_write_chat_values_requires_values(tmp_path: Path) -> None:
    path = _write(tmp_path / "config.toml", FULL_CONFIG)

    result = write_chat_values(path, {})

    assert result.ok is False
    assert isinstance(result, ChatConfigWriteResult)
