"""提示词块注册表与默认模板（templates/prompts.toml）的一致性、顺序契约回归。

这些用例是重构的护栏：新增块只需改 ``prompt/blocks.py`` 与 TOML，
一旦注册表、模板、store 派生的分区清单或阶段顺序漂移，这里立刻报错。
"""

from __future__ import annotations

import tomllib

import pytest

from neobot_app.prompt.blocks import (
    BLOCKS,
    Stage,
    blocks_for,
    known_sections,
    validate_blocks,
)
from neobot_app.prompt.context import Scope
from neobot_app.prompt.store import DEFAULT_TEMPLATE_FILE, KNOWN_SECTIONS


def _template_sections() -> dict[str, dict]:
    """默认模板的分区（排除根级 version 键）。"""
    document = tomllib.loads(DEFAULT_TEMPLATE_FILE.read_text("utf-8"))
    return {key: value for key, value in document.items() if key != "version"}


def _ids(stage: Stage, scope: Scope) -> tuple[str, ...]:
    return tuple(block.id for block in blocks_for(stage, scope))


# ── 注册表自检 ────────────────────────────────────────────────────────────────


def test_validate_blocks_reports_no_problems():
    assert validate_blocks() == []


def test_block_ids_are_unique():
    ids = [block.id for block in BLOCKS]
    assert len(ids) == len(set(ids))


# ── 注册表 <-> TOML 双向一致 ──────────────────────────────────────────────────


def test_registry_and_template_sections_match_both_ways():
    sections = set(_template_sections())
    registered = set(known_sections())
    assert registered == sections, (
        f"注册表登记了模板里没有的分区: {sorted(registered - sections)}; "
        f"模板里有注册表未登记的分区: {sorted(sections - registered)}"
    )


def test_store_known_sections_are_derived_from_registry():
    assert KNOWN_SECTIONS == known_sections()
    assert len(KNOWN_SECTIONS) == len(set(KNOWN_SECTIONS))


def test_every_block_declared_key_exists_in_its_section():
    sections = _template_sections()
    for block in BLOCKS:
        section = block.template_section
        if section is None:
            continue
        assert section in sections, f"{block.id}: 模板缺少分区 [{section}]"
        assert block.key in sections[section], f"{block.id}: 分区缺少键 {block.key!r}"
        for extra_key in block.extra_keys:
            assert extra_key in sections[section], f"{block.id}: 分区缺少键 {extra_key!r}"


def test_problem_solver_runtime_subtable_is_declared():
    runtime = _template_sections()["problem_solver"]["runtime"]
    assert "template" in runtime
    assert str(runtime["template"]).strip()


def test_listed_template_text_is_not_blank():
    """有分区的块必须能在默认模板里渲染出文本（空模板会被组合器静默跳过）。"""
    sections = _template_sections()
    for block in BLOCKS:
        section = block.template_section
        if section is None:
            continue
        assert str(sections[section][block.key]).strip(), block.id


# ── 顺序：同一 (stage, scope) 内唯一，且各阶段块数可枚举 ─────────────────────


@pytest.mark.parametrize("stage", list(Stage), ids=lambda stage: stage.value)
def test_orders_are_unique_within_stage_and_scope(stage: Stage):
    if stage is Stage.CATALOG:
        # catalog 资产不参与注入排序，order 无意义
        return
    for scope in Scope:
        orders = [block.order for block in blocks_for(stage, scope)]
        assert len(orders) == len(set(orders)), f"{stage.value}/{scope.value} order 冲突"


# ── 顺序契约（按注册表当前值固定；改动需同步改本表） ─────────────────────────


@pytest.mark.parametrize(
    ("stage", "scope", "expected"),
    [
        # system 最前面的全局 cot 板块（子块顺序即注入顺序）
        (
            Stage.SYSTEM_PREFIX,
            Scope.GROUP,
            (
                "cot_intro",
                "cot_at_mention",
                "gentle_language",
                "cot_avoid_bot_chat",
                "cot_no_bluffing",
                "cot_no_game_topics",
                "cot_no_echo_images",
                "cot_cross_chat",
                "cot_outro",
            ),
        ),
        (
            Stage.SYSTEM_PREFIX,
            Scope.PRIVATE,
            (
                "cot_intro",
                "cot_at_mention",
                "gentle_language",
                "cot_avoid_bot_chat",
                "cot_no_bluffing",
                "cot_no_game_topics",
                "cot_no_echo_images",
                "cot_cross_chat",
                "cot_outro",
            ),
        ),
        # 主模板：每个会话作用域各自一个
        (Stage.SYSTEM_MAIN, Scope.GROUP, ("group_chat",)),
        (Stage.SYSTEM_MAIN, Scope.PRIVATE, ("friend_chat",)),
        (Stage.SYSTEM_MAIN, Scope.LIVE, ("live_chat",)),
        # system 末尾追加（group 有 @ 提示，private 有私聊提示）
        (
            Stage.SYSTEM_APPEND,
            Scope.GROUP,
            (
                "reply_tool_contract",
                "long_task_progress",
                "human_feel",
                "stale_topic",
                "adaptive_prompt",
                "at_mention_priority",
                "skill_index",
                "tool_packages",
                "available_skills",
                "tool_restriction",
                "native_vision",
                "official_platform_note",
            ),
        ),
        (
            Stage.SYSTEM_APPEND,
            Scope.PRIVATE,
            (
                "reply_tool_contract",
                "friend_chat_hint",
                "long_task_progress",
                "human_feel",
                "stale_topic",
                "adaptive_prompt",
                "skill_index",
                "tool_packages",
                "available_skills",
                "tool_restriction",
                "native_vision",
                "official_platform_note",
            ),
        ),
        # 本轮上下文 user 块
        (Stage.CONTEXT, Scope.GROUP, ("group_context", "at_mention_wait")),
        (Stage.CONTEXT, Scope.PRIVATE, ("friend_context",)),
        # 会话中途的动态内容
        (
            Stage.RUNTIME_DATA,
            Scope.GROUP,
            (
                "background_notification",
                "new_member_profiles",
                "group_chat_resume",
                "vision_fallback_notice",
            ),
        ),
        (Stage.RUNTIME_DATA, Scope.PRIVATE, ("background_notification", "vision_fallback_notice")),
        # 提醒类
        (Stage.REMINDER, Scope.GROUP, ("avoid_repeat", "silent_nudge", "prev_no_tool_call_reminder", "no_tool_call_reminder")),
        (Stage.REMINDER, Scope.PRIVATE, ("avoid_repeat", "silent_nudge", "prev_no_tool_call_reminder", "no_tool_call_reminder")),
        # 时间块（terminal）
        (Stage.TIME, Scope.GROUP, ("current_time", "current_time_short")),
        (Stage.TIME, Scope.PRIVATE, ("current_time", "current_time_short")),
        # 子 Agent
        (Stage.SUBAGENT, Scope.SUBAGENT, ("problem_solver", "self_heal", "maintenance")),
    ],
)
def test_stage_order_contract(stage: Stage, scope: Scope, expected: tuple[str, ...]):
    assert _ids(stage, scope) == expected
