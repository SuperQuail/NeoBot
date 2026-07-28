from __future__ import annotations

import asyncio
import socket
from pathlib import Path

import aiohttp
import neobot_app.console.security as security_module
import neobot_app.console.service as service_module
import tomlkit
from aiohttp import ClientSession
from neobot_app.config.loader.converter import dataclass_to_toml, dict_to_dataclass
from neobot_app.config.proxy import ConfigProxy
from neobot_app.config.schemas.bot import BotConfig, Console
from neobot_app.console.security import CredentialStore, SessionStore, redact
from neobot_app.console.service import ConsoleService
from neobot_contracts.ports.logging import NullLogger


def test_console_defaults_and_config_backfill() -> None:
    defaults = BotConfig().console
    assert defaults.enabled is False
    assert defaults.host == "0.0.0.0"
    assert defaults.port == 9981
    assert defaults.admin_enabled is True
    assert defaults.admin_port == 9891
    assert defaults.port_search_limit == 100

    config = dict_to_dataclass({"version": "0.3.0"}, BotConfig)
    assert config.console.enabled is False
    assert config.console.admin_enabled is True


def test_console_config_rejects_unsafe_ranges() -> None:
    try:
        Console(port_search_limit=101)
    except ValueError as exc:
        assert "port_search_limit" in str(exc)
    else:
        raise AssertionError("invalid console port search limit was accepted")


def test_credential_store_hashes_and_verifies_password(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "console" / "auth.json")
    password = "Correct-Horse-42!"

    store.set_password(password)

    content = store.path.read_text(encoding="utf-8")
    assert password not in content
    assert store.verify(password) is True
    assert store.verify("incorrect-password") is False


def test_session_store_expires_idle_sessions(monkeypatch) -> None:
    now = 1000.0
    monkeypatch.setattr(security_module.time, "time", lambda: now)
    sessions = SessionStore(timeout_seconds=300)
    token, _session = sessions.create()
    assert sessions.get(token) is not None

    now = 1301.0
    assert sessions.get(token) is None


def test_redact_hides_nested_and_inline_secrets() -> None:
    payload = {
        "api_key": "sk-super-secret-value",
        "message": "Authorization=Bearer-example-token",
        "nested": {"password": "hunter2"},
    }

    redacted = redact(payload)

    assert "super-secret" not in str(redacted)
    assert "Bearer-example-token" not in str(redacted)
    assert "hunter2" not in str(redacted)


def test_console_falls_back_from_occupied_port(tmp_path: Path) -> None:
    async def run() -> None:
        occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        preferred = occupied.getsockname()[1]
        config = ConfigProxy(BotConfig())
        config.console.admin_port = preferred
        config.console.port_search_limit = 5
        service = ConsoleService(
            config=config,
            data_dir=tmp_path,
            logger=NullLogger(),
        )
        try:
            await service.start()
            assert service.admin_url is not None
            assert not service.admin_url.endswith(f":{preferred}")
            assert service.public_url is None
        finally:
            await service.stop()
            occupied.close()

    asyncio.run(run())


def test_environment_update_preserves_other_lines(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# provider\nDeepSeek_APIKey=old\nOther_URL=https://example.com\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(service_module, "ENV_FILE", env_path)

    ConsoleService._write_environment_value("DeepSeek_APIKey", "new-secret")
    ConsoleService._write_environment_value("New_APIKey", "added-secret")
    content = env_path.read_text(encoding="utf-8")

    assert "# provider" in content
    assert "DeepSeek_APIKey=new-secret" in content
    assert "Other_URL=https://example.com" in content
    assert "New_APIKey=added-secret" in content

    ConsoleService._delete_environment_value("DeepSeek_APIKey")
    assert "DeepSeek_APIKey" not in env_path.read_text(encoding="utf-8")


def test_http_auth_csrf_config_and_role_isolation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def run() -> None:
        config_path = tmp_path / "config.toml"
        backup_dir = tmp_path / "config_backup"
        document, _required, _optional = dataclass_to_toml(BotConfig)
        assert document is not None
        config_path.write_text(tomlkit.dumps(document), encoding="utf-8")
        monkeypatch.setattr(service_module, "CONFIG_FILE", config_path)
        monkeypatch.setattr(service_module, "CONFIG_BACKUP_DIR", backup_dir)

        config = ConfigProxy(BotConfig())
        config.console.enabled = True
        config.console.host = "127.0.0.1"
        config.console.admin_port = _available_port()
        config.console.port = _available_port()
        service = ConsoleService(
            config=config,
            data_dir=tmp_path,
            logger=NullLogger(),
        )
        await service.start()
        assert service.admin_url is not None
        assert service.public_url is not None
        jar = aiohttp.CookieJar(unsafe=True)
        try:
            async with ClientSession(cookie_jar=jar) as client:
                status = await client.get(f"{service.admin_url}/api/auth/status")
                assert status.status == 200
                assert status.headers["X-Frame-Options"] == "DENY"
                assert (await status.json())["setup_allowed"] is True

                weak = await client.post(
                    f"{service.admin_url}/api/auth/setup",
                    json={"password": "weak", "confirmation": "weak"},
                )
                assert weak.status == 400

                setup = await client.post(
                    f"{service.admin_url}/api/auth/setup",
                    json={
                        "password": "Strong-Console-42!",
                        "confirmation": "Strong-Console-42!",
                    },
                )
                assert setup.status == 200
                csrf = (await setup.json())["csrf_token"]

                config_response = await client.get(
                    f"{service.admin_url}/api/admin/config"
                )
                assert config_response.status == 200
                assert any(
                    section["path"] == "console"
                    for section in (await config_response.json())["sections"]
                )

                rejected = await client.patch(
                    f"{service.admin_url}/api/admin/config",
                    json={"updates": [{"path": "console.enabled", "value": True}]},
                )
                assert rejected.status == 403

                updated = await client.patch(
                    f"{service.admin_url}/api/admin/config",
                    headers={
                        "X-CSRF-Token": csrf,
                        "Origin": service.admin_url,
                    },
                    json={"updates": [{"path": "console.enabled", "value": True}]},
                )
                assert updated.status == 200
                assert config.console.enabled is True

                invalid = await client.patch(
                    f"{service.admin_url}/api/admin/config",
                    headers={
                        "X-CSRF-Token": csrf,
                        "Origin": service.admin_url,
                    },
                    json={
                        "updates": [
                            {"path": "console.port_search_limit", "value": 101}
                        ]
                    },
                )
                assert invalid.status == 400

                public_admin = await client.get(
                    f"{service.public_url}/api/admin/config"
                )
                assert public_admin.status == 403
        finally:
            await service.stop()

    asyncio.run(run())


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])
