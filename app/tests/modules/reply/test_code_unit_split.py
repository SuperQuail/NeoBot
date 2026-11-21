"""分句：反引号包住的代码/命令要整段保住，空格不能被当断句点。

现象：`` `git rebase -i HEAD~2` `` 发出去变成两条 —— ``git rebase`` 和
``-i HEAD~2``，中间的空格被分句器当成句子边界吞掉了。于是约定：模型把代码
或命令用反引号包起来，发送前在分句阶段换成占位符（整段不可切），还原时再把
两侧的反引号去掉，只发字面内容。

范围：只处理行内的 `` `...` `` 片段；行首三反引号围栏仍交给 send_long_reply，
没成对/写坏的反引号会被清掉，不再作为裸记号发出去。引用型内容（`` `cancel` ``、
`` `*(note)*` ``）保留反引号，因为那是它们免于被当成控制词/注记清洗的保护壳。

同时必须保住普通文本的切分能力：这条规则只认反引号包住的部分，反引号外面
的空格、标点仍按原规则断句。
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


# ── 主症状：行内命令不能被空格拆开，反引号也不该发出去 ──────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("`git rebase -i HEAD~2`", ["git rebase -i HEAD~2"]),
        ("先跑 `git rebase -i HEAD~2`", ["先跑 git rebase -i HEAD~2"]),
        ("`pip install -r requirements.txt`", ["pip install -r requirements.txt"]),
        ("执行 `npm run build -- --watch` 再看", ["执行 npm run build -- --watch 再看"]),
    ],
)
def test_inline_code_keeps_spaces_and_drops_backticks(text: str, expected: list[str]) -> None:
    assert _split(text) == expected


def test_inline_code_does_not_swallow_neighbouring_prose() -> None:
    """反引号外面照旧按标点断句，命令本身不被切开。"""
    messages = _split("先跑 `git status`，再跑 `git log --oneline -5`。")

    assert messages == ["先跑 git status", "再跑 git log --oneline -5"]
    assert all("`" not in message for message in messages)


def test_multiple_code_units_in_one_message_are_all_restored() -> None:
    messages = _split("`cd /tmp` 然后 `ls -la`")

    assert messages == ["cd /tmp 然后 ls -la"]


def test_single_token_command_drops_backticks() -> None:
    """不带空格的命令也要去掉反引号，只是它本来就不需要占位符保护。"""
    assert _split("用 `ls` 看一下") == ["用 ls 看一下"]


@pytest.mark.parametrize("literal", ["`cancel`", "`*(note)*`"])
def test_reference_like_content_keeps_backticks(literal: str) -> None:
    """引用型内容靠反引号免于被当成指令/注记，去掉会被输出兜底整条丢掉。"""
    assert _split(literal) == [literal]


# ── 不能误伤：反引号之外的空格规则保持原样 ──────────────────────────


def test_plain_text_split_unchanged() -> None:
    """反引号之外走原逻辑：CJK 与英文之间的排版空格不切句、也不留在正文里。"""
    messages = _split("这是一个 bot 框架;")

    assert messages == ["这是一个bot框架"]


def test_process_reply_text_strips_backticks() -> None:
    result = process_reply_text(
        "先跑 `git fetch --all`。",
        bot_name="聆听",
        max_length=300,
        max_sentence_count=12,
    )

    assert result.fallback_used is False
    assert result.messages == ["先跑 git fetch --all"]
    assert "`" not in "".join(result.messages)


# ── 方括号 / 圆括号写法的命令：注记清洗会整段清空，不能据此判定注记 ──


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("跑 `[ -f config.toml ]` 判断", ["跑 [ -f config.toml ] 判断"]),
        ("然后 `(cd /tmp && make)` 编译", ["然后 (cd /tmp && make) 编译"]),
        ("`[ $# -gt 0 ]`", ["[ $# -gt 0 ]"]),
    ],
)
def test_bracketed_commands_lose_backticks_and_stay_whole(text: str, expected: list[str]) -> None:
    messages = _split(text)

    assert messages == expected
    assert all("`" not in message for message in messages)


def test_cjk_note_inside_backticks_keeps_its_shell() -> None:
    """判据收紧后，含 CJK 的真注记仍然保留反引号。"""
    assert _split("`（待确认）`") == ["`（待确认）`"]


# ── 正文自带的私有区字符不能和占位符撞号 ──────────────────────────


def test_body_private_use_chars_do_not_collide_with_placeholders() -> None:
    literal = "\ue0000\ue001"

    assert _split(f"原文含 {literal} 和 `ls -la`") == [f"原文含 {literal} 和 ls -la"]


# ── 没成对 / 写坏的围栏不能把裸反引号发给用户 ──────────────────────


@pytest.mark.parametrize("text", ["跑 `git status 看看", "先 `git\nstatus` 再", "版本 `` 标记"])
def test_unpaired_backticks_are_not_sent(text: str) -> None:
    messages = _split(text)

    assert messages
    assert all("`" not in message for message in messages)


def test_single_line_triple_backtick_fence_drops_markers() -> None:
    assert _split("```git status```") == ["git status"]


def test_block_fence_is_still_left_to_send_long_reply() -> None:
    """行首三反引号是真围栏，分句层不动它，原样交给 send_long_reply。"""
    assert _split("```text\ncancel\n```") == ["```text", "cancel", "```"]
