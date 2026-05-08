"""Web search ToolPackage — wraps SearchSession as a lockable tool package."""

from __future__ import annotations

import json
from typing import Any

from neobot_app.toolpackage.manager import ToolDefinition, ToolPackage
from neobot_app.toolpackage.web_search import SearchResult, SearchSession


def _build_search_tool() -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": "search",
            "description": (
                "执行联网搜索，返回带编号的搜索结果列表。"
                "强烈建议使用 mode 参数进行多角度研究搜索，一次搜索会从多个变体查询并合并结果，"
                "比多次普通关键词搜索高效得多。"
                "可用 mode：encyclopedia（百科/百度百科/wiki）、community（知乎/贴吧/论坛/NGA）、"
                "news（新闻/资讯）、official（官网）、video（bilibili/评测）、academic（论文/研究）。"
                "不填 mode 则仅做普通关键词搜索，适合简单快速查询。"
                "如需查百科资料，使用 mode='encyclopedia' 比搜索 'xxx 百度百科' 效果好得多。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或研究主题",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "单次搜索返回的结果数量，默认 10",
                    },
                    "mode": {
                        "type": "string",
                        "description": (
                            "研究模式（强烈推荐用于资料收集）：encyclopedia（百科类，查百度百科/wiki等）、"
                            "community（社区类，查知乎/贴吧/论坛/NGA）、"
                            "news（新闻类）、official（官方类，查官网）、"
                            "video（视频类）、academic（学术类）。"
                            "不填则仅做普通关键词搜索，易返回低相关度结果"
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    }


def _build_read_tool() -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": "read",
            "description": (
                "读取指定编号的搜索结果页面完整内容，返回页面正文。"
                "已读过的页面会在后续搜索中自动过滤去重。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "indices": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "要读取的结果编号列表，如 [0, 1, 3]",
                    },
                },
                "required": ["indices"],
            },
        },
    }


def _build_status_tool() -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": "status",
            "description": "查看当前搜索会话状态，包括已完成轮次、已读/未读结果统计",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    }


class WebSearchExecutor:
    """Executes web search tools within a SearchSession."""

    def __init__(
        self,
        engines: list[str] | None = None,
        max_rounds: int = 5,
        preview_pages_limit: int = 30,
        variant_result_limit: int = 6,
    ) -> None:
        self._engines = engines or ["bing", "duckduckgo"]
        self._max_rounds = max_rounds
        self._preview_pages_limit = preview_pages_limit
        self._variant_result_limit = variant_result_limit
        self._session: SearchSession | None = None

    def _get_session(self) -> SearchSession:
        if self._session is None:
            self._session = SearchSession(
                engines=self._engines,
                max_rounds=self._max_rounds,
            )
        return self._session

    def reset(self) -> None:
        """Reset the search session for a new conversation turn."""
        self._session = None

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "search":
            return await self._handle_search(args)
        if tool_name == "read":
            return await self._handle_read(args)
        if tool_name == "status":
            return await self._handle_status(args)
        return f"未知工具: {tool_name}"

    async def _handle_search(self, args: dict[str, Any]) -> str:
        session = self._get_session()
        query = str(args.get("query", "")).strip()
        if not query:
            return "[错误] 搜索关键词不能为空"

        num_results = int(args.get("num_results", 10))
        num_results = max(1, min(num_results, self._preview_pages_limit))
        mode = args.get("mode")

        if mode and mode != "raw":
            try:
                resp = await session.research(
                    query,
                    modes=mode,
                    num_results=num_results,
                    variant_result_limit=self._variant_result_limit,
                    total_result_limit=self._preview_pages_limit,
                )
            except Exception as e:
                return f"[错误] 研究搜索失败: {e}"
        else:
            resp = await session.search(query, num_results=num_results)

        if not resp.success:
            return f"[搜索失败] {resp.error}"

        return resp.summary()

    async def _handle_read(self, args: dict[str, Any]) -> str:
        session = self._get_session()
        raw_indices = args.get("indices", [])
        try:
            indices = [int(i) for i in raw_indices]
        except (TypeError, ValueError):
            return "[错误] indices 必须是整数数组"

        if not indices:
            return "[错误] 请指定要读取的结果编号"

        results = await session.read(indices)
        if not results:
            return "未找到指定编号的结果"

        # Format read results for agent consumption
        from neobot_app.toolpackage.web_parser import ContentExtractor, format_pages_for_agent

        extractor = ContentExtractor()
        parsed_pages = []
        for r in results:
            if r.content_fetched and r.content:
                parsed = extractor.extract(r.content, r.url)
                parsed_pages.append(parsed)
            else:
                # Create a minimal ParsedPage for failed fetches
                from neobot_app.toolpackage.web_parser.models import ParsedPage
                parsed_pages.append(
                    ParsedPage(
                        url=r.url,
                        error=r.content if r.content else "获取失败",
                    )
                )

        formatted = format_pages_for_agent(parsed_pages, compact=True)
        lines = [f"已读取 {len(results)} 个页面:\n", formatted]
        return "\n".join(lines)

    async def _handle_status(self, args: dict[str, Any]) -> str:
        session = self._get_session()
        return session.get_summary_for_agent()


def build_web_search_package(
    *,
    enabled: bool = True,
    engines: list[str] | None = None,
    max_rounds: int = 5,
    preview_pages_limit: int = 30,
    variant_result_limit: int = 6,
) -> ToolPackage | None:
    """构建联网搜索工具包。

    Args:
        enabled: 是否启用该工具包。为 False 时返回 None，不会注册。
        engines: 搜索引擎列表，默认 ["bing", "duckduckgo"]
        max_rounds: 最大搜索轮次，默认 5
        preview_pages_limit: 单次搜索返回结果总数上限，默认 30
        variant_result_limit: 研究模式每个变体查询的最大返回结果数，默认 6

    Returns:
        ToolPackage 实例，或 None（当 enabled=False）
    """
    if not enabled:
        return None

    executor = WebSearchExecutor(
        engines=engines,
        max_rounds=max_rounds,
        preview_pages_limit=preview_pages_limit,
        variant_result_limit=variant_result_limit,
    )

    tools = [
        _build_search_tool(),
        _build_read_tool(),
        _build_status_tool(),
    ]

    return ToolPackage(
        id="web_search",
        name="联网搜索工具包",
        short_description=(
            f"多引擎搜索（Bing/DuckDuckGo）+ 网页读取，最多{max_rounds}轮，"
            f"支持百科/社区/新闻/官方/视频/学术多模式研究"
        ),
        description=(
            f"联网搜索与网页读取。支持多搜索引擎（Bing、DuckDuckGo）、"
            f"多模式研究搜索（百科/社区/新闻/官方/视频/学术）、"
            f"最多 {max_rounds} 轮搜索、单次预览上限 {preview_pages_limit} 页。"
        ),
        tools=tools,
        executor=executor.execute,
        reset_handler=executor.reset,
        locked=True,
    )
