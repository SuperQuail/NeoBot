from __future__ import annotations

import argparse
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_app import cli


def test_run_banner_precedes_real_startup_and_is_printed_once(monkeypatch):
    events = []
    monkeypatch.setattr(cli, "display_banner", lambda version: events.append("banner"))

    async def run():
        events.append("run")
        return False

    monkeypatch.setattr(cli, "run", run)
    cli.cmd_run(argparse.Namespace())
    assert events == ["banner", "run"]


@pytest.mark.parametrize("standby", [False, True])
@pytest.mark.parametrize("result", ["success", "failure", "exception"])
@pytest.mark.parametrize("interrupt", [None, "exit", "cancel"])
@pytest.mark.asyncio
async def test_webui_display_precedes_runtime_and_final_state_is_truthful(monkeypatch, standby, result, interrupt):
    events = []
    displays = []
    controllers = []
    reason = "配置未完整，保持待机" if standby else ""

    class Standby:
        def set_hooks(self, **kwargs):
            pass

        def is_standby(self):
            return standby

        def status(self):
            return {"reason": reason}

        def record_failure(self, detail):
            events.append("failure-recorded")

    class Controller:
        def __init__(self, **kwargs):
            self.exiting = False
            controllers.append(self)
            self.enter = AsyncMock()
            self.resume = AsyncMock()
            self.set_onebot = AsyncMock()

        async def start(self):
            assert displays and displays[0]["initializing"] is True
            events.append("controller-started")
            if result == "exception":
                raise RuntimeError("initialization failed")
            return result == "success", "初始化结果"

    class Plugins:
        async def load_registered(self):
            events.append("plugins-loaded")

        async def start_all(self):
            events.append("plugins-started")

        async def stop_all(self):
            pass

    core = {"standby_service": Standby(), "plugin_runtime": Plugins()}
    monkeypatch.setattr(cli, "enable_core_reuse", lambda: None)
    monkeypatch.setattr(cli, "get_cached_core", lambda key: core.get(key))
    monkeypatch.setattr(cli, "create_application", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(cli, "StandbyController", Controller)
    monkeypatch.setattr(asyncio.get_running_loop(), "add_signal_handler", lambda *args: None)

    async def describe(runtime):
        events.append("dashboard-described")
        await asyncio.sleep(0)
        if interrupt == "exit":
            controllers[0].exiting = True
        elif interrupt == "cancel":
            raise asyncio.CancelledError()
        return {"available": True, "local_url": "http://127.0.0.1:12345/bot/"}

    def display(**kwargs):
        events.append("displayed")
        displays.append(kwargs)

    async def entry_loop(**kwargs):
        await kwargs["startup_task"]
        return False

    monkeypatch.setattr(cli, "_dashboard_startup_info", describe)
    monkeypatch.setattr(cli, "display_startup_result", display)
    monkeypatch.setattr(cli, "run_entry_loop", entry_loop)

    if interrupt == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await cli._run_instance()
    else:
        assert await cli._run_instance() is False

    assert events[:2] == ["plugins-loaded", "plugins-started"]
    if interrupt is not None:
        assert events[-1] == "dashboard-described"
        assert displays == []
        assert "controller-started" not in events
        return
    assert events[:5] == ["plugins-loaded", "plugins-started", "dashboard-described", "displayed", "controller-started"]
    assert displays[0]["ready"] is True
    assert displays[0]["initializing"] is True
    assert displays[0]["dashboard"]["local_url"] == "http://127.0.0.1:12345/bot/"
    if result == "success" and not standby:
        assert len(displays) == 1
    else:
        assert len(displays) == 2
        assert displays[-1]["ready"] is (result == "success")
        assert displays[-1]["standby"] is standby
        if standby and result == "success":
            assert displays[-1]["detail"] == reason


@pytest.mark.asyncio
async def test_dashboard_startup_info_uses_read_only_capability():
    call = AsyncMock(return_value={"available": True, "local_url": "http://[::1]:12000/bot/"})
    handle = SimpleNamespace(ready=True, call=call)
    runtime = SimpleNamespace(manager=SimpleNamespace(registry_view=SimpleNamespace(get=lambda name: handle)))

    result = await cli._dashboard_startup_info(runtime)

    call.assert_awaited_once_with("server.describe")
    assert result["local_url"] == "http://[::1]:12000/bot/"


@pytest.mark.parametrize("state", ["disabled", "failed"])
@pytest.mark.asyncio
async def test_dashboard_unavailable_never_returns_an_assumed_default_url(state):
    handle = (
        None if state == "disabled" else SimpleNamespace(ready=True, call=AsyncMock(return_value={"available": False}))
    )
    runtime = SimpleNamespace(manager=SimpleNamespace(registry_view=SimpleNamespace(get=lambda name: handle)))
    result = await cli._dashboard_startup_info(runtime)
    assert result["available"] is False
    assert "local_url" not in result
