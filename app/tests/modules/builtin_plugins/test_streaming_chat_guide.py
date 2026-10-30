"""通过真实命令服务、事件总线和 SQLite 验证订阅向导。"""

import asyncio
from types import SimpleNamespace

import pytest

from neobot_app.builtin_plugins.streaming_parser.chat_guide import register_chat_guide
from neobot_app.commands.registry import CommandRegistry
from neobot_app.commands.service import CommandService
from neobot_modloader import Plugin, RuntimePluginContext
from neobot_modloader.hooks import PluginHookBus
from streaming_panel_helpers import make_state


@pytest.mark.parametrize("finish", ["确认", "取消", "权限撤销", "停用"])
async def test_subscription_wizard_real_database_and_message_isolation(tmp_path, finish):
    state = await make_state(tmp_path)
    registry = CommandRegistry()
    sent = []

    class Adapter:
        self_id = 10001

        async def send(self, conversation, message):
            sent.append(message)

    ctx = RuntimePluginContext(
        plugin_name="streaming_parser",
        plugin_dir=tmp_path,
        data_dir=tmp_path,
        config={},
        logger=state.ctx.logger,
        adapter=Adapter(),
        hook_bus=PluginHookBus(),
        app_commands=registry,
    )
    plugin = Plugin("streaming_parser")
    register_chat_guide(plugin, state)
    await plugin.on_load(ctx)
    config = SimpleNamespace(
        bot=SimpleNamespace(account=10001), chat=SimpleNamespace(admin_accounts=[], sub_admin_accounts=[42])
    )

    async def send(*args, **kwargs):
        sent.append(args[2])

    service = CommandService(config=config, registry=registry, send_callback=send, register_builtins=False)
    message = SimpleNamespace(
        user_id=42, message=[{"type": "at", "data": {"qq": "10001"}}, {"type": "text", "data": {"text": "/监听向导"}}]
    )

    async def receive(text, user=42):
        raw = {
            "post_type": "message",
            "message_type": "group",
            "self_id": 10001,
            "group_id": 20001,
            "user_id": user,
            "raw_message": text,
        }
        dispatch = SimpleNamespace(raw_event=raw, consumed=False)
        dispatch.consume = lambda: setattr(dispatch, "consumed", True)
        await ctx.hook_bus.dispatch(dispatch)
        return dispatch

    async def settle():
        for _ in range(100):
            await asyncio.sleep(0.005)
            if ctx._message_waiters or not ctx._message_tasks:
                return
        pytest.fail("向导未进入等待状态")

    try:
        assert (await service.handle_message(message, kind="group", queue_key="20001")).consumed
        await settle()
        assert ctx._message_waiters
        assert not (await receive("1001", user=7)).consumed
        assert (await receive("1001")).consumed
        await settle()
        assert any("发送“确认”保存" in str(item) for item in sent)
        if finish == "权限撤销":
            config.chat.sub_admin_accounts.clear()
        if finish == "停用":
            await plugin.on_stop()
            assert ctx._message_sessions == set()
        else:
            await receive("取消" if finish == "取消" else "确认")
        for task in tuple(ctx._message_tasks):
            await task
        from neobot_app.builtin_plugins.streaming_parser.subscriptions import SubscriptionService

        rows = await SubscriptionService(state).list(20001)
        assert len(rows) == (1 if finish == "确认" else 0)
        assert ctx._message_waiters == {}
    finally:
        await plugin.on_stop()
        await state.database.close()
