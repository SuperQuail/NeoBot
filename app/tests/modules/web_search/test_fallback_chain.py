"""回退链路编排的回归测试（fix(9) 附录 B v2）。

链路：Bing HTTP（结构类可重试一次）→ 浏览器脚本化 → DuckDuckGo（最后兜底）。
本文件钉住顺序与三项验收：A5′（内容类失败必须走浏览器而不是先走 DDG）、
A10（回退不放大）、空结果短路（页面明说没结果时不再回退）。
"""

from __future__ import annotations

import asyncio
from typing import Any

from neobot_app.web_search.manager import SearchManager
from neobot_app.web_search.models import SearchResponse, SearchResult


def _result(url: str = "https://example.com/a", title: str = "示例") -> SearchResult:
    return SearchResult(index=1, title=title, url=url, snippet="s", engine="fake")


def _ok(engine: str) -> SearchResponse:
    return SearchResponse(query="q", results=[_result()], engine=engine)


def _fail(engine: str, kind: str, error: str = "校验失败") -> SearchResponse:
    return SearchResponse(
        query="q", results=[], engine=engine, error=error,
        degraded=True, signals={"failure": kind},
    )


def _empty(engine: str) -> SearchResponse:
    return SearchResponse(
        query="q", results=[], engine=engine, error=None,
        degraded=True, signals={"failure": "empty", "empty": True},
    )


class _FakeEngine:
    def __init__(self, responses: list[SearchResponse]) -> None:
        self._responses = list(responses)
        self.calls = 0

    async def search(self, query: str, num_results: int = 10, **kwargs: Any) -> SearchResponse:
        self.calls += 1
        if self._responses:
            return self._responses.pop(0)
        return _fail("fake", "content")


class _SlowEngine:
    def __init__(self, delay: float) -> None:
        self.delay = delay

    async def search(self, query: str, num_results: int = 10, **kwargs: Any) -> SearchResponse:
        await asyncio.sleep(self.delay)
        return _ok("slow")


class _FakeBrowser:
    def __init__(self, response: SearchResponse | None = None, available: bool = True) -> None:
        self._response = response or _ok("bing-browser")
        self._available = available
        self.calls = 0

    def available(self) -> bool:
        return self._available

    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        self.calls += 1
        return self._response


def _manager(
    engines: dict[str, Any],
    *,
    order: list[str],
    browser: _FakeBrowser | None = None,
    budgets: dict[str, float] | None = None,
) -> SearchManager:
    mgr = SearchManager(
        engines=order,
        min_delay=0.0,
        max_retries=0,
        browser_fallback=True,
        browser_channel=browser,
        engine_budgets=budgets,
    )
    for name, engine in engines.items():
        mgr._engines[name] = engine  # 注入假引擎，绕开真实网络
    return mgr


async def test_first_engine_success_does_not_touch_fallbacks() -> None:
    browser = _FakeBrowser()
    mgr = _manager({"bing": _FakeEngine([_ok("bing")]), "duckduckgo": _FakeEngine([])},
                   order=["bing", "duckduckgo"], browser=browser)

    resp = await mgr.search_with_fallback("清华大学")

    assert resp.success is True
    assert resp.engine == "bing"
    assert browser.calls == 0
    assert [s["stage"] for s in resp.signals["stages"]] == ["bing"]


async def test_content_failure_goes_to_browser_before_ddg() -> None:
    """A5′：内容类失败（错配页）必须由浏览器通道补救，而不是先换 DDG。"""
    bing = _FakeEngine([_fail("bing", "content")])
    ddg = _FakeEngine([_ok("duckduckgo")])
    browser = _FakeBrowser(_ok("bing-browser"))
    mgr = _manager({"bing": bing, "duckduckgo": ddg}, order=["bing", "duckduckgo"], browser=browser)

    resp = await mgr.search_with_fallback("京东 购物")

    assert resp.success is True
    assert resp.engine == "bing-browser"
    assert browser.calls == 1
    assert ddg.calls == 0, "浏览器成功时不应再请求 DDG"
    assert [s["stage"] for s in resp.signals["stages"]] == ["bing", "browser"]


