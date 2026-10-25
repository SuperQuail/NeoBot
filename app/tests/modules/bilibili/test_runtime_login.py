"""B站 /login 命令：真实失败原因、成功优先、单任务互斥与收尾。"""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace

from neobot_app.bilibili.runtime import BilibiliRuntime
from neobot_app.commands.registry import CommandRegistry
from neobot_app.config.schemas.bot import BotConfig


class _FakeCommandService:
    def __init__(self) -> None:
        self.registry = CommandRegistry()
        self.replies: list[str] = []

    async def reply_to(self, kind, conv_id, text, *, at_user_id=None) -> None:
        self.replies.append(text)

    async def send_image_bytes(self, *args, **kwargs) -> bool:
        return True


def _ctx(args: list[str] | None = None) -> SimpleNamespace:
    async def _reply(text: str) -> None:
        replies.append(text)

    replies: list[str] = []
    ctx = SimpleNamespace(
        kind="group",
        conv_id="100",
        user_id=1,
        args=list(args or []),
        reply=_reply,
    )
    ctx.replies = replies
    return ctx


def _build() -> tuple[BilibiliRuntime, _FakeCommandService]:
    cfg = BotConfig()
    command_service = _FakeCommandService()
    runtime = BilibiliRuntime(
        config=cfg,
        provider=None,
        archive_service=None,
        uow_factory=None,
        command_service=command_service,
        bot_name=cfg.bot.nick_name,
        bot_data=cfg.bot.bot_data,
    )
    runtime.register_commands(command_service)
    return runtime, command_service


def _login_handler(runtime: BilibiliRuntime, command_service: _FakeCommandService):
    login = command_service.registry.get("login")
    assert login is not None
    return login.handler


async def _await_login(runtime: BilibiliRuntime) -> asyncio.Task[None]:
    """等 /login 起的后台任务结束，并让 done callback 清掉引用。"""
    task = runtime._login_task
    assert task is not None
    await task
    for _ in range(10):
        if runtime._login_task is None:
            break
        await asyncio.sleep(0)
    return task


async def test_login_reports_real_failure_reason(monkeypatch) -> None:
    runtime, command_service = _build()

    async def _fail(*, on_qr=None, on_status=None) -> bool:
        return False

    monkeypatch.setattr(runtime, "login_with_qr", _fail)
    monkeypatch.setattr(
        runtime.service, "status", lambda: {"error": "B站风控拦截"}
    )
    ctx = _ctx()
    await _login_handler(runtime, command_service)(ctx)
    await _await_login(runtime)

    assert len(command_service.replies) == 1
    assert "B站风控拦截" in command_service.replies[0]


async def test_login_treats_available_service_as_success(monkeypatch) -> None:
    runtime, command_service = _build()

    async def _fake_fail(*, on_qr=None, on_status=None) -> bool:
        # B站侧其实已登录：流程报失败，但服务已经可用。
        runtime.service._client = object()
        runtime.service._started = True
        runtime.service._valid = True
        return False

    monkeypatch.setattr(runtime, "login_with_qr", _fake_fail)
    ctx = _ctx()
    await _login_handler(runtime, command_service)(ctx)
    await _await_login(runtime)

    assert len(command_service.replies) == 1
    assert "B站登录成功" in command_service.replies[0]


async def test_login_success_with_warning_mentions_note(monkeypatch) -> None:
    runtime, command_service = _build()
    reason = "登录成功，但凭证保存失败，重启后需重新登录"

    async def _ok(*, on_qr=None, on_status=None) -> bool:
        return True

    monkeypatch.setattr(runtime, "login_with_qr", _ok)
    monkeypatch.setattr(runtime.service, "status", lambda: {"error": reason})
    ctx = _ctx()
    await _login_handler(runtime, command_service)(ctx)
    await _await_login(runtime)

    assert len(command_service.replies) == 1
    assert "B站登录成功" in command_service.replies[0]
    assert "注意" in command_service.replies[0]
    assert reason in command_service.replies[0]


async def test_second_login_cancels_first_and_replies_once(monkeypatch) -> None:
    runtime, command_service = _build()
    started = asyncio.Event()
    release = asyncio.Event()
    calls: list[int] = []

    async def _controlled(*, on_qr=None, on_status=None) -> bool:
        calls.append(1)
        if len(calls) == 1:
            started.set()
            await release.wait()
            return False
        return True

    monkeypatch.setattr(runtime, "login_with_qr", _controlled)
    monkeypatch.setattr(runtime.service, "status", lambda: {"error": ""})
    handler = _login_handler(runtime, command_service)

    await handler(_ctx())
    first = runtime._login_task
    assert first is not None
    await asyncio.wait_for(started.wait(), timeout=5)

    await handler(_ctx())
    second = runtime._login_task
    assert second is not None
    await second

    with contextlib.suppress(asyncio.CancelledError):
        await first
    assert first.cancelled()
    assert command_service.replies == ["B站登录成功。"]


async def test_login_success_ensures_live_listener(monkeypatch) -> None:
    runtime, _ = _build()
    runtime._started = True
    started: list[bool] = []

    async def _ensure() -> None:
        started.append(True)

    async def _ok(*, on_qr=None, on_status=None) -> bool:
        return True

    monkeypatch.setattr(runtime.live_interactor, "ensure_started", _ensure)
    monkeypatch.setattr(runtime.service, "login_with_qr", _ok)

    assert await runtime.login_with_qr() is True
    assert started == [True]


async def test_live_toggle_enable_requires_login(monkeypatch) -> None:
    """未登录时 /直播互动 开 只提示，不出"监听开"的假成功卡片。"""
    runtime, command_service = _build()
    calls: list[str] = []

    async def _refresh() -> bool:
        calls.append("refresh")
        return False

    monkeypatch.setattr(runtime.service, "refresh", _refresh)
    handler = command_service.registry.get("直播互动").handler

    result = await handler(_ctx(["5440", "开"]))

    assert calls == ["refresh"]  # 先自愈再判登录态
    assert "未登录" in result
    assert runtime.live_interactor.list_rooms() == []


async def test_login_task_reference_cleared_after_finish(monkeypatch) -> None:
    runtime, command_service = _build()

    async def _fail(*, on_qr=None, on_status=None) -> bool:
        return False

    monkeypatch.setattr(runtime, "login_with_qr", _fail)
    monkeypatch.setattr(runtime.service, "status", lambda: {"error": ""})
    await _login_handler(runtime, command_service)(_ctx())
    await _await_login(runtime)

    assert runtime._login_task is None
