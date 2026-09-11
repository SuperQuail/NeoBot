"""待机命令：/standby /reboot /standby_status 的文案与缺服务降级。

本文件同时守一个回归：/reboot 只能注册一个（旧的进程重启条目曾与新软重启撞名，
导致 CommandService(register_builtins=True) 直接抛 ValueError）。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_app.commands.builtin import (
    _handle_reboot,
    _handle_standby,
    _handle_standby_status,
)
from neobot_app.commands.service import CommandService
from neobot_app.runtime.standby_service import StandbyService


def _ctx(standby, *args: str):
    """命令处理器拿到的 ctx.service 是 CommandService（其上有 standby_service 属性）。"""
    return SimpleNamespace(
        service=SimpleNamespace(standby_service=standby),
        args=list(args),
        kind="private",
        user_id=10001,
    )


def test_builtin_commands_have_no_duplicate_reboot() -> None:
    service = CommandService(config=None, register_builtins=True)
    names = service.registry.names()

    assert names.count("reboot") == 1
    assert "standby" in names and "standby_status" in names
    assert not {"freeze", "unfreeze", "freeze_status"} & set(names)


@pytest.mark.asyncio
async def test_standby_command_enters_standby() -> None:
    standby = StandbyService()
    message = await _handle_standby(_ctx(standby, "token", "风暴"))

    assert standby.is_standby() is True
    assert "已进入待机" in message
    assert standby.status()["reason"] == "token 风暴"
    assert standby.status()["operator"] == "private:10001"


@pytest.mark.asyncio
async def test_reboot_command_soft_restarts() -> None:
    standby = StandbyService()
    await standby.enter(reason="先待机")

    message = await _handle_reboot(_ctx(standby, "改完配置"))

    assert standby.is_standby() is False
    assert "运行" in message


@pytest.mark.asyncio
async def test_standby_status_text() -> None:
    standby = StandbyService()

    assert "运行中" in await _handle_standby_status(_ctx(standby))

    await standby.enter(reason="排查中", operator="private:1")
    text = await _handle_standby_status(_ctx(standby))
    assert "待机" in text and "排查中" in text and "/reboot" in text


@pytest.mark.asyncio
async def test_commands_report_missing_service() -> None:
    ctx = _ctx(None)

    assert "不可用" in await _handle_standby(ctx)
    assert "不可用" in await _handle_reboot(ctx)
    assert "不可用" in await _handle_standby_status(ctx)
