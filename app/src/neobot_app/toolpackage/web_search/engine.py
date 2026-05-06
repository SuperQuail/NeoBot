"""Search engine implementations.

Supported engines (prioritizing China-direct-connect):
- Bing: web scraping, no API key needed
- DuckDuckGo: via duckduckgo_search library
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from neobot_app.toolpackage.web_search.models import SearchResponse, SearchResult


class BaseSearchEngine(ABC):
    """Abstract base for search engines."""

    name: str

    @abstractmethod
    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        """Execute a search and return structured results."""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.name})>"


class BingSearchEngine(BaseSearchEngine):
    """Bing search via HTML scraping. No API key required."""

    name = "bing"
    base_url = "https://www.bing.com/search"

    def __init__(self, timeout: float = 15.0) -> None:
        self.timeout = timeout

    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(
                    self.base_url,
                    params={"q": query, "count": min(num_results, 50)},
                    headers=self._headers(),
                )
                resp.raise_for_status()
                results = self._parse(resp.text, num_results)
                for i, r in enumerate(results):
                    r.index = i

            return SearchResponse(
                query=query,
                results=results,
                engine=self.name,
                total_estimated=len(results),
                search_time_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:
            return SearchResponse(
                query=query,
                results=[],
                engine=self.name,
                error=str(e),
                search_time_ms=(time.perf_counter() - t0) * 1000,
            )

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    def _parse(self, html: str, limit: int) -> list[SearchResult]:
        soup = BeautifulSoup(html, "lxml")
        results: list[SearchResult] = []

        for li in soup.select("li.b_algo"):
            if len(results) >= limit:
                break
            title_el = li.select_one("h2 a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            url = title_el.get("href", "")
            snippet_el = li.select_one(".b_caption p, .b_lineclamp2")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            results.append(
                SearchResult(index=0, title=title, url=url, snippet=snippet, engine=self.name)
            )

        return results


class DuckDuckGoSearchEngine(BaseSearchEngine):
    """DuckDuckGo search via duckduckgo_search library."""

    name = "duckduckgo"

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        t0 = time.perf_counter()
        try:
            from duckduckgo_search import DDGS

            loop = __import__("asyncio").get_event_loop()
            results_raw = await loop.run_in_executor(
                None, lambda: list(DDGS().text(query, max_results=num_results))
            )

            results = [
                SearchResult(
                    index=i,
                    title=r["title"],
                    url=r["href"],
                    snippet=r["body"],
                    engine=self.name,
                )
                for i, r in enumerate(results_raw)
                if r.get("href")
            ]

            return SearchResponse(
                query=query,
                results=results,
                engine=self.name,
                total_estimated=len(results),
                search_time_ms=(time.perf_counter() - t0) * 1000,
            )
        except ImportError:
            return SearchResponse(
                query=query,
                results=[],
                engine=self.name,
                error="duckduckgo_search 未安装，请执行: pip install duckduckgo_search",
                search_time_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:
            return SearchResponse(
                query=query,
                results=[],
                engine=self.name,
                error=str(e),
                search_time_ms=(time.perf_counter() - t0) * 1000,
            )


ENGINE_REGISTRY: dict[str, type[BaseSearchEngine]] = {
    "bing": BingSearchEngine,
    "duckduckgo": DuckDuckGoSearchEngine,
}


def get_engine(name: str, **kwargs) -> BaseSearchEngine:
    """Create an engine instance by name."""
    cls = ENGINE_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"未知搜索引擎: {name}，可用: {list(ENGINE_REGISTRY)}")
    return cls(**kwargs)
