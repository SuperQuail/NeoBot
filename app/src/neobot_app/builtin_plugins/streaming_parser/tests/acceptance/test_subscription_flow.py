"""插件包独立离线验收：真实数据库、面板和轮询，仅替换外部平台。"""

import asyncio
from types import SimpleNamespace

import pytest
import streaming_parser as package
from streaming_parser import db
from streaming_parser.bilibili.models import LiveRoomInfo

from neobot_contracts.ports.logging import NullLogger
from neobot_modloader import ActionError
from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.sdk import ActionInvocation


class Adapter:
    self_id = 10001

    def __init__(self):
        self.sent = []

    async def call_api(self, action, params, timeout=5):
        assert action == "get_group_list"
        return {
            "status": "ok",
            "data": [{"group_id": 20001, "group_name": "离线验收群"}],
        }

    async def send_group_msg(self, group_id, message):
        self.sent.append((group_id, message))


class Client:
    def __init__(self, *args, **kwargs):
        self.checked = []
        self.closed = False

    async def fetch_live_room_init(self, value):
        return SimpleNamespace(room_id=610001, uid=510001, short_id=1001)

    async def fetch_user_card(self, uid):
        return SimpleNamespace(name="离线验收主播", face="")

    async def fetch_live_room_info(self, room_id):
        self.checked.append(room_id)
        return LiveRoomInfo(
            room_id=room_id,
            short_id=1001,
            uid=510001,
            title="测试新的通知流程",
            live_status=0,
            live_time=None,
        )

    async def aclose(self):
        self.closed = True


@pytest.fixture
async def plugin(tmp_path, monkeypatch):
    monkeypatch.setattr(package, "BilibiliLiveClient", Client)
    adapter = Adapter()
    context = RuntimePluginContext(
        plugin_name="streaming_parser",
        plugin_dir=package.PLUGIN_DIR,
        data_dir=tmp_path,
        config={"default_ai_reply_live": False, "default_ai_reply_live_end": False},
        logger=NullLogger(),
        adapter=adapter,
    )
    await package.plugin.on_load(context)
    try:
        yield package.plugin, adapter
    finally:
        await package.plugin.on_stop()


async def action(plugin, name, values=None, permission="manage"):
    return await plugin.surface.invoke(
        plugin,
        "subscriptions." + name,
        values or {},
        ActionInvocation("package-acceptance", frozenset({permission})),
    )


async def test_preview_and_readonly_cannot_mutate_subscriptions(plugin):
    instance, adapter = plugin
    groups = await action(instance, "groups", permission="read")
    assert groups["items"][0]["name"] == "离线验收群"
    preview = await action(
        instance, "preview", {"group_id": 20001, "target": "1001"}, permission="read"
    )
    assert "离线验收主播" in preview["html"]
    assert "测试新的通知流程" in preview["fallback_text"]
    assert (await action(instance, "list", permission="read"))["items"] == []
    assert adapter.sent == []
    with pytest.raises(ActionError) as error:
        await action(
            instance, "create", {"group_id": 20001, "target": "1001"}, permission="read"
        )
    assert error.value.code == "permission_denied"


async def test_subscription_keeps_group_defaults_and_manual_switches(plugin):
    instance, _ = plugin
    async with package.state.database.transaction() as session:
        await db.ensure_group_setting(
            session, 20001, {"default_push_live": False, "default_push_live_end": True}
        )
    created = await action(instance, "create", {"group_id": 20001, "target": "1001"})
    assert created["created"] is True
    assert created["item"]["push_live"] is False
    await action(
        instance,
        "toggle",
        {
            "group_id": 20001,
            "room_id": 610001,
            "push_live": True,
            "push_live_end": False,
        },
    )
    duplicate = await action(instance, "create", {"group_id": 20001, "target": "1001"})
    assert duplicate["created"] is False
    assert duplicate["item"]["push_live"] is True
    assert duplicate["item"]["push_live_end"] is False
    assert len((await action(instance, "list"))["items"]) == 1
    assert (await action(instance, "remove", {"group_id": 20001, "room_id": 610001}))[
        "removed"
    ]
    assert (await action(instance, "list"))["items"] == []


async def test_completion_requires_a_running_poller_and_a_saved_observation(plugin):
    instance, adapter = plugin
    await action(instance, "create", {"group_id": 20001, "target": "1001"})
    assert (await action(instance, "ready", permission="read"))["completed"] is False
    await instance.on_start()

    async def observed():
        while not (await action(instance, "ready", permission="read"))["completed"]:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(observed(), timeout=2)
    status = await action(instance, "health", permission="read")
    assert status["running"] and status["success_at"] is not None
    assert status["subscriptions"] == 1
    assert adapter.sent == []
    await package.state.stop_polling()
    assert (await action(instance, "ready", permission="read"))["completed"] is False
