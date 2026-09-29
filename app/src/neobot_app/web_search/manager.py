"""SearchManager — 多引擎编排，支持限速与重试。"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Optional

from neobot_app.web_search.engine import BaseSearchEngine, get_engine
from neobot_app.web_search.models import SearchResponse

logger = logging.getLogger(__name__)


class SearchManager:
    """管理多个搜索引擎，支持限速、重试与故障回退。

    特性:
    - 多引擎搜索，按优先级排序
    - 每引擎独立限速（min_delay，per-engine asyncio.Lock 保证并发下真实生效）
    - 全局并发限制（信号量），避免触发反爬防御
    - 指数退避重试
    - 引擎失败时自动回退（含"有结果但判失败"的降级响应）
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
        max_retries: int = 1,
        default_num_results: int = 10,
    ) -> None:
        """
        Args:
            engines: 按顺序使用的引擎名称列表（第一个为主引擎）。
                     默认: ["bing", "duckduckgo"]
            min_delay: 同一引擎两次请求之间的最小间隔秒数。
            max_retries: 同一引擎的最大重试次数。默认 1（不是 3）：实测 7 条错配
                查询各重试 3 次**自愈 0/21**，重试只会浪费时间并加剧风控；
                主力必须放在"换通道/换引擎"（见 fix(9) 的 D2/D3）。
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
        #: per-engine 互斥锁：把「检查间隔 + 等待 + 打点」变成原子操作，
        #: 否则并发调用会同时通过检查，min_delay 形同虚设。
        self._locks: dict[str, asyncio.Lock] = {}

    async def _get_engine(self, name: str) -> BaseSearchEngine:
        if name not in self._engines:
            self._engines[name] = get_engine(name)
        return self._engines[name]

    def _lock_for(self, engine_name: str) -> asyncio.Lock:
        lock = self._locks.get(engine_name)
        if lock is None:
            lock = self._locks[engine_name] = asyncio.Lock()
        return lock

    async def _rate_limit(self, engine_name: str) -> None:
        """强制同一引擎两次请求之间保持最小间隔（并发安全）。"""
        async with self._lock_for(engine_name):
            elapsed = time.monotonic() - self._last_request[engine_name]
            if elapsed < self._min_delay:
                await asyncio.sleep(self._min_delay - elapsed)
            self._last_request[engine_name] = time.monotonic()

    async def aclose(self) -> None:
        """关闭所有引擎持有的长连接资源。"""
        engines, self._engines = self._engines, {}
        for engine in engines.values():
            closer = getattr(engine, "aclose", None)
            if closer is None:
                continue
            try:
                await closer()
            except Exception:  # pragma: no cover - 关闭失败只记日志
                logger.debug("关闭搜索引擎 %r 失败", engine, exc_info=True)

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
        attempts = 0
        degraded = False
        for attempt in range(self._max_retries + 1):
            try:
                await self._rate_limit(engine_name)
                if sem:
                    async with sem:
                        resp = await eng.search(query, num_results)
                else:
                    resp = await eng.search(query, num_results)
                attempts += max(1, int(getattr(resp, "attempts", 1) or 1))
                if resp.success:
                    resp.attempts = attempts
                    resp.degraded = degraded or resp.degraded
                    return resp
                # 严格语义：有结果但判失败(error 非空) 也会走到这里 → 必须回退/重试，
                # 不能因为 results 非空就当成功（fix(9) 回退条件修正）。
                last_error = resp.error or "引擎返回空结果"
                degraded = degraded or resp.degraded
            except Exception as e:
                attempts += 1
                last_error = f"{type(e).__name__}: {e}"

            if attempt < self._max_retries:
                wait = 2**attempt  # exponential backoff: 1s, 2s, 4s
                await asyncio.sleep(wait)

        return SearchResponse(
            query=query,
            results=[],
            engine=engine_name,
            error=f"重试{self._max_retries}次后仍失败: {last_error}",
            degraded=True,
            attempts=max(1, attempts),
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
        attempts = 0
        degraded = False
        for name in self._engine_names:
            resp = await self.search(query, num_results, engine=name)
            attempts += max(1, int(getattr(resp, "attempts", 1) or 1))
            if resp.success:
                resp.attempts = attempts
                resp.degraded = degraded or resp.degraded
                return resp
            # 不再用 if resp.error 过滤：判失败的响应可能 results 非空而 error 恰好为空，
            # 旧实现会把这种引擎静默跳过，最后只报「所有引擎均无结果」。
            errors.append(f"{name}: {resp.error or '结果为空/未通过校验'}")
            degraded = True

        return SearchResponse(
            query=query,
            results=[],
            engine="all",
            error="; ".join(errors) if errors else "所有引擎均无结果",
            degraded=True,
            attempts=max(1, attempts),
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
