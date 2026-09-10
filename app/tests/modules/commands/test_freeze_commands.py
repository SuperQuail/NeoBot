"""冻结命令测试:/freeze /unfreeze /freeze_status 的权限、参数解析与行为。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.commands.service import CommandService
from neobot_app.runtime.freeze_service import FreezeService

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


def _service(freeze_service: FreezeService | None = None) -> CommandService:
    return CommandService(
        config=_config(sub_admin_accounts=[SUB]),
        adapter=SimpleNamespace(send=lambda conv, segments: None),
        register_builtins=True,
        freeze_service=freeze_service,
    )


def _capture(service: CommandService) -> list[str]:
    sent: list[str] = []

    async def send(kind, conv, text, at_user_id):
        sent.append(text)

    service._send_callback = send
    return sent


async def test_freeze_requires_super_admin() -> None:
    """/freeze 是熔断操作，次级管理员不能触发。"""
    freeze_service = FreezeService()
    service = _service(freeze_service)
    sent = _capture(service)

    result = await service.handle_message(
        _text_message("/freeze", user_id=SUB, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )

    assert result.consumed is True
    assert sent and "没有权限" in sent[0]
    assert not freeze_service.is_frozen()


async def test_freeze_stops_bot_indefinitely_by_default() -> None:
    freeze_service = FreezeService()
    service = _service(freeze_service)
    sent = _capture(service)

    await service.handle_message(
        _text_message("/freeze token 风暴", user_id=SUPER, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )

    assert freeze_service.is_frozen()
    status = freeze_service.status()
    assert status["remaining_seconds"] is None
    assert "token 风暴" in status["reason"]
    assert sent and "已冻结" in sent[0]


async def test_freeze_with_duration_sets_deadline() -> None:
    freeze_service = FreezeService()
    service = _service(freeze_service)
    _capture(service)

    await service.handle_message(
        _text_message("/freeze 30m", user_id=SUPER, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )

    remaining = freeze_service.remaining_seconds()
    assert remaining is not None
    assert 1700 <= remaining <= 1800


async def test_freeze_rejects_bad_duration() -> None:
    freeze_service = FreezeService()
    service = _service(freeze_service)
    sent = _capture(service)

    await service.handle_message(
        _text_message("/freeze 2x", user_id=SUPER, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )

    assert not freeze_service.is_frozen()
    assert sent and "无法解析时长" in sent[0]


async def test_unfreeze_restores_bot() -> None:
    freeze_service = FreezeService()
    freeze_service.freeze(reason="manual")
    service = _service(freeze_service)
    sent = _capture(service)

    await service.handle_message(
        _text_message("/unfreeze", user_id=SUPER, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )

    assert not freeze_service.is_frozen()
    assert sent and "已解冻" in sent[0]


async def test_unfreeze_when_not_frozen_is_harmless() -> None:
    freeze_service = FreezeService()
    service = _service(freeze_service)
    sent = _capture(service)

    await service.handle_message(
        _text_message("/unfreeze", user_id=SUPER, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )

    assert sent and "没有处于冻结状态" in sent[0]


async def test_freeze_status_visible_to_sub_admin() -> None:
    freeze_service = FreezeService()
    freeze_service.freeze(reason="token 风暴", operator="panel")
    service = _service(freeze_service)
    sent = _capture(service)

    await service.handle_message(
        _text_message("/freeze_status", user_id=SUB, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )

    assert sent and "已冻结" in sent[0]
    assert "token 风暴" in sent[0]


async def test_freeze_commands_report_missing_service() -> None:
    service = _service(None)
    sent = _capture(service)

    await service.handle_message(
        _text_message("/freeze", user_id=SUPER, at_qqs=[BOT]),
        kind="group",
        queue_key="42",
    )

    assert sent and "未注入冻结服务" in sent[0]
