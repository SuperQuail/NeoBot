"""官方群全量消息没有 @ 时不能触发命令。"""

from __future__ import annotations

from types import SimpleNamespace

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


def _message(text: str, *, at_qq: int | None = None):
    segments = [{"type": "text", "data": {"text": text}}]
    if at_qq is not None:
        segments.append({"type": "at", "data": {"qq": str(at_qq)}})
    return SimpleNamespace(
        user_id=1,
        message=segments,
        neobot_channel="official",
        self_id=BOT,
        raw_message=text,
    )


async def test_official_full_group_message_without_at_does_not_trigger_command() -> None:
    result = await _service().handle_message(_message("/reboot"), kind="group", queue_key="g1")
    assert result.consumed is False


async def test_official_group_command_with_at_still_triggers() -> None:
    result = await _service().handle_message(
        _message("/reboot", at_qq=BOT), kind="group", queue_key="g1"
    )
    assert result.consumed is True
