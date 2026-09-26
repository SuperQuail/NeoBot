"""Authenticated real routes + real application event loop, with only fake IO."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from neobot_app.cli import run_entry_loop
from neobot_app.bootstrap._standby_runtime import StandbyController
from neobot_app.runtime.application import NeoBotApplication
from neobot_app.runtime.process_restart import ProcessRestartSignal

from test_dashboard_api import _login
from test_dashboard_standby import _panel


def _application():
    ready = asyncio.Event()
    runtime = NeoBotApplication(
        adapter=SimpleNamespace(start=AsyncMock(), stop=AsyncMock()),
        file_server=SimpleNamespace(start=AsyncMock(), stop=AsyncMock()),
        chat_stream=SimpleNamespace(initialize=AsyncMock()),
        event_ingress=SimpleNamespace(start=ready.set, stop=Mock()),
        owns_plugins=False,
    )
    return runtime, ready


@pytest.mark.parametrize("phase", ["running", "standby", "failed_startup", "rebuilding"])
async def test_restart_route_reaches_core_in_every_runtime_phase(tmp_path, phase):
    server, base, standby = await _panel(tmp_path, with_service=True)
    runtime, ready = _application()
    restart = ProcessRestartSignal()
    stale = SimpleNamespace(request_restart=Mock(side_effect=AssertionError("stale runtime used")))
    server.services._mapping.update(process_restart=restart, application=stale)
    factory = Mock(return_value=runtime)
    ctrl = StandbyController(standby_service=standby, runtime_factory=factory, restart_signal=restart)
    standby.set_hooks(on_enter=ctrl.enter, on_resume=ctrl.resume)
    blocked, release = asyncio.Event(), asyncio.Event()
    rebuild = None
    if phase == "failed_startup":
        runtime.chat_stream.initialize.side_effect = RuntimeError("bad startup")
        ok, detail = await standby.resume()
        assert not ok and "bad startup" in detail
    elif phase != "standby":
        await ctrl.start()
        await ready.wait()
    if phase == "rebuilding":
        async def cleanup():
            blocked.set()
            await release.wait()
        runtime._reply_orchestrator = SimpleNamespace(shutdown=cleanup)
        rebuild = asyncio.create_task(standby.resume())
        await blocked.wait()
    entry = asyncio.create_task(run_entry_loop(
        controller=ctrl, standby_service=standby, restart_signal=restart,
        state={"stopping": False}, poll_interval=0.005,
    ))
    try:
        token, csrf = await _login(base)
        async with httpx.AsyncClient() as client:
            denied = await client.post(base + "/api/admin/restart")
            assert denied.status_code == 401
            assert not restart.requested
            for _ in range(2):
                response = await client.post(
                    base + "/api/admin/restart", headers={"X-Token": token, "X-CSRF-Token": csrf},
                )
                assert response.status_code == 200
                assert "优雅重启" in response.json()["message"]
            assert restart.requested
            if phase == "rebuilding":
                status = await client.get(base + "/api/admin/power", headers={"X-Token": token})
                assert status.json()["transition"]
                assert status.json()["state"] == "stopping"
                assert not entry.done()
            release.set()
            done, _ = await asyncio.wait((entry,), timeout=1)
            assert done, "restart request must wake a real shutdown_event wait"
            assert await entry is True
        stale.request_restart.assert_not_called()
        assert factory.call_count == (0 if phase == "standby" else 1)
        assert not runtime._started
        assert not restart._waiters
    finally:
        release.set()
        restart.request()
        if rebuild is not None:
            await rebuild
        await entry
        await server.stop()


async def test_restart_route_keeps_legacy_application_fallback(tmp_path):
    server, base, _ = await _panel(tmp_path, with_service=False)
    requested = asyncio.Event()
    server.services._mapping["application"] = SimpleNamespace(request_restart=requested.set)
    try:
        token, csrf = await _login(base)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                base + "/api/admin/restart", headers={"X-Token": token, "X-CSRF-Token": csrf},
            )
        assert response.status_code == 200
        async with asyncio.timeout(1):
            await requested.wait()
    finally:
        await server.stop()
