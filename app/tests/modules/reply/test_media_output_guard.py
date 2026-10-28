"""Media tools sanitize model text before rendering, speech, and history handlers."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage, MessageSegment
from neobot_app.message.numbering import MessageNumbering
from neobot_app.message.queue import MessageQueue
from neobot_app.reply.tools import ReplyToolExecutor


@pytest.fixture
def media():
    queue = MessageQueue(max_size=50, bot_account=10001)
    queue.push("888888", GroupMessage(
        message_id=1, user_id=20001, group_id=888888,
        sender=PostMessageMessagesender(user_id=20001, nickname="贝拉"),
        message=[MessageSegment(type="text", data={"text": "你好"})],
        raw_message="你好",
    ))
    converter = SimpleNamespace(convert=AsyncMock(return_value="rendered.png"))
    handler = AsyncMock(return_value="已发送语音")
    executor = ReplyToolExecutor(
        bot_name="AAA大肥鱼",
        numbering=MessageNumbering(bot_account=10001, queue=queue),
        markdown_image_converter=converter, send_long_reply_handler=handler,
        tts_service=SimpleNamespace(enabled=True), speak_handler=handler,
        send_emoji_handler=handler,
    )
    return executor, converter, handler


@pytest.mark.parametrize("pre_rendered", [False, True])
async def test_long_reply_cleans_render_caption_and_history(media, pre_rendered):
    executor, converter, handler = media
    args = {
        "markdown": "<think>草稿</think>215: 贝拉: # 正文",
        "caption": "[msg_id=9] AAA大肥鱼: 说明",
        "reply_to": 1, "mention": [20001],
    }
    if pre_rendered:
        args["image_path"] = "pre/rendered.png"
    result = json.loads(await executor.execute("send_long_reply", args))
    assert result["ok"] is True
    assert result["caption"] == "说明"
    handler.assert_awaited_once_with(
        image_path="pre/rendered.png" if pre_rendered else "rendered.png",
        markdown="# 正文", caption="说明", reply_to=1, mention=[20001],
    )
    if pre_rendered:
        converter.convert.assert_not_awaited()
    else:
        converter.convert.assert_awaited_once_with("# 正文")


@pytest.mark.parametrize("dirty", ["<think>草稿</think>", "<thinking>未闭合", "215: 贝拉:"])
async def test_required_media_text_rejected_before_costly_work(media, dirty):
    executor, converter, handler = media
    result = json.loads(await executor.execute("send_long_reply", {"markdown": dirty}))
    assert result["ok"] is False
    assert "清洗后为空" in result["error"]
    assert "清洗后为空" in await executor.execute("speak", {"text": dirty})
    converter.convert.assert_not_awaited()
    handler.assert_not_awaited()


@pytest.mark.parametrize("dirty", ["", "<think>草稿</think>", "215: 贝拉:"])
async def test_optional_text_may_be_empty_without_dropping_media(media, dirty):
    executor, converter, handler = media
    result = json.loads(await executor.execute("send_long_reply", {
        "image_path": "pre/rendered.png", "markdown": dirty, "caption": dirty,
    }))
    assert result["ok"] is True
    assert result["caption"] is None
    assert handler.await_args.kwargs["markdown"] == ""
    assert handler.await_args.kwargs["caption"] == ""
    converter.convert.assert_not_awaited()
    handler.reset_mock()
    # 表情包单独发送：带 text 的调用必须被显式拒绝，不能静默丢弃文字
    result = await executor.execute("send_emoji", {"number": 3, "text": dirty})
    if str(dirty).strip():
        assert result.startswith("错误：") and "单独发送" in result
        handler.assert_not_awaited()
    else:
        assert "已发送表情包" in result
        handler.assert_awaited_once_with(number=3)


async def test_empty_caption_still_renders_valid_markdown(media):
    executor, converter, handler = media
    result = json.loads(await executor.execute("send_long_reply", {
        "markdown": "# 正文", "caption": "<think>草稿</think>",
    }))
    assert result["ok"] is True
    converter.convert.assert_awaited_once_with("# 正文")
    assert handler.await_args.kwargs["caption"] == ""


@pytest.mark.parametrize("dirty, expected", [
    ("215: 贝拉: 你好", "你好"),
    ("AAA大肥鱼: ？？？", "？？？"),
    ("<think>草稿</think>你好", "你好"),
    ("HTTP: 200 OK", "HTTP: 200 OK"),
])
async def test_speech_uses_shared_known_names(media, dirty, expected):
    executor, _, handler = media
    await executor.execute("speak", {"text": dirty})
    assert handler.await_args.kwargs["text"] == expected


def test_emoji_tools_require_sending_alone(media):
    """表情包必须单独发送：send_emoji 没有附带文字，send_reply 没有合并开关。"""
    executor, _, _ = media
    definitions = {item["function"]["name"]: item["function"] for item in executor.definitions()}

    send_emoji = definitions["send_emoji"]
    assert set(send_emoji["parameters"]["properties"]) == {"number"}
    assert "单独发送" in send_emoji["description"]

    send_reply = definitions["send_reply"]
    assert "merge_text_with_image" not in send_reply["parameters"]["properties"]
    assert "单独" in send_reply["description"]
    assert "单独" in send_reply["parameters"]["properties"]["images"]["description"]


@pytest.mark.parametrize("fence", ["```", "~~~"])
async def test_markdown_fenced_examples_survive_guard(media, fence):
    executor, converter, handler = media
    markdown = (
        f"# 示例\n{fence}text\n"
        "215: 贝拉: 示例记录\n<think>示例标签</think>\n    保留缩进\n"
        f"{fence}\n结束"
    )
    result = json.loads(await executor.execute("send_long_reply", {"markdown": markdown}))
    assert result["ok"] is True
    converter.convert.assert_awaited_once_with(markdown)
    assert handler.await_args.kwargs["markdown"] == markdown


def test_media_descriptions_no_longer_promise_unsanitized_output(media):
    executor, _, _ = media
    definitions = {item["function"]["name"]: item["function"] for item in executor.definitions()}
    for name in ("send_long_reply", "speak"):
        description = json.dumps(definitions[name], ensure_ascii=False)
        assert "原样发出" not in description
        assert "不做任何清洗" not in description
        assert "输出安全清洗" in description


async def test_math_source_survives_render_and_history_guard(media):
    executor, converter, handler = media
    source = r"行内 \(x^2\) 与 $$\begin{pmatrix}a&b\\c&d\end{pmatrix}$$"
    result = json.loads(await executor.execute("send_long_reply", {"markdown": source}))
    assert result["ok"] is True
    converter.convert.assert_awaited_once_with(source)
    assert handler.await_args.kwargs["markdown"] == source
