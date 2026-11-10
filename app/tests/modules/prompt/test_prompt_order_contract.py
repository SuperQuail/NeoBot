"""提示词阶段顺序契约：system 内部顺序、上下文在 system 之后、运行时注入顺序。"""

from __future__ import annotations

import pytest

from neobot_app.prompt.blocks import Stage, block_by_id, blocks_for
from neobot_app.prompt.builder import PromptBuilder
from neobot_app.prompt.composer import PromptComposer, RuntimeState, make_context
from neobot_app.prompt.context import Scope

#: 让 GROUP 的全部 SYSTEM_APPEND 块都能渲染的最小动态内容。
_APPEND_DYNAMIC = {
    "adaptive_text": "<自适应提示词>测试内容</自适应提示词>",
    "at_mention": True,
    "skill_instructions": "Skill 操作说明",
    "tool_package_index": "可加载工具包清单",
    "available_skills": "本轮命中的技能",
    "allowed_tools": "技能 allowed-tools 限制",
}
_APPEND_FEATURES = {"agent_mode": True, "native_vision": True, "official_platform": True}


def _group_ctx(store, config, **kwargs):
    return make_context(config=config, store=store, scope=Scope.GROUP, **kwargs)


# ── system：cot 前缀 → 主模板 → 末尾追加 ────────────────────────────────────


def test_system_order_prefix_then_main_then_append(prompt_store, bot_config):
    composer = PromptComposer(prompt_store)
    ctx = _group_ctx(
        prompt_store,
        bot_config,
        values={"numbering_guide": "编号说明"},
        dynamic=dict(_APPEND_DYNAMIC),
        features=dict(_APPEND_FEATURES),
    )
    system = composer.build_system(ctx)

    prefix_ids = tuple(block.id for block in blocks_for(Stage.SYSTEM_PREFIX, Scope.GROUP))
    append_ids = tuple(block.id for block in blocks_for(Stage.SYSTEM_APPEND, Scope.GROUP))
    # 构建元信息即顺序契约：cot 前缀 → 主模板 → 按 order 的追加
    assert system.rendered == (*prefix_ids, "group_chat", *append_ids)

    assert system.text.startswith("<cot>")
    prefix_parts = [composer.render_block(block_by_id(block_id), ctx) for block_id in prefix_ids]
    assert all(prefix_parts), "默认配置下 cot 子块都应有内容"
    prefix_positions = [system.text.index(part) for part in prefix_parts]
    assert prefix_positions == sorted(prefix_positions)
    assert system.text.index("</cot>") < system.text.index("<你是谁>")

    parts = {block_id: composer.render_block(block_by_id(block_id), ctx) for block_id in append_ids}
    assert all(parts.values()), "本用例的上下文应让全部追加块都有内容"
    positions = [system.text.index(parts[block_id]) for block_id in append_ids]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)
    assert max(prefix_positions) < positions[0]
    assert system.text.index("<你是谁>") < system.text.index("</你是谁>") < positions[0]


async def test_context_user_blocks_come_after_system_prompt(prompt_store, bot_config, fake_profile, fake_queue):
    """builder 只返回 system 文本；每轮上下文作为 user 消息单独交给调用方追加在后面。"""
    builder = PromptBuilder(bot_config, fake_profile, prompt_store=prompt_store)
    context_blocks: list[dict[str, str]] = []

    prompt = await builder.build_group_chat_prompt(123456, fake_queue, context_blocks=context_blocks)

    assert prompt.strip()
    assert "成员列表：小明、小红" not in prompt  # 默认 [group_chat] 不消费 member_list
    assert len(context_blocks) == 1
    assert context_blocks[0]["role"] == "user"
    assert "成员列表：小明、小红" in context_blocks[0]["content"]


# ── 运行时注入：RUNTIME_DATA → REMINDER → TIME，且 time 块必须最后一条 ────────


def test_inject_orders_runtime_then_reminder_then_terminal_time(prompt_store, bot_config):
    composer = PromptComposer(prompt_store)
    ctx = _group_ctx(
        prompt_store,
        bot_config,
        dynamic={
            "background_notification_text": "【后台通知】任务完成",
            "silent_nudge": True,
            "time_variant": "full",
        },
    )
    messages = [{"role": "user", "content": "历史消息"}]

    result = composer.inject(messages, ctx, RuntimeState())

    texts = [message["content"] for message in result]
    runtime_text = composer.render_block(block_by_id("background_notification"), ctx)
    avoid_repeat_text = composer.render_block(block_by_id("avoid_repeat"), ctx)
    nudge_text = composer.render_block(block_by_id("silent_nudge"), ctx)
    time_text = composer.render_block(block_by_id("current_time"), ctx)
    assert texts[0] == "历史消息"
    assert texts.index(runtime_text) < texts.index(avoid_repeat_text) < texts.index(nudge_text) < texts.index(time_text)
    assert texts[-1] == time_text  # terminal 块必须是消息列表最后一条


@pytest.mark.parametrize(
    ("variant", "block_id"),
    [("full", "current_time"), ("short", "current_time_short")],
)
def test_time_variant_selects_exactly_one_terminal_block(prompt_store, bot_config, variant: str, block_id: str):
    composer = PromptComposer(prompt_store)
    ctx = _group_ctx(prompt_store, bot_config, dynamic={"time_variant": variant})

    texts = [message["content"] for message in composer.inject([], ctx, RuntimeState())]

    expected = composer.render_block(block_by_id(block_id), ctx)
    avoid_repeat_text = composer.render_block(block_by_id("avoid_repeat"), ctx)
    assert texts == [avoid_repeat_text, expected]  # 只追加命中的时间变体，且位于末尾
    other_block_id = "current_time_short" if block_id == "current_time" else "current_time"
    assert composer.render_block(block_by_id(other_block_id), ctx) not in texts
    assert block_by_id(block_id).terminal is True


def test_once_per_activation_block_is_emitted_only_once(prompt_store, bot_config):
    composer = PromptComposer(prompt_store)
    ctx = _group_ctx(prompt_store, bot_config, dynamic={"time_variant": "full"})
    state = RuntimeState()
    avoid_repeat_text = composer.render_block(block_by_id("avoid_repeat"), ctx)
    time_text = composer.render_block(block_by_id("current_time"), ctx)

    first = [message["content"] for message in composer.inject([], ctx, state)]
    assert "avoid_repeat" in state.activation_emitted
    assert first[0] == avoid_repeat_text
    assert first[-1] == time_text

    second = [message["content"] for message in composer.inject([], ctx, state)]
    assert avoid_repeat_text not in second  # 本次激活已发过
    assert time_text in second  # 非 once_per_activation 的块每次调用仍追加
