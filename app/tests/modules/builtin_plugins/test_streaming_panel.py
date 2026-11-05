"""流媒体完整订阅业务：共用规则、真实落库、预览与真实轮询完成条件。"""

import asyncio
from types import SimpleNamespace

import pytest

from neobot_app.builtin_plugins.streaming_parser import db
from neobot_modloader import Plugin
from neobot_modloader.sdk import ActionError, ActionInvocation

from streaming_panel_helpers import make_state


@pytest.fixture
async def state(tmp_path):
    value = await make_state(tmp_path)
    try:
        yield value
    finally:
        await value.stop_polling()
        await value.database.close()


def caller(permission="manage"):
    return ActionInvocation("streaming-test", frozenset({permission}))


def surface(state):
    from neobot_app.builtin_plugins.streaming_parser.panel import register_surface

    plugin = Plugin("streaming_parser", version="0.3.1")
    register_surface(plugin, state)
    return plugin


async def invoke(plugin, action, values=None, permission="manage"):
    action_id = action if "." in action else "subscriptions." + action
    return await plugin.surface.invoke(plugin, action_id, values or {}, caller(permission))


async def test_subscription_service_preserves_group_defaults_and_existing_switches(state):
    from neobot_app.builtin_plugins.streaming_parser.subscriptions import SubscriptionService

    async with state.database.transaction() as session:
        await db.ensure_group_setting(session, 20001, {"default_push_live": False, "default_push_live_end": True})
    service = SubscriptionService(state)
    row, created = await service.create(20001, "https://live.bilibili.com/1001")
    assert created is True
    assert (row.room_id, row.push_live, row.push_live_end) == (610001, False, True)
    await service.toggle(20001, 610001, push_live=True, push_live_end=False)
    row, created = await service.create(20001, "uid:510001")
    assert created is False
    assert (row.push_live, row.push_live_end) == (True, False)


async def test_panel_uses_live_group_directory_and_rejects_forged_group(state):
    plugin = surface(state)
    groups = await invoke(plugin, "groups", permission="read")
    assert groups == {"items": [{"group_id": 20001, "name": "演示交流组", "bot_id": "10001"}]}
    with pytest.raises(ActionError) as error:
        await invoke(plugin, "create", {"group_id": 99999, "target": "1001"})
    assert error.value.code == "group_unavailable"
    async with state.database.session() as session:
        assert await db.distinct_room_ids(session) == []


async def test_group_transport_failure_keeps_public_error_and_logs_only_failure_type(state, monkeypatch):
    warnings = []

    async def unavailable(action, params):
        raise RuntimeError("https://adapter.invalid/?token=synthetic-view-token")

    monkeypatch.setattr(state.ctx.adapter, "call_api", unavailable)
    monkeypatch.setattr(state.ctx.logger, "warning", warnings.append)
    with pytest.raises(ActionError) as error:
        await invoke(surface(state), "groups", permission="read")
    assert error.value.code == "group_list_unavailable"
    assert error.value.message == "暂时无法读取机器人所在的群，请检查机器人连接。"
    assert warnings == ["读取机器人群目录失败，适配器异常类型：RuntimeError"]


async def test_group_response_validation_does_not_log_the_private_response(state, monkeypatch):
    warnings = []

    async def malformed(action, params):
        return {
            "status": "ok",
            "retcode": 0,
            "data": [{"group_id": "synthetic-private-business-input", "group_name": "合成群目录"}],
        }

    monkeypatch.setattr(state.ctx.adapter, "call_api", malformed)
    monkeypatch.setattr(state.ctx.logger, "warning", warnings.append)
    with pytest.raises(ActionError) as error:
        await invoke(surface(state), "groups", permission="read")
    assert error.value.code == "group_list_unavailable"
    assert error.value.message == "暂时无法读取机器人所在的群，请检查机器人连接。"
    assert warnings == ["机器人群目录响应结构无效，请检查适配器返回格式。"]


async def test_readonly_cannot_create_or_change_data(state):
    plugin = surface(state)
    with pytest.raises(ActionError) as error:
        await invoke(plugin, "create", {"group_id": 20001, "target": "1001"}, permission="read")
    assert error.value.code == "permission_denied"
    assert (await invoke(plugin, "list", permission="read"))["items"] == []


