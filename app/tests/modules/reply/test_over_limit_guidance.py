"""回复超限被替换成默认回复时，给模型的处理指引。

背景：`long_reply_max_sentence_count` 只有个位数条时，稍长的回复会被整段替换成
默认回复文本；旧回执只说「请精简为更短的版本」，既没告诉模型可以**直发 Markdown**
（send_long_reply，不受上限约束），也没告诉它可以**分多次 send_reply 发送**。
"""

from __future__ import annotations

import pytest

from neobot_app.reply.postprocess import (
    build_over_limit_guidance,
    build_over_limit_reject_hint,
    process_reply_text,
)
from neobot_app.reply.tools import ReplyToolExecutor


def _long_text(sentences: int = 15) -> str:
    return "".join(f"第{i}句。" for i in range(1, sentences + 1))


# ── 判定口径 ─────────────────────────────────────────────────────


def test_too_many_sentences_uses_fallback_with_reason() -> None:
    result = process_reply_text(
        _long_text(15), bot_name="Bot", max_length=300, max_sentence_count=4
    )

    assert result.fallback_used is True
    assert "切分后消息数量过多" in (result.reason or "")


def test_over_length_uses_fallback_with_reason() -> None:
    result = process_reply_text(
        "啊" * 400, bot_name="Bot", max_length=300, max_sentence_count=12
    )

    assert result.fallback_used is True
    assert "回复过长" in (result.reason or "")


# ── 指引文案 ─────────────────────────────────────────────────────


def test_guidance_tells_agent_to_send_markdown_or_split() -> None:
    text = "\n".join(build_over_limit_guidance(max_length=300, max_sentence_count=4))

    # 出路一：直接发 Markdown（不受上限约束）
    assert "send_long_reply" in text
    assert "Markdown" in text
    assert "不受" in text
    # 出路二：拆成多次 send_reply，且带上真实上限
    assert "多次" in text and "send_reply" in text
    assert "300" in text and "4" in text


def test_module_defaults_match_config_schema() -> None:
    """模块默认值必须与配置 schema 一致，避免「代码里两套默认值」再次漂移。

    历史问题：postprocess 里是 200 / 8，而 schema（以及 tools 构造函数）是 300 / 12，
    调用方一旦省略参数就会拿到更激进的阈值。
    """
    from neobot_app.config.schemas.bot import Chat
    from neobot_app.reply import postprocess

    defaults = Chat()

    assert postprocess.DEFAULT_MAX_REPLY_LENGTH == defaults.long_reply_max_length
    assert postprocess.DEFAULT_MAX_SENTENCE_COUNT == defaults.long_reply_max_sentence_count


def test_reject_hint_is_single_line_and_actionable() -> None:
    hint = build_over_limit_reject_hint(max_length=300, max_sentence_count=4)

    assert "\n" not in hint
    assert "字符上限 300" in hint and "分句上限 4" in hint
    assert "send_long_reply" in hint
    assert "多次" in hint


# ── 工具层回执 ───────────────────────────────────────────────────


async def _noop_handler(**_kwargs) -> None:
    """占位发送处理器：这些用例只关心回执文案，不真正发送。"""


def _executor(**overrides) -> ReplyToolExecutor:
    overrides.setdefault("send_reply_handler", _noop_handler)
    return ReplyToolExecutor(**overrides)


@pytest.mark.asyncio
async def test_lightweight_check_receipt_guides_to_markdown_and_multi_send() -> None:
    """轻量检查触发时的回执必须给出两条出路（旧回执只让「精简」）。"""
    executor = _executor(
        ai_reply_check=False,
        ai_reply_check_lightweight=True,
        long_reply_max_length=300,
        long_reply_max_sentence_count=4,
    )

    receipt = await executor.execute("send_reply", {"text": _long_text(15)})

    assert "已触发默认回复替换" in receipt
    assert "send_long_reply" in receipt
    assert "分多次调用 send_reply" in receipt
    assert "不超过 300 字符" in receipt and "不超过 4 条" in receipt


@pytest.mark.asyncio
async def test_intercept_receipt_guides_to_markdown_and_multi_send() -> None:
    """未开检查、直接拦截时的回执同样要给出这两条出路。"""
    executor = _executor(
        ai_reply_check=False,
        ai_reply_check_lightweight=False,
        enable_ai_reply_regenerate=True,
        long_reply_max_length=300,
        long_reply_max_sentence_count=4,
    )

    receipt = await executor.execute("send_reply", {"text": _long_text(15)})

    assert receipt.startswith("回复被拦截")
    assert "send_long_reply" in receipt
    assert "多次" in receipt and "send_reply" in receipt


@pytest.mark.asyncio
async def test_normal_reply_is_not_touched_by_guidance() -> None:
    """短回复照常发送，回执里不应出现超限指引（防误伤）。"""
    sent: list[dict] = []

    async def handler(**kwargs):
        sent.append(kwargs)

    executor = _executor(
        send_reply_handler=handler,
        ai_reply_check_lightweight=True,
        long_reply_max_length=300,
        long_reply_max_sentence_count=4,
    )

    receipt = await executor.execute("send_reply", {"text": "好的。"})

    assert "send_long_reply" not in receipt
    assert len(sent) == 1
