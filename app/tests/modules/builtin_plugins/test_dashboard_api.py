"""官方 dashboard 插件：HTTP 接口与鉴权集成测试。

直接启动真实的 aiohttp 服务（随机端口）并请求，覆盖登录、CSRF、
配置读取/保存与冲突检测、.env 脱敏与插件列表等关键路径。
"""

from __future__ import annotations

import socket
from pathlib import Path

import httpx
import pytest

from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_app.panel_auth import PanelPasswordStore

PASSWORD = "NeoBot-Panel-2026"


class _NullLogger:
    def debug(self, *args, **kwargs) -> None: ...
    def info(self, *args, **kwargs) -> None: ...
    def warning(self, *args, **kwargs) -> None: ...
    def error(self, *args, **kwargs) -> None: ...
    def exception(self, *args, **kwargs) -> None: ...


class _FakeAdapter:
    connected = True

    async def call_api(self, action: str, params: dict, timeout: float = 5.0):
        if action == "get_login_info":
            return {"status": "ok", "data": {"user_id": 10001, "nickname": "测试机器人"}}
        if action == "get_version_info":
            return {"status": "ok", "data": {"app_name": "NapCat", "app_version": "1.0"}}
        return {"status": "ok", "data": {}}


class _FakeSnapshot:
    def __init__(
        self,
        name: str,
        *,
        source: str = "third_party",
        hot_reload: bool = True,
        config_hot_reload: bool = True,
    ) -> None:
        self.name = name
        self.version = "1.0.0"
        self.state = "running"
        self.enabled = True
        self.path = Path("/tmp") / name
        self.kind = "package"
        self.error = None
        self.description = "测试插件"
        self.author = "tester"
        self.dependencies = ()
        self.python_dependencies = ()
        self.missing_python_dependencies = ()
        self.source = source
        self.repo = ""
        self.branch = ""
        self.homepage = ""
        self.license = ""
        self.tags = ()
        self.hot_reload = hot_reload
        self.config_hot_reload = config_hot_reload

    @property
    def official(self) -> bool:
        return self.source == "official"

    @property
    def manageable(self) -> bool:
        return not self.official

    @property
    def hot_reloadable(self) -> bool:
        return self.hot_reload and self.kind != "unknown"


class _FakeControl:
    def __init__(self, plugins_data: Path | None = None) -> None:
        self.snapshots = [
            _FakeSnapshot(
                "dashboard", source="official", hot_reload=False, config_hot_reload=False
            ),
            _FakeSnapshot("demo"),
        ]
        self.installer_available = True
        self.enabled_calls: list[tuple[str, bool]] = []
        self.proxy_mode = "system"
        self.plugins_data = Path(plugins_data or "/tmp/plugins_data")

    def plugin_config_path(self, name: str) -> Path:
        """插件配置一律在插件数据目录下。"""
        return self.plugins_data / name / "config.toml"

    def plugin_config_defaults(self, name: str) -> dict:
        if name == "dashboard":
            return {"host": "0.0.0.0", "port": 9981}
        return {}

    def installer_proxy(self) -> dict:
        from neobot_modloader.installer import ProxySettings

        return ProxySettings(mode=self.proxy_mode).to_dict()

    def set_installer_proxy(self, *, mode=None, host=None, port=None) -> dict:
        from neobot_modloader.installer import ProxySettings

        settings = ProxySettings(
            mode=mode or self.proxy_mode,
            host=host or "127.0.0.1",
            port=port or 7890,
        )
        self.proxy_mode = settings.mode
        return settings.to_dict()

    def config_model(self, name: str):
        if name != "dashboard":
            return None
        from neobot_app.builtin_plugins.dashboard.config import DashboardConfig

        return DashboardConfig

    def snapshot(self):
        return list(self.snapshots)

    async def set_enabled(self, name: str, enabled: bool):
        self.enabled_calls.append((name, enabled))
        from neobot_modloader import PluginOperationResult

        return PluginOperationResult(ok=True, name=name, state="running" if enabled else "unloaded")

    async def reload(self, name: str):
        from neobot_modloader import PluginOperationResult

        return PluginOperationResult(ok=True, name=name, state="running")

    async def check_updates(self):
        return []


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _start_panel(
    tmp_path: Path,
    *,
    password: str | None = PASSWORD,
    trust_proxy: bool = False,
    services=None,
):
    config_path = tmp_path / "config.toml"
    config_path.write_text('version = "0.6.0"\n', encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text("DeepSeek_APIKey=sk-super-secret\n", encoding="utf-8")

    data_dir = tmp_path / "data"
    if password is not None:
        PanelPasswordStore(data_dir / "auth.json").set_password(password)

    control = _FakeControl(tmp_path / "plugins_data")
    server = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(
            host="127.0.0.1",
            port=_free_port(),
            trust_proxy_headers=trust_proxy,
        ),
        data_dir=data_dir,
        logger=_NullLogger(),
        adapter=_FakeAdapter(),
        plugin_control=control,
        services=services,
        config_path=config_path,
        env_path=env_path,
        backup_dir=tmp_path / "backup",
    )
    await server.start()
    return server, control, f"http://127.0.0.1:{server.bound_port}", config_path


