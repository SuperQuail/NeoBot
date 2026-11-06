"""遍历注册表：每个块都能在默认模板下渲染；enabled=false 能关掉任意分区；
温和语言插入位置与「system 已消费的占位符不再进上下文」两个跨块行为。
"""

from __future__ import annotations

import pytest

from neobot_app.prompt.blocks import BLOCKS, Block, Stage
from neobot_app.prompt.builder import PromptBuilder
from neobot_app.prompt.composer import PromptComposer, RuntimeState, make_context
from neobot_app.prompt.context import Scope
from neobot_app.prompt.render import template_placeholders
from neobot_app.prompt.store import get_template_value

#: 有运行时条件的块需要的最小 dynamic 值（其余块不需要）。
_DYNAMIC: dict[str, dict[str, object]] = {
    "adaptive_prompt": {"adaptive_text": "<自适应提示词>测试内容</自适应提示词>"},
    "at_mention_priority": {"at_mention": True},
    "skill_index": {"skill_instructions": "Skill 操作说明"},
    "tool_packages": {"tool_package_index": "可加载工具包清单"},
    "available_skills": {"available_skills": "本轮命中的技能"},
    "tool_restriction": {"allowed_tools": "技能 allowed-tools 限制"},
    "at_mention_wait": {"at_mention_wait": True},
    "background_notification": {"background_notification_text": "后台任务完成通知"},
    "new_member_profiles": {"new_member_profiles_text": "新出现的群友档案"},
    "group_chat_resume": {"resume_text": "群聊挂起恢复说明"},
    "vision_fallback_notice": {"vision_fallback": "原生视觉回退说明"},
    "silent_nudge": {"silent_nudge": True},
    "no_tool_call_reminder": {"no_tool_call_reminder": True},
    "current_time": {"time_variant": "full"},
    "current_time_short": {"time_variant": "short"},
}

#: agent 模式能力开关（skill / 工具包 / 原生视觉块依赖）。
_FEATURES = {"agent_mode": True, "native_vision": True}

_SCOPE_ORDER = (Scope.GROUP, Scope.PRIVATE, Scope.LIVE, Scope.SUBAGENT)

GENTLE_MARKER = "你是一个基于LLM的QQ机器人"


def _scope_for(block: Block) -> Scope:
    for scope in _SCOPE_ORDER:
        if block.applies_to(scope):
            return scope
    raise AssertionError(f"{block.id}: 没有任何可用作用域")


def _ctx(block: Block, store, config):
    """按块的阶段/作用域构造最小上下文：模板里的占位符全部给值，动态条件查表。"""
    section = block.template_section
    values: dict[str, str] = {}
    if section is not None:
        raw = get_template_value(store, section, block.key)
        values = {name: f"值_{name}" for name in template_placeholders(raw)}
    return make_context(
        config=config,
        store=store,
        scope=_scope_for(block),
        values=values,
        dynamic=dict(_DYNAMIC.get(block.id, {})),
        features=dict(_FEATURES),
    )


def _run_stage(block: Block, composer: PromptComposer, ctx) -> tuple[bool, list[str]]:
    """按块自身阶段走对应构建路径，返回 (该块是否产出消息/文本, 产出文本列表)。"""
    if block.stage in (Stage.SYSTEM_MAIN, Stage.SYSTEM_INSERT, Stage.SYSTEM_APPEND):
        system = composer.build_system(ctx)
        return block.id in system.rendered, [system.text]
    if block.stage is Stage.CONTEXT:
        build = composer.build_context(ctx)
        return block.id in build.rendered, [message["content"] for message in build.messages]
    if block.stage in (Stage.RUNTIME_DATA, Stage.REMINDER, Stage.TIME):
        messages = composer.inject([], ctx, RuntimeState())
        texts = [message["content"] for message in messages]
        return composer.render_block(block, ctx) in texts, texts
    text = composer.render_status_text(block.id, ctx)
    return bool(text), [text]


# ── 每个块都能渲染 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("block", BLOCKS, ids=lambda block: block.id)
def test_block_renders_with_default_templates(block: Block, prompt_store, bot_config):
    composer = PromptComposer(prompt_store)
    ctx = _ctx(block, prompt_store, bot_config)

    assert composer.block_skip_reason(block, ctx) is None
    assert composer.render_block(block, ctx), f"{block.id}: 渲染为空"

    produced, _ = _run_stage(block, composer, ctx)
    assert produced, f"{block.id}: 未出现在 {block.stage.value} 阶段的产出里"


# ── enabled = false 的自定义覆盖能关掉块 ─────────────────────────────────────

_DISABLE_CANDIDATES = [
    block
    for block in BLOCKS
    if block.template_section is not None and block.stage not in (Stage.SYSTEM_MAIN, Stage.SUBAGENT)
]


@pytest.mark.parametrize("block", _DISABLE_CANDIDATES, ids=lambda block: block.id)
def test_enabled_false_hides_block(block: Block, custom_store, bot_config):
    store = custom_store(f"[{block.template_section}]\nenabled = false\n")
    composer = PromptComposer(store)
    ctx = _ctx(block, store, bot_config)

    assert composer.block_skip_reason(block, ctx) == f"分区 [{block.template_section}] 已关闭"
    produced, _ = _run_stage(block, composer, ctx)
    assert produced is False, f"{block.id}: enabled=false 后仍被产出"


