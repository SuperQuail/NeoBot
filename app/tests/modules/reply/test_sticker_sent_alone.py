"""表情包单独发送：输出层必须产生独立的图片消息与文字消息，绝不合并。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from neobot_app.reply.debug import DebugHelper
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.sender import ReplySender
from neobot_app.reply.tools import ReplyToolExecutor
from neobot_contracts.models import ConversationRef


class _Adapter:
    def __init__(self) -> None:
        self.sent: list[list[dict]] = []

    async def send(self, conversation_ref, payload, **kwargs):
        self.sent.append(payload)
        return {"message_id": len(self.sent)}


def _make_sender(image_path):
    adapter = _Adapter()
    emoji = SimpleNamespace(
        get_entry=lambda number: SimpleNamespace(file_path=image_path),
        record_usage=AsyncMock(),
    )
    sender = ReplySender(
        adapter=adapter,
        file_server=SimpleNamespace(_enabled=False),
        bot_name="Bot",
        emoji_service=emoji,
        debug_helper=DebugHelper(),
        sentence_cooldown_seconds=0,
        private_chat_sentence_cooldown_seconds=0,
    )
    event = ReplyEvent(conversation_ref=ConversationRef(kind="group", id="123"))
    event.transition(ReplyState.BUILDING_PROMPT)
    event.transition(ReplyState.GENERATING)
    return sender, event, adapter, emoji


async def test_send_reply_with_images_and_text_sends_separate_messages(tmp_path):
    """images+text 一次调用时，必须「图片一条 + 文字一条」，不得走合并发送。"""
    image = tmp_path / "sticker.png"
    image.write_bytes(b"fake image")
    sender, event, adapter, emoji = _make_sender(image)

    async def handler(**args):
        return await sender.send_reply(
            event,
            args["text"],
            segments=args["segments"],
            send_original=args["send_original"],
            images=args["images"],
        )

    executor = ReplyToolExecutor(send_reply_handler=handler)
    result = await executor.execute("send_reply", {"text": "哈哈", "images": [1]})

    assert "已发送" in result
    assert len(adapter.sent) == 2
    assert [part["type"] for part in adapter.sent[0]] == ["image"]
    assert [part["type"] for part in adapter.sent[1]] == ["text"]
    assert adapter.sent[1][0]["data"]["text"] == "哈哈"
    for payload in adapter.sent:
        payload_types = {part["type"] for part in payload}
        assert not {"text", "image"} <= payload_types
    emoji.record_usage.assert_awaited_once_with(1)