@pytest.fixture()
async def panel(tmp_path: Path):
    server, control, base, config_path = await _start_panel(tmp_path)
    try:
        yield server, control, base, config_path
    finally:
        await server.stop()


async def _login(base: str, password: str = PASSWORD) -> tuple[str, str]:
    async with httpx.AsyncClient() as client:
        response = await client.post(base + "/api/auth/login", json={"password": password})
    assert response.status_code == 200, response.text
    payload = response.json()
    return payload["token"], payload["csrf_token"]


async def test_healthz_and_auth_status(panel) -> None:
    _, _, base, _ = panel
    async with httpx.AsyncClient() as client:
        health = await client.get(base + "/healthz")
        status = await client.get(base + "/api/auth/status")

    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert status.status_code == 200
    assert status.json()["authenticated"] is False


async def test_login_rejects_wrong_password(panel) -> None:
    _, _, base, _ = panel
    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/api/auth/login", json={"password": "wrong-password"}
        )

    assert response.status_code == 401
    assert response.json()["ok"] is False


async def test_status_reports_password_configured(panel) -> None:
    _, _, base, _ = panel
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/auth/status")

    payload = response.json()
    assert payload["configured"] is True
    assert payload["setup_required"] is False
    assert payload["loopback"] is True


async def test_unconfigured_panel_blocks_external_access(tmp_path: Path) -> None:
    """未设置密码时，外网来源必须被拒绝，且提示设置方式。"""
    server, _, base, _ = await _start_panel(
        tmp_path, password=None, trust_proxy=True
    )
    try:
        headers = {"X-Forwarded-For": "203.0.113.9"}
        async with httpx.AsyncClient() as client:
            status = await client.get(base + "/api/auth/status", headers=headers)
            overview = await client.get(base + "/api/overview", headers=headers)
            login = await client.post(
                base + "/api/auth/login", json={"password": PASSWORD}, headers=headers
            )
            setup = await client.post(
                base + "/api/auth/setup",
                json={"password": PASSWORD, "confirm": PASSWORD},
                headers=headers,
            )

        assert status.json()["loopback"] is False
        assert status.json()["setup_allowed"] is False
        assert overview.status_code == 403
        assert "外网" in overview.json()["error"]
        assert login.status_code == 403
        assert setup.status_code == 403
        assert server.passwords.configured is False
    finally:
        await server.stop()


async def test_unconfigured_panel_allows_loopback_setup(tmp_path: Path) -> None:
    """本机访问未配置密码的面板时，只允许进入设置流程。"""
    server, _, base, _ = await _start_panel(tmp_path, password=None)
    try:
        async with httpx.AsyncClient() as client:
            status = await client.get(base + "/api/auth/status")
            blocked = await client.get(base + "/api/overview")
            weak = await client.post(
                base + "/api/auth/setup", json={"password": "short", "confirm": "short"}
            )
            mismatch = await client.post(
                base + "/api/auth/setup",
                json={"password": PASSWORD, "confirm": PASSWORD + "x"},
            )
            ok = await client.post(
                base + "/api/auth/setup",
                json={"password": PASSWORD, "confirm": PASSWORD},
            )
            overview = await client.get(
                base + "/api/overview", headers={"X-Token": ok.json()["token"]}
            )

        assert status.json()["setup_allowed"] is True
        assert blocked.status_code == 403
        assert blocked.json()["setup_required"] is True
        assert weak.status_code == 400
        assert mismatch.status_code == 400
        assert ok.status_code == 200
        assert server.passwords.verify(PASSWORD) is True
        assert overview.status_code == 200
    finally:
        await server.stop()