async def test_preview_uses_notification_template_without_creating_or_sending(state):
    plugin = surface(state)
    preview = await invoke(plugin, "preview", {"group_id": 20001, "target": "1001"}, permission="read")
    assert preview["target"]["room_id"] == 610001
    assert "演示主播" in preview["html"]
    assert "一起认识新的插件面板" in preview["html"]
    assert "card" in preview["html"]
    assert "一起认识新的插件面板" in preview["fallback_text"]
    assert state.ctx.adapter.sent == []
    assert (await invoke(plugin, "list", permission="read"))["items"] == []


async def test_first_subscription_wakes_real_poller_and_completion_is_not_just_saved(state):
    plugin = surface(state)
    created = await invoke(plugin, "create", {"group_id": 20001, "target": "1001"})
    assert created["created"] is True
    assert (await invoke(plugin, "ready", permission="read"))["completed"] is False
    await state.start_polling()

    async def observed():
        while True:
            ready = await invoke(plugin, "ready", permission="read")
            if ready["completed"]:
                return ready
            await asyncio.sleep(0.01)

    assert (await asyncio.wait_for(observed(), 2))["completed"] is True
    health = await invoke(plugin, "health", permission="read")
    assert health["running"] is True
    assert health["subscriptions"] == 1
    assert health["success_at"] is not None
    assert state.client.queried == [610001]
    await state.stop_polling()
    assert (await invoke(plugin, "ready", permission="read"))["completed"] is False


async def test_subscribing_after_empty_initial_poll_does_not_wait_for_interval(state):
    plugin = surface(state)
    await state.start_polling()
    await asyncio.sleep(0)
    await invoke(plugin, "create", {"group_id": 20001, "target": "1001"})

    async def observed():
        while not state.client.queried:
            await asyncio.sleep(0.01)

    await asyncio.wait_for(observed(), 2)
    assert state.client.queried == [610001]


async def test_list_toggle_and_remove_use_saved_records(state):
    plugin = surface(state)
    await invoke(plugin, "create", {"group_id": 20001, "target": "1001"})
    row = (await invoke(plugin, "list", permission="read"))["items"][0]
    assert row["name"] == "演示主播"
    changed = await invoke(
        plugin, "toggle", {"group_id": 20001, "room_id": 610001, "push_live": False, "push_live_end": True}
    )
    assert changed["item"]["push_live"] is False
    assert changed["item"]["push_live_end"] is True
    assert await invoke(plugin, "remove", {"group_id": 20001, "room_id": 610001}) == {"removed": True}
    assert (await invoke(plugin, "list", permission="read"))["items"] == []


async def test_manager_can_manage_saved_subscription_after_bot_leaves_group(state, monkeypatch):
    plugin = surface(state)
    await invoke(plugin, "create", {"group_id": 20001, "target": "1001"})

    async def no_groups(*arguments, **options):
        return {"status": "ok", "retcode": 0, "data": []}

    monkeypatch.setattr(state.ctx.adapter, "call_api", no_groups)
    assert await invoke(plugin, "groups", permission="read") == {"items": []}
    with pytest.raises(ActionError) as error:
        await invoke(plugin, "remove", {"group_id": 20001, "room_id": 610001}, permission="read")
    assert error.value.code == "permission_denied"
    changed = await invoke(
        plugin, "toggle", {"group_id": 20001, "room_id": 610001, "push_live": False, "push_live_end": False}
    )
    assert changed["item"]["push_live"] is False
    assert changed["item"]["push_live_end"] is False
    assert await invoke(plugin, "remove", {"group_id": 20001, "room_id": 610001}) == {"removed": True}
    assert (await invoke(plugin, "list", permission="read"))["items"] == []


async def test_health_explains_platform_failure_from_actual_poll(state):
    plugin = surface(state)
    await invoke(plugin, "create", {"group_id": 20001, "target": "1001"})
    state.client.fail = True
    await state.poller.poll_once()
    health = await invoke(plugin, "health", permission="read")
    assert health["failed"] == 1
    assert health["checked"] == 0
    assert health["checked_at"] is not None
    assert health["success_at"] is None
    assert "610001" in health["error"]
    assert "合成的外部连接失败" not in health["error"]


