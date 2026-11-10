"""官方机器人提示词块：注册、顺序与 official_platform 能力门控。"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.prompt.blocks import BLOCKS, Stage, block_by_id, blocks_for
from neobot_app.prompt.composer import PromptComposer, make_context
from neobot_app.prompt.context import Scope
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


def test_orchestrator_detects_official_platform_from_profile() -> None:
    orchestrator = ReplyOrchestrator.__new__(ReplyOrchestrator)
    for kind, expected in (("official", True), ("unofficial", False), (None, False)):
        profile = None if kind is None else SimpleNamespace(kind=kind)
        orchestrator._bot_profile = SimpleNamespace(profile=profile)
        assert orchestrator._is_official_platform() is expected

    orchestrator._bot_profile = None
    assert orchestrator._is_official_platform() is False
