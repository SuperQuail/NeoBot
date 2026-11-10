"""官方机器人提示词块：注册、顺序与 official_platform 能力门控。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from neobot_contracts.models import ConversationRef

from neobot_app.prompt.blocks import BLOCKS, Stage, block_by_id, blocks_for
from neobot_app.prompt.composer import PromptComposer, make_context
from neobot_app.prompt.context import Scope
from neobot_app.reply.event import ReplyEvent
from neobot_app.reply.orchestrator import ReplyOrchestrator

_BLOCK_ID = "official_platform_note"


def test_block_is_registered_as_per_round_system_append() -> None:
    block = block_by_id(_BLOCK_ID)

    assert block.stage is Stage.SYSTEM_APPEND
    assert block.per_round is True
    assert block.template_section is None  # 固定文案，不新增 TOML 分区
    assert {Scope.GROUP, Scope.PRIVATE} == set(block.scopes)
    assert blocks_for(Stage.SYSTEM_APPEND, Scope.GROUP)[-1].id == _BLOCK_ID
    assert blocks_for(Stage.SYSTEM_APPEND, Scope.PRIVATE)[-1].id == _BLOCK_ID


def test_order_is_after_every_stable_append_block() -> None:
    stable_orders = [block.order for block in BLOCKS if block.stage is Stage.SYSTEM_APPEND and not block.per_round]
    assert block_by_id(_BLOCK_ID).order > max(stable_orders)


def test_block_is_skipped_without_official_platform_feature() -> None:
    composer = PromptComposer()
    block = block_by_id(_BLOCK_ID)
    ctx = make_context(scope=Scope.GROUP)

    assert composer.block_skip_reason(block, ctx) == "缺少能力 official_platform"
    assert composer.render_status_text(_BLOCK_ID, ctx) == ""

    system = composer.build_system(ctx)
    assert (_BLOCK_ID, "缺少能力 official_platform") in system.skipped
    assert _BLOCK_ID not in system.rendered


def test_block_renders_capability_boundaries_when_feature_enabled() -> None:
    composer = PromptComposer()
    ctx = make_context(scope=Scope.GROUP, features={"official_platform": True})

    assert composer.block_skip_reason(block_by_id(_BLOCK_ID), ctx) is None
    text = composer.render_status_text(_BLOCK_ID, ctx)
    assert text.startswith("<官方机器人限制>")
    for phrase in ("被动回复", "不能主动加好友或入群", "群成员列表", "群管理", "好友管理"):
        assert phrase in text


def _orchestrator() -> ReplyOrchestrator:
    """只挂构建提示词需要的最小属性（沿用 test_at_mention_wait_hint 的做法）。"""
    orch = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orch._config = None
    orch._prompt_store = None
    orch._bot_profile = None
    orch._willing_service = None
    orch._image_parse_service = None
    orch._debug_helper = SimpleNamespace(
        record=lambda *_args, **_kwargs: None,
        emit_runtime_event=AsyncMock(return_value=SimpleNamespace(consumed=False, payload={}, result=None)),
    )
    return orch


def _event(*, channel: str | None = None, account: int = 0) -> ReplyEvent:
    event = ReplyEvent(neobot_channel=channel, bot_account=account)
    event.conversation_ref = ConversationRef(kind="group", id="42")
    event.message = SimpleNamespace(
        message_id=1,
        message=[{"type": "text", "data": {"text": "在吗"}}],
    )
    return event


def test_orchestrator_detects_official_platform_from_event_channel() -> None:
    orchestrator = ReplyOrchestrator.__new__(ReplyOrchestrator)
    orchestrator._bot_profile = SimpleNamespace(profile=SimpleNamespace(kind="official"))

    # 双待模式：事件自带通道优先，另一通道的回复不该被当成官方通道
    assert orchestrator._is_official_platform(_event(channel="official")) is True
    assert orchestrator._is_official_platform(_event(channel="onebot")) is False

    # 旧路径没有 neobot_channel 时才回退身份判定
    assert orchestrator._is_official_platform(_event()) is True
    orchestrator._bot_profile = None
    assert orchestrator._is_official_platform(_event()) is False


async def test_build_prompt_injects_note_only_for_official_event_channel() -> None:
    orchestrator = _orchestrator()
    builder = SimpleNamespace(build_group_chat_prompt=AsyncMock(return_value="系统提示词"))
    orchestrator._prompt_builder = builder

    prompt = await orchestrator._build_prompt(
        _event(channel="official", account=777), queue=SimpleNamespace(), queue_key="42"
    )

    assert "<官方机器人限制>" in prompt
    # 官方通道提示词最前面追加身份说明
    assert prompt.startswith(
        "当前你是使用官方渠道搭建的QQ机器人,所以你看不到QQ号和群号,只看得到QQ ID和群ID,"
    )
    assert builder.build_group_chat_prompt.await_args.kwargs["bot_account"] == 777


async def test_build_prompt_rewrites_qq_and_group_terms_for_official() -> None:
    orchestrator = _orchestrator()
    builder = SimpleNamespace(
        build_group_chat_prompt=AsyncMock(
            return_value="你的QQ号是123，<群聊>群号:456；不要出现QQ群号。"
        )
    )
    orchestrator._prompt_builder = builder
    context_blocks = [{"role": "user", "content": "群友的QQ号是789"}]

    prompt = await orchestrator._build_prompt(
        _event(channel="official", account=777),
        queue=SimpleNamespace(),
        queue_key="42",
        context_blocks=context_blocks,
    )

    # 系统提示词：最前面保留需求原文，正文里的 QQ号/群号改为 ID
    prefix, _, body = prompt.partition("\n")
    assert prefix == "当前你是使用官方渠道搭建的QQ机器人,所以你看不到QQ号和群号,只看得到QQ ID和群ID,"
    assert "你的QQ ID是123" in body
    assert "群 ID:456" in body
    assert "QQ群 ID" in body
    assert "QQ号" not in body and "群号" not in body
    # 上下文块只替换术语，不重复加前缀
    assert context_blocks[0]["content"] == "群友的QQ ID是789"


async def test_build_prompt_keeps_note_out_of_other_channels() -> None:
    orchestrator = _orchestrator()
    builder = SimpleNamespace(build_group_chat_prompt=AsyncMock(return_value="系统提示词"))
    orchestrator._prompt_builder = builder

    prompt = await orchestrator._build_prompt(
        _event(channel="onebot", account=111), queue=SimpleNamespace(), queue_key="42"
    )

    assert "<官方机器人限制>" not in prompt
    assert builder.build_group_chat_prompt.await_args.kwargs["bot_account"] == 111
