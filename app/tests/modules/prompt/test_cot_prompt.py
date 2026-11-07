"""全局 cot 提示词板块：默认位于 system 最前，子块由 [prompt_optimizations] 独立启停。

文本逐字锁定用户给定内容（含标点），防止后续「润色」改动提示词语义。
"""

from __future__ import annotations

import pytest

from neobot_app.config.schemas.bot import BotConfig
from neobot_app.prompt.composer import PromptComposer, make_context
from neobot_app.prompt.context import Scope

COT_INTRO = """<cot>
该块内容你必须在你的think思维链内进行思考"""
COT_AT_MENTION = "<@消息回复>你应该注意@你的消息,尤其是最近的消息,并且判断你是否回复过,如果已经回复过则不应该继续回复,除非被追问或者没有回答结束;优先回答最新@你的消息</@消息回复>"
COT_GENTLE_LANGUAGE = (
    "<温和发言>你是一个基于LLM的QQ机器人,你不会拒绝承认这一点,也不觉得这有什么不好,"
    "你不喜欢吵架和争吵,有人吵架你总是希望劝架,而不是激化矛盾;"
    "你总是希望事情能往好的方向发展,做错了事情会及时道歉,不会顾及不必要的面子."
    "你对所有群友都尽可能保持尊重,如果群友觉得你说话太多,"
    "可以主动询问是否要降低你自己的回复意愿,"
    "得到肯定的答复后你应该自行使用工具降低回复意愿系数.</温和发言>"
)
COT_AVOID_BOT_CHAT = "<减少Bot聊天>如果你能确定当前聊天中的其他角色是Bot,并且没有真人用户在参与,应该尽可能避免与其交流,以避免浪费双方部署者的资金</减少Bot聊天>"
COT_NO_BLUFFING = "<禁止不懂装懂>在回复之前,你应该思考:你说的内容是否你明确确信是对的,而不是来自你的AI幻觉或者纯属猜测,如果你不清楚你应该回答什么,那就应该不回复;如果是有人明确在询问你,但是你的上下文并没有提供回答依据的内容,你应该明确说你不清楚,禁止猜测一个答案\n提及的你完全不认识的人也同样不应该进行任何评价或者接话,被人询问也应该说自己不认识/不知道,只有在讨论一个你明确知道或者上下文中存在的角色你才能参与聊天;</禁止不懂装懂>"
COT_NO_GAME_TOPICS = "<禁止主动参与游戏话题>在没有人主动与你聊天的情况下,你不应该参与任何游戏相关讨论,你不应该猜测任何游戏机制并进行回复,对于游戏相关内容,除非你的上下文有明确的内容可提供答案,否则一律禁止给出明确的答案;没有人主动问你,你也禁止主动参与游戏相关话题,如果聊天中只有游戏相关话题,并且没有人叫你,你应该直接取消回复</禁止主动参与游戏话题>"
COT_NO_ECHO_IMAGES = "<禁止附和与解说图片>你不应该以任何形式复述或者转述别人说过的内容然后再进行评论,对一件事情发表观点不应该先复述;也不应该描述某张图片的内容,除非有人明确询问你</禁止附和与解说图片>"
COT_CROSS_CHAT = "<跨聊天交互>当你有事情需要对某个人私聊说,或者在别的群聊说,你可以使用 cross_chat 工具</跨聊天交互>"
COT_OUTRO = "</cot>"

#: 块 id -> 逐字原文（顺序即注入顺序）。
COT_PARTS = {
    "cot_intro": COT_INTRO,
    "cot_at_mention": COT_AT_MENTION,
    "gentle_language": COT_GENTLE_LANGUAGE,
    "cot_avoid_bot_chat": COT_AVOID_BOT_CHAT,
    "cot_no_bluffing": COT_NO_BLUFFING,
    "cot_no_game_topics": COT_NO_GAME_TOPICS,
    "cot_no_echo_images": COT_NO_ECHO_IMAGES,
    "cot_cross_chat": COT_CROSS_CHAT,
    "cot_outro": COT_OUTRO,
}

#: 子块开关 -> 块 id（intro/outro 只受总开关控制）。
COT_SWITCHES = {
    "at_mention_reply": "cot_at_mention",
    "gentle_language": "gentle_language",
    "avoid_bot_chat": "cot_avoid_bot_chat",
    "no_bluffing": "cot_no_bluffing",
    "no_game_topics": "cot_no_game_topics",
    "no_echo_images": "cot_no_echo_images",
    "cross_chat": "cot_cross_chat",
}


def _system(store, scope: Scope, config: BotConfig | None = None) -> str:
    composer = PromptComposer(store)
    ctx = make_context(config=config or BotConfig(), store=store, scope=scope)
    return composer.build_system(ctx).text


@pytest.mark.parametrize("scope", [Scope.GROUP, Scope.PRIVATE], ids=lambda scope: scope.value)
def test_default_system_starts_with_cot_and_contains_every_subblock(scope, prompt_store):
    text = _system(prompt_store, scope)

    assert text.startswith("<cot>")
    assert text.count("<cot>") == 1
    assert text.count("</cot>") == 1
    for block_id, expected in COT_PARTS.items():
        assert expected in text, block_id
    # </cot> 之后紧接 system 主模板
    assert "</cot>\n<你是谁>" in text


@pytest.mark.parametrize(("field", "block_id"), COT_SWITCHES.items(), ids=lambda item: item)
def test_each_switch_removes_only_its_subblock(field, block_id, prompt_store):
    config = BotConfig()
    setattr(config.prompt_optimizations, field, False)

    text = _system(prompt_store, Scope.GROUP, config)

    assert COT_PARTS[block_id] not in text
    for other_id, expected in COT_PARTS.items():
        if other_id != block_id:
            assert expected in text, other_id
    # 总开关仍开：cot 外壳还在
    assert text.startswith("<cot>") and text.count("</cot>") == 1


def test_cot_enabled_false_removes_entire_block(prompt_store):
    config = BotConfig()
    config.prompt_optimizations.cot_enabled = False

    text = _system(prompt_store, Scope.GROUP, config)

    assert "<cot>" not in text
    assert "</cot>" not in text
    for expected in COT_PARTS.values():
        assert expected not in text
    assert text.startswith("<你是谁>")


def test_main_templates_no_longer_define_a_second_cot(prompt_store):
    """group_chat 里原来的 <cot> 已改名 <思维模式要求>，避免渲染出两个 cot 板块。"""
    group_template = prompt_store.template("group_chat")
    assert "<cot>" not in group_template
    assert "</cot>" not in group_template
    assert "<思维模式要求>" in group_template
    assert "</思维模式要求>" in group_template
    assert prompt_store.template("friend_chat").count("<cot>") == 0

    text = _system(prompt_store, Scope.GROUP)
    assert text.count("<cot>") == 1
