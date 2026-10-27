"""星舰默认不加载、持久 opt-in 与真实扩展生命周期（全部使用临时目录）。"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from neobot_app.builtin_plugins import builtin_plugin_dirs
from neobot_app.builtin_plugins.dashboard.config import DashboardConfig
from neobot_app.builtin_plugins.dashboard.server import DashboardServer
from neobot_contracts.ports.logging import NullLogger
from neobot_contracts.ports.plugin import PluginState
from neobot_modloader.host import PluginHostFacade
from neobot_modloader.runtime import PluginRuntime
from neobot_modloader.state import PluginStateStore

from test_dashboard_api import _FakeSnapshot, _login, _start_panel


class _LoggerFactory:
    def get_logger(self, name: str) -> NullLogger:
        return NullLogger()


@pytest.fixture
async def starship_runtime(tmp_path: Path):
    official_dir = tmp_path / "official"
    starship_dir = official_dir / "starship"
    starship_dir.mkdir(parents=True)
    source = builtin_plugin_dirs()[0] / "starship"
    # 复制实际后端与实际清单；不复制前端产物，也不触碰真实插件数据。
    for path in source.glob("*.py"):
        shutil.copy2(path, starship_dir / path.name)
    shutil.copy2(source / "plugin.toml", starship_dir / "plugin.toml")
    dashboard_dir = official_dir / "dashboard"
    dashboard_dir.mkdir()
    (dashboard_dir / "plugin.toml").write_text('name = "dashboard"\nversion = "1.0.0"\n', encoding="utf-8")
    (dashboard_dir / "__init__.py").write_text(
        "from neobot_modloader import Plugin\n"
        "plugin = Plugin('dashboard', version='1.0.0')\n"
        "server = None\n"
        "@plugin.on_load\n"
        "async def load(ctx):\n"
        "    global server\n"
        "    server = ctx.plugin_host.services.require('test_panel')\n"
        "@plugin.capability('web.register_extension')\n"
        "async def register(payload):\n"
        "    return server.register_extension(payload['name'], payload['extension'])\n"
        "@plugin.capability('web.unregister_extension')\n"
        "async def unregister(payload):\n"
        "    return server.unregister_extension(payload['name'])\n",
        encoding="utf-8",
    )
    panel = DashboardServer(
        plugin_name="dashboard",
        config=DashboardConfig(host="127.0.0.1"),
        data_dir=tmp_path / "panel",
        logger=NullLogger(),
        adapter=object(),
        plugin_control=None,
        config_path=tmp_path / "config.toml",
        env_path=tmp_path / ".env",
        backup_dir=tmp_path / "backups",
    )
    host = PluginHostFacade()
    host.services.register("test_panel", panel)
    store = PluginStateStore(tmp_path / "plugin_state.json")
    runtime = PluginRuntime(
        plugin_dir=tmp_path / "user_plugins",
        data_dir=tmp_path / "plugins_data",
        builtin_plugin_dirs=(official_dir,),
        state_store=store,
        adapter=object(),
        logger_factory=_LoggerFactory(),
        host=host,
    )
    try:
        yield runtime, panel, store
    finally:
        for name in reversed(runtime.manager.names()):
            await runtime.unload_plugin(name)


async def _start(runtime: PluginRuntime) -> None:
    runtime.load_all()
    await runtime.load_registered()
    await runtime.start_all()


async def test_starship_default_does_not_import_start_or_register(starship_runtime) -> None:
    runtime, panel, store = starship_runtime
    importer = runtime.official_loader._importer
    with patch.object(importer, "import_module", wraps=importer.import_module) as imported:
        await _start(runtime)
    assert all(call.args[1] != "starship" for call in imported.call_args_list)
    assert runtime.manager.get_record("starship") is None
    assert runtime.control.get("starship").enabled is False
    assert panel.describe_extensions() == []
    assert panel._extension_for("/game/") is None
    assert not (runtime.data_dir / "starship").exists()
    assert store.get("starship") is None


@pytest.mark.parametrize("enabled", [True, False])
async def test_existing_explicit_starship_choice_survives_default_change(starship_runtime, enabled: bool) -> None:
    runtime, panel, store = starship_runtime
    store.set_enabled("starship", enabled)
    await _start(runtime)
    assert runtime.control.get("starship").enabled is enabled
    assert (runtime.manager.get_state("starship") == PluginState.RUNNING) is enabled
    assert bool(panel.describe_extensions()) is enabled
    assert PluginStateStore(store.path).is_enabled("starship", not enabled) is enabled


async def test_starship_switch_loads_and_unloads_extension_and_preserves_data(starship_runtime) -> None:
    runtime, panel, store = starship_runtime
    await _start(runtime)

    enabled = await runtime.set_enabled("starship", True)
    assert enabled.ok, enabled.error
    assert runtime.manager.get_state("starship") == PluginState.RUNNING
    assert PluginStateStore(store.path).is_enabled("starship", False) is True
    assert panel.describe_extensions()[0]["name"] == "starship"
    assert panel.describe_extensions()[0]["panel"]["path"] == "/game/"
    assert panel._extension_for("/game/api/bootstrap") is not None
    database = runtime.data_dir / "starship" / "databases" / "starship.db"
    assert database.is_file()

    disabled = await runtime.set_enabled("starship", False)
    assert disabled.ok, disabled.error
    assert runtime.manager.get_record("starship") is None
    assert panel.describe_extensions() == []
    assert panel._extension_for("/game/api/bootstrap") is None
    assert PluginStateStore(store.path).is_enabled("starship", True) is False
    assert database.is_file()


@pytest.fixture
async def toggle_panel(tmp_path: Path):
    server, control, base, _ = await _start_panel(tmp_path, trust_proxy=True)
    starship = _FakeSnapshot("starship", source="official")
    starship.enabled = False
    control.snapshots.append(starship)
    token, csrf = await _login(base)
    try:
        yield server, control, starship, base, {"X-Token": token, "X-CSRF-Token": csrf}
    finally:
        await server.stop()


async def test_plugin_toggle_accepts_explicit_target_and_rejects_stale_state(toggle_panel) -> None:
    _, control, starship, base, headers = toggle_panel
    async with httpx.AsyncClient() as client:
        response = await client.post(
            base + "/api/plugins/starship/toggle",
            headers=headers,
            json={"enabled": True, "expected_enabled": False},
        )
        assert response.status_code == 200, response.text
        assert control.enabled_calls == [("starship", True)]
        starship.enabled = True
        stale = await client.post(
            base + "/api/plugins/starship/toggle",
            headers=headers,
            json={"enabled": False, "expected_enabled": False},
        )
    assert stale.status_code == 409
    assert stale.json()["enabled"] is True
    assert control.enabled_calls == [("starship", True)]


@pytest.mark.parametrize("payload", [{"enabled": "false"}, {"enabled": 1}, {"expected_enabled": None}])
async def test_plugin_toggle_requires_boolean_fields(toggle_panel, payload: dict) -> None:
    _, control, _, base, headers = toggle_panel
    async with httpx.AsyncClient() as client:
        response = await client.post(base + "/api/plugins/starship/toggle", headers=headers, json=payload)
    assert response.status_code == 400
    assert control.enabled_calls == []


async def test_plugin_toggle_preserves_csrf_and_management_permissions(toggle_panel) -> None:
    server, control, _, base, headers = toggle_panel
    async with httpx.AsyncClient() as client:
        denied_csrf = await client.post(
            base + "/api/plugins/starship/toggle",
            headers={"X-Token": headers["X-Token"]},
            json={"enabled": True},
        )
        (server.data_dir / "config.toml").write_text("manage_plugins = false\n", encoding="utf-8")
        denied_manage = await client.post(
            base + "/api/plugins/starship/toggle",
            headers=headers,
            json={"enabled": True},
        )
    assert denied_csrf.status_code == 403
    assert denied_manage.status_code == 403
    assert control.enabled_calls == []


async def test_concurrent_explicit_toggle_cannot_overwrite_a_new_choice(toggle_panel) -> None:
    _, control, starship, base, headers = toggle_panel
    original = control.set_enabled

    async def delayed(name: str, enabled: bool):
        await asyncio.sleep(0.02)
        result = await original(name, enabled)
        starship.enabled = enabled
        return result

    control.set_enabled = delayed
    async with httpx.AsyncClient() as client:
        responses = await asyncio.gather(
            *(
                client.post(
                    base + "/api/plugins/starship/toggle",
                    headers=headers,
                    json={"enabled": True, "expected_enabled": False},
                )
                for _ in range(2)
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert control.enabled_calls == [("starship", True)]


async def test_legacy_toggle_without_body_still_reverses_state(toggle_panel) -> None:
    _, control, _, base, headers = toggle_panel
    async with httpx.AsyncClient() as client:
        response = await client.post(base + "/api/plugins/starship/toggle", headers=headers)
    assert response.status_code == 200, response.text
    assert control.enabled_calls == [("starship", True)]


async def test_remote_read_only_state_and_toggle_share_permission_gate(toggle_panel) -> None:
    server, control, _, base, headers = toggle_panel
    (server.data_dir / "config.toml").write_text("allow_remote_manage = false\n", encoding="utf-8")
    remote_headers = {**headers, "X-Forwarded-For": "203.0.113.9"}
    async with httpx.AsyncClient() as client:
        plugins = await client.get(base + "/api/plugins", headers=remote_headers)
        denied = await client.post(
            base + "/api/plugins/starship/toggle", headers=remote_headers, json={"enabled": True}
        )
    assert plugins.status_code == 200
    assert plugins.json()["manage_enabled"] is False
    assert denied.status_code == 403
    assert control.enabled_calls == []


async def test_plugin_toggle_surfaces_runtime_failure(toggle_panel) -> None:
    from neobot_modloader.management import PluginOperationResult

    _, control, _, base, headers = toggle_panel

    async def fail(name: str, enabled: bool):
        return PluginOperationResult(ok=False, name=name, error="前置插件未就绪")

    control.set_enabled = fail
    async with httpx.AsyncClient() as client:
        response = await client.post(base + "/api/plugins/starship/toggle", headers=headers, json={"enabled": True})
    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert response.json()["error"] == "前置插件未就绪"