async def test_chat_and_panel_keep_the_same_group_defaults_and_existing_switches(state):
    from neobot_app.builtin_plugins.streaming_parser.commands import register_commands

    handlers = {}

    class Registrar:
        available = True

        def register(self, name, **metadata):
            def decorate(handler):
                handlers[name] = handler
                return handler

            return decorate

    replies = []

    async def reply(text):
        replies.append(text)

    context = SimpleNamespace(kind="group", conv_id="20001", args=["1001"], reply_plain=reply)
    command_host = SimpleNamespace(app_commands=Registrar(), logger=state.ctx.logger, screenshots=None)
    async with state.database.transaction() as session:
        await db.ensure_group_setting(session, 20001, {"default_push_live": False, "default_push_live_end": True})
    register_commands(command_host, state)
    await handlers["监听"](context)
    plugin = surface(state)
    row = (await invoke(plugin, "list", permission="read"))["items"][0]
    assert row["push_live"] is False and row["push_live_end"] is True
    await invoke(plugin, "toggle", {"group_id": 20001, "room_id": 610001, "push_live": True, "push_live_end": False})
    await handlers["监听"](context)
    row = (await invoke(plugin, "list", permission="read"))["items"][0]
    assert row["push_live"] is True and row["push_live_end"] is False
    assert len(replies) == 2


def group_settings_values(**changes):
    return {
        "group_id": 20001,
        "card_style": "neon",
        "ai_reply_live": False,
        "ai_reply_live_end": True,
        "default_push_live": False,
        "default_push_live_end": True,
        **changes,
    }


async def test_group_settings_read_uses_current_config_without_creating_row(state):
    state.config.default_card_style = "minimal"
    state.config.default_ai_reply_live = False
    state.config.default_ai_reply_live_end = True
    state.config.default_push_live = False
    state.config.default_push_live_end = False
    plugin = surface(state)
    expected = group_settings_values(card_style="minimal", default_push_live_end=False)
    assert await invoke(plugin, "groups.settings.get", {"group_id": 20001}, permission="read") == {
        **expected,
        "inherited": True,
    }
    state.config.default_card_style = "sakura"
    assert (await invoke(plugin, "groups.settings.get", {"group_id": 20001}, permission="read"))[
        "card_style"
    ] == "sakura"
    async with state.database.session() as session:
        assert await db.get_group_setting(session, 20001) is None
    assert state.ctx.adapter.calls == []


@pytest.mark.parametrize(
    "style,expected",
    [
        (" NEON ", "neon"),
        (" RANDOM ", "random"),
        ("随机", "random"),
        ("", "random"),
        ("synthetic-unknown-style", "random"),
    ],
)
async def test_group_settings_get_normalizes_inherited_style_without_saving(state, style, expected):
    state.config.default_card_style = style
    result = await invoke(surface(state), "groups.settings.get", {"group_id": 20001}, permission="read")
    assert result["card_style"] == expected
    assert result["inherited"] is True
    assert state.config.default_card_style == style
    async with state.database.session() as session:
        assert await db.get_group_setting(session, 20001) is None
    assert state.ctx.adapter.calls == []


@pytest.mark.parametrize(
    "style,global_style,expected",
    [
        (" NEON ", "minimal", "neon"),
        (" RANDOM ", "minimal", "random"),
        ("随机", "minimal", "random"),
        ("synthetic-unknown-style", "neon", "random"),
        ("", " SAKURA ", "random"),
        ("", "synthetic-unknown-style", "random"),
        ("   ", "neon", "random"),
    ],
)
async def test_group_settings_get_normalizes_saved_legacy_style_without_rewriting_row(
    state, style, global_style, expected
):
    state.config.default_card_style = global_style
    async with state.database.transaction() as session:
        await db.ensure_group_setting(
            session,
            20001,
            {
                "card_style": style,
                "ai_reply_live": False,
                "ai_reply_live_end": True,
                "default_push_live": False,
                "default_push_live_end": True,
            },
        )
    async with state.database.session() as session:
        row = await db.get_group_setting(session, 20001)
        before = (row.card_style, row.updated_at)
    result = await invoke(surface(state), "groups.settings.get", {"group_id": 20001}, permission="read")
    assert result == {**group_settings_values(card_style=expected), "inherited": False}
    async with state.database.session() as session:
        row = await db.get_group_setting(session, 20001)
        assert (row.card_style, row.updated_at) == before
    assert state.ctx.adapter.calls == []