async def test_password_change_invalidates_existing_sessions(panel) -> None:
    server, _, base, _ = panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        before = await client.get(base + "/api/overview", headers={"X-Token": token})
        server.passwords.set_password("NeoBot-Rotated-2026")
        after = await client.get(base + "/api/overview", headers={"X-Token": token})
        relogin = await client.post(
            base + "/api/auth/login", json={"password": "NeoBot-Rotated-2026"}
        )

    assert before.status_code == 200
    assert after.status_code == 401
    assert relogin.status_code == 200


async def test_requires_authentication(panel) -> None:
    _, _, base, _ = panel
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/overview")

    assert response.status_code == 401


async def test_overview_returns_bot_and_stats(panel) -> None:
    _, _, base, _ = panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/overview", headers={"X-Token": token})

    assert response.status_code == 200
    payload = response.json()
    assert payload["bot_nickname"] == "测试机器人"
    assert payload["bot_user_id"] == 10001
    assert payload["app_name"] == "NapCat"
    assert payload["online"] is True


async def test_write_requires_csrf(panel) -> None:
    _, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        without = await client.post(
            base + "/api/plugins/demo/toggle", headers={"X-Token": token}
        )
        with_token = await client.post(
            base + "/api/plugins/demo/toggle",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
        )

    assert without.status_code == 403
    assert with_token.status_code == 200
    assert with_token.json()["ok"] is True


async def test_plugins_payload_marks_official(panel) -> None:
    _, _, base, _ = panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/plugins", headers={"X-Token": token})

    items = {item["name"]: item for item in response.json()["items"]}
    assert items["dashboard"]["official"] is True
    assert items["dashboard"]["manageable"] is False
    assert items["demo"]["official"] is False
    assert response.json()["console_plugin"] == "dashboard"


async def test_config_read_and_save_roundtrip(panel) -> None:
    """本体配置读写：面板插件自己的配置已不在 config.toml，这里用 [debug] 验证回环。"""
    _, _, base, config_path = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        read = await client.get(base + "/api/config", headers={"X-Token": token})
        assert read.status_code == 200
        document = read.json()
        assert document["revision"]
        assert document["config"]["debug"]["retention_days"] == 10

        payload = {
            "revision": document["revision"],
            "mode": "form",
            "config": {
                **document["config"],
                "debug": {**document["config"]["debug"], "retention_days": 20},
            },
            "reload": False,
        }
        saved = await client.post(
            base + "/api/config",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json=payload,
        )

    assert saved.status_code == 200, saved.text
    assert saved.json()["config"]["debug"]["retention_days"] == 20
    assert "retention_days = 20" in config_path.read_text(encoding="utf-8")


async def test_config_save_detects_conflict(panel) -> None:
    _, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        read = await client.get(base + "/api/config", headers={"X-Token": token})
        stale = read.json()["revision"]
        payload = {"revision": stale, "mode": "form", "config": read.json()["config"]}
        first = await client.post(
            base + "/api/config",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json=payload,
        )
        second = await client.post(
            base + "/api/config",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json=payload,
        )

    assert first.status_code == 200
    assert second.status_code == 409


async def test_config_save_rejects_invalid_payload(panel) -> None:
    _, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/api/config",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"revision": None, "mode": "form", "config": {"dashboard": {"port": "abc"}}},  # 该分区已不存在
        )

    assert response.status_code == 400
    assert response.json()["errors"]


async def test_env_never_exposes_secret(panel) -> None:
    """敏感键只返回「是否已设置」：既无明文，也无掩码片段，且没有取回明文的接口。"""
    _, _, base, _ = panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        listed = await client.get(base + "/api/config/env", headers={"X-Token": token})
        legacy = await client.get(
            base + "/api/config/env/DeepSeek_APIKey/value", headers={"X-Token": token}
        )

    payload = listed.json()
    entry = {item["key"]: item for item in payload["items"]}["DeepSeek_APIKey"]
    assert entry["value"] == ""
    assert entry["has_value"] is True
    assert entry["masked"] is True
    assert entry["sensitive"] is True
    assert "source" not in payload
    assert payload["secret_policy"] == "write_only"
    assert "sk-super-secret" not in listed.text
    assert legacy.status_code >= 400
    assert "sk-super-secret" not in legacy.text


