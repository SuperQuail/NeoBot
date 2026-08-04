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
from neobot_app.console.telemetry import ConsoleTelemetry
from neobot_contracts.ports.runtime_event import RuntimeEnvelope
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


def test_credential_store_accepts_any_password_and_hashes_it(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "console" / "auth.json")
    password = ""

    store.set_password(password)

    content = store.path.read_text(encoding="utf-8")
    assert '"algorithm": "scrypt"' in content
    assert store.verify(password) is True
    assert store.verify("incorrect-password") is False

    store.set_password("1")
    assert store.verify("1") is True

    store.set_password("中文 密码")
    assert "中文 密码" not in store.path.read_text(encoding="utf-8")
    assert store.verify("中文 密码") is True


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


def test_console_telemetry_captures_redacted_model_io() -> None:
    async def run() -> None:
        telemetry = ConsoleTelemetry()
        await telemetry.capture(
            RuntimeEnvelope(
                kind="reply_lifecycle",
                stage="model.call.after",
                target="private:42",
                context={"event_id": "evt-1", "mode": "agent"},
                payload={
                    "messages": [{"role": "user", "content": "hello"}],
                    "response": {
                        "content": "world",
                        "api_key": "sk-do-not-leak",
                    },
                },
            )
        )
        snapshot = telemetry.snapshot()
        assert snapshot[0]["target"] == "private:42"
        assert snapshot[0]["input"][0]["content"] == "hello"
        assert "do-not-leak" not in str(snapshot)

    asyncio.run(run())


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
        class FakeApplication:
            def __init__(self) -> None:
                self.restart_requested = False

            def request_restart(self) -> None:
                self.restart_requested = True

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
        application = FakeApplication()
        service.bind_application(application)
        await service.start()
        assert service.admin_url is not None
        assert service.public_url is not None
        jar = aiohttp.CookieJar(unsafe=True)
        try:
            async with ClientSession(cookie_jar=jar) as client:
                status = await client.get(f"{service.admin_url}/api/auth/status")
                assert status.status == 200
                assert status.headers["X-Frame-Options"] == "DENY"
                status_payload = await status.json()
                assert status_payload["setup_allowed"] is True
                assert status_payload["password_file"] == str(
                    (tmp_path / "console" / "auth.json").resolve()
                )

                setup = await client.post(
                    f"{service.admin_url}/api/auth/setup",
                    json={"password": "", "confirmation": ""},
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

                preview = await client.get(
                    f"{service.admin_url}/api/runtime-preview"
                )
                assert preview.status == 200
                preview_payload = await preview.json()
                assert preview_payload["chats"] == []
                assert preview_payload["ai_calls"] == []

                restart = await client.post(
                    f"{service.admin_url}/api/admin/restart",
                    headers={"X-CSRF-Token": csrf},
                )
                assert restart.status == 202
                await asyncio.sleep(0.3)
                assert application.restart_requested is True

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

                password_change = await client.post(
                    f"{service.admin_url}/api/auth/password",
                    headers={
                        "X-CSRF-Token": csrf,
                        "Origin": service.admin_url,
                    },
                    json={"new_password": "No-Web-Password-Change-42!"},
                )
                assert password_change.status == 404

                public_admin = await client.get(
                    f"{service.public_url}/api/admin/config"
                )
                assert public_admin.status == 403
        finally:
            await service.stop()

    asyncio.run(run())


def test_public_console_allows_remote_initial_password_setup(
    tmp_path: Path,
    monkeypatch,
) -> None:
    async def run() -> None:
        config = ConfigProxy(BotConfig())
        config.console.admin_enabled = False
        config.console.enabled = True
        config.console.host = "0.0.0.0"
        config.console.port = _available_port()
        service = ConsoleService(
            config=config,
            data_dir=tmp_path,
            logger=NullLogger(),
        )
        monkeypatch.setattr(
            service,
            "_client_ip",
            lambda _request: "203.0.113.42",
        )
        await service.start()
        try:
            public_base = f"http://127.0.0.1:{service.public_port}"
            async with ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as client:
                status = await client.get(f"{public_base}/api/auth/status")
                assert status.status == 200
                assert (await status.json())["setup_allowed"] is True

                setup = await client.post(
                    f"{public_base}/api/auth/setup",
                    json={
                        "password": "Remote-Console-42!",
                        "confirmation": "Remote-Console-42!",
                    },
                )
                assert setup.status == 200
                assert service.credentials.configured is True
        finally:
            await service.stop()

    asyncio.run(run())


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return int(candidate.getsockname()[1])


async def _instant_sleep(delay: float) -> None:
    """跳过登录失败时的 0.35s 人为延迟，加速限速类用例。"""
    return None


def _make_public_service(tmp_path: Path, *, trust_proxy_headers: bool = False) -> ConsoleService:
    """Arrange 辅助：构造启用公开控制台（仅 public，无 admin）的 ConsoleService。"""
    config = ConfigProxy(BotConfig())
    config.console.admin_enabled = False
    config.console.enabled = True
    config.console.host = "127.0.0.1"
    config.console.port = _available_port()
    config.console.trust_proxy_headers = trust_proxy_headers
    return ConsoleService(
        config=config,
        data_dir=tmp_path,
        logger=NullLogger(),
    )


def test_auth_setup_rejects_second_setup_after_password_configured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """密码已配置后再次调用 /api/auth/setup 必须返回 409，防止抢注覆盖原密码。"""
    async def run() -> None:
        service = _make_public_service(tmp_path)
        await service.start()
        try:
            async with ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as client:
                first = await client.post(
                    f"http://127.0.0.1:{service.public_port}/api/auth/setup",
                    json={"password": "First-Password-1!", "confirmation": "First-Password-1!"},
                )
                assert first.status == 200

                second = await client.post(
                    f"http://127.0.0.1:{service.public_port}/api/auth/setup",
                    json={"password": "Evil-Password-2!", "confirmation": "Evil-Password-2!"},
                )
                assert second.status == 409
                assert "已经设置" in (await second.json())["error"]

                assert service.credentials.verify("First-Password-1!") is True
                assert service.credentials.verify("Evil-Password-2!") is False
        finally:
            await service.stop()

    asyncio.run(run())


def test_login_rate_limit_returns_429_after_repeated_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """连续 5 次密码错误后第 6 次登录必须返回 429 且携带 Retry-After 头。"""
    async def run() -> None:
        service = _make_public_service(tmp_path)
        service.credentials.set_password("s3cret-pw")
        monkeypatch.setattr(service_module.asyncio, "sleep", _instant_sleep)
        await service.start()
        try:
            async with ClientSession() as client:
                statuses: list[int] = []
                for _ in range(6):
                    response = await client.post(
                        f"http://127.0.0.1:{service.public_port}/api/auth/login",
                        json={"password": "wrong-password"},
                    )
                    statuses.append(response.status)
                    if response.status == 429:
                        assert response.headers["Retry-After"].isdigit()

                assert statuses == [401, 401, 401, 401, 401, 429]
        finally:
            await service.stop()

    asyncio.run(run())


def test_xff_headers_cannot_bypass_login_rate_limit_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """默认不信任代理头时，轮换 X-Forwarded-For 无法绕过登录限速（负例）。"""
    async def run() -> None:
        service = _make_public_service(tmp_path)
        service.credentials.set_password("s3cret-pw")
        monkeypatch.setattr(service_module.asyncio, "sleep", _instant_sleep)
        await service.start()
        try:
            async with ClientSession() as client:
                statuses: list[int] = []
                for index in range(6):
                    response = await client.post(
                        f"http://127.0.0.1:{service.public_port}/api/auth/login",
                        headers={"X-Forwarded-For": f"203.0.113.{index}"},
                        json={"password": "wrong-password"},
                    )
                    statuses.append(response.status)

                assert statuses == [401, 401, 401, 401, 401, 429]
        finally:
            await service.stop()

    asyncio.run(run())


def test_client_ip_ignores_xff_without_proxy_trust(tmp_path: Path) -> None:
    """未开启 trust_proxy_headers 时 _client_ip 必须忽略 XFF 头，返回真实 peer 地址。"""
    service = _make_public_service(tmp_path)

    async def run() -> None:
        request = _mocked_request(headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"})
        assert service._client_ip(request) == "127.0.0.1"

    asyncio.run(run())


def test_client_ip_trusts_first_xff_entry_when_proxy_headers_enabled(tmp_path: Path) -> None:
    """开启 trust_proxy_headers 后 _client_ip 必须取 XFF 首个条目。"""
    service = _make_public_service(tmp_path, trust_proxy_headers=True)

    async def run() -> None:
        request = _mocked_request(headers={"X-Forwarded-For": "203.0.113.9, 10.0.0.1"})
        assert service._client_ip(request) == "203.0.113.9"

    asyncio.run(run())


def _mocked_request(headers: dict):
    """Arrange 辅助：构造 peer 为 127.0.0.1 的假 aiohttp 请求。"""
    from aiohttp.test_utils import make_mocked_request

    class _FakeTransport:
        def get_extra_info(self, key: str):
            if key == "peername":
                return ("127.0.0.1", 54321)
            return None

    return make_mocked_request("GET", "/api/auth/status", headers=headers, transport=_FakeTransport())
