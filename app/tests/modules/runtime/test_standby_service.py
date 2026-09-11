"""StandbyService：待机状态机、钩子、持久化与启动即待机。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from neobot_app.runtime.standby_service import RUNNING, STANDBY, StandbyService


def _service(path: Path | None = None, **kwargs) -> tuple[StandbyService, dict]:
    calls: dict = {"enter": 0, "resume": 0, "onebot": []}

    async def on_enter() -> tuple[bool, str]:
        calls["enter"] += 1
        return True, "enter-ok"

    async def on_resume() -> tuple[bool, str]:
        calls["resume"] += 1
        return True, "resume-ok"

    async def on_onebot(enabled: bool) -> tuple[bool, str]:
        calls["onebot"].append(enabled)
        return True, "onebot-ok"

    service = StandbyService(
        state_path=path,
        on_enter=on_enter,
        on_resume=on_resume,
        on_onebot_change=on_onebot,
        **kwargs,
    )
    return service, calls


def test_initially_running() -> None:
    service, _ = _service()
    status = service.status()

    assert service.state == RUNNING
    assert service.is_standby() is False
    assert status["standby"] is False
    assert status["state"] == RUNNING
    assert status["standby_seconds"] == 0
    assert status["connect_onebot"] is True


def test_start_in_standby() -> None:
    service, _ = _service(start_in_standby=True)

    assert service.state == STANDBY
    assert service.status()["reason"] == "启动即待机"


@pytest.mark.asyncio
async def test_enter_and_reboot_round_trip() -> None:
    service, calls = _service()

    ok, message = await service.enter(reason="token 风暴", operator="private:1")
    assert ok is True
    assert "已进入待机" in message
    assert (calls["enter"], service.state) == (1, STANDBY)
    assert service.is_standby() is True
    assert service.status()["reason"] == "token 风暴"
    assert service.status()["operator"] == "private:1"

    ok, message = await service.reboot(reason="改完配置", operator="private:1")
    assert ok is True
    assert message == "resume-ok"
    assert (calls["resume"], service.state) == (1, RUNNING)
    assert service.is_standby() is False


@pytest.mark.asyncio
async def test_enter_is_idempotent_and_updates_reason() -> None:
    service, calls = _service()
    await service.enter(reason="先待机")

    ok, message = await service.enter()
    assert ok is True and message == "Bot 已处于待机状态。"
    assert calls["enter"] == 1

    ok, message = await service.enter(reason="换个原因")
    assert ok is True and "已更新待机原因" in message
    assert calls["enter"] == 1
    assert service.status()["reason"] == "换个原因"


@pytest.mark.asyncio
async def test_hook_failure_keeps_state() -> None:
    async def on_enter() -> tuple[bool, str]:
        return False, "运行时停止失败"

    service = StandbyService(on_enter=on_enter)

    ok, message = await service.enter(reason="x")
    assert ok is False and message == "运行时停止失败"
    assert service.state == RUNNING


@pytest.mark.asyncio
async def test_connect_onebot_toggle_and_noop() -> None:
    service, calls = _service()

    ok, message = await service.set_connect_onebot(False, operator="private:1")
    assert ok is True and service.connect_onebot is False
    assert calls["onebot"] == [False]
    assert "断开" in message

    ok, _ = await service.set_connect_onebot(False)
    assert ok is True
    assert calls["onebot"] == [False], "值未变化时不应再次调用钩子"


@pytest.mark.asyncio
async def test_persist_and_restore_only_connect_flag(tmp_path: Path) -> None:
    path = tmp_path / "standby.json"
    service, _ = _service(path)
    await service.enter(reason="事故")
    await service.set_connect_onebot(False)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["state"] == STANDBY
    assert payload["connect_onebot"] is False

    restored, _ = _service(path)
    assert restored.connect_onebot is False
    assert restored.state == RUNNING, "待机状态不跨进程恢复，避免静默哑火"