@pytest.mark.parametrize("style", ["random", "sakura", "neon", "minimal"])
async def test_group_settings_update_persists_all_fields_and_reads_saved_snapshot(state, style):
    plugin = surface(state)
    values = group_settings_values(card_style=style)
    expected = {**values, "inherited": False}
    assert await invoke(plugin, "groups.settings.update", values) == expected
    state.config.default_card_style = "minimal" if style != "minimal" else "neon"
    state.config.default_ai_reply_live = True
    state.config.default_ai_reply_live_end = False
    state.config.default_push_live = True
    state.config.default_push_live_end = False
    assert await invoke(surface(state), "groups.settings.get", {"group_id": 20001}, permission="read") == expected
    async with state.database.session() as session:
        row = db.setting_view(await db.get_group_setting(session, 20001))
    assert row is not None
    assert row.card_style == style
    assert (row.ai_reply_live, row.ai_reply_live_end) == (False, True)
    assert (row.default_push_live, row.default_push_live_end) == (False, True)
    assert state.ctx.adapter.sent == []


async def test_group_settings_defaults_apply_only_to_new_subscriptions(state):
    from neobot_app.builtin_plugins.streaming_parser.subscriptions import SubscriptionService

    plugin = surface(state)
    await invoke(plugin, "create", {"group_id": 20001, "target": "1001"})
    before = (await invoke(plugin, "list", permission="read"))["items"]
    await invoke(plugin, "groups.settings.update", group_settings_values(default_push_live_end=False))
    assert (await invoke(plugin, "list", permission="read"))["items"] == before
    repeated = await invoke(plugin, "create", {"group_id": 20001, "target": "1001"})
    assert repeated["created"] is False
    assert (repeated["item"]["push_live"], repeated["item"]["push_live_end"]) == (True, True)
    new_row, created = await SubscriptionService(state).create_resolved(20001, {"room_id": 610002})
    assert created is True
    assert (new_row.push_live, new_row.push_live_end) == (False, False)
    await invoke(plugin, "groups.settings.update", group_settings_values())
    assert (await invoke(plugin, "list", permission="read"))["items"][1]["push_live_end"] is False


@pytest.mark.parametrize("permission", ["read", "operate"])
async def test_group_settings_update_requires_manage_before_adapter_or_db_access(state, permission):
    plugin = surface(state)
    with pytest.raises(ActionError) as error:
        await invoke(plugin, "groups.settings.update", group_settings_values(), permission=permission)
    assert error.value.code == "permission_denied"
    assert error.value.message == "没有执行此动作的权限"
    assert state.ctx.adapter.calls == []
    async with state.database.session() as session:
        assert await db.get_group_setting(session, 20001) is None


async def test_group_settings_get_requires_read_permission(state):
    plugin = surface(state)
    with pytest.raises(ActionError) as error:
        await plugin.surface.invoke(
            plugin,
            "groups.settings.get",
            {"group_id": 20001},
            ActionInvocation("streaming-test", frozenset()),
        )
    assert error.value.code == "permission_denied"
    assert state.ctx.adapter.calls == []


@pytest.mark.parametrize("action", ["groups.settings.get", "groups.settings.update"])
@pytest.mark.parametrize("group_id", [0, -1, True, "20001", 20001.0, None])
async def test_group_settings_rejects_non_positive_or_coerced_group_ids(state, action, group_id):
    values = group_settings_values(group_id=group_id) if action.endswith("update") else {"group_id": group_id}
    with pytest.raises(ActionError) as error:
        await invoke(surface(state), action, values)
    assert error.value.code == "invalid_input"
    assert error.value.message == "动作输入不符合声明"
    assert state.ctx.adapter.calls == []
    async with state.database.session() as session:
        assert await db.get_group_setting(session, 20001) is None


@pytest.mark.parametrize(
    "field",
    [
        "ai_reply_live",
        "ai_reply_live_end",
        "default_push_live",
        "default_push_live_end",
    ],
)
@pytest.mark.parametrize("value", ["false", 0, 1, None])
async def test_group_settings_requires_actual_booleans(state, field, value):
    with pytest.raises(ActionError) as error:
        await invoke(surface(state), "groups.settings.update", group_settings_values(**{field: value}))
    assert error.value.code == "invalid_input"
    assert error.value.fields == [{"path": [field], "type": "bool_type"}]
    assert state.ctx.adapter.calls == []


@pytest.mark.parametrize("style", ["", "NEON", "随机", "unknown", 1, None])
async def test_group_settings_rejects_unregistered_styles_without_echoing_input(state, style):
    with pytest.raises(ActionError) as error:
        await invoke(surface(state), "groups.settings.update", group_settings_values(card_style=style))
    assert error.value.to_dict() == {
        "code": "invalid_input",
        "message": "动作输入不符合声明",
        "fields": [{"path": ["card_style"], "type": "literal_error"}],
    }
    assert state.ctx.adapter.calls == []


