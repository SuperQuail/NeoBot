"""B站 /直播互动列表：HTML 卡片路径与纯文本降级（不真的启动 Chromium）。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from neobot_app.bilibili.runtime import BilibiliRuntime
from neobot_app.commands import card as card_module
from neobot_app.commands.registry import CommandRegistry
from neobot_app.config.schemas.bot import BotConfig

_ROOM = {
    "room_id": 5440,
    "real_room_id": 21452505,
    "name": "测试主播",
    "auto_reply": True,
    "asr": False,
}
_ROOM_UNNAMED = {
    "room_id": 777,
    "real_room_id": 888,
    "name": "",
    "auto_reply": False,
    "asr": True,
}
_PNG = b"\x89PNG\r\n\x1a\n" + b"fake-live-rooms"
_HINT = "还没有启用的直播间交互；用 /直播互动 <房间号> 开 启用。"


class _FakeCommandService:
    def __init__(self) -> None:
        self.registry = CommandRegistry()
        self.replies: list[str] = []
        self.images: list[dict[str, Any]] = []
        self.screenshots: Any = object()

    async def reply_to(self, kind, conv_id, text, *, at_user_id=None) -> None:
        self.replies.append(text)

    async def send_image_bytes(
        self, kind, conv_id, data, *, at_user_id=None, filename=None
    ) -> bool:
        self.images.append(
            {"kind": kind, "conv_id": conv_id, "data": data, "filename": filename}
        )
        return True


def _build() -> tuple[BilibiliRuntime, _FakeCommandService]:
    cfg = BotConfig()
    command_service = _FakeCommandService()
    runtime = BilibiliRuntime(
        config=cfg,
        provider=None,
        archive_service=None,
        uow_factory=None,
        command_service=command_service,
        bot_name=cfg.bot.nick_name,
        bot_data=cfg.bot.bot_data,
    )
    runtime.register_commands(command_service)
    return runtime, command_service


def _ctx(service: _FakeCommandService) -> SimpleNamespace:
    async def _reply(text: str) -> None:
        service.replies.append(text)

    return SimpleNamespace(
        kind="group",
        conv_id="100",
        user_id=1,
        args=[],
        reply=_reply,
        service=service,
    )


def _list_handler(runtime: BilibiliRuntime, command_service: _FakeCommandService):
    command = command_service.registry.get("直播互动列表")
    assert command is not None
    return command.handler


def _rooms(
    monkeypatch: pytest.MonkeyPatch, rooms: list[dict[str, Any]]
) -> tuple[BilibiliRuntime, _FakeCommandService]:
    runtime_rooms = [dict(room) for room in rooms]
    runtime, command_service = _build()
    monkeypatch.setattr(runtime.live_interactor, "list_rooms", lambda: runtime_rooms)
    return runtime, command_service


async def test_list_renders_card_and_sends_png(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, command_service = _rooms(monkeypatch, [_ROOM, _ROOM_UNNAMED])
    rendered: list[str] = []

    async def _fake_render(html: str, **_kwargs: Any) -> bytes:
        rendered.append(html)
        return _PNG

    monkeypatch.setattr(card_module, "render_card_image", _fake_render)

    result = await _list_handler(runtime, command_service)(_ctx(command_service))

    assert result is None, "出图成功时 handler 不应再返回补发文本"
    assert len(rendered) == 1
    html = rendered[0]
    for text in (
        "直播互动列表",
        "共 2 个",
        "主播",
        "房间号",
        "真实房间号",
        "自动回复",
        "ASR",
        "测试主播",
        "5440",
        "21452505",
        "777",
        "888",
        "(未命名)",
        "启用或停用",
    ):
        assert text in html, text
    assert command_service.images == [
        {
            "kind": "group",
            "conv_id": "100",
            "data": _PNG,
            "filename": "bilibili-live-rooms.png",
        }
    ]
    assert command_service.replies == []


@pytest.mark.parametrize("mode", ["none", "raises"])
async def test_list_falls_back_to_original_text(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    runtime, command_service = _rooms(monkeypatch, [_ROOM, _ROOM_UNNAMED])

    async def _fake_render(html: str, **_kwargs: Any):
        if mode == "raises":
            raise RuntimeError("截图端口不可用")
        return None

    monkeypatch.setattr(card_module, "render_card_image", _fake_render)

    result = await _list_handler(runtime, command_service)(_ctx(command_service))

    assert result == (
        "已启用的直播间交互：\n"
        "- 测试主播（5440，真实房间 21452505，自动回复开，ASR关）\n"
        "- (未命名)（777，真实房间 888，自动回复关，ASR开）"
    )
    assert command_service.images == []
    assert command_service.replies == []


async def test_list_without_rooms_keeps_plain_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime, command_service = _rooms(monkeypatch, [])
    rendered: list[str] = []

    async def _fake_render(html: str, **_kwargs: Any) -> bytes:
        rendered.append(html)
        return _PNG

    monkeypatch.setattr(card_module, "render_card_image", _fake_render)

    result = await _list_handler(runtime, command_service)(_ctx(command_service))

    assert result == _HINT
    assert rendered == [], "没有房间时不出空卡片"
    assert command_service.images == []
