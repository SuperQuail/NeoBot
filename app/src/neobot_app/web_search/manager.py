"""SearchManager — 多引擎编排，支持限速与重试。"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Optional

from neobot_app.web_search.engine import BaseSearchEngine, get_engine
from neobot_app.web_search.models import SearchResponse


class SearchManager:
    """管理多个搜索引擎，支持限速、重试与故障回退。

    特性:
    - 多引擎搜索，按优先级排序
    - 每引擎独立限速（令牌桶）
    - 全局并发限制（信号量），避免触发反爬防御
    - 指数退避重试
    - 引擎失败时自动回退
    """

    _global_semaphore: asyncio.Semaphore | None = None

    @classmethod
    def set_global_concurrency(cls, max_concurrent: int) -> None:
        """限制所有 SearchManager 实例的总并发搜索请求数。"""
        cls._global_semaphore = asyncio.Semaphore(max_concurrent)

    def __init__(
        self,
        engines: Optional[list[str]] = None,
        min_delay: float = 1.0,
        max_retries: int = 3,
        default_num_results: int = 10,
    ) -> None:
        """
        Args:
            engines: 按顺序使用的引擎名称列表（第一个为主引擎）。
                     默认: ["bing", "duckduckgo"]
            min_delay: 同一引擎两次请求之间的最小间隔秒数。
            max_retries: 每个引擎的最大重试次数。
            default_num_results: 每次搜索的默认返回结果数。
        """
        if engines is None:
            engines = ["bing", "duckduckgo"]
        self._engine_names = engines
        self._min_delay = min_delay
        self._max_retries = max_retries
        self._default_num_results = default_num_results

        self._engines: dict[str, BaseSearchEngine] = {}
        self._last_request: dict[str, float] = defaultdict(float)

    async def _get_engine(self, name: str) -> BaseSearchEngine:
        if name not in self._engines:
            self._engines[name] = get_engine(name)
        return self._engines[name]

    async def _rate_limit(self, engine_name: str) -> None:
        """强制同一引擎两次请求之间保持最小间隔。"""
        elapsed = time.monotonic() - self._last_request[engine_name]
        if elapsed < self._min_delay:
            await asyncio.sleep(self._min_delay - elapsed)
        self._last_request[engine_name] = time.monotonic()

    async def search(
        self,
        query: str,
        num_results: Optional[int] = None,
        *,
        engine: Optional[str] = None,
    ) -> SearchResponse:
        """使用指定引擎或主引擎执行搜索。"""
        if num_results is None:
            num_results = self._default_num_results

        engine_name = engine or self._engine_names[0]
        eng = await self._get_engine(engine_name)

        sem = self._global_semaphore

        last_error: Optional[str] = None
        for attempt in range(self._max_retries + 1):
            try:
                await self._rate_limit(engine_name)
                if sem:
                    async with sem:
                        resp = await eng.search(query, num_results)
                else:
                    resp = await eng.search(query, num_results)
                if resp.success:
                    return resp
                last_error = resp.error
            except Exception as e:
                last_error = str(e)

            if attempt < self._max_retries:
                wait = 2**attempt  # exponential backoff: 1s, 2s, 4s
                await asyncio.sleep(wait)

        return SearchResponse(
            query=query,
            results=[],
            engine=engine_name,
            error=f"重试{self._max_retries}次后仍失败: {last_error}",
        )

    async def search_with_fallback(
        self,
        query: str,
        num_results: Optional[int] = None,
    ) -> SearchResponse:
        """依次搜索各引擎，失败时自动回退。"""
        if num_results is None:
            num_results = self._default_num_results

        errors: list[str] = []
        for name in self._engine_names:
            resp = await self.search(query, num_results, engine=name)
            if resp.success and resp.results:
                return resp
            if resp.error:
                errors.append(f"{name}: {resp.error}")

        return SearchResponse(
            query=query,
            results=[],
            engine="all",
            error="; ".join(errors) if errors else "所有引擎均无结果",
        )

    async def search_all(
        self,
        query: str,
        num_results: Optional[int] = None,
    ) -> list[SearchResponse]:
        """并发搜索所有引擎并返回全部响应。"""
        if num_results is None:
            num_results = self._default_num_results

        async def _search_one(name: str) -> SearchResponse:
            return await self.search(query, num_results, engine=name)

        return list(await asyncio.gather(*(_search_one(n) for n in self._engine_names)))

    @property
    def primary_engine(self) -> str:
        return self._engine_names[0]
