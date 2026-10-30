"""真实本机 HTTP 控制、选定源码监听与实例文件锁的闭环验证。"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import aiohttp
import pytest

from neobot_app.runtime.instance_lease import InstanceAlreadyRunning, InstanceLease
from neobot_app.runtime.local_control import LocalControlServer
from neobot_contracts.ports.logging import NullLogger
from neobot_contracts.ports.plugin import PluginState
from neobot_modloader.runtime import PluginRuntime
from neobot_modloader.sdk.tooling.project import export_contract, init_project


class LoggerFactory:
    def get_logger(self, _name: str) -> NullLogger:
        return NullLogger()


def make_plugin(root: Path, name: str) -> Path:
    path = root / "plugins" / name
    assert init_project(path, name).ok
    entry = path / "__init__.py"
    entry.write_text(f"from neobot_modloader import Plugin\nplugin = Plugin({name!r}, description='before')\n")
    assert export_contract(path).ok
    return entry


def make_runtime(root: Path) -> PluginRuntime:
    runtime = PluginRuntime(
        plugin_dir=root / "plugins",
        data_dir=root / "data" / "plugins_data",
        adapter=object(),
        logger_factory=LoggerFactory(),
    )
    runtime.development.watcher.poll_interval = 0.01
    runtime.development.watcher.debounce = 0
    return runtime


async def wait_description(runtime: PluginRuntime, name: str, description: str) -> None:
    async with asyncio.timeout(3):
        while runtime.manager.get_plugin(name).description != description:
            await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_new_plugin_develops_in_existing_runtime_and_retains_old_on_failure(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    await runtime.start_all()
    server = LocalControlServer(runtime, data_dir=tmp_path / "data", version="test", request_stop=lambda: None)
    await server.start()
    document = json.loads(server.discovery.read_text())
    assert document["schema_version"] == 1
    assert document["pid"] == os.getpid()
    if os.name != "nt":
        assert server.discovery.stat().st_mode & 0o777 == 0o600
    headers = {"Authorization": f"Bearer {document['token']}"}
    try:
        # 实例先运行，再创建插件，不通过安装器或第二个运行时。
        selected = make_plugin(tmp_path, "selected")
        other = make_plugin(tmp_path, "other")
        assert (await runtime.load_plugin_path(other.parent, start=True)).ok
        async with aiohttp.ClientSession(headers=headers, trust_env=False) as client:
            async with client.post(
                server.url + "/v1/plugins/dev", json={"name": "selected", "enabled": True}
            ) as response:
                assert response.status == 200
                body = await response.json()
                assert body["ok"]
                assert body["data"]["instance_id"] == server.instance_id
                assert "plugin.install" not in body["data"]["capabilities"]
            assert runtime.manager.get_state("selected") is PluginState.RUNNING
            assert runtime._hot_reloader is None
            first = runtime.manager.get_plugin("selected")
            selected.write_text(selected.read_text().replace("before", "after"))
            other.write_text(other.read_text().replace("before", "after"))
            await wait_description(runtime, "selected", "after")
            assert runtime.manager.get_plugin("selected") is not first
            assert runtime.manager.get_plugin("other").description == "before"
            previous = runtime.manager.get_plugin("selected")
            selected.write_text("invalid python (\n")
            async with asyncio.timeout(3):
                while runtime.development.status("selected")["reload"]["status"] != "failed":
                    await asyncio.sleep(0.02)
            assert runtime.manager.get_plugin("selected") is previous
            selected.write_text(
                "from neobot_modloader import Plugin\nplugin = Plugin('selected', description='fixed')\n"
            )
            await wait_description(runtime, "selected", "fixed")
            async with client.get(server.url + "/v1/status") as response:
                plugins = (await response.json())["data"]["plugins"]
                status = next(item for item in plugins if item["name"] == "selected")
                assert status["development"]
                assert status["reload"]["status"] == "succeeded"
            async with client.post(
                server.url + "/v1/plugins/dev", json={"name": "selected", "enabled": False}
            ) as response:
                assert response.status == 200
            selected.write_text(selected.read_text().replace("fixed", "unwatched"))
            await asyncio.sleep(0.06)
            assert runtime.manager.get_plugin("selected").description == "fixed"
    finally:
        await server.close()
        await runtime.stop_all()
    assert not server.discovery.exists()
    assert runtime.development.watcher._task is None


@pytest.mark.asyncio
async def test_authentication_origin_host_body_and_local_path_boundaries(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    stop = asyncio.Event()
    server = LocalControlServer(runtime, data_dir=tmp_path / "data", version="test", request_stop=stop.set)
    await server.start()
    token = json.loads(server.discovery.read_text())["token"]
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with aiohttp.ClientSession(trust_env=False) as client:
            for values, expected in [
                ({}, 401),
                ({**headers, "Origin": "http://localhost"}, 403),
                ({**headers, "Host": "evil.test"}, 403),
            ]:
                async with client.get(server.url + "/v1/status", headers=values) as response:
                    assert response.status == expected
                    assert not (await response.json())["ok"]
            for payload in [
                {"name": "../outside", "enabled": True},
                {"name": "absent", "enabled": True},
                {"name": "absent", "enabled": "false"},
            ]:
                async with client.post(server.url + "/v1/plugins/dev", headers=headers, json=payload) as response:
                    assert response.status in {400, 409}
            async with client.post(
                server.url + "/v1/plugins/dev",
                headers=headers,
                data='{"padding":"' + "x" * 9000 + '"}',
                skip_auto_headers={"Content-Type"},
            ) as response:
                assert response.status == 400
            async with client.post(
                server.url + "/v1/plugins/dev", headers=headers, json={"name": "x" * 9000, "enabled": True}
            ) as response:
                assert response.status == 413
                assert not (await response.json())["ok"]
            async with client.post(server.url + "/v1/plugins/install", headers=headers, json={}) as response:
                assert response.status == 404
            async with client.post(server.url + "/v1/stop", headers=headers, json={}) as response:
                assert response.status == 200
                assert (await response.json())["data"]["stopping"]
            await asyncio.wait_for(stop.wait(), 1)
            async with client.get(server.url + "/v1/status", headers=headers) as response:
                assert (await response.json())["data"]["stopping"]
            async with client.post(
                server.url + "/v1/plugins/dev", headers=headers, json={"name": "absent", "enabled": True}
            ) as response:
                assert response.status == 409
                assert (await response.json())["error"]["code"] == "shutting_down"
    finally:
        await server.close()
        await runtime.stop_all()


@pytest.mark.asyncio
async def test_development_does_not_restart_stopped_or_disabled_plugin(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    entry = make_plugin(tmp_path, "paused")
    assert (await runtime.load_plugin_path(entry.parent, start=True)).ok
    await runtime.stop_plugin("paused")
    with pytest.raises(ValueError, match="未运行"):
        await runtime.development.set_enabled("paused", True)
    assert runtime.manager.get_state("paused") is PluginState.STOPPED
    await runtime.set_enabled("paused", False)
    with pytest.raises(ValueError, match="已停用"):
        await runtime.development.set_enabled("paused", True)
    await runtime.stop_all()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["stop", "disable", "replace"])
async def test_http_reload_preserves_concurrent_state_or_generation_change(tmp_path: Path, operation: str) -> None:
    runtime = make_runtime(tmp_path)
    entry = make_plugin(tmp_path, "paused")
    assert (await runtime.load_plugin_path(entry.parent, start=True)).ok
    original_plugin = runtime.manager.get_plugin("paused")
    server = LocalControlServer(runtime, data_dir=tmp_path / "data", version="test", request_stop=lambda: None)
    await server.start()
    headers = {"Authorization": f"Bearer {json.loads(server.discovery.read_text())['token']}"}
    cascade = runtime._cascade_stop_dependents
    entered, release = asyncio.Event(), asyncio.Event()

    async def hold_first_reload(name, *, reason):
        result = await cascade(name, reason=reason)
        if "正在重载" in reason and not entered.is_set():
            entered.set()
            await release.wait()
        return result

    runtime._cascade_stop_dependents = hold_first_reload
    request = None
    try:
        async with aiohttp.ClientSession(headers=headers, trust_env=False) as client:
            request = asyncio.create_task(client.post(server.url + "/v1/plugins/reload", json={"name": "paused"}))
            await asyncio.wait_for(entered.wait(), timeout=2)
            if operation == "stop":
                assert (await runtime.stop_plugin("paused")).ok
                assert runtime.manager.get_state("paused") is PluginState.STOPPED
            elif operation == "disable":
                assert (await runtime.set_enabled("paused", False)).ok
                assert runtime.manager.get_record("paused") is None
            else:
                entry.write_text(entry.read_text().replace("before", "replacement"))
                assert (await runtime.reload_plugin_result("paused", auto_install_dependencies=False)).ok
                assert runtime.manager.get_plugin("paused") is not original_plugin
            current_record = runtime.manager.get_record("paused")
            release.set()
            async with await request as response:
                assert response.status == 409
                body = await response.json()
                assert not body["ok"]
                assert body["error"]["code"] == "reload_failed"
            assert runtime.manager.get_record("paused") is current_record
            if operation == "stop":
                assert current_record.state is PluginState.STOPPED
                assert runtime.manager.get_plugin("paused") is original_plugin
            elif operation == "disable":
                assert not runtime._resolve_enabled_state("paused", True)
            else:
                assert current_record.state is PluginState.RUNNING
                assert runtime.manager.get_plugin("paused").description == "replacement"
    finally:
        release.set()
        if request is not None:
            await asyncio.gather(request, return_exceptions=True)
        await server.close()
        await runtime.stop_all()


@pytest.mark.asyncio
async def test_development_respects_global_disable_before_importing_author_code(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    entry = make_plugin(tmp_path, "blocked")
    marker = tmp_path / "author_was_imported"
    entry.write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('unexpected')\n" + entry.read_text())
    runtime.user_plugins_enabled = False
    with pytest.raises(ValueError, match="全局禁用") as error:
        await runtime.development.set_enabled("blocked", True)
    assert error.value.code == "user_plugins_disabled"
    assert not marker.exists()
    assert runtime.manager.get_record("blocked") is None
    assert not runtime.development.names
    await runtime.stop_all()


def test_instance_lease_excludes_another_process_and_recovers_after_close(tmp_path: Path) -> None:
    data = tmp_path / "data"
    with InstanceLease(data):
        with pytest.raises(InstanceAlreadyRunning):
            InstanceLease(data).acquire()
        code = (
            "from pathlib import Path\n"
            "from neobot_app.runtime.instance_lease import InstanceLease, InstanceAlreadyRunning\n"
            f"try:\n    InstanceLease(Path({str(data)!r})).acquire()\n"
            "except InstanceAlreadyRunning:\n    raise SystemExit(7)\n"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=10, check=False)
        assert result.returncode == 7, result.stderr.decode()
    with InstanceLease(data):
        assert (data / ".neobot" / "instance.lock").exists()


@pytest.mark.asyncio
async def test_cli_retains_status_and_instance_lock_until_plugin_cleanup_finishes(tmp_path: Path, monkeypatch) -> None:
    from neobot_app import cli

    runtime = make_runtime(tmp_path)
    data = tmp_path / "data"
    discovery = data / ".neobot" / "control.json"
    original_stop = runtime.stop_all
    observed = []

    async def stop_core():
        document = json.loads(discovery.read_text())
        headers = {"Authorization": f"Bearer {document['token']}"}
        async with aiohttp.ClientSession(headers=headers, trust_env=False) as client:
            async with client.get(document["url"] + "/v1/status") as response:
                assert (await response.json())["data"]["stopping"]
        with pytest.raises(InstanceAlreadyRunning):
            InstanceLease(data).acquire()
        observed.append("cleanup")
        await original_stop()

    class Controller:
        exiting = False

        def __init__(self, **_arguments):
            pass

        async def start(self):
            return True, ""

        async def enter(self):
            pass

        resume = enter
        set_onebot = enter

    async def entry_loop(**arguments):
        await arguments["startup_task"]
        return False

    values = {"plugin_runtime": runtime, "standby_service": SimpleNamespace(set_hooks=lambda **_kwargs: None)}
    monkeypatch.setattr(cli, "DATA_DIR", data)
    monkeypatch.setattr(cli, "get_cached_core", values.get)
    monkeypatch.setattr(cli, "create_application", lambda **_kwargs: object())
    monkeypatch.setattr(cli, "StandbyController", Controller)
    monkeypatch.setattr(cli, "run_entry_loop", entry_loop)
    monkeypatch.setattr(asyncio.BaseEventLoop, "add_signal_handler", lambda *_args: None)
    monkeypatch.setattr(runtime, "stop_all", stop_core)
    assert await cli.run() is False
    assert observed == ["cleanup"]
    assert not discovery.exists()
    with InstanceLease(data):
        pass