def test_env_manager_keeps_secret_when_value_blank(tmp_path: Path) -> None:
    """.env 保存：留空 = 保持原密钥，占位符不会被写回文件。"""
    from neobot_app.builtin_plugins.dashboard.config_manager import EnvFileManager

    env_path = tmp_path / ".env"
    env_path.write_text("DeepSeek_APIKey=sk-original\n", encoding="utf-8")
    manager = EnvFileManager(env_path=env_path, backup_dir=tmp_path / "backup")

    manager.save(updates={"DeepSeek_APIKey": "", "Other_URL": "https://example.com"})
    text = env_path.read_text(encoding="utf-8")
    assert "DeepSeek_APIKey=sk-original" in text
    assert "Other_URL=https://example.com" in text

    manager.save(updates={"DeepSeek_APIKey": "••••••••"})
    assert "DeepSeek_APIKey=sk-original" in env_path.read_text(encoding="utf-8")

    manager.save(updates={"DeepSeek_APIKey": "sk-updated"})
    assert "DeepSeek_APIKey=sk-updated" in env_path.read_text(encoding="utf-8")


async def test_env_add_platform_writes_url_and_key(panel) -> None:
    """一键添加 API 供应商：写入 <平台名>_URL 与 <平台名>_APIKey，响应不含明文 Key。"""
    server, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        listed = await client.get(base + "/api/config/env", headers={"X-Token": token})
        response = await client.post(
            base + "/api/config/env/platform",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={
                "name": "MyProvider",
                "url": "https://api.example.com/v1",
                "api_key": "sk-my-provider-secret",
                "revision": listed.json()["revision"],
            },
        )

    assert response.status_code == 200, response.text
    text = server.env_manager.env_path.read_text(encoding="utf-8")
    assert "MyProvider_URL=https://api.example.com/v1" in text
    assert "MyProvider_APIKey=sk-my-provider-secret" in text
    platforms = {item["name"]: item for item in response.json()["platforms"]}
    assert platforms["MyProvider"]["url"] == "https://api.example.com/v1"
    assert platforms["MyProvider"]["has_key"] is True
    assert "sk-my-provider-secret" not in response.text


async def test_env_add_platform_validates_input(panel) -> None:
    _, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        bad_name = await client.post(
            base + "/api/config/env/platform",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"name": "我的平台", "url": "https://api.example.com"},
        )
        bad_url = await client.post(
            base + "/api/config/env/platform",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"name": "MyProvider", "url": "api.example.com"},
        )

    assert bad_name.status_code == 400
    assert "平台名" in bad_name.json()["error"]
    assert bad_url.status_code == 400
    assert "http" in bad_url.json()["error"]


async def test_models_library_crud_and_assignments(panel) -> None:
    """模型库单独存储：面板可新增/改绑/删除，调用方只引用 key。"""
    _, _, base, config_path = panel
    token, csrf = await _login(base)
    headers = {"X-Token": token, "X-CSRF-Token": csrf}
    entry = {
        "key": "my-flux",
        "description": "自定义生图模型",
        "provider": "SiliconFlow",
        "model_name": "black-forest-labs/FLUX.1-dev",
        "native_vision": False,
        "balance_query_hint": "",
    }
    async with httpx.AsyncClient() as client:
        listed = await client.get(base + "/api/config/models", headers={"X-Token": token})
        created = await client.post(
            base + "/api/config/models/library",
            headers=headers,
            json={"action": "upsert", "entry": entry, "revision": listed.json()["revision"]},
        )
        after_create = await client.get(base + "/api/config/models", headers={"X-Token": token})
        bound = await client.post(
            base + "/api/config/models/assignments",
            headers=headers,
            json={
                "assignments": {"creator_image_models": ["my-flux"]},
                "revision": after_create.json()["revision"],
            },
        )
        blocked = await client.post(
            base + "/api/config/models/library",
            headers=headers,
            json={"action": "delete", "key": "my-flux", "revision": bound.json()["revision"]},
        )

    assert created.status_code == 200, created.text
    library = {item["key"]: item for item in created.json()["models"]["library"]}
    assert library["my-flux"]["model_name"] == "black-forest-labs/FLUX.1-dev"
    assert library["my-flux"]["assigned"] is False
    assert bound.status_code == 200, bound.text
    assert bound.json()["models"]["assignments"]["creator_image_models"] == ["my-flux"]
    # 仍被调用方引用时不允许删除
    assert blocked.status_code == 400
    assert "引用" in blocked.json()["error"]
    raw = config_path.read_text(encoding="utf-8")
    assert 'key = "my-flux"' in raw
    assert "creator_image_models = [\"my-flux\"]" in raw


