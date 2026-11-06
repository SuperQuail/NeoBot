"""send_reply 回执：告诉模型「实际怎么切分」，并支持 raw=true 整段直发。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

from neobot_app.reply.debug import DebugHelper
from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.sender import ReplySender
from neobot_app.reply.tools import ReplyToolExecutor

from neobot_contracts.models import ConversationRef

# 多句回复：自动切分必然是好几条，却不会触碰条数上限。
MULTI_SENTENCE = "今天天气不错，我们去公园走走吧。顺便买点吃的回来。晚上再一起看电影怎么样？"


class _Adapter:
    def __init__(self) -> None:
        self.sent: list[list[dict]] = []

    async def send(self, conversation_ref, payload, **kwargs):
        self.sent.append(payload)
        return {"message_id": len(self.sent)}


def _sender(image_path=None):
    adapter = _Adapter()
    emoji = (
        SimpleNamespace(
            get_entry=lambda number: SimpleNamespace(file_path=image_path),
            record_usage=AsyncMock(),
        )
        if image_path is not None
        else None
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
    return sender, event, adapter


def _executor(sender, event, **kwargs):
    async def handler(**args):
        return await sender.send_reply(
            event,
            args["text"],
            segments=args["segments"],
            send_original=args["send_original"],
            images=args["images"],
        )

    return ReplyToolExecutor(send_reply_handler=handler, **kwargs)


def _wire_texts(adapter):
    return [
        part["data"]["text"]
        for payload in adapter.sent
        for part in payload
        if part["type"] == "text"
    ]


async def test_receipt_reports_the_parts_actually_sent():
    """多句回复：回执的 parts 必须逐条对上真正发出去的顺序与内容。"""
    sender, event, adapter = _sender()
    receipt = json.loads(
        await _executor(sender, event).execute("send_reply", {"text": MULTI_SENTENCE})
    )

    wire = _wire_texts(adapter)
    assert len(wire) > 1  # 前提：这段文本确实被切成了多条
    assert receipt["ok"] is True
    assert receipt["raw"] is False
    assert receipt["sent_count"] == len(wire)
    assert [part["text"] for part in receipt["parts"]] == wire
    assert [part["index"] for part in receipt["parts"]] == list(range(1, len(wire) + 1))
    assert {part["type"] for part in receipt["parts"]} == {"text"}


async def test_raw_true_sends_one_unmodified_message_and_bypasses_review():
    """raw=true：不切分、整段一条，且不触发 AI 回复检查。"""
    sender, event, adapter = _sender()
    executor = _executor(sender, event, ai_reply_check=True)
    receipt = json.loads(
        await executor.execute("send_reply", {"text": MULTI_SENTENCE, "raw": True})
    )

    assert _wire_texts(adapter) == [MULTI_SENTENCE]
    assert receipt["raw"] is True
    assert receipt["sent_count"] == 1
    assert receipt["parts"] == [{"index": 1, "type": "text", "text": MULTI_SENTENCE}]


async def test_raw_bypasses_over_limit_intercept():
    """raw=true：超限也不拦截（与被拦截路径形成对照）。"""
    sender, event, adapter = _sender()
    executor = _executor(
        sender,
        event,
        ai_reply_check_lightweight=False,
        enable_ai_reply_regenerate=True,
        long_reply_max_sentence_count=4,
    )
    text = "".join(f"第{i}句。" for i in range(1, 16))
    receipt = json.loads(
        await executor.execute("send_reply", {"text": text, "raw": True})
    )

    assert _wire_texts(adapter) == [text]
    assert receipt["parts"] == [{"index": 1, "type": "text", "text": text}]


async def test_images_are_reported_as_separate_parts(tmp_path):
    """图片与文字各算一条：parts 按发送顺序标注类型。"""
    image = tmp_path / "sticker.png"
    image.write_bytes(b"fake image")
    sender, event, adapter = _sender(image)
    receipt = json.loads(
        await _executor(sender, event).execute(
            "send_reply", {"text": "哈哈", "images": [1]}
        )
    )

    assert [part["type"] for part in receipt["parts"]] == ["image", "text"]
    assert receipt["parts"][0]["image"] == 1
    assert receipt["parts"][1]["text"] == "哈哈"
    assert receipt["sent_count"] == len(adapter.sent) == 2


def test_send_reply_schema_documents_raw_and_splitting():
    definitions = {
        item["function"]["name"]: item["function"]
        for item in ReplyToolExecutor().definitions()
    }
    send_reply = definitions["send_reply"]

    raw = send_reply["parameters"]["properties"]["raw"]
    assert raw["type"] == "boolean"
    assert "不切分" in raw["description"]

    description = send_reply["description"]
    assert "raw=true" in description
    assert "切分" in description and "超过" in description  # 切分规则与超限处理
    assert "原样整段发送" in description
    assert "send_long_reply" in description


async def test_failure_receipt_keeps_error_semantics():
    sender, event, adapter = _sender()
    result = await _executor(sender, event).execute("send_reply", {"text": "cancel"})

    assert result.startswith("错误：") and "未发送" in result
    assert not adapter.sent


async def test_fallback_receipt_reports_fallback_and_reason():
    """兜底（默认回复替换）被放行时，回执必须标出 fallback 与原因。"""
    sender, event, adapter = _sender()
    executor = _executor(
        sender,
        event,
        ai_reply_check_lightweight=False,
        enable_ai_reply_regenerate=False,
        long_reply_max_sentence_count=4,
    )
    receipt = json.loads(
        await executor.execute("send_reply", {"text": "".join(f"第{i}句。" for i in range(1, 16))})
    )

    assert _wire_texts(adapter) == ["Bot懒得和你说道理，你不配听"]
    assert receipt["fallback_used"] is True
    assert "切分后消息数量过多" in receipt["reason"]
    assert receipt["parts"] == [
        {"index": 1, "type": "text", "text": "Bot懒得和你说道理，你不配听"}
    ]


async def test_intercept_receipt_is_not_a_success_payload():
    """未放行的兜底仍走原有的拦截文案，不得伪装成 ok。"""
    sender, event, adapter = _sender()
    executor = _executor(
        sender,
        event,
        ai_reply_check_lightweight=False,
        enable_ai_reply_regenerate=True,
        long_reply_max_sentence_count=4,
    )
    result = await executor.execute(
        "send_reply", {"text": "".join(f"第{i}句。" for i in range(1, 16))}
    )

    assert result.startswith("回复被拦截：")
    assert not adapter.sent


# ── 多条语句 + 逐条 raw ──────────────────────────────────────────────────────

FORMULA = "勾股定理：$a^2+b^2=c^2$"


async def test_segments_object_raw_keeps_formula_whole_and_splits_the_rest():
    """对象 raw=true 只对那一条负责：公式整段直发，其余语句交给系统切分。"""
    sender, event, adapter = _sender()
    receipt = json.loads(
        await _executor(sender, event).execute(
            "send_reply",
            {
                "segments": [
                    {"text": FORMULA, "raw": True},
                    {"text": "第一句。第二句。第三句。"},
                ]
            },
        )
    )

    wire = _wire_texts(adapter)
    assert wire[0] == FORMULA  # 公式没有被拆开
    assert len(wire) > 2  # 其余语句被自动切成多条
    assert receipt["sent_count"] == len(wire)
    assert receipt["parts"][0] == {
        "index": 1, "type": "text", "text": FORMULA, "raw": True,
    }
    assert [part["text"] for part in receipt["parts"]] == wire
    assert not any(part.get("raw") for part in receipt["parts"][1:])


async def test_segments_object_without_raw_is_auto_split():
    sender, event, adapter = _sender()
    receipt = json.loads(
        await _executor(sender, event).execute(
            "send_reply", {"segments": [{"text": MULTI_SENTENCE}]}
        )
    )

    wire = _wire_texts(adapter)
    assert len(wire) > 1
    assert [part["text"] for part in receipt["parts"]] == wire


async def test_plain_string_segments_stay_final_messages():
    """旧语义保留：字符串元素是已确认分条，不再二次切分。"""
    sender, event, adapter = _sender()
    receipt = json.loads(
        await _executor(sender, event).execute(
            "send_reply", {"segments": ["第一句。第二句。"], "text": "第一句。第二句。"}
        )
    )

    assert _wire_texts(adapter) == ["第一句。第二句。"]
    assert receipt["sent_count"] == 1


async def test_segments_only_without_text_is_allowed():
    sender, event, adapter = _sender()
    receipt = json.loads(
        await _executor(sender, event).execute(
            "send_reply", {"segments": [{"text": "只有这一条。"}]}
        )
    )

    assert _wire_texts(adapter)[0].startswith("只有这一条")
    assert receipt["ok"] is True


async def test_auto_segment_over_limit_reports_which_statement():
    sender, event, adapter = _sender()
    executor = _executor(
        sender, event, long_reply_max_sentence_count=4
    )
    result = await executor.execute(
        "send_reply",
        {"segments": [{"text": "。".join(f"第{i}句" for i in range(1, 16)) + "。"}]},
    )

    assert result.startswith("错误：第 1 条语句无法自动切分")
    assert "raw=true" in result
    assert not adapter.sent


def test_send_reply_schema_documents_per_statement_raw():
    definitions = {
        item["function"]["name"]: item["function"]
        for item in ReplyToolExecutor().definitions()
    }
    send_reply = definitions["send_reply"]
    segments = send_reply["parameters"]["properties"]["segments"]
    assert segments["items"]["oneOf"][0] == {"type": "string"}
    assert segments["items"]["oneOf"][1]["type"] == "object"
    assert "raw" in segments["items"]["oneOf"][1]["properties"]
    assert "该条" in segments["description"] and "自动切分" in segments["description"]
    assert send_reply["parameters"]["required"] == []