@pytest.mark.parametrize(
    "action,values",
    [
        ("groups.settings.get", {}),
        ("groups.settings.get", {"group_id": 20001, "synthetic-private-token": "not-public"}),
        ("groups.settings.update", {"group_id": 20001}),
        ("groups.settings.update", group_settings_values(inherited=True)),
        ("groups.settings.update", group_settings_values(**{"synthetic-private-token": "not-public"})),
    ],
)
async def test_group_settings_requires_exact_declared_input_without_leaking_unknown_fields(state, action, values):
    with pytest.raises(ActionError) as error:
        await invoke(surface(state), action, values)
    assert error.value.code == "invalid_input"
    assert "synthetic-private-token" not in str(error.value.to_dict())
    assert "not-public" not in str(error.value.to_dict())
    assert state.ctx.adapter.calls == []


async def test_group_settings_rejects_group_no_longer_joined_without_changing_saved_settings(state, monkeypatch):
    plugin = surface(state)
    saved = await invoke(plugin, "groups.settings.update", group_settings_values())

    async def no_groups(*arguments, **options):
        return {"status": "ok", "retcode": 0, "data": []}

    monkeypatch.setattr(state.ctx.adapter, "call_api", no_groups)
    with pytest.raises(ActionError) as error:
        await invoke(plugin, "groups.settings.update", group_settings_values(card_style="minimal"))
    assert error.value.code == "group_unavailable"
    assert error.value.message == "机器人不在这个群中，请重新选择接收群。"
    assert await invoke(plugin, "groups.settings.get", {"group_id": 20001}, permission="read") == saved
    with pytest.raises(ActionError) as error:
        await invoke(plugin, "groups.settings.update", group_settings_values(group_id=99999))
    assert error.value.code == "group_unavailable"
    async with state.database.session() as session:
        assert await db.get_group_setting(session, 99999) is None


async def test_group_settings_adapter_failure_does_not_block_local_settings_list_health_or_mutations(
    state, monkeypatch
):
    plugin = surface(state)
    await invoke(plugin, "create", {"group_id": 20001, "target": "1001"})
    saved = await invoke(plugin, "groups.settings.update", group_settings_values())
    before = await invoke(plugin, "list", permission="read")
    health = await invoke(plugin, "health", permission="read")
    warnings = []

    async def unavailable(*arguments, **options):
        raise RuntimeError("https://adapter.invalid/?token=synthetic-private-token")

    monkeypatch.setattr(state.ctx.adapter, "call_api", unavailable)
    monkeypatch.setattr(state.ctx.logger, "warning", warnings.append)
    with pytest.raises(ActionError) as error:
        await invoke(plugin, "groups.settings.update", group_settings_values(card_style="minimal"))
    assert error.value.code == "group_list_unavailable"
    assert error.value.message == "暂时无法读取机器人所在的群，请检查机器人连接。"
    assert warnings == ["读取机器人群目录失败，适配器异常类型：RuntimeError"]
    assert await invoke(plugin, "groups.settings.get", {"group_id": 20001}, permission="read") == saved
    assert await invoke(plugin, "list", permission="read") == before
    assert await invoke(plugin, "health", permission="read") == health
    assert (await invoke(plugin, "groups.settings.get", {"group_id": 99999}, permission="read"))["inherited"] is True
    changed = await invoke(
        plugin, "toggle", {"group_id": 20001, "room_id": 610001, "push_live": False, "push_live_end": False}
    )
    assert changed["item"]["push_live"] is False
    assert await invoke(plugin, "remove", {"group_id": 20001, "room_id": 610001}) == {"removed": True}


async def test_group_settings_database_failure_is_not_exposed(state, monkeypatch):
    async def unavailable(*arguments, **options):
        raise RuntimeError("synthetic-private-database-url")

    monkeypatch.setattr(db, "ensure_group_setting", unavailable)
    with pytest.raises(ActionError) as error:
        await invoke(surface(state), "groups.settings.update", group_settings_values())
    assert error.value.to_dict() == {
        "code": "action_failed",
        "message": "动作执行失败",
        "fields": [],
    }
    async with state.database.session() as session:
        assert await db.get_group_setting(session, 20001) is None
