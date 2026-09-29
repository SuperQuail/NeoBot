"""BingSearchEngine 会话化 / 出口归一化 / 失败语义测试（离线夹具 + MockTransport）。

覆盖 fix(9) D1/D2/D3：
- 出口归一化：展示 URL 不应再出现 ck/a 跳转壳，raw_url 留痕，channel 标记来源；
- 失败语义：错配页（degraded 夹具）必须判失败（error 非空 + results 为空），
  不能把 10 条错结果当成功交给模型；
- 会话化：持久 client 复用、预热先打首页、Accept-Encoding 禁 br。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

import httpx
import pytest

from neobot_app.web_search import engine as engine_module
from neobot_app.web_search.engine import BING_HOME, BROWSER_HEADERS, BingSearchEngine
from neobot_app.web_search.urls import is_tracking_wrapper


def _fixtures_dir() -> Path:
    env = os.environ.get("NEOBOT_WS_FIXTURES")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "fixtures" / "bing"
        if candidate.is_dir():
            return candidate
    raise RuntimeError("找不到 bing 夹具目录（可用 NEOBOT_WS_FIXTURES 指定）")


def _fixture(name: str) -> str:
    return (_fixtures_dir() / name).read_text(encoding="utf-8", errors="replace")


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> list[httpx.Request]:
    """把 MockTransport 注入引擎内部自建的 httpx.AsyncClient，并记录请求。"""
    seen: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    transport = httpx.MockTransport(_record)
    real_client = httpx.AsyncClient

    def _factory(**kwargs: object) -> httpx.AsyncClient:
        kwargs.pop("transport", None)
        return real_client(transport=transport, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(engine_module.httpx, "AsyncClient", _factory)
    return seen


def _serp_handler(body: str) -> Callable[[httpx.Request], httpx.Response]:
    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.rstrip("/").endswith("search"):
            return httpx.Response(
                200, text=body, headers={"content-type": "text/html; charset=utf-8"}
            )
        return httpx.Response(
            200, text="<html><body>home</body></html>", headers={"content-type": "text/html"}
        )

    return _handler


async def test_good_serp_returns_normalized_real_urls(monkeypatch: pytest.MonkeyPatch) -> None:
    """good 夹具：结果要过校验，且展示 URL 不再含 ck/a 壳（A1 口径）。"""
    _install_transport(monkeypatch, _serp_handler(_fixture("good_00_tsinghua.html")))
    engine = BingSearchEngine(warmup=False)
    try:
        resp = await engine.search("清华大学 官网", 10)
    finally:
        await engine.aclose()

    assert resp.error is None, resp.error
    assert resp.success is True
    assert resp.degraded is False
    assert resp.attempts >= 1
    assert len(resp.results) >= 5
    for item in resp.results:
        assert item.channel == "html"
        assert item.raw_url, "raw_url 必须留痕"
        assert item.url.startswith("http")
        assert not is_tracking_wrapper(item.url), f"展示 URL 仍是跳转壳: {item.url}"
        assert item.site_name


async def test_degraded_page_is_rejected_not_returned(monkeypatch: pytest.MonkeyPatch) -> None:
    """degraded 夹具（错配页）：必须判失败，绝不把 10 条错结果当成功。"""
    _install_transport(monkeypatch, _serp_handler(_fixture("degraded_05_zhihu-zhinan.html")))
    engine = BingSearchEngine(warmup=False)
    try:
        resp = await engine.search("知乎 直男", 10)
    finally:
        await engine.aclose()

    assert resp.success is False
    assert resp.error, "判失败必须给出非空 error"
    assert resp.results == [], "宁可丢结果，也不能把错结果交出去"
    assert resp.degraded is True
    assert resp.validation.get("codes"), "校验判据明细应留痕到 signals.validation"


async def test_page_without_algo_results_reports_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """0 结果页：error 非空（旧实现会返回 error=None 的"成功"空响应）。"""
    _install_transport(
        monkeypatch,
        _serp_handler("<html><body><ol id='b_results'></ol></body></html>"),
    )
    engine = BingSearchEngine(warmup=False)
    try:
        resp = await engine.search("任意查询", 10)
    finally:
        await engine.aclose()

    assert resp.success is False
    assert resp.error
    assert resp.results == []


async def test_accept_encoding_disables_brotli(monkeypatch: pytest.MonkeyPatch) -> None:
    """禁 br：Accept-Encoding 只允许 gzip, deflate（F1 乱码的来源之一）。"""
    seen = _install_transport(monkeypatch, _serp_handler(_fixture("good_08_douban.html")))
    engine = BingSearchEngine(warmup=False)
    try:
        await engine.search("豆瓣电影", 5)
    finally:
        await engine.aclose()

    assert seen, "应至少发出一次请求"
    sent = seen[-1].headers.get("accept-encoding", "")
    assert sent == "gzip, deflate"
    assert "br" not in sent
    assert BROWSER_HEADERS["Accept-Encoding"] == "gzip, deflate"


async def test_client_is_persistent_and_warmup_hits_home_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """会话化：预热先访问首页；多次 search 复用同一个 client（Cookie 才能累积）。"""
    seen = _install_transport(monkeypatch, _serp_handler(_fixture("good_11_netease-music.html")))
    engine = BingSearchEngine()  # warmup 默认开启
    try:
        await engine.search("网易云音乐", 5)
        client_after_first = engine._client
        await engine.search("网易云音乐", 5)
        client_after_second = engine._client
    finally:
        await engine.aclose()

    assert client_after_first is not None
    assert client_after_first is client_after_second, "client 必须复用（持久会话）"
    assert str(seen[0].url).startswith(BING_HOME), "首个请求应为预热首页"
    home_hits = [r for r in seen if str(r.url).rstrip("/") == BING_HOME.rstrip("/")]
    assert len(home_hits) == 1, "预热只做一次"


async def test_aclose_releases_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_transport(monkeypatch, _serp_handler(_fixture("good_08_douban.html")))
    engine = BingSearchEngine(warmup=False)
    await engine.search("豆瓣电影", 3)
    client = engine._client
    assert client is not None
    await engine.aclose()
    assert engine._client is None
    assert client.is_closed is True
