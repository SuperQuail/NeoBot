"""面板保存边界：表单回传的字符串值必须转成声明类型。

前端输入框一律回传字符串（"0.5" / "2048"）。旧实现直接拿字符串去校验/落盘：
要么「校验通过、保存 400」，要么把字符串写进 config.toml（下次加载静默回默认值）。
这里守住 save / validate / update_models / update_section 四条路径同源转换。
"""

from __future__ import annotations

import socket
import tomllib
from pathlib import Path

import httpx
import pytest

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.config_manager import (
    BotConfigManager,
    ConfigValidationError,
)
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.panel_auth import PanelPasswordStore

PASSWORD = "NeoBot-Panel-2026"

CONFIG_TEXT = (
    'version = "0.6.0"\n'
    "\n[chat]\n"
    "reply_blacklist = [111]\n"
    "\n[chat.group_response_coefficient]\n"
    "111 = 0.5\n"
)


class _NullLogger:
    def debug(self, *args, **kwargs) -> None: ...
    def info(self, *args, **kwargs) -> None: ...
    def warning(self, *args, **kwargs) -> None: ...
    def error(self, *args, **kwargs) -> None: ...
    def exception(self, *args, **kwargs) -> None: ...


def _manager(tmp_path: Path) -> tuple[BotConfigManager, Path]:
    config_path = tmp_path / "config.toml"
    config_path.write_text(CONFIG_TEXT, encoding="utf-8")
    return (
        BotConfigManager(config_path=config_path, backup_dir=tmp_path / "backup"),
        config_path,
    )


def _stringified(document: dict) -> dict:
    """模拟前端表单：数字/列表元素一律回传成字符串。"""
    config = document["config"]
    chat = {
        **config["chat"],
        "group_response_coefficient": {"111": "0.5"},
        "reply_blacklist": ["123"],
    }
    registry = [dict(entry) for entry in config["models"]["registry"]]
    registry[0] = {
        **registry[0],
        "settings": {**registry[0]["settings"], "max_output_tokens": "2048"},
    }
    return {**config, "chat": chat, "models": {**config["models"], "registry": registry}}


def test_save_coerces_stringified_values(tmp_path: Path) -> None:
    manager, config_path = _manager(tmp_path)

    manager.save(config=_stringified(manager.read()))

    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["chat"]["group_response_coefficient"]["111"] == 0.5
    assert saved["chat"]["reply_blacklist"] == [123]
    assert saved["models"]["registry"][0]["settings"]["max_output_tokens"] == 2048


def test_validate_agrees_with_save(tmp_path: Path) -> None:
    manager, _ = _manager(tmp_path)

    assert manager.validate(config=_stringified(manager.read())) == []


def test_invalid_string_is_rejected_with_path(tmp_path: Path) -> None:
    manager, config_path = _manager(tmp_path)
    config = _stringified(manager.read())
    config["chat"]["group_response_coefficient"] = {"111": "abc"}

    errors = manager.validate(config=config)
    assert [error["path"] for error in errors] == ["chat.group_response_coefficient.111"]
    with pytest.raises(ConfigValidationError) as excinfo:
        manager.save(config=config)
    assert excinfo.value.errors == errors
    assert "abc" not in config_path.read_text(encoding="utf-8")


def test_update_models_coerces_stringified_settings(tmp_path: Path) -> None:
    manager, config_path = _manager(tmp_path)

    manager.update_models(
        upsert={
            "model_ref": "m1",
            "model_name": "deepseek-chat",
            "model_type": "chat",
            "provider": "DeepSeek",
            "settings": {"temperature": "0.7", "max_output_tokens": "512"},
        }
    )

    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    entry = saved["models"]["registry"][-1]
    assert entry["settings"]["temperature"] == 0.7
    assert entry["settings"]["max_output_tokens"] == 512


def test_update_section_coerces_stringified_values(tmp_path: Path) -> None:
    manager, config_path = _manager(tmp_path)

    manager.update_section("debug", {"retention_days": "20", "enabled": "true"})

    saved = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert saved["debug"]["retention_days"] == 20
    assert saved["debug"]["enabled"] is True


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _panel(tmp_path: Path):
    config_path = tmp_path / "config.toml"
    config_path.write_text(CONFIG_TEXT, encoding="utf-8")
    data_dir = tmp_path / "data"
    PanelPasswordStore(data_dir / "auth.json").set_password(PASSWORD)
    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(host="127.0.0.1", port=_free_port()),
        data_dir=data_dir,
        logger=_NullLogger(),
        config_path=config_path,
        env_path=tmp_path / ".env",
        backup_dir=tmp_path / "backup",
    )
    await server.start()
    return server, config_path, f"http://127.0.0.1:{server.bound_port}"


async def _login(base: str) -> dict[str, str]:
    async with httpx.AsyncClient() as client:
        response = await client.post(base + "/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200, response.text
    payload = response.json()
    return {"X-Token": payload["token"], "X-CSRF-Token": payload["csrf_token"]}


async def test_api_save_accepts_stringified_form(tmp_path: Path) -> None:
    server, config_path, base = await _panel(tmp_path)
    try:
        headers = await _login(base)
        async with httpx.AsyncClient() as client:
            read = await client.get(base + "/api/config", headers=headers)
            document = read.json()
            saved = await client.post(
                base + "/api/config",
                headers=headers,
                json={
                    "revision": document["revision"],
                    "mode": "form",
                    "config": _stringified(document),
                },
            )
    finally:
        await server.stop()

    assert read.status_code == 200, read.text
    assert saved.status_code == 200, saved.text
    on_disk = tomllib.loads(config_path.read_text(encoding="utf-8"))
    assert on_disk["chat"]["group_response_coefficient"]["111"] == 0.5
    assert on_disk["chat"]["reply_blacklist"] == [123]
    assert on_disk["models"]["registry"][0]["settings"]["max_output_tokens"] == 2048


async def test_api_validate_and_save_agree_on_invalid_string(tmp_path: Path) -> None:
    server, config_path, base = await _panel(tmp_path)
    try:
        headers = await _login(base)
        async with httpx.AsyncClient() as client:
            read = await client.get(base + "/api/config", headers=headers)
            document = read.json()
            payload = {
                "revision": document["revision"],
                "mode": "form",
                "config": {
                    **_stringified(document),
                    "chat": {
                        **document["config"]["chat"],
                        "group_response_coefficient": {"111": "abc"},
                    },
                },
            }
            validated = await client.post(
                base + "/api/config/validate", headers=headers, json=payload
            )
            saved = await client.post(base + "/api/config", headers=headers, json=payload)
    finally:
        await server.stop()

    assert validated.status_code == 400, validated.text
    assert saved.status_code == 400, saved.text
    assert validated.json()["errors"] == saved.json()["errors"]
    assert saved.json()["errors"][0]["path"] == "chat.group_response_coefficient.111"
    assert "abc" not in config_path.read_text(encoding="utf-8")
