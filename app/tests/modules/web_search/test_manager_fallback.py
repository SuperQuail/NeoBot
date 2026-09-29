"""SearchManager 回退条件与限速测试（假引擎，无网络）。

覆盖 fix(9) D3：
- 回退条件修正：引擎"有结果但判失败"（error 非空 / degraded）也必须回退；
- per-engine asyncio.Lock：并发调用下 min_delay 真实生效（旧实现无互斥，形同虚设）；
- degraded / attempts 透传到最终响应。
"""

from __future__ import annotations

import asyncio
import time

from neobot_app.web_search.manager import SearchManager
from neobot_app.web_search.models import SearchResponse, SearchResult


def _result(engine: str, index: int = 0) -> SearchResult:
    return SearchResult(
        index=index, title="t", url=f"https://example.com/{index}", snippet="s", engine=engine
    )


def _ok(engine: str, n: int = 2) -> SearchResponse:
    results = [_result(engine, i) for i in range(n)]
    return SearchResponse(query="q", results=results, engine=engine, total_estimated=n)


def _rejected_with_results(engine: str) -> SearchResponse:
    """非空但判失败：10 条结果 + error（旧 success 语义会把它当成功）。"""
    results = [_result(engine, i) for i in range(10)]
    return SearchResponse(
        query="q",
        results=results,
        engine=engine,
        error="结果校验失败(cov_max: 相关性不足)",
        degraded=True,
        signals={"validation": {"codes": ["cov_max"]}},
    )


class _FakeEngine:
    def __init__(self, name: str, response: SearchResponse, calls: list[float] | None = None) -> None:
        self.name = name
        self._response = response
        self.calls = calls if calls is not None else []

    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        self.calls.append(time.monotonic())
        await asyncio.sleep(0.01)
        return self._response

    async def aclose(self) -> None:
        return None


def _manager(engines: list[_FakeEngine], **kwargs: object) -> SearchManager:
    names = [e.name for e in engines]
    mgr = SearchManager(engines=names, **kwargs)  # type: ignore[arg-type]
    mgr._engines = {e.name: e for e in engines}  # type: ignore[assignment]
    return mgr


async def test_nonempty_but_rejected_response_falls_back() -> None:
    """非空但判失败 → 必须回退到下一个引擎（回退条件修正的核心）。"""
    bad = _FakeEngine("bad", _rejected_with_results("bad"))
    good = _FakeEngine("good", _ok("good"))
    mgr = _manager([bad, good], min_delay=0.0, max_retries=0)

    resp = await mgr.search_with_fallback("q")

    assert resp.success is True, resp.error
    assert resp.engine == "good"
    assert bad.calls, "坏引擎应被调用过"
    assert good.calls, "必须真的回退到好引擎"


async def test_all_rejected_engines_report_each_reason() -> None:
    bad1 = _FakeEngine("bad1", _rejected_with_results("bad1"))
    bad2 = _FakeEngine("bad2", _rejected_with_results("bad2"))
    mgr = _manager([bad1, bad2], min_delay=0.0, max_retries=0)

    resp = await mgr.search_with_fallback("q")

    assert resp.success is False
    assert resp.results == []
    assert resp.degraded is True
    assert "bad1:" in (resp.error or "")
    assert "bad2:" in (resp.error or "")
    assert resp.attempts >= 2


async def test_search_reports_error_for_rejected_nonempty_engine() -> None:
    """单引擎 search() 同样不得把"非空但判失败"当成功。"""
    bad = _FakeEngine("bing", _rejected_with_results("bing"))
    mgr = _manager([bad], min_delay=0.0, max_retries=1)

    resp = await mgr.search("q")

    assert resp.success is False
    assert resp.error
    assert resp.degraded is True
    assert len(bad.calls) == 2, "max_retries=1 → 共尝试 2 次"


async def test_rate_limit_lock_is_effective_under_concurrency() -> None:
    """并发两次同引擎搜索：第二次必须等到 min_delay 之后（锁保证原子）。"""
    timings: list[float] = []
    engine = _FakeEngine("bing", _ok("bing"), calls=timings)
    mgr = _manager([engine], min_delay=0.3, max_retries=0)

    await asyncio.gather(mgr.search("q1"), mgr.search("q2"))

    assert len(timings) == 2
    gap = timings[1] - timings[0]
    assert gap >= 0.2, f"min_delay 未生效（间隔 {gap:.3f}s）"


async def test_degraded_and_attempts_are_propagated() -> None:
    bad = _FakeEngine("bad", _rejected_with_results("bad"))
    good = _FakeEngine("good", _ok("good"))
    mgr = _manager([bad, good], min_delay=0.0, max_retries=0)

    resp = await mgr.search_with_fallback("q")

    assert resp.degraded is True, "走过回退路径必须标记 degraded"
    assert resp.attempts >= 2


async def test_aclose_closes_engines() -> None:
    class _Closable(_FakeEngine):
        def __init__(self) -> None:
            super().__init__("bing", _ok("bing"))
            self.closed = 0

        async def aclose(self) -> None:
            self.closed += 1

    engine = _Closable()
    mgr = _manager([engine], min_delay=0.0)
    await mgr.aclose()

    assert engine.closed == 1
    assert mgr._engines == {}
