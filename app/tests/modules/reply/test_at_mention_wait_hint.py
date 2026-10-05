"""被 @ 时的等待提示（issue #81）：固定延迟默认关，改由提示词让模型自己 wait。

本体不再无条件 sleep `at_mention_reply_delay_seconds`（默认 5.0 → 0），改为被 @ 触发的那一轮
注入 `[at_mention_wait]`：说清了要做什么就直接做，没说要做什么才 wait 五秒。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from neobot_contracts.models import ConversationRef

from neobot_app.config.schemas.bot import Chat
from neobot_app.prompt.store import (
    DEFAULT_TEMPLATE_FILE,
    KNOWN_SECTIONS,
    _FALLBACK_SECTIONS,
    parse_prompt_file,
)
from neobot_app.reply.event import ReplyEvent
from neobot_app.reply.orchestrator import ReplyOrchestrator


def _orchestrator(*, mentioned: bool, store=None) -> ReplyOrchestrator:
    orch = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orch._prompt_store = store
    orch._config = None
    orch._willing_service = SimpleNamespace(is_at_mentioned=lambda _message: mentioned)
    return orch


def _event(kind: str = "group") -> ReplyEvent:
    event = ReplyEvent()
    event.conversation_ref = ConversationRef(kind=kind, id="42")
    event.message = SimpleNamespace(message_id=1, message=[{"type": "text", "data": {"text": "@bot"}}])
    return event


def test_default_at_mention_reply_delay_is_disabled() -> None:
    assert Chat().at_mention_reply_delay_seconds == 0.0


def test_section_registered_and_matches_packaged_template() -> None:
    assert "at_mention_wait" in KNOWN_SECTIONS, "自定义文件里的同名分区会被忽略"
    packaged = parse_prompt_file(DEFAULT_TEMPLATE_FILE)["at_mention_wait"]["template"]
    assert packaged == _FALLBACK_SECTIONS["at_mention_wait"]["template"], "两处默认值不能漂移"


def test_hint_teaches_wait_tool_and_five_seconds() -> None:
    hint = _orchestrator(mentioned=True)._at_mention_wait_message(_event())
    assert hint is not None
    assert hint["role"] == "user"
    assert "wait" in hint["content"] and "五秒" in hint["content"]
    assert "没有说明要你做什么" in hint["content"]
    assert "直接照做，不要等待" in hint["content"]


def test_hint_only_for_group_at_mentions() -> None:
    assert _orchestrator(mentioned=True)._at_mention_wait_message(_event("private")) is None
    assert _orchestrator(mentioned=False)._at_mention_wait_message(_event()) is None


def test_hint_respects_disabled_section() -> None:
    store = SimpleNamespace(enabled=lambda key, default=True: key != "at_mention_wait")
    orch = _orchestrator(mentioned=True, store=store)
    assert orch._at_mention_wait_message(_event()) is None


def _wire_build_prompt(orch: ReplyOrchestrator) -> None:
    orch._prompt_builder = SimpleNamespace(build_group_chat_prompt=AsyncMock(return_value="系统提示词"))
    orch._debug_helper = SimpleNamespace(
        record=lambda *_args, **_kwargs: None,
        emit_runtime_event=AsyncMock(return_value=SimpleNamespace(consumed=False, payload={}, result=None)),
    )
    orch._image_parse_service = None


async def test_build_prompt_appends_hint_to_context_blocks() -> None:
    orch = _orchestrator(mentioned=True)
    _wire_build_prompt(orch)
    context: list[dict[str, str]] = []

    prompt = await orch._build_prompt(_event(), queue=SimpleNamespace(), queue_key="42", context_blocks=context)

    assert prompt == "系统提示词"
    assert [block["role"] for block in context] == ["user"]
    assert "wait" in context[0]["content"]


async def test_build_prompt_skips_hint_without_at_mention() -> None:
    orch = _orchestrator(mentioned=False)
    _wire_build_prompt(orch)
    context: list[dict[str, str]] = []

    await orch._build_prompt(_event(), queue=SimpleNamespace(), queue_key="42", context_blocks=context)

    assert context == []
