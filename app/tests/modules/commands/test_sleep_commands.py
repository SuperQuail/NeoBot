"""睡眠命令测试:/sleep /awake 的权限、参数解析与行为。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.commands.service import CommandService
from neobot_app.runtime.sleep_service import SleepService

BOT = 88888
SUPER = 10000
SUB = 30000


def _config(*, admin_accounts: list[int] | None = None, sub_admin_accounts: list[int] | None = None):
    chat = SimpleNamespace(
        admin_accounts=list(admin_accounts if admin_accounts is not None else [SUPER]),
        sub_admin_accounts=list(sub_admin_accounts or []),
    )
    bot = SimpleNamespace(account=BOT)
    return SimpleNamespace(chat=chat, bot=bot)


def _text_message(text: str, *, user_id: int = 1, at_qqs: list[int] | None = None):
    segments = [{"type": "text", "data": {"text": text}}]
    for qq in at_qqs or []:
        segments.append({"type": "at", "data": {"qq": str(qq)}})
    return SimpleNamespace(user_id=user_id, message=segments)


def _service(config=None, sleep_service: SleepService | None = None, **kwargs) -> CommandService:
    return CommandService(
        config=config if config is not None else _config(sub_admin_accounts=[SUB]),
        adapter=SimpleNamespace(send=lambda conv, segments: None),
        register_builtins=kwargs.get("register_builtins", True),
        sleep_service=sleep_service,
    )


# ── /sleep ──


async def test_sleep_command_requires_sub_admin() -> None:
    sent: list[tuple] = []

    async def send(kind, conv, text, at_user_id):
        sent.append((kind, conv, text, at_user_id))

    service = CommandService(
        config=_config(),
        adapter=SimpleNamespace(send=lambda c, s: None),
        send_callback=send,
        register_builtins=True,
    )
    result = await service.handle_message(
        _text_message("/sleep 2h", user_id=99999, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert result.consumed is True
    assert sent and "没有权限" in sent[0][2]


async def test_sleep_command_starts_sleep() -> None:
    sleep_service = SleepService()
    service = _service(sleep_service=sleep_service)
    result = await service.handle_message(
        _text_message("/sleep 2h", user_id=SUB, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert result.consumed is True
    assert result.background is None
    assert sleep_service.is_sleeping()
    assert 7150 <= sleep_service.remaining_seconds() <= 7200


async def test_sleep_command_bare_number_is_minutes() -> None:
    sleep_service = SleepService()
    service = _service(sleep_service=sleep_service)
    await service.handle_message(
        _text_message("/sleep 30", user_id=SUB, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert sleep_service.remaining_seconds() <= 1800


async def test_sleep_command_missing_argument() -> None:
    sleep_service = SleepService()
    service = _service(sleep_service=sleep_service)
    sent: list[str] = []

    async def send(kind, conv, text, at_user_id):
        sent.append(text)

    service._send_callback = send
    await service.handle_message(
        _text_message("/sleep", user_id=SUB, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert sent and "请提供睡眠时长" in sent[0]
    assert not sleep_service.is_sleeping()


async def test_sleep_command_invalid_duration() -> None:
    sleep_service = SleepService()
    service = _service(sleep_service=sleep_service)
    sent: list[str] = []

    async def send(kind, conv, text, at_user_id):
        sent.append(text)

    service._send_callback = send
    await service.handle_message(
        _text_message("/sleep abc", user_id=SUB, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert sent and "无法解析时长" in sent[0]
    assert not sleep_service.is_sleeping()


async def test_sleep_command_over_cap_rejected() -> None:
    sleep_service = SleepService()
    service = _service(sleep_service=sleep_service)
    sent: list[str] = []

    async def send(kind, conv, text, at_user_id):
        sent.append(text)

    service._send_callback = send
    await service.handle_message(
        _text_message("/sleep 13h", user_id=SUB, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert sent and "最多 12 小时" in sent[0]
    assert not sleep_service.is_sleeping()


async def test_sleep_command_allowed_in_private() -> None:
    sleep_service = SleepService()
    service = _service(sleep_service=sleep_service)
    result = await service.handle_message(
        _text_message("/sleep 1h", user_id=SUB),
        kind="private",
        queue_key=str(SUB),
    )
    assert result.consumed is True
    assert sleep_service.is_sleeping()


async def test_sleep_command_without_service() -> None:
    service = _service(sleep_service=None)
    sent: list[str] = []

    async def send(kind, conv, text, at_user_id):
        sent.append(text)

    service._send_callback = send
    await service.handle_message(
        _text_message("/sleep 1h", user_id=SUB, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert sent and "睡眠功能不可用" in sent[0]


# ── /awake ──


async def test_awake_command_wakes_sleeping_bot() -> None:
    sleep_service = SleepService()
    sleep_service.sleep(3600)
    service = _service(sleep_service=sleep_service)
    sent: list[str] = []

    async def send(kind, conv, text, at_user_id):
        sent.append(text)

    service._send_callback = send
    result = await service.handle_message(
        _text_message("/awake", user_id=SUB, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert result.consumed is True
    assert not sleep_service.is_sleeping()
    assert sent and "被叫醒" in sent[0]


async def test_awake_command_when_not_sleeping() -> None:
    sleep_service = SleepService()
    service = _service(sleep_service=sleep_service)
    sent: list[str] = []

    async def send(kind, conv, text, at_user_id):
        sent.append(text)

    service._send_callback = send
    await service.handle_message(
        _text_message("/awake", user_id=SUB, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )
    assert sent and "没有在睡觉" in sent[0]
