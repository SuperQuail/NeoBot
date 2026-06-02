from __future__ import annotations

import unittest
from typing import Any

from neobot_contracts.models import ConversationRef
from neobot_modloader.message import Message, image
from neobot_modloader.reply import Reply


class FakeContext:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, Any]] = []

    async def reply(self, event: dict[str, Any], message: Any) -> str:
        self.calls.append(("reply", event, message))
        return "ok"

    async def send_private(self, user_id: int, message: Any) -> str:
        self.calls.append(("private", user_id, message))
        return "ok"

    async def send_group(self, group_id: int, message: Any) -> str:
        self.calls.append(("group", group_id, message))
        return "ok"

    def conversation_from_event(self, event: dict[str, Any]) -> ConversationRef:
        return ConversationRef(kind="private", id=str(event["user_id"]))


class ReplyTest(unittest.IsolatedAsyncioTestCase):
    async def test_send_text(self) -> None:
        ctx = FakeContext()
        reply = Reply(ctx, {"user_id": 1})

        await reply.send("hello")

        self.assertEqual(ctx.calls[0], ("reply", {"user_id": 1}, "hello"))

    async def test_send_message_chain_object(self) -> None:
        ctx = FakeContext()
        reply = Reply(ctx, {"user_id": 1})
        message = Message({"message": [{"type": "text", "data": {"text": "hello"}}, {"type": "image", "data": {"file": "a.image"}}]})

        await reply.send(message)

        self.assertEqual(
            ctx.calls[0][2],
            [{"type": "text", "data": {"text": "hello"}}, {"type": "image", "data": {"file": "a.image"}}],
        )

    async def test_send_single_segment(self) -> None:
        ctx = FakeContext()
        reply = Reply(ctx, {"user_id": 1})

        await reply.send(image(url="https://example/image.png"))

        self.assertEqual(ctx.calls[0][2], [{"type": "image", "data": {"url": "https://example/image.png"}}])


if __name__ == "__main__":
    unittest.main()
