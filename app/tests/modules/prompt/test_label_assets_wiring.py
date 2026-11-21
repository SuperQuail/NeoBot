"""label_* 资产在调用方的接线测试。

- custom 覆盖经 prompt_store 生效（role_messages / keyword_reaction / skills /
  tool_packages / vision_context）；
- ``[label_*] enabled = false`` 时文本为空、不注入；
- prompt_store 缺省时输出与内置模板逐字一致。
"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_adapter.model.basic import PostMessageMessagesender
from neobot_adapter.model.message import GroupMessage, MessageSegment

from neobot_app.message.queue import MessageQueue
from neobot_app.prompt.keyword_reaction import KeywordReactionBuilder
from neobot_app.prompt.role_messages import _format_message_age, build_role_messages
from neobot_app.reply.orchestrator_parts.prompt_blocks import PromptBlocksMixin
from neobot_app.reply.orchestrator_parts.tool_text import _render_tool_package_index
from neobot_app.reply.vision_context import (
    ReplyVisionContext,
    append_image_context,
    labelled_tool_images,
)

KEY = "888888"
BASE = 1_700_000_000


def _role_queue(*texts: str) -> MessageQueue:
    queue = MessageQueue(timestamp_interval_seconds=10**9)
    for index, text in enumerate(texts, start=1):
        queue.push_history(
            KEY,
            GroupMessage(
                message_id=index,
                user_id=10001,
                group_id=int(KEY),
                message=[MessageSegment(type="text", data={"text": text})],
                raw_message=text,
                sender=PostMessageMessagesender(user_id=10001, nickname="群友"),
            ),
            occurred_at=BASE + index,
        )
    return queue


class _KeywordQueue:
    bot_account = 0

    def iterate_from_newest(self, key: str) -> list:
        return [
            SimpleNamespace(
                user_id=10001,
                message=[SimpleNamespace(type="text", data={"text": "妈妈"})],
            )
        ]


_RULES = [{"enabled": True, "keywords": ["妈妈"], "prompt_list": ["你可以反问对方是不是叫夏亚"]}]


class _Skill:
    qualified_name = "p:weather"
    name = "weather"
    description = "查天气"


class _Blocks(PromptBlocksMixin):
    def __init__(self, prompt_store=None) -> None:
        self._prompt_store = prompt_store


class _ImageResult:
    image_parts = [{"type": "image_url", "image_url": {"url": "x"}}]

    def __str__(self) -> str:
        return '{"ok": true, "images": [{"sender": "小明", "msg_number": 1}]}'


_PACKAGE_MANAGER = SimpleNamespace(
    deferred_skill_names=["pkg"],
    skill_tool_names=lambda name: ["tool_a", "tool_b"],
)


def _build_keyword(prompt_store):
    return KeywordReactionBuilder(_RULES, prompt_store=prompt_store).build(
        queue=_KeywordQueue(), queue_key="1", conversation_type="group"
    )


# ── 默认输出：prompt_store=None 时与内置模板逐字一致 ──


def test_defaults_are_verbatim_without_store():
    assert build_role_messages(_role_queue("你好"), KEY) == [
        {"role": "user", "content": "[msg_id=1] [刚刚] 群友: 你好"}
    ]
    assert _format_message_age(BASE, BASE + 60) == "1分钟前"
    assert _build_keyword(None) == '<追加信息_1>对于"妈妈",你可以反问对方是不是叫夏亚</追加信息_1>'
    assert _Blocks()._render_skills([_Skill()]) == ('<skill id="p:weather" description="查天气" />')
    assert _render_tool_package_index(_PACKAGE_MANAGER) == "- pkg: tool_a, tool_b"


def test_vision_defaults_are_verbatim_without_store():
    messages: list[dict] = []
    append_image_context(messages, [{"type": "image_url", "image_url": {"url": "x"}}])
    assert messages[0]["content"][0]["text"].startswith("[视觉上下文]")

    parts = labelled_tool_images(_ImageResult(), tool_call_id="call-1")
    assert parts[0]["text"].startswith("[主动加载图片] call-1，发送者：小明")
    assert "正文消息编号 1" in parts[0]["text"]


# ── custom 覆盖 ──


def test_custom_label_message_meta_line_applies_to_role_messages(custom_store):
    store = custom_store('[label_message_meta]\nline = "[{sender}] {age}{content}"\n')

    messages = build_role_messages(_role_queue("你好"), KEY, prompt_store=store)

    assert messages == [{"role": "user", "content": "[群友] [刚刚] 你好"}]


def test_custom_label_keyword_reaction_entry_applies(custom_store):
    store = custom_store('[label_keyword_reaction]\nentry = "关键词:{keywords} -> {prompt_text}"\n')

    assert _build_keyword(store) == "关键词:妈妈 -> 你可以反问对方是不是叫夏亚"


def test_custom_label_skills_item_applies(custom_store):
    store = custom_store('[label_skills]\nitem = "技能:{skill_id}|{description}"\n')

    assert _Blocks(store)._render_skills([_Skill()]) == "技能:p:weather|查天气"


def test_custom_label_tool_packages_entry_applies(custom_store):
    store = custom_store('[label_tool_packages]\nentry = "{name}=>{tools}"\n')

    assert _render_tool_package_index(_PACKAGE_MANAGER, prompt_store=store) == ("pkg=>tool_a, tool_b")


def test_custom_label_vision_context_applies(custom_store):
    store = custom_store('[label_vision_context]\nintro = "自定义视觉说明"\n')

    messages: list[dict] = []
    append_image_context(messages, [{"type": "image_url", "image_url": {"url": "x"}}], prompt_store=store)
    assert messages[0]["content"][0] == {"type": "text", "text": "自定义视觉说明"}


# ── enabled = false：文本为空 / 不注入 ──


def test_label_message_meta_cannot_be_disabled(custom_store):
    """机制标签禁用会让聊天记录整条消失；enabled=false 对 label_* 不生效。"""
    store = custom_store("[label_message_meta]\nenabled = false\n")

    messages = build_role_messages(_role_queue("你好"), KEY, prompt_store=store)
    assert messages
    assert _format_message_age(BASE, BASE + 60, prompt_store=store)


def test_disabled_label_keyword_reaction_is_not_injected(custom_store):
    store = custom_store("[label_keyword_reaction]\nenabled = false\n")

    assert _build_keyword(store) == ""


def test_disabled_label_skills_is_not_injected(custom_store):
    store = custom_store("[label_skills]\nenabled = false\n")

    assert _Blocks(store)._render_skills([_Skill()]) == ""


def test_disabled_label_tool_packages_is_not_injected(custom_store):
    store = custom_store("[label_tool_packages]\nenabled = false\n")

    assert _render_tool_package_index(_PACKAGE_MANAGER, prompt_store=store) == ""


def test_disabled_label_vision_context_leaves_images_but_no_text(custom_store):
    store = custom_store("[label_vision_context]\nenabled = false\n")
    image = {"type": "image_url", "image_url": {"url": "x"}}

    parts = labelled_tool_images(_ImageResult(), prompt_store=store)
    assert parts == [image]

    messages: list[dict] = []
    append_image_context(messages, parts, prompt_store=store)
    assert messages == [{"role": "user", "content": [image]}]


def test_reply_vision_context_passes_its_store_to_the_appendix(custom_store):
    store = custom_store('[label_vision_context]\nintro = "自定义视觉说明"\n')
    context = ReplyVisionContext(prompt_store=store)
    context.manual_parts = [{"type": "image_url", "image_url": {"url": "x"}}]

    request = context.request_messages([])

    assert request[-1]["content"][0] == {"type": "text", "text": "自定义视觉说明"}
