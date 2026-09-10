"""内置命令 /set_password：权限、私聊限制与密码写入。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_app.commands.model import PERM_SUPER_ADMIN
from neobot_app.commands.service import CommandService
from neobot_app.panel_auth import PanelPasswordStore

BOT = 88888
SUPER = 10000
OTHER = 20000


@pytest.fixture()
def store(tmp_path, monkeypatch):
    store = PanelPasswordStore(tmp_path / "auth.json")
    monkeypatch.setattr(
        "neobot_app.commands.builtin.get_panel_password_store", lambda: store
    )
    return store


def _config():
    chat = SimpleNamespace(admin_accounts=[SUPER], sub_admin_accounts=[])
    return SimpleNamespace(chat=chat, bot=SimpleNamespace(account=BOT))


def _message(text: str, user_id: int, *, at_qqs: list[int] | None = None):
    segments = [{"type": "text", "data": {"text": text}}]
    for qq in at_qqs or []:
        segments.append({"type": "at", "data": {"qq": str(qq)}})
    return SimpleNamespace(user_id=user_id, message=segments)


class _Adapter:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, conversation, segments):
        text = "".join(
            str((segment.get("data") or {}).get("text") or "")
            for segment in segments
            if isinstance(segment, dict) and segment.get("type") == "text"
        )
        self.sent.append((conversation.kind, text))
        return SimpleNamespace(status="ok")

    async def send_private_msg(self, user_id, message):
        return await self.send(SimpleNamespace(kind="private", id=str(user_id)), message)


async def _run(text: str, *, user_id: int, kind: str = "private") -> tuple[str, _Adapter]:
    adapter = _Adapter()
    service = CommandService(config=_config(), adapter=adapter)
    result = await service.handle_message(
        _message(text, user_id, at_qqs=[BOT] if kind == "group" else None),
        kind=kind,
        queue_key=str(user_id),
    )
    assert result.consumed is True
    return (adapter.sent[-1][1] if adapter.sent else ""), adapter


async def test_set_password_is_super_admin_only() -> None:
    text, adapter = await _run("/set_password NeoBot-2026", user_id=OTHER)

    assert "没有权限" in text
    assert adapter.sent


async def test_set_password_rejects_group_chat(store) -> None:
    text, _ = await _run("/set_password NeoBot-2026", user_id=SUPER, kind="group")

    assert "私聊" in text
    assert store.configured is False


async def test_set_password_sets_custom_password(store) -> None:
    text, _ = await _run("/set_password NeoBot-Panel-2026", user_id=SUPER)

    assert "已更新" in text
    assert store.verify("NeoBot-Panel-2026") is True


async def test_set_password_rejects_weak_password(store) -> None:
    text, _ = await _run("/set_password short", user_id=SUPER)

    assert "不符合要求" in text
    assert store.configured is False


async def test_set_password_generates_random_when_empty(store) -> None:
    text, _ = await _run("/set_password", user_id=SUPER)

    assert "自动生成的密码" in text
    generated = text.split("自动生成的密码:", 1)[1].split("\n", 1)[0].strip()
    assert store.verify(generated) is True


def test_command_declared_as_super_admin() -> None:
    from neobot_app.commands.builtin import build_builtin_commands

    service = CommandService(config=_config(), adapter=_Adapter())
    command = next(
        item for item in build_builtin_commands(service) if item.name == "set_password"
    )
    assert command.permission == PERM_SUPER_ADMIN
    assert command.usage == "[新密码]"
