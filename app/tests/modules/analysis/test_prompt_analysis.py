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


class _FakeAgent:
    """符合规范的假 Agent：只实现 agent_prompt_parts() 与 agent_name。"""

    agent_name = "假 Agent"

    def agent_prompt_parts(self) -> list[tuple[str, str, str]]:
        return [("系统提示词", "system", "你好")]


class _FakeRegistry:
    def __init__(self, mapping: dict) -> None:
        self._mapping = mapping

    def describe(self) -> list[dict]:
        return [{"name": name} for name in self._mapping]

    def get(self, name: str):
        return self._mapping.get(name)


def test_catalog_registers_only_conforming_objects() -> None:
    from neobot_app.analysis.agent_spec import AgentCatalog

    catalog = AgentCatalog()

    assert catalog.register(_FakeAgent()) is True
    assert catalog.register(object()) is False, "未实现规范的对象应被忽略"
    assert [spec.name for spec in catalog.specs] == ["假 Agent"]


@pytest.mark.asyncio
async def test_analyzer_collects_catalog_agents_automatically() -> None:
    """新增 Agent 只需实现 agent_prompt_parts()，分析器自动收集，无需改分析代码。"""
    from neobot_app.analysis.agent_spec import AgentCatalog

    analyzer = PromptAnalyzer(catalog=AgentCatalog())
    analyzer.add_source("非 Agent 条目", lambda: [("模型路由", "instructions", "x")])
    analyzer.catalog.register(_FakeAgent())

    report = await analyzer.collect()

    names = [agent["name"] for agent in report["agents"]]
    assert names == ["非 Agent 条目", "假 Agent"], "catalog 条目自动追加在显式来源之后"
    assert report["agents"][1]["parts"][0]["text"] == "你好"


def test_catalog_discover_scans_host_services() -> None:
    """装配层把它注册成宿主服务，就会被自动发现（插件 Agent 同样适用）。"""
    from neobot_app.analysis.agent_spec import AgentCatalog

    catalog = AgentCatalog()
    registry = _FakeRegistry({"archive_memory_service": _FakeAgent(), "config": object()})

    assert catalog.discover(registry) == 1
    assert [spec.name for spec in catalog.specs] == ["假 Agent"]


def test_tools_to_text_is_json() -> None:
    text = tools_to_text([{"type": "function", "function": {"name": "demo"}}])

    assert '"demo"' in text and text.startswith("[")
