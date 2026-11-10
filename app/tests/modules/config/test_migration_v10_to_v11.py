"""0.10.0 -> 0.11.0：通道模式默认值语义（老配置升级 onebot，新部署 official）。"""

from __future__ import annotations

from neobot_app.config.loader.manager import Config
from neobot_app.config.migrations import ensure_legacy_adapter_mode, migrate_v10_to_v11
from neobot_app.config.schemas.bot import BotConfig

_DEEPSEEK_KEYS = {
    "DeepSeek_URL": "https://api.deepseek.com",
    "DeepSeek_APIKey": "sk-deepseek-test-1234567890",
}


def _prepare(monkeypatch) -> None:
    for key in (
        "DeepSeek_URL",
        "DeepSeek_APIKey",
        "SiliconFlow_URL",
        "SiliconFlow_APIKey",
        "HuoShan_APIKey",
    ):
        monkeypatch.delenv(key, raising=False)
    for key, value in _DEEPSEEK_KEYS.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(
        "neobot_app.config.loader.manager.backup_config", lambda *a, **k: None
    )


def test_migration_fills_onebot_when_mode_missing() -> None:
    new = migrate_v10_to_v11(
        {"version": "0.10.0", "adapter": {"qq_appid": "appid"}}
    )

    assert new["version"] == "0.11.0"
    assert new["adapter"]["mode"] == "onebot"
    assert new["adapter"]["qq_appid"] == "appid"


def test_migration_preserves_explicit_mode() -> None:
    for mode in ("onebot", "official", "dual", "local"):
        new = migrate_v10_to_v11({"version": "0.10.0", "adapter": {"mode": mode}})
        assert new["adapter"]["mode"] == mode


def test_legacy_without_version_defaults_onebot() -> None:
    data: dict = {"bot": {"account": 10001}}
    ensure_legacy_adapter_mode(data)
    assert data["adapter"]["mode"] == "onebot"


def test_fresh_config_defaults_to_official(monkeypatch, tmp_path) -> None:
    _prepare(monkeypatch)
    cfg_path = tmp_path / "bot.toml"

    config = Config.load(cfg_path, BotConfig)

    assert config.version == "0.11.0"
    assert config.adapter.mode == "official"
    raw = cfg_path.read_text(encoding="utf-8")
    assert 'mode = "official"' in raw
    assert 'version = "0.11.0"' in raw


def test_upgraded_config_defaults_to_onebot(monkeypatch, tmp_path) -> None:
    _prepare(monkeypatch)
    cfg_path = tmp_path / "bot.toml"
    cfg_path.write_text(
        'version = "0.10.0"\n'
        "[bot]\naccount = 10001\n\n"
        "[adapter]\n"
        'qq_appid = "appid"\n',
        encoding="utf-8",
    )

    config = Config.load(cfg_path, BotConfig)

    assert config.version == "0.11.0"
    assert config.adapter.mode == "onebot"
    raw = cfg_path.read_text(encoding="utf-8")
    assert 'mode = "onebot"' in raw
    assert 'version = "0.11.0"' in raw
