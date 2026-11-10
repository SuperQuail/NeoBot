"""/linkqq 管理员命令：@用户 + 真实 QQ 号。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_app.commands.service import CommandService
from neobot_app.user_identity import (
    bind_user_identity,
    group_number_for,
    qq_for_user,
    trusted_qq_for_user,
)

BOT = 88888
SUPER = 10000
SUB = 30000
SYNTHETIC = 9000000000001
REAL_QQ = 123456789


def _config():
    return SimpleNamespace(
        chat=SimpleNamespace(admin_accounts=[SUPER], sub_admin_accounts=[SUB]),
        bot=SimpleNamespace(account=BOT),
    )


def _message(text: str, *, user_id: int, at_qqs: list[int]):
    segments = [{"type": "text", "data": {"text": text}}]
    for qq in at_qqs:
        segments.append({"type": "at", "data": {"qq": str(qq)}})
    return SimpleNamespace(user_id=user_id, message=segments)


SYNTHETIC_ADMIN = 9000000000010


def _service(sent: list[tuple], config=None):
    async def send(kind, conv, text, at_user_id):
        sent.append((kind, conv, text, at_user_id))

    return CommandService(config=config or _config(), send_callback=send)


def _synthetic_admin_config():
    return SimpleNamespace(
        chat=SimpleNamespace(
            admin_accounts=[SUPER], sub_admin_accounts=[SYNTHETIC_ADMIN]
        ),
        bot=SimpleNamespace(account=BOT),
    )


@pytest.fixture(autouse=True)
def _bind(tmp_path):
    bind_user_identity(tmp_path)
    yield
    bind_user_identity(None)


@pytest.mark.asyncio
async def test_admin_links_at_target_to_qq():
    sent: list[tuple] = []
    service = _service(sent)

    result = await service.handle_message(
        _message("/linkqq 123456789", user_id=SUB, at_qqs=[BOT, SYNTHETIC]),
        kind="group",
        queue_key="100",
    )

    assert result.consumed is True
    assert qq_for_user(SYNTHETIC) == REAL_QQ
    # 管理员命令写入的映射是 trusted 的，权限判定可用
    assert trusted_qq_for_user(SYNTHETIC) == REAL_QQ
    assert "已映射" in sent[-1][2]


@pytest.mark.asyncio
async def test_admin_links_current_group_number():
    sent: list[tuple] = []
    service = _service(sent)

    result = await service.handle_message(
        _message("/linkgroup 987654321", user_id=SUB, at_qqs=[BOT]),
        kind="group",
        queue_key="8000000000002",
    )

    assert result.consumed is True
    assert group_number_for(8000000000002) == 987654321
    assert "已映射群" in sent[-1][2]


@pytest.mark.asyncio
async def test_non_admin_cannot_link_group():
    sent: list[tuple] = []
    service = _service(sent)

    await service.handle_message(
        _message("/linkgroup 987654321", user_id=999, at_qqs=[BOT]),
        kind="group",
        queue_key="8000000000002",
    )

    assert group_number_for(8000000000002) is None
    assert "没有权限" in sent[-1][2]


@pytest.mark.asyncio
async def test_non_admin_cannot_link():
    sent: list[tuple] = []
    service = _service(sent)

    await service.handle_message(
        _message("/linkqq 123456789", user_id=999, at_qqs=[BOT, SYNTHETIC]),
        kind="group",
        queue_key="100",
    )

    assert qq_for_user(SYNTHETIC) is None
    assert "没有权限" in sent[-1][2]


@pytest.mark.asyncio
async def test_one_arg_links_sender_self():
    """只有一个参数时映射发送者本人（官方通道主路径）。"""
    sent: list[tuple] = []
    service = _service(sent, config=_synthetic_admin_config())

    result = await service.handle_message(
        _message("/linkqq 123456789", user_id=SYNTHETIC_ADMIN, at_qqs=[BOT]),
        kind="group",
        queue_key="100",
    )

    assert result.consumed is True
    assert trusted_qq_for_user(SYNTHETIC_ADMIN) == REAL_QQ
    assert qq_for_user(SYNTHETIC_ADMIN) == REAL_QQ
    assert "已映射" in sent[-1][2]


async def test_sub_admin_cannot_map_to_super_admin_qq():
    """超管 QQ 的映射只允许超管操作，防止次级管理员自提权。"""
    sent: list[tuple] = []
    service = _service(sent)

    await service.handle_message(
        _message("/linkqq 10000", user_id=SUB, at_qqs=[BOT]),
        kind="group",
        queue_key="100",
    )

    assert trusted_qq_for_user(SUB) is None
    assert "只允许超级管理员" in sent[-1][2]


async def test_at_segment_separates_command_and_argument():
    """没有显式空格的「/linkqq@用户 123」也要能按 at 段分隔出命令参数。"""
    sent: list[tuple] = []
    service = _service(sent)
    message = SimpleNamespace(
        user_id=SUB,
        message=[
            {"type": "text", "data": {"text": "/linkqq"}},
            {"type": "at", "data": {"qq": str(BOT)}},
            {"type": "at", "data": {"qq": str(SYNTHETIC)}},
            {"type": "text", "data": {"text": "3514733681"}},
        ],
    )

    result = await service.handle_message(message, kind="group", queue_key="100")

    assert result.consumed is True
    assert qq_for_user(SYNTHETIC) == 3514733681


async def test_at_target_without_qq_shows_usage():
    sent: list[tuple] = []
    service = _service(sent)

    await service.handle_message(
        _message("/linkqq", user_id=SUB, at_qqs=[BOT, SYNTHETIC]),
        kind="group",
        queue_key="100",
    )

    assert qq_for_user(SYNTHETIC) is None
    assert "用法" in sent[-1][2]


@pytest.mark.asyncio
async def test_invalid_qq_rejected():
    sent: list[tuple] = []
    service = _service(sent)

    await service.handle_message(
        _message("/linkqq 12", user_id=SUB, at_qqs=[BOT, SYNTHETIC]),
        kind="group",
        queue_key="100",
    )

    assert qq_for_user(SYNTHETIC) is None
    assert "5~11" in sent[-1][2]
