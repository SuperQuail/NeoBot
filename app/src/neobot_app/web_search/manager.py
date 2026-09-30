"""SearchManager — 多引擎编排，支持限速与重试。"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any, Optional

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
        *,
        browser_fallback: bool = True,
        engine_budgets: Optional[dict[str, float]] = None,
        browser_channel: Any = None,
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
            browser_fallback: 两个 HTTP 引擎都失败时，是否再走浏览器脚本化通道
                （fix(9) 附录 B v2 §2：内容类失败是身份/缓存问题，换浏览器才有效）。
            engine_budgets: 每级的时间预算（秒）。默认 duckduckgo=15s（部署实测它慢，
                因此给固定上限而不是无限等）。
            browser_channel: 注入用（测试）；默认用进程级单例。
        """
        if engines is None:
            engines = ["bing", "duckduckgo"]
        names = [str(name) for name in engines]
        # DuckDuckGo 是"最后兜底"（fix(9) v2 §3）：它排在浏览器通道之后，
        # 而不是在主循环里先试一遍。即使调用方把它写在 engines 列表里，
        # 也统一挪到最后一级，避免"先付一次慢请求再走浏览器"。
        self._degraded_engines = [name for name in names if name == "duckduckgo"]
        self._engine_names = [name for name in names if name != "duckduckgo"] or list(names)
        self._min_delay = min_delay
        self._max_retries = max_retries
        self._default_num_results = default_num_results
        self._browser_fallback = bool(browser_fallback)
        self._engine_budgets = dict(engine_budgets or {})
        self._browser_channel = browser_channel

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
                if (getattr(resp, "signals", None) or {}).get("empty"):
                    # 页面明说"没有结果"：不是故障，直接交回上层，不要重试。
                    resp.attempts = attempts
                    resp.degraded = True
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
        stages: list[dict[str, Any]] = []

        async def _try(name: str, coro_factory: Any) -> SearchResponse | None:
            """跑一级：成功返回响应；空结果（页面明说没结果）直接收工；失败记 stages。"""
            nonlocal attempts, degraded
            budget = self._engine_budgets.get(name)
            started = time.monotonic()
            try:
                if budget is None:
                    resp = await coro_factory()
                else:
                    resp = await asyncio.wait_for(coro_factory(), timeout=budget)
            except asyncio.TimeoutError:
                degraded = True
                attempts += 1
                stages.append({"stage": name, "kind": "network", "reason": f"超过预算 {budget:g}s"})
                errors.append(f"{name}: 超过预算 {budget:g}s")
                return None
            attempts += max(1, int(getattr(resp, "attempts", 1) or 1))
            kind = (resp.signals or {}).get("failure")
            stages.append(
                {
                    "stage": name,
                    "kind": kind or ("ok" if resp.success else "unknown"),
                    "ms": round((time.monotonic() - started) * 1000),
                    "results": len(resp.results),
                }
            )
            if resp.success:
                resp.attempts = attempts
                resp.degraded = degraded or resp.degraded
                resp.signals = {**(resp.signals or {}), "stages": stages}
                return resp
            if (resp.signals or {}).get("empty"):
                # 页面明说"没有结果"：不是故障，继续回退只是浪费（v2 §1）。
                attempts_total = attempts
                return SearchResponse(
                    query=query,
                    results=[],
                    engine=resp.engine,
                    total_estimated=0,
                    error=None,
                    search_time_ms=sum(s.get("ms", 0) for s in stages),
                    degraded=True,
                    attempts=max(1, attempts_total),
                    signals={**(resp.signals or {}), "stages": stages, "empty": True},
                )
            errors.append(f"{name}: {resp.error or '结果为空/未通过校验'}")
            degraded = True
            return None

        for name in self._engine_names:
            done = await _try(name, lambda n=name: self.search(query, num_results, engine=n))
            if done is not None:
                return done

        # ② 浏览器脚本化通道：内容类失败的真正补救手段（换身份而非换站点）。
        if self._browser_fallback:
            channel = self._browser_channel
            if channel is None:
                from neobot_app.web_search.browser_channel import get_browser_channel

                channel = get_browser_channel()
            try:
                if channel.available():
                    done = await _try("browser", lambda: channel.search(query, num_results))
                    if done is not None:
                        return done
                else:
                    stages.append({"stage": "browser", "kind": "unavailable", "reason": "未安装 Chromium"})
            except Exception as exc:  # 本级失败不得让整次搜索抛错
                logger.warning("浏览器检索通道异常，跳过本级: %s", exc)
                stages.append({"stage": "browser", "kind": "error", "reason": str(exc)[:120]})

        # ③ DuckDuckGo：最后兜底，带固定预算（部署实测很慢）。
        for name in self._degraded_engines:
            done = await _try(name, lambda n=name: self.search(query, num_results, engine=n))
            if done is not None:
                return done

        return SearchResponse(
            query=query,
            results=[],
            engine="all",
            error="; ".join(errors) if errors else "所有引擎均无结果",
            degraded=True,
            attempts=max(1, attempts),
            signals={"stages": stages},
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