async def test_models_view_exposes_options_and_proxy_flag(panel) -> None:
    """模型库视图需提供下拉候选值与代理开关，字段描述带 options。"""
    _, _, base, _ = panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/config/models", headers={"X-Token": token})

    payload = response.json()
    assert "DeepSeek" in payload["provider_options"]
    assert isinstance(payload["model_name_options"], list)
    entry = next(item for item in payload["library"] if item["key"] == "deepseek-v4-pro")
    assert entry["use_system_proxy"] is False
    assert entry["entry"]["use_system_proxy"] is False

    fields = {field["name"]: field for field in payload["entry_schema"]}
    assert fields["use_system_proxy"]["type"] == "bool"
    assert fields["provider"]["kind"] == "scalar"
    settings = {field["name"]: field for field in fields["settings"]["fields"]}
    assert settings["deepseek_thinking_mode"]["options"] == ["enabled", "disabled", "random"]
    assert settings["deepseek_thinking_mode"]["options_strict"] is True
    assert settings["deepseek_reasoning_effort"]["options"] == ["high", "max"]


async def test_models_test_endpoint_reports_missing_credentials(panel) -> None:
    _, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        missing = await client.post(
            base + "/api/config/models/test",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"key": "deepseek-v4-pro"},
        )
        unknown = await client.post(
            base + "/api/config/models/test",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"key": "no-such-model"},
        )

    assert missing.status_code == 200
    payload = missing.json()
    assert payload["ok"] is False
    assert "未配置" in payload["message"]
    assert payload["proxy"] is False
    assert unknown.status_code == 404


async def test_models_test_endpoint_returns_probe_result(panel, monkeypatch) -> None:
    from neobot_app.builtin_plugins.dashboard import model_probe

    calls: list[dict] = []

    async def fake_probe(**kwargs):
        calls.append(kwargs)
        return model_probe.ModelProbeResult(
            ok=True,
            reachable=True,
            authorized=True,
            model_found=True,
            status=200,
            latency_ms=42,
            url="https://api.example.com/models",
            proxy=kwargs["use_system_proxy"],
            message="连接正常，模型可用",
        )

    monkeypatch.setattr(model_probe, "probe_model", fake_probe)
    _, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/api/config/models/test",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={
                "entry": {
                    "key": "draft-model",
                    "provider": "MyProvider",
                    "model_name": "my-model",
                    "use_system_proxy": True,
                }
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["latency_ms"] == 42
    assert payload["proxy"] is True
    assert calls and calls[-1]["use_system_proxy"] is True
    assert calls[-1]["provider"] == "MyProvider"


async def test_models_assignments_reject_unknown_key(panel) -> None:
    _, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        listed = await client.get(base + "/api/config/models", headers={"X-Token": token})
        response = await client.post(
            base + "/api/config/models/assignments",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={
                "assignments": {"primary_chat_model": "not-in-library"},
                "revision": listed.json()["revision"],
            },
        )

    assert response.status_code == 400
    assert "模型库中不存在" in response.json()["error"]


async def test_env_save_updates_file(panel) -> None:
    _, _, base, _ = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        listed = await client.get(base + "/api/config/env", headers={"X-Token": token})
        response = await client.post(
            base + "/api/config/env",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={
                "revision": listed.json()["revision"],
                "updates": {"MyProvider_URL": "https://example.com/v1"},
                "deletes": [],
            },
        )

    assert response.status_code == 200
    assert "MyProvider_URL=https://example.com/v1" in panel[0].env_manager.env_path.read_text(encoding="utf-8")