# ── 温和语言：插在人设块之后、回复要求之前 ───────────────────────────────────


@pytest.mark.parametrize("scope", [Scope.GROUP, Scope.PRIVATE], ids=lambda scope: scope.value)
def test_gentle_language_sits_after_persona_before_reply_rules(scope: Scope, prompt_store, bot_config):
    composer = PromptComposer(prompt_store)
    ctx = make_context(config=bot_config, store=prompt_store, scope=scope)
    text = composer.build_system(ctx).text

    assert text.count(GENTLE_MARKER) == 1
    assert text.index("</你是谁>") < text.index(GENTLE_MARKER) < text.index("<回复要求>")


def test_gentle_language_survives_whole_group_chat_override(custom_store, bot_config):
    """整段覆盖 [group_chat] 后，温和语言仍插在自定义人设块之后。"""
    store = custom_store(
        '[group_chat]\ntemplate = """<你是谁>\n自定义人设\n</你是谁>\n<回复要求>自定义规则</回复要求>"""\n'
    )
    composer = PromptComposer(store)
    ctx = make_context(config=bot_config, store=store, scope=Scope.GROUP)
    text = composer.build_system(ctx).text

    assert "自定义人设" in text
    assert text.count(GENTLE_MARKER) == 1
    assert text.index("</你是谁>") < text.index(GENTLE_MARKER) < text.index("<回复要求>")


# ── 占位符去重：system 用掉 {member_list} 后，上下文块不再重复群友内容 ─────────


async def test_system_consumed_member_list_is_not_repeated_in_context(
    custom_store, bot_config, fake_profile, fake_queue
):
    store = custom_store(
        '[group_chat]\ntemplate = """<你是谁>\n{bot_name}\n</你是谁>\n<群友信息>{member_list}</群友信息>"""\n'
    )
    builder = PromptBuilder(bot_config, fake_profile, prompt_store=store)
    context_blocks: list[dict[str, str]] = []

    prompt = await builder.build_group_chat_prompt(123456, fake_queue, context_blocks=context_blocks)

    assert "成员列表：小明、小红" in prompt  # system 消费了 {member_list}
    assert len(context_blocks) == 1
    context_text = context_blocks[0]["content"]
    assert context_blocks[0]["role"] == "user"
    assert "成员列表：小明、小红" not in context_text
    assert "群友信息" not in context_text  # 空区块被 strip_empty_tag_blocks 删除


async def test_fragment_consumed_placeholders_are_deduped_from_context(
    custom_store, bot_config, fake_profile, fake_queue
):
    """共享片段（qq_chat）里用掉的占位符也必须算作 system 已消费。"""
    store = custom_store(
        '[qq_chat]\ntemplate = """<你是谁>\n{bot_name}\n</你是谁>\n<群友信息>{member_list}</群友信息>"""\n'
    )
    builder = PromptBuilder(bot_config, fake_profile, prompt_store=store)
    context_blocks: list[dict[str, str]] = []

    prompt = await builder.build_group_chat_prompt(123456, fake_queue, context_blocks=context_blocks)

    assert "成员列表：小明、小红" in prompt  # 片段消费了 {member_list}
    assert len(context_blocks) == 1
    assert "成员列表：小明、小红" not in context_blocks[0]["content"]


async def test_dedup_only_clears_documented_dedupe_keys(custom_store, bot_config, fake_profile, fake_queue):
    """只去重历史契约的 6 个键；{bot_name}/{group_name} 在 context 里仍应正常渲染。"""
    store = custom_store('[group_context]\ntemplate = """我是{bot_name},群名{group_name}"""\n')
    builder = PromptBuilder(bot_config, fake_profile, prompt_store=store)
    context_blocks: list[dict[str, str]] = []

    await builder.build_group_chat_prompt(123456, fake_queue, context_blocks=context_blocks)

    assert context_blocks, "上下文块不应为空"
    text = context_blocks[0]["content"]
    assert "测试群名" in text
    assert "我是,群名" not in text  # bot_name 不应被误清空


async def test_disabled_fragment_does_not_leak_placeholder(custom_store, bot_config, fake_profile, fake_queue):
    """[qq_chat] enabled=false 后 system 不应残留字面量 {qq_chat}。"""
    store = custom_store("[qq_chat]\nenabled = false\n")
    builder = PromptBuilder(bot_config, fake_profile, prompt_store=store)

    prompt = await builder.build_group_chat_prompt(123456, fake_queue)

    assert "{qq_chat}" not in prompt
    assert "{qq_chat_examples}" not in prompt


async def test_member_archive_hint_can_be_disabled(custom_store, bot_config, fake_profile, fake_queue):
    """[member_archive_hint] enabled=false 时不再注入「群友记忆未在此注入」提示。"""
    store = custom_store("[member_archive_hint]\nenabled = false\n")
    builder = PromptBuilder(bot_config, fake_profile, prompt_store=store)
    context_blocks: list[dict[str, str]] = []

    prompt = await builder.build_group_chat_prompt(123456, fake_queue, context_blocks=context_blocks)

    combined = prompt + "".join(block["content"] for block in context_blocks)
    assert "群友的长期记忆未在此注入" not in combined
