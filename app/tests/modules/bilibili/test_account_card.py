"""spec(28)：/B站账号 卡片命令。

所有外部数据（service / 名片接口 / 头像下载）都用 fake 注入；ctx.service 为空，
send_card 走纯文本降级——测试不截图、不发消息。
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from typing import Any

import pytest

from neobot_app.bilibili import account_card as module
from neobot_app.bilibili.account_card import (
    LOGIN_HINT,
    STATS_UNAVAILABLE_NOTE,
    account_card_blocks,
    account_card_text,
    build_account_snapshot,
    register_account_command,
    send_account_card,
)
from neobot_app.commands.card import AVATAR_MARKER
from neobot_app.commands.model import PERM_EVERYONE
from neobot_app.commands.registry import CommandRegistry

_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-avatar"
_LOGIN_AT = "2026-10-24T12:00:00+08:00"
_STATUS_FACE = "http://i2.hdslb.com/bfs/face/status.jpg"
_DETAIL = {
    "ok": True,
    "uid": 12345,
    "name": "测试UP",
    "sign": "签名",
    "level": 6,
    "fans": 12345,
    "following": 42,
    "videos": 7,
    "articles": 2,
    "likes": 999,
    "face": "http://i2.hdslb.com/bfs/face/detail.jpg",
    "url": "https://space.bilibili.com/12345",
}
_SENSITIVE = ("sessdata", "bili_jct", "refresh_token", "cookie")


class _FakeService:
    def __init__(
        self,
        *,
        available: bool = True,
        valid: bool = True,
        uid: int = 12345,
        uname: str = "测试UP",
        face: str = _STATUS_FACE,
        client: Any = None,
    ) -> None:
        self._available = available
        self._status = {
            "valid": valid,
            "uid": uid,
            "uname": uname,
            "face": face,
            "login_at": _LOGIN_AT,
            "error": "",
        }
        self.client = client

    @property
    def available(self) -> bool:
        return self._available

    def status(self) -> dict[str, Any]:
        return dict(self._status)


class _FakeReadApi:
    def __init__(self, detail: dict[str, Any] | None = None, *, error: Exception | None = None) -> None:
        self.detail = detail or {}
        self.error = error
        self.calls: list[int] = []

    def user_card_detail(self, mid: int) -> dict[str, Any]:
        self.calls.append(mid)
        if self.error is not None:
            raise self.error
        return dict(self.detail)


class _FakeClient:
    def __init__(self, data: bytes | None = _PNG, *, error: Exception | None = None) -> None:
        self.data = data
        self.error = error
        self.calls: list[str] = []

    def fetch_bytes(self, url: str) -> bytes | None:
        self.calls.append(url)
        if self.error is not None:
            raise self.error
        return self.data


class _FakeCtx:
    """ctx.service 为空 → send_card 直接返回 fallback_text（不截图、不发消息）。"""

    kind = "private"
    conv_id = "1"
    user_id = 1

    def __init__(self, service: Any = None) -> None:
        self.service = service


async def test_register_account_command_exposes_everyone_command() -> None:
    registry = CommandRegistry()
    register_account_command(registry, SimpleNamespace(service=_FakeService()))

    command = registry.get("B站账号")
    assert command is not None
    assert command.permission == PERM_EVERYONE
    assert command.aliases == ("biliaccount", "bili_account")
    assert registry.get("biliaccount") is command
    assert registry.get("bili_account") is command
    assert command.description


async def test_registered_handler_sends_card_text_fallback() -> None:
    registry = CommandRegistry()
    register_account_command(registry, SimpleNamespace(service=_FakeService(client=_FakeClient())))
    command = registry.get("B站账号")
    assert command is not None

    text = await command.handler(_FakeCtx())

    assert text is not None
    assert "@测试UP" in text
    assert "UID: 12345" in text


async def test_snapshot_logged_in_collects_fields_and_avatar_data_uri() -> None:
    client = _FakeClient()
    api = _FakeReadApi(_DETAIL)
    snapshot = await build_account_snapshot(_FakeService(client=client), read_api=api)

    assert snapshot["available"] is True
    assert snapshot["uid"] == 12345
    assert snapshot["uname"] == "测试UP"
    assert snapshot["login_at"] == _LOGIN_AT
    assert snapshot["valid"] is True
    assert snapshot["detail"] == _DETAIL
    assert snapshot["stats_ok"] is True
    # 名片接口里的 face 优先，且 http 一律换 https（卡片不自包含外链）
    assert snapshot["face_url"] == "https://i2.hdslb.com/bfs/face/detail.jpg"
    assert api.calls == [12345]
    assert client.calls == ["https://i2.hdslb.com/bfs/face/detail.jpg"]
    uri = snapshot["avatar_data_uri"]
    assert uri.startswith("data:image/png;base64,")
    assert base64.b64decode(uri.split(",", 1)[1]) == _PNG


async def test_snapshot_face_falls_back_to_status_face() -> None:
    detail = {key: value for key, value in _DETAIL.items() if key != "face"}
    snapshot = await build_account_snapshot(
        _FakeService(client=_FakeClient()), read_api=_FakeReadApi(detail)
    )
    assert snapshot["face_url"] == "https://i2.hdslb.com/bfs/face/status.jpg"


async def test_snapshot_unavailable_skips_stats_and_avatar() -> None:
    client = _FakeClient()
    api = _FakeReadApi(_DETAIL)
    snapshot = await build_account_snapshot(
        _FakeService(available=False, uid=0, uname="", client=client), read_api=api
    )

    assert snapshot["available"] is False
    assert snapshot["detail"] == {}
    assert snapshot["stats_ok"] is False
    assert snapshot["avatar_data_uri"] is None
    assert api.calls == []
    assert client.calls == []


@pytest.mark.parametrize("mode", ["denied", "raises"])
async def test_stats_failure_degrades_to_dash_and_note(mode: str) -> None:
    api = (
        _FakeReadApi({"ok": False, "error": "风控校验失败"})
        if mode == "denied"
        else _FakeReadApi(error=RuntimeError("接口炸了"))
    )
    snapshot = await build_account_snapshot(_FakeService(client=_FakeClient()), read_api=api)

    assert snapshot["available"] is True
    assert snapshot["stats_ok"] is False
    assert snapshot["detail"] == {}

    blocks = account_card_blocks(snapshot)
    stats = next(block for block in blocks if block["kind"] == "stats")
    assert [value for _, value in stats["items"]] == ["—", "—", "—"]
    kv = next(block for block in blocks if block["kind"] == "kv")
    assert ("投稿", "—") in kv["items"]
    assert any(block.get("text") == STATS_UNAVAILABLE_NOTE for block in blocks)

    text = account_card_text(snapshot)
    assert STATS_UNAVAILABLE_NOTE in text
    assert "粉丝: —" in text


async def test_avatar_download_failure_renders_initial_block(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_send_card(ctx: Any, **kwargs: Any) -> str:
        captured.update(kwargs)
        return str(kwargs["fallback_text"])

    monkeypatch.setattr(module, "send_card", fake_send_card)
    service = _FakeService(client=_FakeClient(None))
    result = await send_account_card(_FakeCtx(), service)

    assert captured["title"] == "B站账号"
    assert captured["subtitle"] == "@测试UP"
    assert captured["filename"] == "bilibili-account.png"
    assert captured["fallback_text"] == result
    avatars = captured["avatars"]
    assert "cmd-avatar cmd-avatar-fallback" in avatars
    assert ">测<" in avatars
    assert "data:image" not in avatars


async def test_avatar_unknown_magic_bytes_and_errors_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_send_card(ctx: Any, **kwargs: Any) -> str:
        captured.update(kwargs)
        return str(kwargs["fallback_text"])

    monkeypatch.setattr(module, "send_card", fake_send_card)

    for client in (_FakeClient(b"not-an-image"), _FakeClient(error=RuntimeError("连接中断"))):
        snapshot = await build_account_snapshot(_FakeService(client=client), read_api=_FakeReadApi(_DETAIL))
        assert snapshot["avatar_data_uri"] is None
        await send_account_card(_FakeCtx(), _FakeService(client=client))
        assert "cmd-avatar-fallback" in captured["avatars"]


async def test_avatar_fragment_escapes_initial(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_send_card(ctx: Any, **kwargs: Any) -> str:
        captured.update(kwargs)
        return str(kwargs["fallback_text"])

    monkeypatch.setattr(module, "send_card", fake_send_card)
    service = _FakeService(uname='<b>坏"&', client=_FakeClient(None))
    await send_account_card(_FakeCtx(), service)

    assert "&lt;" in captured["avatars"]
    assert "<b>" not in captured["avatars"]


async def test_card_blocks_hold_avatar_marker_stats_and_labels() -> None:
    snapshot = await build_account_snapshot(
        _FakeService(client=_FakeClient()), read_api=_FakeReadApi(_DETAIL)
    )
    blocks = account_card_blocks(snapshot)

    assert blocks[0] == {"kind": "note", "text": AVATAR_MARKER}
    stats = next(block for block in blocks if block["kind"] == "stats")
    assert stats["cols"] == 3
    assert stats["items"] == [("粉丝", "12345"), ("关注", "42"), ("获赞", "999")]
    kv = next(block for block in blocks if block["kind"] == "kv")
    labels = [label for label, _ in kv["items"]]
    assert labels == ["UID", "登录状态", "登录时间", "投稿"]
    assert ("登录状态", "有效") in kv["items"]
    assert ("登录时间", _LOGIN_AT) in kv["items"]
    assert any("https://space.bilibili.com/12345" in (block.get("text") or "") for block in blocks)


async def test_text_and_blocks_never_contain_credentials() -> None:
    snapshot = await build_account_snapshot(
        _FakeService(client=_FakeClient()), read_api=_FakeReadApi(_DETAIL)
    )
    text = account_card_text(snapshot).lower()
    blocks = str(account_card_blocks(snapshot)).lower()

    for word in _SENSITIVE:
        assert word not in text
        assert word not in blocks


async def test_send_account_card_degrades_to_text_without_render(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _FakeReadApi(_DETAIL)
    monkeypatch.setattr(module, "BilibiliReadApi", lambda client: api)
    client = _FakeClient()
    result = await send_account_card(_FakeCtx(), _FakeService(client=client))

    assert result is not None
    assert "B站账号 @测试UP" in result
    assert "UID: 12345" in result
    assert "粉丝: 12345" in result
    assert len(client.calls) == 1


async def test_send_account_card_unlogged_returns_hint_without_network() -> None:
    client = _FakeClient()
    service = _FakeService(available=False, uid=0, uname="", client=client)

    assert await send_account_card(_FakeCtx(), service) == LOGIN_HINT
    assert account_card_text(await build_account_snapshot(service)) == LOGIN_HINT
    assert client.calls == []
