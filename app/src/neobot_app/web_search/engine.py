"""搜索引擎实现。

支持的引擎（优先国内可直连）:
- Bing: 会话化 HTML 抓取（持久 client + Cookie + 预热 + 完整浏览器头），无需 API key
- DuckDuckGo: 通过 duckduckgo_search 库

fix(9) D1/D2/D3 要点:
1. 持久 httpx.AsyncClient：复用连接与 Cookie（首次使用前预热：首页 + 一次搜索），
   并带完整浏览器请求头；Accept-Encoding 固定为 gzip, deflate（禁 br —— 服务端按 br
   返回而本地缺 brotli 时会得到乱码或解码异常）。
2. 出口统一调用 urls.normalize_result_url：相对转绝对 → 解追踪壳 → 去跟踪参数；
   原始 href 记入 SearchResult.raw_url，展示 URL 里不应再出现 ck/a 壳。
3. 出口统一调用 validate.validate_results：校验判失败或 0 结果 → error 非空、
   degraded=True、results=[]（宁可判失败，也不把错结果交给模型）。
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx
from bs4 import BeautifulSoup

from neobot_app.web_search.models import SearchResponse, SearchResult
from neobot_app.web_search.urls import host_of, normalize_for_dedup, normalize_result_url
from neobot_app.web_search.validate import (
    FailureKind,
    classify_failure,
    validate_results,
)

logger = logging.getLogger(__name__)

BING_HOME = "https://www.bing.com/"

#: 完整浏览器头。Accept-Encoding 明确禁 br（见模块说明）。
BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

#: 预热查询：只为拿 Cookie / 会话状态，结果直接丢弃。
_WARMUP_QUERY = "neobot warmup"


class BaseSearchEngine(ABC):
    """搜索引擎的抽象基类。"""

    name: str

    @abstractmethod
    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        """执行搜索并返回结构化结果。"""
        ...

    async def aclose(self) -> None:
        """释放引擎持有的长连接资源（默认无资源可释放）。"""
        return None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self.name})>"


class BingSearchEngine(BaseSearchEngine):
    """通过会话化 HTML 抓取实现 Bing 搜索，无需 API key。"""

    name = "bing"
    base_url = "https://www.bing.com/search"

    def __init__(
        self,
        timeout: float = 15.0,
        *,
        market: str = "zh-CN",
        setlang: str = "zh-Hans",
        warmup: bool = True,
        coverage_threshold: float | None = None,
        structural_retry: bool = True,
        structural_retry_delay: float = 0.5,
    ) -> None:
        self.timeout = timeout
        self.market = market
        self.setlang = setlang
        self.warmup = warmup
        self.coverage_threshold = coverage_threshold
        #: 结构类失败（半包 HTML / 未解码压缩 / li.b_algo=0）才值得同通道重试一次；
        #: 内容类失败实测重试自愈 0/21，重试只会浪费时间并加深风控（fix(9) D2/D3）。
        self.structural_retry = bool(structural_retry)
        self.structural_retry_delay = max(0.0, float(structural_retry_delay))
        self._client: httpx.AsyncClient | None = None
        self._warmed = False

    # ── 资源生命周期 ──────────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        """返回持久会话 client（懒建 + 预热一次；连接与 Cookie 全程复用）。"""
        client = self._client
        if client is None or client.is_closed:
            client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers=dict(BROWSER_HEADERS),
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
            )
            self._client = client
            self._warmed = False
        if self.warmup and not self._warmed:
            # 只尝试一次：预热失败也不能挡住正式搜索。
            self._warmed = True
            await self._warm_up(client)
        return client

    async def aclose(self) -> None:
        """关闭持久会话，释放连接与 Cookie。"""
        client, self._client = self._client, None
        self._warmed = False
        if client is not None and not client.is_closed:
            try:
                await client.aclose()
            except Exception:  # pragma: no cover - 关闭失败只记日志
                logger.debug("关闭 Bing 会话失败", exc_info=True)

    async def __aenter__(self) -> "BingSearchEngine":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def _warm_up(self, client: httpx.AsyncClient) -> None:
        """首页 + 一次搜索，拿 Cookie 并让服务端把会话视为正常浏览器。"""
        for url, params in ((BING_HOME, None), (self.base_url, {"q": _WARMUP_QUERY})):
            try:
                resp = await client.get(url, params=params, headers=self._navigation_headers())
                logger.debug("Bing 预热 %s -> %s", url, resp.status_code)
            except Exception as exc:  # 预热失败不致命
                logger.debug("Bing 预热失败(忽略) %s: %s", url, exc)

    def _navigation_headers(self) -> dict[str, str]:
        headers = dict(BROWSER_HEADERS)
        headers["Referer"] = BING_HOME
        headers["Sec-Fetch-Site"] = "same-origin"
        return headers

    def _params(self, query: str) -> dict[str, str]:
        """标准 SERP 参数。不带 count：实测 count 会破坏翻页且仍只回 10 条（fix(9) D5）。"""
        params = {"q": query}
        if self.market:
            params["mkt"] = self.market
        if self.setlang:
            params["setlang"] = self.setlang
        return params

    # ── 搜索 ──────────────────────────────────────────────────────

    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        """会话化抓取 + 判据；**仅结构类失败**允许同通道重试一次。"""
        t0 = time.perf_counter()
        attempts = 0
        last: SearchResponse | None = None
        max_attempts = 2 if self.structural_retry else 1
        for index in range(max_attempts):
            attempts += 1
            last = await self._attempt(query, num_results, t0, attempts)
            if last.success:
                return last
            kind = (last.signals.get("failure") if isinstance(last.signals, dict) else None) or ""
            if index + 1 >= max_attempts or kind != FailureKind.STRUCTURE.value:
                break
            logger.debug(
                "Bing 结构类失败，同通道重试一次（attempt=%d）: %s", attempts, last.error
            )
            if self.structural_retry_delay:
                import asyncio

                await asyncio.sleep(self.structural_retry_delay)
        assert last is not None
        return last

    async def _attempt(
        self, query: str, num_results: int, t0: float, attempts: int
    ) -> SearchResponse:
        """单次抓取 + 判据（失败时带上分级结论，供上层决定换什么）。"""
        try:
            client = await self._get_client()
            resp = await client.get(
                self.base_url,
                params=self._params(query),
                headers=self._navigation_headers(),
            )
            resp.raise_for_status()
            html = resp.text or ""
            results = self._parse(html, num_results, base=str(resp.url))
            failure = classify_failure(
                query,
                results,
                html=html,
                channel="html",
                coverage_threshold=self.coverage_threshold,
            )
            if failure.kind is FailureKind.EMPTY:
                # 页面明说"没有结果"：不是故障，不要触发回退（fix(9) v2 §1）。
                return SearchResponse(
                    query=query,
                    results=[],
                    engine=self.name,
                    search_time_ms=(time.perf_counter() - t0) * 1000,
                    degraded=True,
                    attempts=attempts,
                    signals={
                        "validation": failure.signals,
                        "failure": failure.kind.value,
                        "empty": True,
                    },
                )
            if not failure.ok:
                return self._failure(
                    query,
                    f"结果校验失败({failure.reason})",
                    t0,
                    attempts,
                    failure.signals,
                    failure_kind=failure.kind,
                )
            return SearchResponse(
                query=query,
                results=results,
                engine=self.name,
                total_estimated=len(results),
                search_time_ms=(time.perf_counter() - t0) * 1000,
                attempts=attempts,
                signals={"validation": failure.signals},
            )
        except Exception as e:
            return self._failure(
                query,
                f"{type(e).__name__}: {e}",
                t0,
                attempts,
                None,
                failure_kind=FailureKind.NETWORK,
            )

    def _failure(
        self,
        query: str,
        error: str,
        t0: float,
        attempts: int,
        signals: dict[str, Any] | None,
        *,
        failure_kind: FailureKind | None = None,
    ) -> SearchResponse:
        """判失败一律不带结果：宁可丢，也不把错结果交给模型。"""
        payload: dict[str, Any] = {}
        if signals:
            payload["validation"] = signals
        if failure_kind is not None:
            payload["failure"] = failure_kind.value
        return SearchResponse(
            query=query,
            results=[],
            engine=self.name,
            error=error,
            search_time_ms=(time.perf_counter() - t0) * 1000,
            degraded=True,
            attempts=max(1, attempts),
            signals=payload,
        )

    def _parse(self, html: str, limit: int, base: str = "") -> list[SearchResult]:
        """解析 SERP，并在出口完成归一化 + 去重（按去重键）。"""
        soup = BeautifulSoup(html, "lxml")
        results: list[SearchResult] = []
        seen: set[str] = set()
        origin = base or self.base_url

        for li in soup.select("li.b_algo"):
            if len(results) >= limit:
                break
            title_el = li.select_one("h2 a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = str(title_el.get("href") or "")
            if not title or not href:
                continue
            display, raw_href = normalize_result_url(origin, href)
            if not display:
                continue
            key = normalize_for_dedup(display)
            if key and key in seen:
                continue
            if key:
                seen.add(key)

            snippet_el = li.select_one(".b_caption p, .b_lineclamp2, .b_algoSlug")
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            site_el = li.select_one("cite, .b_attribution cite")
            date_el = li.select_one(".news_dt, .b_algo .news_dt")
            results.append(
                SearchResult(
                    index=0,
                    title=title,
                    url=display,
                    snippet=snippet,
                    engine=self.name,
                    raw_url=raw_href,
                    channel="html",
                    site_name=(site_el.get_text(strip=True) if site_el else host_of(display)),
                    published_at=(date_el.get_text(strip=True) if date_el else None),
                )
            )

        return results


class DuckDuckGoSearchEngine(BaseSearchEngine):
    """通过 duckduckgo_search 库实现 DuckDuckGo 搜索。"""

    name = "duckduckgo"

    def __init__(self, timeout: float = 20.0, *, coverage_threshold: float | None = None) -> None:
        self.timeout = timeout
        self.coverage_threshold = coverage_threshold

    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        t0 = time.perf_counter()
        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS  # 旧版兼容

            loop = __import__("asyncio").get_event_loop()
            results_raw = await loop.run_in_executor(
                None, lambda: list(DDGS().text(query, max_results=num_results))
            )

            results: list[SearchResult] = []
            seen: set[str] = set()
            for row in results_raw:
                href = str(row.get("href") or "")
                if not href:
                    continue
                display, raw_href = normalize_result_url("https://duckduckgo.com/", href)
                if not display:
                    continue
                key = normalize_for_dedup(display)
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                results.append(
                    SearchResult(
                        index=len(results),
                        title=str(row.get("title") or ""),
                        url=display,
                        snippet=str(row.get("body") or ""),
                        engine=self.name,
                        raw_url=raw_href,
                        channel="api",
                        site_name=host_of(display),
                    )
                )

            # 出口统一校验：DDG 没有 HTML，只做 C1(可解 URL 比例)/C3(相关性)/0 结果。
            report = validate_results(
                query,
                results,
                html=None,
                channel="api",
                coverage_threshold=self.coverage_threshold,
            )
            if not report.valid:
                return SearchResponse(
                    query=query,
                    results=[],
                    engine=self.name,
                    error=f"结果校验失败({report.reason})",
                    search_time_ms=(time.perf_counter() - t0) * 1000,
                    degraded=True,
                    signals={"validation": report.signals},
                )
            return SearchResponse(
                query=query,
                results=results,
                engine=self.name,
                total_estimated=len(results),
                search_time_ms=(time.perf_counter() - t0) * 1000,
                signals={"validation": report.signals},
            )
        except ImportError:
            return SearchResponse(
                query=query,
                results=[],
                engine=self.name,
                error="duckduckgo_search 未安装，请执行: pip install duckduckgo_search",
                search_time_ms=(time.perf_counter() - t0) * 1000,
                degraded=True,
            )
        except Exception as e:
            return SearchResponse(
                query=query,
                results=[],
                engine=self.name,
                error=f"{type(e).__name__}: {e}",
                search_time_ms=(time.perf_counter() - t0) * 1000,
                degraded=True,
            )


ENGINE_REGISTRY: dict[str, type[BaseSearchEngine]] = {
    "bing": BingSearchEngine,
    "duckduckgo": DuckDuckGoSearchEngine,
}


def get_engine(name: str, **kwargs) -> BaseSearchEngine:
    """按名称创建引擎实例。"""
    cls = ENGINE_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"未知搜索引擎: {name}，可用: {list(ENGINE_REGISTRY)}")
    return cls(**kwargs)
