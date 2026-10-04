"""联网搜索配置接线的回归测试（fix(9) F5）。

背景：`[web_search]` 段此前是**死配置** —— bootstrap 两处调用点都硬编码
`web_search_config={}`，`engines` 等字段从未被消费。现在按配置构造字典，
并给 duckduckgo/浏览器通道补上实测默认预算。
"""

from __future__ import annotations

from types import SimpleNamespace

from neobot_app.bootstrap import _web_search_config_dict
from neobot_app.config.schemas.bot import WebSearchConfig


def test_defaults_are_passed_through() -> None:
    config = SimpleNamespace(web_search=WebSearchConfig())

    result = _web_search_config_dict(config)

    assert result["engines"] == ["bing", "duckduckgo"]
    assert result["browser_fallback"] is True
    assert result["browser_timeout_seconds"] == 8.0
    assert result["max_rounds"] == 5
    assert result["preview_pages_limit"] == 30
    assert result["variant_result_limit"] == 6
    assert "engine_budgets" not in result  # 未显式配置时不写死，交由 SearchSession 兜底


def test_custom_engines_and_budgets_are_honoured() -> None:
    config = SimpleNamespace(
        web_search=WebSearchConfig(
            engines=["duckduckgo"],
            browser_fallback=False,
            browser_timeout_seconds=12.0,
            engine_timeout_seconds={"duckduckgo": 20, "bing": 10},
        )
    )

    result = _web_search_config_dict(config)

    assert result["engines"] == ["duckduckgo"]
    assert result["browser_fallback"] is False
    assert result["browser_timeout_seconds"] == 12.0
    assert result["engine_budgets"] == {"duckduckgo": 20.0, "bing": 10.0}


def test_missing_section_returns_empty_dict() -> None:
    """没有 web_search 段（老配置/测试替身）时保持旧行为：返回空 dict。"""
    assert _web_search_config_dict(SimpleNamespace()) == {}


def test_schema_defaults_are_typed() -> None:
    section = WebSearchConfig()
    # 默认搜索源**写死在 schema 里**，而不是留 None 靠 SearchManager 兜底：
    # 这样面板、配置参考与审计脚本看到的就是真实生效的值（两者语义本就相同）
    assert section.engines == ["bing", "duckduckgo"]
    assert section.browser_fallback is True
    assert section.browser_timeout_seconds == 8.0
    assert section.engine_timeout_seconds is None
