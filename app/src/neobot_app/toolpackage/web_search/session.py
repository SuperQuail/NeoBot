"""SearchSession — multi-turn retrieve-read workflow with diversity & dedup."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx

from neobot_app.toolpackage.web_search.manager import SearchManager
from neobot_app.toolpackage.web_search.models import SearchResponse, SearchResult


@dataclass
class SearchRound:
    """A single search round within a session."""

    round_num: int
    query: str
    response: SearchResponse
    read_indices: list[int] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SearchSession:
    """Manages a multi-round search-and-read conversation."""

    MAX_PAGE_SIZE = 500_000       # 500KB limit per page
    MAX_RESULTS_PER_SEARCH = 20   # cap results per search round

    RESEARCH_MODES: dict[str, list[str]] = {
        "encyclopedia": [
            "{topic} 百度百科",
            "{topic} 百科",
            "{topic} wiki",
        ],
        "community": [
            "{topic} 知乎",
            "{topic} 贴吧",
            "{topic} 论坛",
            "{topic} NGA",
        ],
        "news": [
            "{topic} 新闻",
            "{topic} 资讯",
            "{topic} 最新消息",
            "{topic} 情报",
        ],
        "official": [
            "{topic} 官网",
            "{topic} 官方网站",
        ],
        "video": [
            "{topic} bilibili",
            "{topic} 视频",
            "{topic} 评测",
        ],
        "academic": [
            "{topic} 论文",
            "{topic} 研究",
            "{topic} 文献",
        ],
        "raw": [],
    }

    _DEFAULT_MODES = ("encyclopedia", "community")

    def __init__(
        self,
        engines: Optional[list[str]] = None,
        max_rounds: int = 5,
        read_timeout: float = 30.0,
    ) -> None:
        self._manager = SearchManager(engines=engines)
        self._max_rounds = max_rounds
        self._read_timeout = read_timeout
        self._rounds: list[SearchRound] = []
        self._results_index: dict[int, SearchResult] = {}
        self._read_urls: set[str] = set()

    @property
    def rounds(self) -> list[SearchRound]:
        return list(self._rounds)

    @property
    def current_round(self) -> int:
        return len(self._rounds)

    @property
    def all_results(self) -> list[SearchResult]:
        """All search results across all rounds, indexed globally."""
        return sorted(self._results_index.values(), key=lambda r: r.index)

    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        """Execute a new search round."""
        resp = await self._execute_search(query, num_results)
        if resp.success:
            self._rounds.append(
                SearchRound(round_num=self.current_round + 1, query=query, response=resp)
            )
        return resp

    async def read(self, indices: list[int]) -> list[SearchResult]:
        """Fetch full page content for the given result indices."""
        results_to_fetch = []
        for idx in indices:
            r = self._results_index.get(idx)
            if r is None:
                continue
            if not r.content_fetched:
                results_to_fetch.append(r)

        if not results_to_fetch:
            return [self._results_index[idx] for idx in indices if idx in self._results_index]

        async with httpx.AsyncClient(timeout=self._read_timeout) as client:
            await self._fetch_all(client, results_to_fetch)

        for r in results_to_fetch:
            if r.content_fetched:
                self._read_urls.add(r.url)

        if self._rounds:
            self._rounds[-1].read_indices.extend(indices)

        return [self._results_index[idx] for idx in indices if idx in self._results_index]

    async def read_single(self, index: int) -> Optional[SearchResult]:
        """Read a single result by index."""
        results = await self.read([index])
        return results[0] if results else None

    def get_summary_for_agent(self) -> str:
        """Generate a summary of the session state for the agent."""
        lines = [f"===== 搜索会话 (共 {self.current_round} 轮) ====="]
        unread = [r for r in self._results_index.values() if not r.content_fetched]
        read_count = len(self._results_index) - len(unread)
        lines.append(f"结果: {len(self._results_index)} 条 (已读 {read_count}, 未读 {len(unread)})")
        lines.append("")

        for rd in self._rounds:
            lines.append(f"--- 第 {rd.round_num} 轮: '{rd.query}' ---")
            lines.append(f"引擎: {rd.response.engine}, 结果: {len(rd.response.results)} 条")
            for r in rd.response.results:
                status = "[R]" if r.content_fetched else "[ ]"
                lines.append(f"  [{r.index}] {status} {r.title}")
                lines.append(f"      {r.snippet[:100]}...")
            if rd.read_indices:
                lines.append(f"  已读取: {rd.read_indices}")
            lines.append("")
        return "\n".join(lines)

    async def research(
        self,
        topic: str,
        *,
        modes: list[str] | str | None = None,
        variants: list[str] | None = None,
        num_results: int = 10,
        variant_result_limit: int = 6,
        total_result_limit: int = 30,
    ) -> SearchResponse:
        """智能研究模式：从多个角度自动生成查询变体，合并去重，仅计 1 轮。

        Args:
            topic: 研究主题
            modes: 查询模式
            variants: 手动覆盖变体列表
            num_results: 主查询返回结果数
            variant_result_limit: 每个变体查询的最大返回结果数
            total_result_limit: 合并后总结果数上限
        """
        import asyncio

        if variants is None:
            mode_list: list[str] = []
            if modes is None:
                mode_list = list(self._DEFAULT_MODES)
            elif isinstance(modes, str):
                mode_list = [modes]
            else:
                mode_list = modes

            resolved: list[str] = []
            for m in mode_list:
                tmpls = self.RESEARCH_MODES.get(m)
                if tmpls is None:
                    continue
                for t in tmpls:
                    resolved.append(t.format(topic=topic))
            variants = resolved

        async def _query(q: str, n: int) -> SearchResponse:
            return await self._execute_search(q, n)

        # 每个变体使用统一的 variant_result_limit
        variant_n = max(1, min(variant_result_limit, num_results))
        primary_future = _query(topic, num_results)
        variant_futures = [_query(v, variant_n) for v in variants]

        primary = await primary_future
        variant_responses = await asyncio.gather(*variant_futures)

        if not primary.success:
            return primary

        seen_urls: set[str] = {r.url for r in primary.results} | self._read_urls

        for vp in variant_responses:
            if not vp.success:
                continue
            for r in vp.results:
                if r.url not in seen_urls:
                    seen_urls.add(r.url)
                    primary.results.append(r)

        primary.results = self._rerank_by_diversity(primary.results)
        self._reindex_results(primary.results)

        # 总结果数受 total_result_limit 限制
        cap = max(1, total_result_limit)
        if len(primary.results) > cap:
            primary.results = primary.results[:cap]

        primary.total_estimated = len(primary.results)
        primary.query = topic

        mode_labels = mode_list if variants is None else ["custom"]
        self._rounds.append(
            SearchRound(
                round_num=self.current_round + 1,
                query=f"{topic} [modes: {','.join(mode_labels)}, +{len(variants)} variants]",
                response=primary,
            )
        )
        return primary

    async def _execute_search(
        self, query: str, num_results: int
    ) -> SearchResponse:
        """Core search pipeline: fetch → dedup → diversity → index."""
        if self.current_round >= self._max_rounds:
            return SearchResponse(
                query=query,
                results=[],
                engine="session",
                error=f"已达到最大搜索轮次 ({self._max_rounds})",
            )

        fetch_count = min(num_results * 2, 30)
        resp = await self._manager.search_with_fallback(query, fetch_count)

        if not resp.success:
            return resp

        # Filter out already-read URLs
        unfiltered = len(resp.results)
        resp.results = [r for r in resp.results if r.url not in self._read_urls]
        filtered = unfiltered - len(resp.results)

        # Domain diversity reranking
        resp.results = self._rerank_by_diversity(resp.results)

        # Cap
        if len(resp.results) > self.MAX_RESULTS_PER_SEARCH:
            resp.results = resp.results[: self.MAX_RESULTS_PER_SEARCH]

        # Assign global indices
        self._reindex_results(resp.results)

        resp.total_estimated = len(resp.results)
        if filtered:
            resp.engine += f" (dedup: -{filtered})"
        return resp

    def _reindex_results(self, results: list[SearchResult]) -> None:
        start_idx = max(self._results_index.keys(), default=-1) + 1
        for i, r in enumerate(results):
            r.index = start_idx + i
            self._results_index[r.index] = r

    @staticmethod
    def _extract_domain(url: str) -> str:
        try:
            netloc = urlparse(url).netloc
            if netloc.startswith("www."):
                netloc = netloc[4:]
            return netloc
        except Exception:
            return url

    @staticmethod
    def _rerank_by_diversity(results: list[SearchResult]) -> list[SearchResult]:
        """Re-rank results to promote domain diversity via round-robin interleaving."""
        if len(results) <= 1:
            return list(results)

        domain_buckets: dict[str, list[SearchResult]] = defaultdict(list)
        domain_order: list[str] = []
        for r in results:
            domain = SearchSession._extract_domain(r.url)
            if domain not in domain_buckets:
                domain_order.append(domain)
            domain_buckets[domain].append(r)

        reranked: list[SearchResult] = []
        while len(reranked) < len(results):
            added = False
            for domain in domain_order:
                bucket = domain_buckets[domain]
                if bucket:
                    reranked.append(bucket.pop(0))
                    added = True
            if not added:
                break

        return reranked

    async def _fetch_all(
        self,
        client: httpx.AsyncClient,
        results: list[SearchResult],
    ) -> list[SearchResult]:
        import asyncio

        async def _fetch_one(r: SearchResult) -> SearchResult:
            try:
                resp = await client.get(r.url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; NeoBot/1.0)",
                    "Accept": "text/html,application/xhtml+xml",
                })
                resp.raise_for_status()
                r.content = resp.text[: SearchSession.MAX_PAGE_SIZE]
                r.content_fetched = True
            except Exception as e:
                r.content = f"[获取失败] {e}"
                r.content_fetched = False
            return r

        return list(await asyncio.gather(*(_fetch_one(r) for r in results)))
