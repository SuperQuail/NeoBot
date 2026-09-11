"""提示词分析：token 估算口径与收集框架。"""

from __future__ import annotations

import pytest

from neobot_app.analysis.prompt_analysis import (
    PromptAnalyzer,
    PromptPart,
    estimate_tokens,
    tools_to_text,
)


def test_estimate_tokens_rule() -> None:
    assert estimate_tokens("") == 0.0
    # 10 个中文字符 × 0.6
    cjk = "这是一段中文提示词内容字符"
    assert estimate_tokens(cjk) == round(len(cjk) * 0.6, 1)
    # 10 个英文字符 × 0.3
    assert estimate_tokens("abcdefghij") == 3.0
    # 混合：4 中文 + 4 英文
    assert estimate_tokens("中文测试abcd") == round(4 * 0.6 + 4 * 0.3, 1)


def test_prompt_part_stats_and_truncation() -> None:
    part = PromptPart(label="系统提示词", kind="system", text="中文abc")

    assert part.chars == 5
    assert part.tokens == round(2 * 0.6 + 3 * 0.3, 1)

    payload = part.to_dict(text_limit=3)
    assert payload["truncated"] is True
    assert payload["text"] == "中文a"
    assert payload["chars"] == 5, "截断只影响展示文本，统计仍按全文"


@pytest.mark.asyncio
async def test_collect_reports_parts_and_totals() -> None:
    analyzer = PromptAnalyzer()
    analyzer.add_source(
        "主 Agent",
        lambda: [("系统提示词", "system", "你好"), ("工具定义", "tools", "abcd")],
        note="空聊天",
    )

    report = await analyzer.collect()

    assert report["available"] is True
    assert "估算口径" in report["rule"]
    agent = report["agents"][0]
    assert agent["name"] == "主 Agent" and agent["note"] == "空聊天"
    assert [part["kind"] for part in agent["parts"]] == ["system", "tools"]
    assert agent["total_chars"] == 6
    assert agent["total_tokens"] == round(2 * 0.6 + 4 * 0.3, 1)


@pytest.mark.asyncio
async def test_collect_isolates_failures_and_supports_async() -> None:
    analyzer = PromptAnalyzer()

    def boom():
        raise RuntimeError("装配失败")

    async def ok():
        return [PromptPart(label="系统提示词", kind="system", text="ok")]

    analyzer.add_source("坏的", boom)
    analyzer.add_source("好的", ok)

    report = await analyzer.collect()

    assert report["agents"][0]["error"].startswith("RuntimeError:")
    assert report["agents"][1]["parts"][0]["text"] == "ok"


@pytest.mark.asyncio
async def test_add_source_is_idempotent() -> None:
    analyzer = PromptAnalyzer()
    analyzer.add_source("A", lambda: [])
    analyzer.add_source("A", lambda: [("x", "system", "y")])

    assert len(analyzer.sources) == 1
    report = await analyzer.collect()
    assert report["agents"][0]["parts"][0]["text"] == "y"


def test_tools_to_text_is_json() -> None:
    text = tools_to_text([{"type": "function", "function": {"name": "demo"}}])

    assert '"demo"' in text and text.startswith("[")
