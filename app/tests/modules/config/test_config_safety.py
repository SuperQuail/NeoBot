"""配置加载的安全语义测试。

覆盖两条路径：
1. 配置文件解析失败时**不得**用默认值整份覆盖用户配置（原行为会先备份、
   再用 schema 默认值重写整份文件，用户设置全部丢失）；
2. 写回（补全缺失项/生成）必须是原子的，不留半截文件。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import tomlkit

from neobot_app.config.loader.manager import Config, ConfigLoadError
from neobot_app.config.schemas.bot import BotConfig

_BROKEN_TOML = "this is {{{ not valid toml"


def _clear_platform_env(monkeypatch) -> None:
    for key in (
        "DeepSeek_URL",
        "DeepSeek_APIKey",
        "SiliconFlow_URL",
        "SiliconFlow_APIKey",
        "HuoShan_APIKey",
    ):
        monkeypatch.delenv(key, raising=False)


def test_broken_toml_keeps_original_file(monkeypatch, tmp_path: Path) -> None:
    """语法错误时报错并保持原文件内容，不能被默认值覆盖。"""
    _clear_platform_env(monkeypatch)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(_BROKEN_TOML, encoding="utf-8")

    with pytest.raises(ConfigLoadError) as excinfo:
        Config.load(cfg_path, BotConfig)

    assert "解析失败" in str(excinfo.value)
    assert cfg_path.read_text(encoding="utf-8") == _BROKEN_TOML


def test_broken_toml_does_not_write_backup(monkeypatch, tmp_path: Path) -> None:
    """解析失败时连备份/覆盖都不应发生（文件保持原样即可）。"""
    _clear_platform_env(monkeypatch)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(_BROKEN_TOML, encoding="utf-8")
    backup_calls: list[tuple] = []
    monkeypatch.setattr(
        "neobot_app.config.loader.manager.backup_config",
        lambda *args, **kwargs: backup_calls.append(args),
    )

    with pytest.raises(ConfigLoadError):
        Config.load(cfg_path, BotConfig)

    assert backup_calls == []


def test_missing_file_is_generated_as_parseable_toml(
    monkeypatch, tmp_path: Path
) -> None:
    """缺平台密钥不影响配置文件生成：文件必须已生成且可解析。"""
    _clear_platform_env(monkeypatch)
    cfg_path = tmp_path / "bot.toml"

    Config.load(cfg_path, BotConfig)

    assert cfg_path.is_file()
    doc = tomlkit.parse(cfg_path.read_text(encoding="utf-8")).unwrap()
    assert doc["bot"]["account"] == 0


def test_write_back_is_atomic_and_leaves_no_temp_files(
    monkeypatch, tmp_path: Path
) -> None:
    """补全缺失项走临时文件 + os.replace，目录里不留 .tmp 残片。"""
    _clear_platform_env(monkeypatch)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text('[bot]\naccount = 10001\n\n[chat]\n', encoding="utf-8")
    monkeypatch.setattr(
        "neobot_app.config.loader.manager.backup_config", lambda *a, **k: None
    )

    Config.load(cfg_path, BotConfig)

    doc = tomlkit.parse(cfg_path.read_text(encoding="utf-8")).unwrap()
    assert doc["bot"]["account"] == 10001  # 用户填的值必须保留
    assert "models" in doc  # 缺失项已补全
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []
