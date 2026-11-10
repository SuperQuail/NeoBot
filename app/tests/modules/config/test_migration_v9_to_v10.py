"""0.9.0 -> 0.10.0：chat.gentle_language_enabled 搬到 [prompt_optimizations].gentle_language。

旧字段升级后删除；true/false 原样保留，其余子块由默认值 true 补齐。
"""

from __future__ import annotations

import pytest

from neobot_app.config.loader.manager import Config
from neobot_app.config.migrations import migrate_v9_to_v10
from neobot_app.config.schemas.bot import BotConfig

_DEEPSEEK_KEYS = {
    "DeepSeek_URL": "https://api.deepseek.com",
    "DeepSeek_APIKey": "sk-deepseek-test-1234567890",
}


def _clear_platform_env(monkeypatch) -> None:
    for key in (
        "DeepSeek_URL",
        "DeepSeek_APIKey",
        "SiliconFlow_URL",
        "SiliconFlow_APIKey",
        "HuoShan_APIKey",
    ):
        monkeypatch.delenv(key, raising=False)


# ----------------------------------------------------------------------
# 迁移函数本身
# ----------------------------------------------------------------------


@pytest.mark.parametrize(("legacy", "expected"), [(True, True), (False, False)])
def test_moves_gentle_language_flag_to_prompt_optimizations(legacy: bool, expected: bool) -> None:
    old = {
        "version": "0.9.0",
        "bot": {"account": 10001},
        "chat": {"gentle_language_enabled": legacy, "reply_mode": "agent"},
    }

    new = migrate_v9_to_v10(old)

    assert new["version"] == "0.10.0"
    assert new["bot"] == {"account": 10001}
    assert "gentle_language_enabled" not in new["chat"]
    assert new["chat"]["reply_mode"] == "agent"
    assert new["prompt_optimizations"] == {"gentle_language": expected}
    # 原配置不被就地改写
    assert old["chat"]["gentle_language_enabled"] is legacy


def test_missing_legacy_flag_leaves_new_section_absent() -> None:
    new = migrate_v9_to_v10({"version": "0.9.0", "chat": {"reply_mode": "agent"}})

    assert new == {"version": "0.10.0", "chat": {"reply_mode": "agent"}}


def test_handwritten_string_bool_is_normalized() -> None:
    new = migrate_v9_to_v10({"version": "0.9.0", "chat": {"gentle_language_enabled": "false"}})

    assert new["prompt_optimizations"] == {"gentle_language": False}


def test_existing_prompt_optimizations_section_is_kept() -> None:
    new = migrate_v9_to_v10(
        {
            "version": "0.9.0",
            "chat": {"gentle_language_enabled": False},
            "prompt_optimizations": {"no_bluffing": False, "gentle_language": True},
        }
    )

    # 显式写入的新分区优先于旧字段
    assert new["prompt_optimizations"] == {"no_bluffing": False, "gentle_language": True}


# ----------------------------------------------------------------------
# 默认值与 Config.load 端到端
# ----------------------------------------------------------------------


def test_new_section_defaults_to_all_true() -> None:
    options = BotConfig().prompt_optimizations

    assert options.cot_enabled is True
    assert options.at_mention_reply is True
    assert options.gentle_language is True
    assert options.avoid_bot_chat is True
    assert options.no_bluffing is True
    assert options.no_game_topics is True
    assert options.no_echo_images is True


def test_load_old_false_keeps_gentle_language_disabled(monkeypatch, tmp_path) -> None:
    _clear_platform_env(monkeypatch)
    monkeypatch.setattr("neobot_app.config.loader.manager.backup_config", lambda *a, **k: None)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        'version = "0.9.0"\n'
        "[bot]\naccount = 10001\n\n"
        "[chat]\n"
        "gentle_language_enabled = false\n",
        encoding="utf-8",
    )

    config = Config.load(cfg_path, BotConfig)

    assert config.version == "0.11.1"
    assert config.prompt_optimizations.gentle_language is False
    assert config.prompt_optimizations.cot_enabled is True
    assert not hasattr(config.chat, "gentle_language_enabled")
    raw = cfg_path.read_text(encoding="utf-8")
    # 旧键不再作为配置项写出（新字段的描述里会提到它的历史名字）
    assert "gentle_language_enabled =" not in raw
    assert "[prompt_optimizations]" in raw
    assert "gentle_language = false" in raw
    assert 'version = "0.11.1"' in raw
