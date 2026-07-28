from __future__ import annotations

from typing import get_type_hints

from neobot_app.emoji.service import EmojiEntry, EmojiService
from neobot_chat.runtime.agent import Agent
from neobot_contracts.models.memory import EmojiRecord


def test_runtime_type_hints_resolve_for_emoji_service():
    entry_hints = get_type_hints(EmojiEntry)
    method_hints = get_type_hints(EmojiService.update_emoji_source)

    assert entry_hints["created_at"] is not None
    assert method_hints["return"] == EmojiRecord | None


def test_runtime_type_hints_resolve_for_agent_constructor():
    hints = get_type_hints(Agent.__init__)

    assert "on_model_usage" in hints
    assert "output" in hints
