"""说明书必须对应真实配置与宿主命令；外部平台只使用离线端口。"""

from types import SimpleNamespace

import pytest

from neobot_app.builtin_plugins.streaming_parser import db, plugin
from neobot_app.builtin_plugins.streaming_parser.commands import register_commands
from neobot_app.builtin_plugins.streaming_parser.config import StreamConfig
from neobot_app.builtin_plugins.streaming_parser.subscriptions import SubscriptionService
from neobot_app.commands.registry import CommandRegistry
from neobot_app.commands.service import CommandService
from neobot_modloader.context import PluginCommandRegistrar

from streaming_panel_helpers import make_state


@pytest.fixture
async def manual_host(tmp_path):
    state = await make_state(tmp_path)
    registry = CommandRegistry()
    replies = []

    async def send(kind, conversation, text, at_user_id):
        replies.append((kind, conversation, text))

    registrar = PluginCommandRegistrar(plugin_name="streaming_parser", registry=registry, record_cleanup=None)
    context = SimpleNamespace(app_commands=registrar, logger=state.ctx.logger, screenshots=None)
    register_commands(context, state)
    config = SimpleNamespace(
        bot=SimpleNamespace(account=10001),
        chat=SimpleNamespace(admin_accounts=[], sub_admin_accounts=[42]),
    )
    service = CommandService(config=config, registry=registry, send_callback=send, register_builtins=False)
    host = SimpleNamespace(state=state, registry=registry, service=service, replies=replies)
    try:
        yield host
    finally:
        await state.stop_polling()
        await state.database.close()


def manual():
    return {guide["id"]: guide for guide in plugin.surface.describe(plugin)["guides"]}


async def send_command(host, text, *, user_id=42, mentioned=True, kind="group"):
    segments = [{"type": "text", "data": {"text": text}}]
    if mentioned:
        segments.insert(0, {"type": "at", "data": {"qq": "10001"}})
    message = SimpleNamespace(user_id=user_id, message=segments)
    return await host.service.handle_message(message, kind=kind, queue_key="20001")


async def subscriptions(host):
    async with host.state.database.session() as session:
        return [db.sub_view(row) for row in await db.list_group_subscriptions(session, 20001)]


async def test_manual_covers_real_fields_and_registered_command_paths(manual_host):
    guides = manual()
    fields = set()
    command_names = set()
    steps = [step for guide in guides.values() for step in guide["steps"]]
    for step in steps:
        command = step.get("command")
        if command:
            parsed = manual_host.registry.match(command["text"])
            assert parsed is not None and parsed[0] is not None
            assert "QQ 群" in command["context"] and "@机器人" in command["context"]
            command_names.add(parsed[0].name)
            continue
        if step["target"].startswith("view.") or step.get("form"):
            continue
        name = step["target"].removeprefix("config.")
        assert step["target"].startswith("config.")
        assert set(step["example"]) == {name}
        fields.add(name)
    assert fields == set(StreamConfig.model_fields)
    assert command_names == set(manual_host.registry.names())


async def test_start_manual_commands_execute_in_real_host_and_list_current_group(manual_host):
    steps = manual()["group-commands"]["steps"][:3]
    assert (await send_command(manual_host, steps[0]["command"]["text"])).consumed
    row = (await subscriptions(manual_host))[0]
    assert (row.group_id, row.room_id, row.push_live, row.push_live_end) == (20001, 610001, True, True)
    assert "已开始监听" in manual_host.replies[-1][2]
    assert "主播: 演示主播" in manual_host.replies[-1][2]

    assert (await send_command(manual_host, steps[1]["command"]["text"], user_id=99)).consumed
    assert "本群监听的直播间" in manual_host.replies[-1][2]
    assert "610001" in manual_host.replies[-1][2]
    assert (await send_command(manual_host, steps[2]["command"]["text"], user_id=99)).consumed
    assert "本群关注的主播" in manual_host.replies[-1][2]
    assert manual_host.state.client.queried == [610001]
    assert manual_host.state.ctx.adapter.sent == []


async def test_notification_manual_commands_change_group_settings_and_cancel_only_its_subscription(manual_host):
    start = manual()["group-commands"]["steps"][0]["command"]["text"]
    await send_command(manual_host, start)
    steps = manual()["group-commands"]["steps"][3:]
    for step in steps[:-1]:
        previous = len(manual_host.replies)
        assert (await send_command(manual_host, step["command"]["text"])).consumed
        assert len(manual_host.replies) == previous + 1
        assert "失败" not in manual_host.replies[-1][2]

    row = (await subscriptions(manual_host))[0]
    assert row.push_live is False and row.push_live_end is True
    async with manual_host.state.database.session() as session:
        setting = db.setting_view(await db.get_group_setting(session, 20001))
    assert (setting.ai_reply_live, setting.ai_reply_live_end) == (False, False)
    assert setting.card_style == "minimal"
    assert (setting.default_push_live, setting.default_push_live_end) == (False, True)

    # 相同直播间在其他群的订阅不应被当前群的取消命令删除。
    await SubscriptionService(manual_host.state).create(20002, "610001")
    assert (await send_command(manual_host, steps[-1]["command"]["text"])).consumed
    assert "已取消监听" in manual_host.replies[-1][2]
    assert await subscriptions(manual_host) == []
    async with manual_host.state.database.session() as session:
        assert await db.get_subscription(session, 20002, 610001) is not None
    assert manual_host.state.ctx.adapter.sent == []


@pytest.mark.parametrize(
    ("user_id", "mentioned", "kind", "consumed", "message"),
    [
        (42, False, "group", False, ""),
        (99, True, "group", True, "需要权限:次级管理员"),
        (42, False, "private", True, "需要在群聊里发送"),
    ],
)
async def test_manual_subscription_obeys_real_mention_permission_and_group_requirements(
    manual_host, user_id, mentioned, kind, consumed, message
):
    text = manual()["group-commands"]["steps"][0]["command"]["text"]
    result = await send_command(manual_host, text, user_id=user_id, mentioned=mentioned, kind=kind)
    assert result.consumed is consumed
    assert await subscriptions(manual_host) == []
    if message:
        assert message in manual_host.replies[-1][2]
    else:
        assert manual_host.replies == []
