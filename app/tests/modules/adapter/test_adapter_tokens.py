"""适配器鉴权 token 的配置贯通测试。

覆盖两类 token：
- ``local_auth_token``：local 模式 HTTP/WS 的 Bearer token；
- ``reverse_ws_access_token``：OneBot 反向 WebSocket 握手 token。

历史上 ``[adapter]`` 与 ``AdapterSettings`` 都缺少 local token 字段，
``assembly/adapter.py`` 的 ``getattr(..., "local_auth_token", "")`` 永远取空，
导致 local 适配器已实现的鉴权中间件形同虚设。
"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_adapter import AdapterSettings
from neobot_app.assembly.adapter import _settings_from_config
from neobot_app.config.schemas.bot import Adapter


def test_adapter_schema_has_local_auth_token() -> None:
    assert Adapter().local_auth_token == ""
    assert Adapter(local_auth_token="L").local_auth_token == "L"


def test_adapter_schema_has_reverse_ws_access_token() -> None:
    assert Adapter().reverse_ws_access_token == ""
    assert Adapter(reverse_ws_access_token="R").reverse_ws_access_token == "R"


def test_settings_from_config_carries_both_tokens() -> None:
    config = SimpleNamespace(
        adapter=Adapter(local_auth_token="LOCAL", reverse_ws_access_token="REVERSE"),
        bot=SimpleNamespace(account=10001, nick_name="NeoBot"),
    )
    settings = _settings_from_config(config)
    assert isinstance(settings, AdapterSettings)
    assert settings.local_auth_token == "LOCAL"
    assert settings.reverse_ws_access_token == "REVERSE"


def test_settings_default_tokens_are_empty() -> None:
    config = SimpleNamespace(adapter=Adapter(), bot=SimpleNamespace(account=0, nick_name=""))
    settings = _settings_from_config(config)
    assert settings.local_auth_token == ""
    assert settings.reverse_ws_access_token == ""
