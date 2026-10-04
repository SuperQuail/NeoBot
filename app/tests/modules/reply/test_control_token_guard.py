"""PR #45 regressions through the real sender, not just string predicates."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_app.reply.debug import DebugHelper
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.output_guard import clean_segments, clean_text
from neobot_app.reply.postprocess import process_reply_text
from neobot_app.reply.sender import ReplySender
from neobot_app.reply.tools import ReplyToolExecutor
from neobot_contracts.models import ConversationRef


class Adapter:
    def __init__(self):
        self.sent = []

    async def send(self, conversation_ref, payload, **kwargs):
        self.sent.append(payload)
        return {"message_id": len(self.sent)}


class Rewriter:
    def __init__(self, stage, text):
        self.stage, self.text = stage, text

    async def dispatch_envelope(self, envelope):
        if envelope.stage == self.stage:
            if self.stage == "reply.postprocess.after":
                # In-place mutation must not defeat the pre-hook snapshot.
                envelope.payload["reply_messages"][:] = [self.text]
            else:
                envelope.payload.update(text=self.text, segments=None)
        return envelope


def make_sender(*, hook=None, **kwargs):
    adapter = Adapter()
    sender = ReplySender(
        adapter=adapter,
        file_server=SimpleNamespace(_enabled=False),
        bot_name="Bot",
        sentence_cooldown_seconds=0,
        private_chat_sentence_cooldown_seconds=0,
        debug_helper=DebugHelper(runtime_events=hook),
        **kwargs,
    )
    event = ReplyEvent(conversation_ref=ConversationRef(kind="group", id="123"))
    event.transition(ReplyState.BUILDING_PROMPT)
    event.transition(ReplyState.GENERATING)
    return sender, event, adapter


def wire_text(adapter):
    return [part["data"]["text"] for payload in adapter.sent for part in payload if part["type"] == "text"]


def tool_for(sender, event, **kwargs):
    async def handler(**args):
        return await sender.send_reply(
            event, args["text"], segments=args["segments"], send_original=args["send_original"],
            images=args["images"], merge_text_with_image=args["merge_text_with_image"],
            split_preview=args.get("split_preview"),
        )

    return ReplyToolExecutor(send_reply_handler=handler, **kwargs)


@pytest.mark.parametrize("raw", ["cancel", " CANCEL ", "Bot: cancel", "<think>secret</think>cancel"])
@pytest.mark.parametrize("route", ["text", "segments", "original", "reply.postprocess.before", "reply.send.before", "reply.postprocess.after"])
async def test_control_only_output_never_reaches_adapter(raw, route):
    hook = Rewriter(route, raw) if route.startswith("reply.") else None
    sender, event, adapter = make_sender(hook=hook)
    text = "safe draft" if hook or route == "segments" else raw
    delivered = await sender.send_reply(
        event, text, segments=[raw] if route == "segments" else None,
        send_original=route == "original",
    )
    assert delivered is False
    assert adapter.sent == []
    assert event.send_response is None
    assert event.state is ReplyState.GENERATING  # allow a tool retry, not fake completion


@pytest.mark.parametrize("args", [
    {"text": "cancel"},
    {"text": "cancel", "send_original": True},
    {"text": "ignored draft", "segments": ["cancel"]},
    {"text": "cancel", "segments": ["cancel"], "ai_check_approved": True},
    {"text": "(internal note)cancel"},
])
async def test_real_tool_reports_non_success_without_calling_cancel(args):
    sender, event, adapter = make_sender()
    cancel = AsyncMock()
    executor = tool_for(sender, event, cancel_handler=cancel)
    result = await executor.execute("send_reply", args)
    assert result.startswith("错误：")
    assert "未发送" in result and "cancel" in result
    assert "已发送" not in result
    assert not adapter.sent
    cancel.assert_not_awaited()  # token suppression does not decide to cancel a turn


@pytest.mark.parametrize("raw", ["cancel", "Bot: cancel", "<think>draft</think>"])
async def test_split_preview_is_non_success_when_cleaned_empty(raw):
    result = json.loads(await ReplyToolExecutor().execute("split_reply", {"text": raw}))
    assert result["ok"] is False
    assert result["messages"] == []
    assert "清洗后为空" in result["error"]


@pytest.mark.parametrize("phrase", [
    "不需要回滚", "不需要回家", "不是不需要回复", "你的代码没有问题，不需要回滚。",
    "不需要插话，取消这条回复。", "取消", "cancel 是什么意思", "请解释 cancel 命令",
    '"cancel"', "'cancel'", "「cancel」", "`cancel`", "> cancel", "*", "__", "~~~", "？？？",
])
@pytest.mark.parametrize("route", ["text", "segments", "original"])
async def test_legitimate_prose_quotes_code_and_punctuation_survive(phrase, route):
    sender, event, adapter = make_sender()
    delivered = await sender.send_reply(
        event, phrase, segments=[phrase] if route == "segments" else None,
        send_original=route == "original",
    )
    assert delivered is True
    if route == "text":
        # Ordinary sentence splitting may remove punctuation/space, but no words.
        def compact(value):
            return value.translate(str.maketrans("", "", " ，,。;\n"))
        assert compact("".join(wire_text(adapter))) == compact(phrase)
    else:
        assert wire_text(adapter) == [phrase]


@pytest.mark.parametrize("fence", ["```", "~~~", "````", "~~~~"])
@pytest.mark.parametrize("use_tool", [False, True])
async def test_cross_segment_fence_state_preserves_cancel_and_removes_trailing_thought(fence, use_tool):
    raw = [
        "cancel", fence + "text", "cancel", "<think>literal</think>", fence,
        "<think>outer", "<think>nested</think>private", "</think>你好", "cancel",
    ]
    expected = [fence + "text", "cancel", "<think>literal</think>", fence, "你好"]
    assert clean_segments(raw) == expected
    assert clean_segments(expected) == expected
    sender, event, adapter = make_sender()
    if use_tool:
        result = await tool_for(sender, event).execute("send_reply", {"text": "ignored", "segments": raw})
        assert "已发送" in result
    else:
        assert await sender.send_reply(event, "ignored", segments=raw)
    assert wire_text(adapter) == expected


@pytest.mark.parametrize("fence", ["```", "~~~"])
async def test_automatic_split_does_not_erase_closing_fence_or_leak_trailing_think(fence):
    sender, event, adapter = make_sender()
    assert await sender.send_reply(event, f"{fence}text\ncancel\n{fence}\n<think>秘密草稿</think>你好")
    assert wire_text(adapter) == [fence + "text", "cancel", fence, "你好"]


@pytest.mark.parametrize("fence", ["```", "~~~"])
async def test_send_original_keeps_code_and_still_cleans_leading_think(fence):
    body = f"{fence}text\ncancel\n{fence}"
    sender, event, adapter = make_sender()
    result = await tool_for(sender, event).execute("send_reply", {
        "text": "<think>secret</think>" + body,
        "segments": ["different text"], "send_original": True,
    })
    assert wire_text(adapter) == [body]
    assert "已发送原文" in result and "different text" not in result


@pytest.mark.parametrize("raw", [
    "cancel", "Bot: " * 20 + "<think>a<think>b</think></think>cancel",
    "不需要回滚", '"cancel"', "`cancel`", "~~~text\ncancel\n~~~", "**", "~",
])
def test_guard_fixed_point_preserves_main_contract(raw):
    once = clean_text(raw, known_sender_names=["Bot"])
    assert clean_text(once, known_sender_names=["Bot"]) == once


@pytest.mark.parametrize("merge", [False, True])
@pytest.mark.parametrize("original", [False, True])
async def test_cancel_caption_does_not_drop_image_attachment(tmp_path, merge, original):
    image = tmp_path / "image.png"
    image.write_bytes(b"fake image, never rendered")
    emoji = SimpleNamespace(
        get_entry=lambda number: SimpleNamespace(file_path=image), record_usage=AsyncMock(),
    )
    sender, event, adapter = make_sender(emoji_service=emoji)
    result = await tool_for(sender, event).execute("send_reply", {
        "text": "cancel", "images": [1], "merge_text_with_image": merge, "send_original": original,
    })
    assert "已发送" in result
    assert wire_text(adapter) == []
    assert len(adapter.sent) == 1
    assert [part["type"] for part in adapter.sent[0]] == ["image"]
    assert event.send_response == {"message_id": 1}


@pytest.mark.parametrize("merge", [False, True])
async def test_missing_image_plus_cleaned_empty_text_is_not_success(merge):
    sender, event, adapter = make_sender()
    result = await tool_for(sender, event).execute("send_reply", {
        "text": "cancel", "images": [404], "merge_text_with_image": merge,
    })
    assert result.startswith("错误：") and "未发送" in result
    assert not adapter.sent
    assert event.state is ReplyState.GENERATING
    assert event.send_response is None


@pytest.mark.parametrize("tool", ["send_emoji", "send_long_reply"])
async def test_special_media_caption_uses_guard_before_real_transport(tmp_path, tool):
    image = tmp_path / "rendered.png"
    image.write_bytes(b"fake image")
    sender, event, adapter = make_sender()
    converter = SimpleNamespace(convert=AsyncMock(return_value=image))

    async def handler(**args):
        caption = args.get("caption", args.get("text", ""))
        payload = [{"type": "image", "data": {"file": str(image)}}]
        if caption:
            payload.insert(0, {"type": "text", "data": {"text": caption}})
        return await sender.send_with_timeout(event.conversation_ref, payload)

    executor = ReplyToolExecutor(
        send_emoji_handler=handler, send_long_reply_handler=handler, markdown_image_converter=converter,
    )
    args = {"number": 1, "text": "cancel"} if tool == "send_emoji" else {
        "image_path": str(image), "markdown": "cancel", "caption": "cancel",
    }
    await executor.execute(tool, args)
    assert not wire_text(adapter)
    assert len(adapter.sent) == 1 and adapter.sent[0][0]["type"] == "image"
    converter.convert.assert_not_awaited()


@pytest.mark.parametrize("raw", ["*（取消回复）*", "**(note)**", "_（动作）_", "~~(note)~~"])
async def test_only_postprocess_created_emphasis_shell_is_rejected(raw):
    processed = process_reply_text(raw, bot_name="Bot")
    assert processed.messages == []
    assert processed.reason == "postprocess_empty_markup_shell"
    sender, event, adapter = make_sender()
    assert not await sender.send_reply(event, raw)
    assert not adapter.sent
    executor = tool_for(sender, event, ai_reply_check=True)
    result = await executor.execute("send_reply", {"text": raw})
    assert result.startswith("错误：") and "未发送" in result
    preview = json.loads(await executor.execute("split_reply", {"text": raw}))
    assert preview["ok"] is False and preview["messages"] == []
    assert not executor.ai_check_pending  # nothing to review


@pytest.mark.parametrize("raw", ["**", "****", "__", "~~~~", "~~~", "```", "** （note）", "~~~(note)~~~", "`*(note)*`"])
async def test_existing_markers_fences_and_literals_are_not_postprocess_shells(raw):
    result = process_reply_text(raw, bot_name="Bot")
    assert result.messages
    assert result.reason != "postprocess_empty_markup_shell"
    # send_original has not removed any notes, so no shell was created there.
    sender, event, adapter = make_sender()
    assert await sender.send_reply(event, raw, send_original=True)
    assert wire_text(adapter) == [raw]


# 边界从空格换成全角逗号：空格在中英之间已不再切句（见 test_split_spacing.py），
# 这里要的是「合法正文里出现一个裸 cancel 片段」这个场景，用标点边界同样成立。
@pytest.mark.parametrize("text,expected", [
    ("cancel，是什么意思", ["cancel", "是什么意思"]),
    ("我选择\ncancel", ["我选择", "cancel"]),
])
@pytest.mark.parametrize("preview_tool", ["split_reply", "send_reply"])
async def test_exposed_preview_approved_round_trip_preserves_literal_word(text, expected, preview_tool):
    sender, event, adapter = make_sender()
    executor = tool_for(sender, event, ai_reply_check=True)
    exposed = await executor.execute(preview_tool, {"text": text})
    segments = json.loads(exposed)["messages"] if preview_tool == "split_reply" else re.findall(r"^\d+\. (.*)$", exposed, re.MULTILINE)
    assert segments == expected
    assert not adapter.sent
    result = await executor.execute("send_reply", {
        "text": text, "segments": segments, "ai_check_approved": True,
    })
    assert "已发送 2 条消息" in result
    assert wire_text(adapter) == expected


@pytest.mark.parametrize("text,expected", [
    ("cancel，是什么意思", ["cancel", "是什么意思"]),
    ("我选择\ncancel", ["我选择", "cancel"]),
])
async def test_plain_split_round_trip_requires_no_ai_approval_flag(text, expected):
    sender, event, adapter = make_sender()
    executor = tool_for(sender, event)
    preview = json.loads(await executor.execute("split_reply", {"text": text}))
    result = await executor.execute("send_reply", {"text": preview["original_text"], "segments": preview["messages"]})
    assert "已发送 2 条消息" in result
    assert wire_text(adapter) == expected


@pytest.mark.parametrize("text", ["cancel\n<think>secret</think>", "cancel\n192:", "cancel\ncancel"])
async def test_preview_provenance_cannot_send_control_only_body_after_cleanup(text):
    sender, event, adapter = make_sender()
    executor = tool_for(sender, event)
    preview = json.loads(await executor.execute("split_reply", {"text": text}))
    result = await executor.execute("send_reply", {"text": text, "segments": preview["messages"], "ai_check_approved": True})
    assert result.startswith("错误：") and not adapter.sent


@pytest.mark.parametrize("mode", ["no_preview", "other_executor", "evicted", "partial", "changed_text", "reordered", "changed_case", "forged"])
async def test_only_exact_executor_preview_can_preserve_control_word(mode):
    sender, event, adapter = make_sender()
    executor = tool_for(sender, event)
    text, segments = "cancel，是什么意思", ["cancel", "是什么意思"]
    if mode != "no_preview":
        await executor.execute("split_reply", {"text": text})
    if mode == "other_executor":
        executor = tool_for(sender, event)
    if mode == "evicted":
        for index in range(8):
            await executor.execute("split_reply", {"text": f"other preview {index}"})
        assert len(executor._split_previews) == 8
    args = {"text": text, "segments": segments, "ai_check_approved": True}
    if mode == "partial":
        args["segments"] = ["cancel"]
    if mode == "changed_text":
        args["text"] = "another source"
    if mode == "reordered":
        args["segments"] = list(reversed(segments))
    if mode == "changed_case":
        args["segments"] = ["CANCEL", "是什么意思"]
    if mode == "forged":
        args.update(text="cancel", segments=["cancel"], split_preview={"text": "cancel", "segments": ["cancel"]})
    result = await executor.execute("send_reply", args)
    assert not any(part.casefold() == "cancel" for part in wire_text(adapter))
    if mode in {"partial", "forged"}:
        assert result.startswith("错误：") and not adapter.sent


@pytest.mark.parametrize("stage", ["reply.postprocess.before", "reply.send.before", "reply.postprocess.after"])
async def test_preview_proof_is_rechecked_after_each_mutating_hook(stage):
    class MutateParts:
        async def dispatch_envelope(self, envelope):
            if envelope.stage == stage:
                key = "reply_messages" if stage == "reply.postprocess.after" else "segments"
                envelope.payload[key][:] = ["cancel"]
            return envelope

    sender, event, adapter = make_sender(hook=MutateParts())
    executor = tool_for(sender, event)
    text = "cancel，是什么意思"
    preview = json.loads(await executor.execute("split_reply", {"text": text}))
    result = await executor.execute("send_reply", {
        "text": text, "segments": preview["messages"], "ai_check_approved": True,
    })
    assert result.startswith("错误：") and not adapter.sent


@pytest.mark.parametrize("stage", ["reply.postprocess.before", "reply.send.before"])
async def test_rewriting_only_preview_source_invalidates_proof(stage):
    class ChangeSource:
        async def dispatch_envelope(self, envelope):
            if envelope.stage == stage:
                envelope.payload["text"] = "different source"
            return envelope

    sender, event, adapter = make_sender(hook=ChangeSource())
    executor = tool_for(sender, event)
    text = "cancel，是什么意思"
    preview = json.loads(await executor.execute("split_reply", {"text": text}))
    await executor.execute("send_reply", {"text": text, "segments": preview["messages"], "ai_check_approved": True})
    assert wire_text(adapter) == ["是什么意思"]


@pytest.mark.parametrize("raw", ["cancel", "Bot: cancel", "<think>draft</think>cancel"])
async def test_preview_cannot_authorize_bare_control_only_source(raw):
    sender, event, adapter = make_sender()
    executor = tool_for(sender, event)
    preview = json.loads(await executor.execute("split_reply", {"text": raw}))
    assert not preview["ok"]
    result = await executor.execute("send_reply", {"text": raw, "segments": ["cancel"], "ai_check_approved": True})
    assert result.startswith("错误：") and not adapter.sent
    assert not executor._split_previews


@pytest.mark.parametrize("fence", ["```", "~~~"])
async def test_verified_preview_still_cleans_think_and_preserves_fenced_cancel(fence):
    sender, event, adapter = make_sender()
    executor = tool_for(sender, event)
    text = f"{fence}text\ncancel\n{fence}\n<think>private</think>你好"
    preview = json.loads(await executor.execute("split_reply", {"text": text}))
    await executor.execute("send_reply", {"text": text, "segments": preview["messages"], "ai_check_approved": True})
    assert wire_text(adapter) == [fence + "text", "cancel", fence, "你好"]


@pytest.mark.parametrize("raw,expected", [
    ("你好\n*（微笑）*", ["你好"]),
    ("*（取消回复）*\n*（点头）*", []),
    ("*（点头）*\n你好\n__（微笑）__\n**", ["你好", "**"]),
    ("你好 *（微笑）*", ["你好"]),
    ("*（取消回复）* *（点头）*", []),
])
async def test_mixed_and_multiple_note_shells_have_source_provenance(raw, expected):
    sender, event, adapter = make_sender()
    delivered = await sender.send_reply(event, raw)
    assert delivered is bool(expected)
    assert wire_text(adapter) == expected
    preview = json.loads(await tool_for(sender, event).execute("split_reply", {"text": raw}))
    assert preview["ok"] is bool(expected)
    assert preview["messages"] == expected


@pytest.mark.parametrize("fence", ["```", "~~~", "````", "~~~~"])
async def test_note_lines_inside_fences_remain_literal_while_outside_shells_disappear(fence):
    sender, event, adapter = make_sender()
    text = f"你好\n{fence}text\n*（微笑）*\ncancel\n{fence}\n*（点头）*\n**"
    assert await sender.send_reply(event, text)
    assert wire_text(adapter) == ["你好", fence + "text", "*（微笑）*", "cancel", fence, "**"]


@pytest.mark.parametrize("literal", ['"*（微笑）*"', "'*(note)*'", "“*（微笑）*”", "「*（微笑）*」", "`*(note)*`", ">*（微笑）*"])
async def test_quoted_note_lines_are_not_empty_shells(literal):
    sender, event, adapter = make_sender()
    assert await sender.send_reply(event, literal + "\n*（点头）*")
    assert wire_text(adapter) == [literal]


async def test_required_media_control_token_stops_before_render_or_speech():
    converter = SimpleNamespace(convert=AsyncMock(return_value=Path("unused.png")))
    handler = AsyncMock()
    executor = ReplyToolExecutor(
        send_long_reply_handler=handler, markdown_image_converter=converter,
        tts_service=SimpleNamespace(enabled=True), speak_handler=handler,
    )
    assert not json.loads(await executor.execute("send_long_reply", {"markdown": "cancel"}))["ok"]
    assert (await executor.execute("speak", {"text": "cancel"})).startswith("错误：")
    converter.convert.assert_not_awaited()
    handler.assert_not_awaited()
