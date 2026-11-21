"""官方群消息的 @ 判定：mentioned_self 权威，None 回退 OneBot at 段。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_app.commands.service import CommandService

BOT = 88888


def _config():
    chat = SimpleNamespace(admin_accounts=[], sub_admin_accounts=[])
    return SimpleNamespace(chat=chat, bot=SimpleNamespace(account=BOT))


async def _send(*args, **kwargs) -> None:
    return None


def _service() -> CommandService:
    return CommandService(
        config=_config(),
        adapter=SimpleNamespace(send=lambda c, s: None),
        send_callback=_send,
        register_builtins=True,
    )


def _message(
    text: str,
    *,
    at_qq: int | None = None,
    mentioned_self: bool | None = None,
    channel: str = "official",
) -> GroupMessage:
    segments = [MessageSegment(type="text", data={"text": text})]
    if at_qq is not None:
        segments.append(MessageSegment(type="at", data={"qq": str(at_qq)}))
    return GroupMessage(
        message_id=1,
        user_id=1,
        group_id=42,
        neobot_channel=channel,
        self_id=BOT,
        mentioned_self=mentioned_self,
        message=segments,
        raw_message=text,
    )


async def test_official_full_group_message_without_at_does_not_trigger_command() -> None:
    """GROUP_MESSAGE_CREATE 未 @ 机器人：mentioned_self=False，不触发命令。"""
    result = await _service().handle_message(_message("/reboot", mentioned_self=False), kind="group", queue_key="g1")
    assert result.consumed is False


async def test_official_at_event_triggers_command_without_at_segment() -> None:
    """GROUP_AT_MESSAGE_CREATE 的权威结论是 True：正文没有 at 段也触发命令。"""
    result = await _service().handle_message(_message("/reboot", mentioned_self=True), kind="group", queue_key="g1")
    assert result.consumed is True


async def test_official_mentioned_self_false_ignores_matching_at_segment() -> None:
    """官方权威结论 False 时不看 at 段，避免全量消息被旧补丁误判。"""
    result = await _service().handle_message(
        _message("/reboot", at_qq=BOT, mentioned_self=False), kind="group", queue_key="g1"
    )
    assert result.consumed is False


async def test_onebot_at_bot_still_triggers_command() -> None:
    """OneBot 路径行为不变：显式 at 机器人触发命令。"""
    result = await _service().handle_message(
        _message("/reboot", at_qq=BOT, channel="onebot"), kind="group", queue_key="g1"
    )
    assert result.consumed is True


async def test_onebot_without_at_does_not_trigger_command() -> None:
    result = await _service().handle_message(_message("/reboot", channel="onebot"), kind="group", queue_key="g1")
    assert result.consumed is False
