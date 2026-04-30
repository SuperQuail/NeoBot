from __future__ import annotations

import unittest
from dataclasses import dataclass

from pydantic import BaseModel

from neobot_app.runtime.reply_block import ReplyBlockRegistry


class MessageModel(BaseModel):
    message_type: str = "group"
    group_id: int | None = None
    user_id: int | None = None
    message_id: int


@dataclass
class MessageObject:
    message_type: str
    group_id: int | None
    user_id: int | None
    message_id: int


class ReplyBlockRegistryTest(unittest.TestCase):
    def test_consumes_dict_event_once(self) -> None:
        registry = ReplyBlockRegistry()
        event = {"message_type": "group", "group_id": 100, "message_id": 1}

        registry.block_event(event)

        self.assertTrue(registry.consume_message(event))
        self.assertFalse(registry.consume_message(event))

    def test_matches_model_and_object_with_same_key(self) -> None:
        registry = ReplyBlockRegistry()
        registry.block_event(MessageModel(group_id=100, message_id=1))

        self.assertTrue(
            registry.consume_message(
                MessageObject(message_type="group", group_id=100, user_id=None, message_id=1)
            )
        )

    def test_message_id_fallback_handles_model_shape_mismatch(self) -> None:
        registry = ReplyBlockRegistry()
        registry.block_event({"message_type": "private", "user_id": 42, "message_id": 7})

        self.assertTrue(
            registry.consume_message({"message_type": "private", "user_id": 43, "message_id": 7})
        )
        self.assertFalse(
            registry.consume_message({"message_type": "private", "user_id": 42, "message_id": 7})
        )

    def test_capacity_evicts_oldest_key(self) -> None:
        registry = ReplyBlockRegistry(max_size=1)
        first = {"message_type": "group", "group_id": 1, "message_id": 1}
        second = {"message_type": "group", "group_id": 1, "message_id": 2}

        registry.block_event(first)
        registry.block_event(second)

        self.assertFalse(registry.consume_message(first))
        self.assertTrue(registry.consume_message(second))


if __name__ == "__main__":
    unittest.main()