async def test_plugins_payload_reports_hot_reload_and_proxy(panel) -> None:
    """插件列表必须带热重载标注、插件配置路径与代理设置。"""
    _, control, base, _ = panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/plugins", headers={"X-Token": token})

    payload = response.json()
    items = {item["name"]: item for item in payload["items"]}
    assert items["demo"]["hot_reload"] is True
    assert items["demo"]["config_hot_reload"] is True
    assert items["dashboard"]["official"] is True
    # 官方与第三方插件的配置都在插件数据目录，不再有本体 config.toml 分区
    assert items["dashboard"]["config_path"] == str(
        control.plugins_data / "dashboard" / "config.toml"
    )
    assert items["demo"]["config_path"] == str(control.plugins_data / "demo" / "config.toml")
    assert payload["proxy"]["mode"] == "system"
    assert payload["proxy_modes"] == ["system", "none", "custom"]


async def test_plugins_proxy_save_writes_config(panel) -> None:
    """切换插件下载代理：写入 config.toml 的 [plugins] 并校验非法输入。"""
    server, _, base, config_path = panel
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        saved = await client.post(
            base + "/api/plugins/proxy",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"mode": "custom", "host": "127.0.0.1", "port": 1080},
        )
        invalid = await client.post(
            base + "/api/plugins/proxy",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"mode": "bogus"},
        )

    assert saved.status_code == 200, saved.text
    assert saved.json()["proxy"]["mode"] == "custom"
    raw = config_path.read_text(encoding="utf-8")
    assert 'proxy_mode = "custom"' in raw
    assert "proxy_port = 1080" in raw
    assert invalid.status_code == 400
    assert server.plugin_control.proxy_mode == "custom"


async def test_manage_plugins_switch_follows_plugin_config_file(panel) -> None:
    """manage_plugins 改为 false 后立即生效：管理员不会把自己锁在外面。"""
    server, _, base, _ = panel
    token, _ = await _login(base)

    (server.data_dir / "config.toml").write_text(
        "manage_plugins = false\n", encoding="utf-8"
    )

    async with httpx.AsyncClient() as client:
        listed = await client.get(base + "/api/plugins", headers={"X-Token": token})
        denied = await client.post(base + "/api/plugins/demo/toggle", headers={"X-Token": token})

    assert listed.json()["manage_enabled"] is False
    assert denied.status_code == 403


async def test_official_plugin_config_read_and_save(panel) -> None:
    """官方插件配置写在插件数据目录，不再碰本体 config.toml。"""
    _, control, base, config_path = panel
    before = config_path.read_text(encoding="utf-8")
    target = control.plugins_data / "dashboard" / "config.toml"
    token, csrf = await _login(base)
    async with httpx.AsyncClient() as client:
        read = await client.get(
            base + "/api/plugins/dashboard/config", headers={"X-Token": token}
        )
        payload = read.json()
        saved = await client.post(
            base + "/api/plugins/dashboard/config",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={
                "config": {"log_buffer_size": 600},
                "revision": payload["revision"],
            },
        )
        invalid = await client.post(
            base + "/api/plugins/dashboard/config",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"config": {"port": 70000}, "revision": payload["revision"]},
        )
        conflict = await client.post(
            base + "/api/plugins/dashboard/config",
            headers={"X-Token": token, "X-CSRF-Token": csrf},
            json={"config": {"port": 9982}, "revision": payload["revision"]},
        )

    assert read.status_code == 200, read.text
    assert payload["official"] is True
    assert payload["path"] == str(target)
    assert payload["exists"] is False  # 还没保存过：按默认值渲染
    assert payload["config"]["port"] == 9981
    assert any(field["name"] == "port" for field in payload["schema"])
    assert payload["config_hot_reload"] is False

    assert saved.status_code == 200, saved.text
    raw = target.read_text(encoding="utf-8")
    assert "log_buffer_size = 600" in raw
    assert saved.json()["exists"] is True
    # 本体 config.toml 保持不变
    assert config_path.read_text(encoding="utf-8") == before

    assert invalid.status_code == 400
    assert invalid.json()["errors"]
    assert conflict.status_code == 409


async def test_logs_endpoint_shape(panel) -> None:
    _, _, base, _ = panel
    token, _ = await _login(base)
    async with httpx.AsyncClient() as client:
        response = await client.get(base + "/api/logs", headers={"X-Token": token})

    payload = response.json()
    assert payload["ok"] is True
    assert isinstance(payload["items"], list)
    assert "last_id" in payload
