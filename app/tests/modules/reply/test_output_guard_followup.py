"""Independent review failures, including actual tool-to-sender delivery."""
from types import SimpleNamespace

import pytest

from neobot_contracts.models import ConversationRef
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.output_guard import clean_text, clean_segments
from neobot_app.reply.sender import ReplySender
from neobot_app.reply.tools import ReplyToolExecutor


@pytest.mark.parametrize("raw", [
    "<think>outer<think>inner</think>tail</think>hello",
    "<think>first</think>\n\n<think>second</think>hello",
    "Bot: " * 100 + "<think>draft</think>hello",
])
def test_nested_and_repeated_annotations_reach_fixed_point(raw):
    result = clean_text(raw, known_sender_names=["Bot"])
    assert result == "hello"
    assert clean_text(result, known_sender_names=["Bot"]) == result


@pytest.mark.parametrize("fence", ["```", "~~~~", "````"])
@pytest.mark.parametrize("closed", [True, False])
def test_fenced_annotations_are_literal(fence, closed):
    raw = fence + "text\n192:\n12: Bot: example\n[msg_id=1] value\n<think>example</think>"
    if closed:
        raw += "\n" + fence
    assert clean_text(raw, known_sender_names=["Bot"]) == raw


@pytest.mark.parametrize("raw", [
    "1: ```code```",
    "1: ~~~code~~~",
    "```text\nexample ``` inline\n192:\n12: Bot: example\n```",
])
def test_fence_slicing_does_not_invent_line_boundaries(raw):
    assert clean_text(raw, known_sender_names=["Bot"]) == raw


def test_inline_tag_after_fence_is_not_a_new_message():
    raw = "Example:\n```xml\n<x/>\n```<think>literal</think>end"
    assert clean_text(raw) == raw


def test_split_fences_keep_literal_content_and_are_idempotent():
    raw = ["```text", "192:", "<think>example</think>", "```", "Bot: hello"]
    expected = raw[:-1] + ["hello"]
    result = clean_segments(raw, known_sender_names=["Bot"])
    assert result == expected
    assert clean_segments(result, known_sender_names=["Bot"]) == result


@pytest.mark.parametrize("example", ["Use ```code``` here.", "```code```", "Use ``` here."])
def test_inline_backticks_do_not_disable_guard_for_later_segments(example):
    assert clean_segments([example, "<think>secret</think>hello", "Bot: world"], known_sender_names=["Bot"]) == [example, "hello", "world"]


@pytest.mark.parametrize("prefix", ["Bot: ", "[msg_id=1] ", "Bot: [msg_id=1] " * 20])
def test_annotation_prefix_exposes_fence_before_cleaning_code(prefix):
    code = "```text\n192:\n[msg_id=1] literal\n```"
    assert clean_text(prefix + code, known_sender_names=["Bot"]) == code


def test_split_thoughts_keep_depth_and_reply_boundaries():
    raw = ["<think>outer", "<think>inner</think>private", "</think>hello", "world"]
    assert clean_segments(raw) == ["hello", "world"]
    assert clean_segments(["Bot: <think>draft", "private", "</think>hello"], known_sender_names=["Bot"]) == ["hello"]
    assert clean_segments(["<think>draft", "private"]) == []


@pytest.mark.parametrize("raw,segments,original,expected", [
    ("<think>draft</think>hello", ["<think>draft", "private", "</think>hello"], False, ["hello"]),
    ("<think>outer<think>inner</think>tail</think>hello", None, True, ["hello"]),
    ("```text\n192:\n```", None, True, ["```text\n192:\n```"]),
])
async def test_real_tool_and_sender_preserve_only_expected_content(raw, segments, original, expected):
    sent = []
    async def send(conversation_ref, payload, **kwargs):
        sent.extend(s["data"]["text"] for s in payload if s["type"] == "text")
        return {"message_id": 1}
    sender = ReplySender(adapter=SimpleNamespace(send=send), file_server=None, sentence_cooldown_seconds=0)
    event = ReplyEvent(conversation_ref=ConversationRef(kind="group", id="1"))
    event.transition(ReplyState.BUILDING_PROMPT)
    event.transition(ReplyState.GENERATING)
    async def handler(**kwargs):
        return await sender.send_reply(event, kwargs["text"], segments=kwargs["segments"], send_original=kwargs["send_original"])
    executor = ReplyToolExecutor(send_reply_handler=handler)
    result = await executor.execute("send_reply", {"text": raw, "segments": segments, "send_original": original})
    assert sent == expected
    assert "已发送" in result
