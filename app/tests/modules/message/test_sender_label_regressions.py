"""Conversation-scoped labels must match the labels shown to the model."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage
from neobot_app.message.numbering import MessageNumbering
from neobot_app.message.queue import MessageQueue
from neobot_app.reply.event import ReplyEvent
from neobot_app.reply.orchestrator import ReplyOrchestrator
from neobot_app.reply.output_guard import clean_text
from neobot_contracts.models import ConversationRef


def _message(message_id, user_id, name, card=""):
    return GroupMessage(
        message_id=message_id, user_id=user_id, group_id=42,
        sender=PostMessageMessagesender(user_id=user_id, nickname=name, card=card),
        message=[], raw_message="hello",
    )


def test_labels_are_scoped_and_legacy_aggregate_remains_available():
    queue = MessageQueue()
    queue.push("42", _message(1, 7, "Alice", "A"))
    queue.push("99", _message(2, 8, "Elsewhere"))
    assert set(queue.sender_labels("42")) == {"Alice", "A"}
    assert "Elsewhere" in queue.sender_labels()
    assert queue.sender_labels("missing") == []
    numbering = MessageNumbering(queue=queue, queue_key="42")
    names = numbering.known_sender_names()
    assert clean_text("Elsewhere: keep this", known_sender_names=names) == "Elsewhere: keep this"
    assert clean_text("Alice: remove label", known_sender_names=names) == "remove label"
    assert "Elsewhere" in MessageNumbering(queue=queue).known_sender_names()


def test_rendered_duplicate_labels_and_replied_only_authors_are_collected():
    queue = MessageQueue(bot_account=99)
    queue.push("42", _message(1, 7, "Twin"))
    queue.push("42", _message(2, 8, "Twin"), replied_messages=[
        _message(3, 10, "ReplyOnly", "ReplyCard"),
        _message(4, 7, "OldTwin"),
        _message(5, 99, "Bot"),
    ])
    numbering = MessageNumbering(queue=queue, queue_key="42")
    rendered = numbering.apply(queue, "42")
    names = numbering.known_sender_names()
    for label in ("Twin(7)", "Twin(8)", "ReplyOnly"):
        assert label + ":" in rendered
        assert label in names
        assert clean_text(f"12: {label}: body", known_sender_names=names) == "body"
    assert "ReplyCard" in names
    assert "Bot" in names
    assert "Bot" not in queue.sender_labels("42", include_bot=False)
    assert names == queue.clone("42").sender_labels("42")


def test_duplicate_names_in_other_conversations_do_not_change_labels():
    queue = MessageQueue()
    queue.push("42", _message(1, 7, "Twin"))
    queue.push("99", _message(2, 8, "Twin"))
    assert queue.sender_labels("42") == ["Twin"]
    assert queue.sender_labels() == ["Twin"]


def test_unnamed_replied_author_uses_rendered_fallback_label():
    queue = MessageQueue()
    queue.push("42", _message(1, 7, "Alice"), replied_messages=[_message(2, 8, "")])
    numbering = MessageNumbering(queue=queue, queue_key="42")
    assert "QQ:8:" in numbering.apply(queue, "42")
    assert "QQ:8" in numbering.known_sender_names()


def test_numbering_apply_binds_key_for_legacy_construction():
    queue = MessageQueue()
    queue.push("42", _message(1, 7, "Alice"))
    queue.push("99", _message(2, 8, "Elsewhere"))
    numbering = MessageNumbering()
    numbering.apply(queue, "42")
    assert numbering.known_sender_names() == ["Alice"]


def test_no_argument_legacy_getters_and_unavailable_queues_are_supported():
    queue = SimpleNamespace(sender_labels=lambda: ["Legacy"])
    assert MessageNumbering(queue=queue).known_sender_names() == ["Legacy"]
    assert ReplyOrchestrator._known_sender_names(queue) == ["Legacy"]
    # A scoped lookup must not fall back to a potentially global legacy getter.
    assert MessageNumbering(queue=queue, queue_key="42").known_sender_names() == []
    assert ReplyOrchestrator._known_sender_names(queue, queue_key="42") == []
    assert MessageNumbering().known_sender_names() == []


def test_orchestrator_merges_live_and_snapshot_labels_only_for_current_key():
    queue = MessageQueue()
    queue.push("42", _message(1, 7, "Alice"))
    snapshot = queue.clone("42")
    queue.push("42", _message(2, 8, "New"))
    queue.push("99", _message(3, 9, "Elsewhere"))
    assert ReplyOrchestrator._known_sender_names(
        queue, snapshot, queue_key="42"
    ) == ["Alice", "New"]


@pytest.mark.parametrize("kind", ["group", "private", None])
async def test_send_fallback_uses_only_event_conversation(kind):
    group = MessageQueue()
    friend = MessageQueue()
    group.push("42", _message(1, 7, "GroupAuthor"))
    group.push("99", _message(2, 8, "OtherGroup"))
    friend.push("42", _message(3, 9, "PrivateAuthor"))
    orchestrator = object.__new__(ReplyOrchestrator)
    orchestrator._group_queue = group
    orchestrator._friend_queue = friend
    orchestrator._config = SimpleNamespace(bot=SimpleNamespace(nick_name="Bot"))
    orchestrator._apply_post_reply_hooks = AsyncMock(return_value="hello")
    orchestrator._sender = SimpleNamespace(send_reply=AsyncMock(return_value=True))
    event = ReplyEvent(conversation_ref=ConversationRef(kind=kind, id="42") if kind else None)
    assert await orchestrator._send_reply(event, "hello")
    names = orchestrator._sender.send_reply.call_args.kwargs["sender_names"]
    expected = {"Bot"}
    if kind:
        expected.add("GroupAuthor" if kind == "group" else "PrivateAuthor")
    assert set(names) == expected
