"""插件消息对象必须在公开发送边界变成可编码的 OneBot 消息。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from neobot_contracts.models import ConversationRef
from neobot_modloader.bot import Bot
from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.message import Message, MessageChain, MessageSegment, image


_RAW_SEGMENTS = [
    {"type": "text", "data": {"text": "说明"}},
    {"type": "vendor.card", "data": {"nested": {"items": [1, None, False]}}},
]


class JsonAdapter:
    """用 JSON 编码模拟真实传输边界，避免宽松 mock 吞掉消息对象。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, Any]] = []
        self.result = object()
        self.error: Exception | None = None

    def _send(self, action: str, target: Any, message: Any) -> Any:
        json.dumps({"message": message}, ensure_ascii=False)
        self.calls.append((action, target, message))
        if self.error is not None:
            raise self.error
        return self.result

    async def send(self, conversation: ConversationRef, message: Any) -> Any:
        return self._send("send", conversation, message)

    async def send_private_msg(self, user_id: int, message: Any) -> Any:
        return self._send("send_private_msg", user_id, message)

    async def send_group_msg(self, group_id: int, message: Any) -> Any:
        return self._send("send_group_msg", group_id, message)


def make_sender(surface: str, adapter: JsonAdapter, tmp_path: Path) -> Any:
    if surface == "bot":
        return Bot(adapter)
    return RuntimePluginContext(
        plugin_name="payload_boundary",
        plugin_dir=tmp_path,
        data_dir=tmp_path / "data",
        config={},
        logger=None,
        adapter=adapter,
    )


@pytest.mark.parametrize("surface", ["bot", "context"])
@pytest.mark.parametrize("method", ["send", "send_private", "send_group"])
@pytest.mark.parametrize(
    ("make_payload", "expected"),
    [
        pytest.param(lambda: "原样文本", "原样文本", id="text"),
        pytest.param(lambda: MessageChain(_RAW_SEGMENTS), _RAW_SEGMENTS, id="chain"),
        pytest.param(lambda: Message({"message": _RAW_SEGMENTS}), _RAW_SEGMENTS, id="message"),
        pytest.param(
            lambda: image(file="image.file"),
            [{"type": "image", "data": {"file": "image.file"}}],
            id="typed-segment",
        ),
        pytest.param(
            lambda: MessageSegment.from_raw(_RAW_SEGMENTS[1]),
            [_RAW_SEGMENTS[1]],
            id="unknown-segment",
        ),
        pytest.param(lambda: _RAW_SEGMENTS[1], [_RAW_SEGMENTS[1]], id="raw-segment"),
        pytest.param(lambda: list(_RAW_SEGMENTS), _RAW_SEGMENTS, id="raw-list"),
        pytest.param(lambda: tuple(_RAW_SEGMENTS), _RAW_SEGMENTS, id="raw-tuple"),
    ],
)
async def test_send_payloads_reach_json_adapter(
    surface: str, method: str, make_payload: Any, expected: Any, tmp_path: Path
) -> None:
    adapter = JsonAdapter()
    sender = make_sender(surface, adapter, tmp_path)
    target = ConversationRef(kind="group", id="42") if method == "send" else 42

    result = await getattr(sender, method)(target, make_payload())

    action = "send" if method == "send" else f"{method}_msg"
    assert adapter.calls == [(action, target, expected)]
    assert result is adapter.result


@pytest.mark.parametrize("surface", ["bot", "context"])
@pytest.mark.parametrize("method", ["send", "send_private", "send_group"])
async def test_send_keeps_adapter_exception(surface: str, method: str, tmp_path: Path) -> None:
    adapter = JsonAdapter()
    adapter.error = RuntimeError("offline")
    sender = make_sender(surface, adapter, tmp_path)
    target = ConversationRef(kind="private", id="42") if method == "send" else 42

    with pytest.raises(RuntimeError) as raised:
        await getattr(sender, method)(target, MessageChain().text("hello"))

    assert raised.value is adapter.error
    assert adapter.calls[0][2] == [{"type": "text", "data": {"text": "hello"}}]
