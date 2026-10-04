"""分句：中英之间的排版空格不该切成新消息。

现象：「这是一个 bot 框架;」被从「个|空格|bot」处切开，切成
「这是一个」+「bot 框架」两条发出 —— agent 习惯在英文词前后加空格，
这种空格只是排版，不是句子边界。

同时必须保住英文句子的切分能力：英文靠「句号/感叹号之后的那个空格」断句
（半角 . ! ? 本身不在分隔符集合里），所以不能把所有空格都设成不可切。
"""

from __future__ import annotations

import random

import pytest

from neobot_app.reply.postprocess import (
    process_reply_text,
    split_into_sentences_w_remove_punctuation,
)


def _split(text: str) -> list[str]:
    # 固定随机源：合并步骤是随机化的，断言必须可复现
    return split_into_sentences_w_remove_punctuation(text, rng=random.Random(0))


# ── 主症状：CJK 与英文之间的空格不该切句，也不该留在正文里 ──────────


@pytest.mark.parametrize(
    "text",
    [
        "这是一个 bot 框架;",
        "这是一个 bot 框架",
        "配置 data/config.toml 文件;",
    ],
)
def test_cjk_latin_space_does_not_split(text: str) -> None:
    """中文里夹一个英文词时，整句不能被空格切开。"""
    messages = _split(text)
    assert len(messages) == 1, f"不该切开：{messages}"
    # 切出一个两字以内的碎片就是症候（「这是一个」+「bot 框架」）
    assert not any(len(message) <= 2 for message in messages)


def test_cjk_latin_spaces_are_removed() -> None:
    """英文词两侧的排版空格去掉：「这是一个 bot 框架」->「这是一个bot框架」。"""
    assert _split("这是一个 bot 框架;") == ["这是一个bot框架"]
    assert _split("第 1 章 开始了") == ["第1章 开始了"]


# ── 不能误伤：英文词内部与 Markdown 记号后的空格必须保留 ────────────


def test_spaces_inside_latin_phrase_are_preserved() -> None:
    """pip install 是两个词，中间的空格两侧都不是 CJK，必须原样保留。"""
    assert _split("运行 pip install 命令") == ["运行pip install命令"]


@pytest.mark.parametrize("text", ["- 项目一", "# 标题 内容", "1. 第一条"])
def test_markdown_control_spacing_is_preserved(text: str) -> None:
    """Markdown 记号不是字母数字，记号后的空格必须保留，否则列表项/标题会被毁。"""
    assert _split(text) == [text]


def test_cjk_only_space_is_kept_and_not_split() -> None:
    """两个汉字之间的空格既不删也不切（删了会把两个词粘成一个）。"""
    assert _split("你好 世界") == ["你好 世界"]


# ── 英文切分能力不能被弄坏 ────────────────────────────────────────


def test_english_still_splits_after_sentence_punctuation() -> None:
    """英文靠「句号后那个空格」断句：半角句号不在分隔符集合里，切点只能是空格。"""
    assert _split("Hello. World. Bye.") == ["Hello.", "World.", "Bye."]


def test_chinese_punctuation_still_splits() -> None:
    assert _split("这是第一句。这是第二句。") == ["这是第一句", "这是第二句"]


# ── 端到端 ────────────────────────────────────────────────────────


def test_process_reply_text_sends_single_message_for_mixed_sentence() -> None:
    result = process_reply_text("这是一个 bot 框架;", bot_name="Neo", max_sentence_count=12)
    assert result.messages == ["这是一个bot框架"]
    assert result.fallback_used is False