async def test_ddg_is_last_resort_when_browser_also_fails() -> None:
    bing = _FakeEngine([_fail("bing", "content")])
    ddg = _FakeEngine([_ok("duckduckgo")])
    browser = _FakeBrowser(_fail("bing-browser", "content"))
    mgr = _manager({"bing": bing, "duckduckgo": ddg}, order=["bing", "duckduckgo"], browser=browser)

    resp = await mgr.search_with_fallback("某查询")

    assert resp.success is True
    assert resp.engine == "duckduckgo"
    assert [s["stage"] for s in resp.signals["stages"]] == ["bing", "browser", "duckduckgo"]


async def test_empty_result_short_circuits_fallbacks() -> None:
    """页面明说"没有结果"：不应继续回退（否则是纯浪费）。"""
    browser = _FakeBrowser()
    ddg = _FakeEngine([_ok("duckduckgo")])
    mgr = _manager({"bing": _FakeEngine([_empty("bing")]), "duckduckgo": ddg},
                   order=["bing", "duckduckgo"], browser=browser)

    resp = await mgr.search_with_fallback("不存在的查询 xyzzy")

    assert resp.success is False
    assert resp.error is None, "空结果不是故障"
    assert resp.signals.get("empty") is True
    assert browser.calls == 0 and ddg.calls == 0


async def test_engine_budget_times_out_and_falls_through() -> None:
    """DDG 部署实测很慢：它在最后一级，且带固定预算，超时即放弃并如实报失败。"""
    browser = _FakeBrowser(_fail("bing-browser", "content"))  # 浏览器也失败 → 才轮到 DDG
    mgr = _manager(
        {"bing": _FakeEngine([_fail("bing", "network")]), "duckduckgo": _SlowEngine(5.0)},
        order=["bing", "duckduckgo"],
        browser=browser,
        budgets={"duckduckgo": 0.05},
    )

    resp = await mgr.search_with_fallback("某查询")

    assert resp.success is False
    stages = [s["stage"] for s in resp.signals["stages"]]
    assert stages == ["bing", "browser", "duckduckgo"], "DDG 必须在浏览器之后"
    timeout_stage = next(s for s in resp.signals["stages"] if s["stage"] == "duckduckgo")
    assert timeout_stage["kind"] == "network"
    assert "超过预算" in resp.error


async def test_browser_unavailable_is_recorded_and_does_not_raise() -> None:
    browser = _FakeBrowser(available=False)
    mgr = _manager({"bing": _FakeEngine([_fail("bing", "content")])}, order=["bing"], browser=browser)

    resp = await mgr.search_with_fallback("某查询")

    assert resp.success is False
    stages = [s["stage"] for s in resp.signals["stages"]]
    assert stages == ["bing", "browser"]
    assert resp.signals["stages"][1]["kind"] == "unavailable"


async def test_browser_exception_is_swallowed() -> None:
    class _BoomBrowser:
        def available(self) -> bool:
            return True

        async def search(self, query: str, num_results: int = 10) -> SearchResponse:
            raise RuntimeError("browser exploded")

    mgr = _manager({"bing": _FakeEngine([_fail("bing", "content")])}, order=["bing"], browser=_BoomBrowser())

    resp = await mgr.search_with_fallback("某查询")

    assert resp.success is False
    assert any(s["kind"] == "error" for s in resp.signals["stages"])


def test_search_all_is_unchanged_by_orchestration() -> None:
    """search_all 仍只按引擎列表并发，不参与回退编排。"""
    mgr = _manager({"bing": _FakeEngine([_ok("bing")])}, order=["bing"])
    assert mgr.primary_engine == "bing"
