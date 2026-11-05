"""验证公开 SDK 的消息隔离、命令鉴权与卸载边界。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_contracts.ports.logging import NullLogger
from neobot_modloader import IncomingEvent, Plugin, Rule, RuntimePluginContext, starts_with
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.messaging import MessageWaitBusy


def event(text="hello", *, user=42, group=20001, bot=10001):
    return {
        "post_type": "message",
        "message_type": "group",
        "self_id": bot,
        "group_id": group,
        "user_id": user,
        "message": [{"type": "text", "data": {"text": text}}],
    }


class Dispatch:
    def __init__(self, raw):
        self.raw_event = raw
        self.consumed = False

    def consume(self):
        self.consumed = True


def context(tmp_path, *, registry=None):
    return RuntimePluginContext(
        plugin_name="conversation",
        plugin_dir=tmp_path,
        data_dir=tmp_path,
        config={},
        logger=NullLogger(),
        adapter=SimpleNamespace(self_id=10001, send=AsyncMock()),
        hook_bus=PluginHookBus(),
        app_commands=registry,
    )


async def test_rules_short_circuit_and_typed_notice_injection(tmp_path):
    calls = []

    async def second(raw):
        calls.append(raw)
        return True

    assert not await (starts_with("/") & Rule(second))(event("hello"))
    assert await (starts_with("/") | Rule(second))(event("/ping"))
    assert calls == []
    plugin = Plugin("conversation")
    seen = []

    @plugin.event(post_type="notice", notice_type="group_increase")
    async def joined(incoming: IncomingEvent):
        seen.append((incoming.group_id, incoming.sender.user_id))

    ctx = context(tmp_path)
    await plugin.on_load(ctx)
    await ctx.hook_bus.dispatch(Dispatch({"post_type": "notice", "notice_type": "group_decrease", "user_id": 42}))
    await ctx.hook_bus.dispatch(
        Dispatch({"post_type": "notice", "notice_type": "group_increase", "user_id": 42, "group_id": 20001})
    )
    assert seen == [(20001, "42")]
    await plugin.on_stop()


async def test_waiter_scopes_and_consumes_only_matching_user_message(tmp_path):
    ctx = context(tmp_path)
    waiting = ctx.create_task(ctx.wait_for_message(IncomingEvent(event()), rule=~starts_with("/"), prompt="链接？"))
    await asyncio.sleep(0)
    assert ctx.adapter.send.await_count == 1
    with pytest.raises(MessageWaitBusy):
        await ctx.wait_for_message(IncomingEvent(event()))
    for raw in [event(user=7), event(group=9), event(bot=8), event("/help")]:
        dispatch = Dispatch(raw)
        await ctx.hook_bus.dispatch(dispatch)
        assert not dispatch.consumed
        assert not waiting.done()
    dispatch = Dispatch(event("1001"))
    await ctx.hook_bus.dispatch(dispatch)
    assert dispatch.consumed
    assert (await waiting).chain.plain_text == "1001"
    assert ctx.hook_bus._hooks == []
    await ctx.close_tasks()


async def test_waiter_timeout_cancellation_prompt_failure_and_plugin_stop_cleanup(tmp_path):
    ctx = context(tmp_path)
    origin = IncomingEvent(event())
    with pytest.raises(TimeoutError):
        await ctx.wait_for_message(origin, timeout=0.01)
    ctx.adapter.send.side_effect = RuntimeError("offline")
    with pytest.raises(RuntimeError, match="offline"):
        await ctx.wait_for_message(origin, prompt="链接？")
    assert ctx._message_waiters == {}
    assert ctx.hook_bus._hooks == []

    # 提示发送本身也必须受等待超时约束，不能留下永久监听。
    async def stalled_send(*args):
        await asyncio.Event().wait()

    ctx.adapter.send.side_effect = stalled_send
    with pytest.raises(TimeoutError):
        await ctx.wait_for_message(origin, timeout=0.01, prompt="链接？")
    assert ctx.hook_bus._hooks == []
    waiting = ctx.create_task(ctx.wait_for_message(origin))
    await asyncio.sleep(0)
    plugin = Plugin("conversation")

    @plugin.on_shutdown
    async def verify_tasks_stopped_before_business_cleanup():
        assert waiting.cancelled()

    await plugin.on_load(ctx)
    await plugin.on_stop()
    assert waiting.cancelled()
    assert ctx.hook_bus._hooks == []
    assert ctx._message_waiters == {}


async def test_session_remains_busy_between_waits_and_releases_on_cancel(tmp_path):
    ctx = context(tmp_path)
    origin = IncomingEvent(event())
    entered = asyncio.Event()

    async def interaction():
        async with ctx.message_session(origin):
            entered.set()
            await asyncio.Event().wait()

    task = ctx.create_task(interaction())
    await entered.wait()
    with pytest.raises(MessageWaitBusy):
        async with ctx.message_session(origin):
            pytest.fail("重复交互不应取得会话")
    await ctx.close_tasks()
    assert task.cancelled()
    assert ctx._message_sessions == set()


async def test_managed_command_uses_real_permissions_help_aliases_and_rename(tmp_path):
    from neobot_app.commands.model import Command
    from neobot_app.commands.registry import CommandRegistry
    from neobot_app.commands.service import CommandService

    registry = CommandRegistry()
    registry.register(Command(name="echo", description="占位", handler=AsyncMock()))
    ctx = context(tmp_path, registry=registry)
    plugin = Plugin("conversation")
    seen = []

    @plugin.command("echo <count:int>", permission=1, description="回显数量", aliases=["say"])
    async def echo(count: int, incoming: IncomingEvent):
        seen.append((count, incoming.sender.user_id))
        return str(count)

    await plugin.on_load(ctx)
    replies = []

    async def send(*args, **kwargs):
        replies.append(args)

    service = CommandService(
        config=SimpleNamespace(
            bot=SimpleNamespace(account=10001), chat=SimpleNamespace(admin_accounts=[], sub_admin_accounts=[42])
        ),
        registry=registry,
        send_callback=send,
        register_builtins=False,
    )

    async def invoke(text, user):
        message = SimpleNamespace(
            user_id=user, message=[{"type": "at", "data": {"qq": "10001"}}, {"type": "text", "data": {"text": text}}]
        )
        return await service.handle_message(message, kind="group", queue_key="20001")

    command = registry.match("/conversation__echo 3")[0]
    assert command.permission == 1
    assert command.source == "conversation"
    assert "回显数量" in command.help_line
    assert "<count:int>" in command.help_line
    assert (await invoke("/conversation__echo 3", 7)).consumed
    assert seen == []
    assert (await invoke("/conversation__echo bad", 42)).consumed
    assert seen == []
    assert (await invoke("/conversation__echo 3", 42)).consumed
    assert (await invoke("/say 4", 42)).consumed
    assert seen == [(3, "42"), (4, "42")]
    ctx.app_commands.unregister_all()
    assert registry.match("/say 4")[0] is None
    assert registry.match("/conversation__echo 3")[0] is None
    await plugin.on_stop()


def test_managed_command_cannot_shadow_trusted_command_context():
    plugin = Plugin("conversation")
    with pytest.raises(ValueError, match="保留参数"):
        plugin.command("echo <command_context:str>", permission=1)
