"""QQ 官方协议配置：schema 默认值、official_mode 非法回落、热重载分类与环境变量补全。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_adapter import AdapterSettings
from neobot_app.assembly.adapter import _settings_from_config
from neobot_app.config.hot_reload import is_hot_reloadable
from neobot_app.config.schemas.bot import Adapter, Bot
from neobot_app.config.schemas.bot_parts.core import (
    OFFICIAL_MODES,
    normalize_official_mode,
)
from neobot_app.core import DATA_DIR

_QQ_ENV_KEYS = ("NEOBOT_QQ_APPID", "NEOBOT_QQ_SECRET", "NEOBOT_QQ_BASE_URL")


def _field_description(cls: type, name: str) -> str:
    return str(cls.__dataclass_fields__[name].metadata.get("description", ""))


def test_adapter_qq_defaults() -> None:
    adapter = Adapter()

    assert adapter.mode == "official"
    assert adapter.qq_appid == ""
    assert adapter.qq_client_secret == ""
    assert adapter.qq_base_url == "https://api.bot.qq.com"
    assert adapter.qq_token_url == "https://api.bot.qq.com/app/getAppAccessToken"
    assert adapter.qq_portal_host == "q.qq.com"


def test_adapter_mode_description_mentions_official() -> None:
    assert "official" in _field_description(Adapter, "mode")


def test_bot_official_mode_defaults_to_auto() -> None:
    assert Bot().official_mode == "auto"
    assert OFFICIAL_MODES == ("auto", "official", "unofficial")


def test_bot_official_mode_description_documents_values_and_unconnected() -> None:
    description = _field_description(Bot, "official_mode")

    for token in ("auto", "official", "unofficial", "未连接"):
        assert token in description


def test_every_qq_field_has_description() -> None:
    for name in (
        "qq_appid",
        "qq_client_secret",
        "qq_base_url",
        "qq_token_url",
        "qq_portal_host",
    ):
        assert _field_description(Adapter, name), name


def test_normalize_official_mode_falls_back_to_auto() -> None:
    assert normalize_official_mode("auto") == "auto"
    assert normalize_official_mode(" OFFICIAL ") == "official"
    assert normalize_official_mode("unofficial") == "unofficial"
    assert normalize_official_mode("nonsense") == "auto"
    assert normalize_official_mode(None) == "auto"
    assert normalize_official_mode("") == "auto"


def test_identity_config_is_hot_reloadable() -> None:
    """account / official_mode 连接后可重放身份判定，不需要重启。"""
    assert is_hot_reloadable(("bot", "account")) is True
    assert is_hot_reloadable(("bot", "official_mode")) is True


def test_settings_from_config_carries_qq_fields(monkeypatch) -> None:
    for key in _QQ_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    config = SimpleNamespace(
        adapter=Adapter(
            qq_appid="app-id",
            qq_client_secret="client-secret",
            qq_base_url="https://api.example.test",
            qq_token_url="https://api.example.test/token",
            qq_portal_host="portal.example.test",
        ),
        bot=SimpleNamespace(account=0, nick_name=""),
    )

    settings = _settings_from_config(config)

    assert isinstance(settings, AdapterSettings)
    assert settings.qq_appid == "app-id"
    assert settings.qq_client_secret == "client-secret"
    assert settings.qq_base_url == "https://api.example.test"
    assert settings.qq_token_url == "https://api.example.test/token"
    assert settings.qq_portal_host == "portal.example.test"
    assert settings.data_dir == str(DATA_DIR)


def test_env_vars_fill_qq_settings(monkeypatch) -> None:
    """不到 config.toml 里写凭据：环境变量补全 qq_appid / secret / base_url。"""
    for key in _QQ_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NEOBOT_QQ_APPID", "ENV_APP")
    monkeypatch.setenv("NEOBOT_QQ_SECRET", "ENV_SECRET")
    monkeypatch.setenv("NEOBOT_QQ_BASE_URL", "https://env.example.test")
    config = SimpleNamespace(
        adapter=Adapter(),
        bot=SimpleNamespace(account=0, nick_name=""),
    )

    settings = _settings_from_config(config)

    assert settings.qq_appid == "ENV_APP"
    assert settings.qq_client_secret == "ENV_SECRET"
    assert settings.qq_base_url == "https://env.example.test"


def test_config_values_pass_through_without_env(monkeypatch) -> None:
    for key in _QQ_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    config = SimpleNamespace(
        adapter=Adapter(),
        bot=SimpleNamespace(account=0, nick_name=""),
    )

    settings = _settings_from_config(config)

    assert settings.qq_appid == ""
    assert settings.qq_client_secret == ""
    assert settings.qq_base_url == "https://api.bot.qq.com"
