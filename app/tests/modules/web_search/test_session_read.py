"""SearchSession.read() 加固测试（MockTransport，无真实网络）。

覆盖 fix(9) D3 read 加固：
- 抓取前先归一化（ck/a 壳 → 真实 URL），且归一化在 SSRF 校验之前生效；
- 壳页 / 空正文 / 非文本 content-type → content_fetched=False（不再当成抓取成功）；
- 正常页面仍能抓到正文。
"""

from __future__ import annotations

import base64
from typing import Callable

import httpx
import pytest

from neobot_app.web_search import session as session_module
from neobot_app.web_search.models import SearchResult
from neobot_app.web_search.session import SearchSession


def _make_session(*results: SearchResult) -> SearchSession:
    """绕过 SearchManager（需要搜索引擎依赖）构造一个只用于抓取测试的会话。"""
    session = SearchSession.__new__(SearchSession)
    session._results_index = {index: r for index, r in enumerate(results)}
    session._read_urls = set()
    session._rounds = []
    session._read_timeout = 5.0
    return session


def _result(url: str, index: int = 0) -> SearchResult:
    return SearchResult(index=index, title="t", url=url, snippet="s", engine="fake")


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True, timeout=5.0
    )


async def _allow_all(_url: str) -> bool:
    return True


def _bing_wrapper(target: str) -> str:
    payload = base64.urlsafe_b64encode(target.encode()).decode().rstrip("=")
    return f"https://www.bing.com/ck/a?!&&p=abc&u=a1{payload}&ntb=1"


GOOD_BODY = "<html><body>" + ("这是一段足够长的正常正文内容。" * 40) + "</body></html>"


async def test_tracking_shell_is_unwrapped_before_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_module, "validate_public_url_async", _allow_all)
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(
            200, text=GOOD_BODY, headers={"content-type": "text/html; charset=utf-8"}
        )

    target = "https://example.com/page"
    result = _result(_bing_wrapper(target))
    session = _make_session(result)
    async with _client(handler) as client:
        await session._fetch_all(client, [result])

    assert requested == [target], f"应先解壳再抓取，实际请求: {requested}"
    assert result.content_fetched is True
    assert "正常正文" in str(result.content)


async def test_private_url_hidden_in_tracking_shell_is_still_blocked() -> None:
    """归一化必须在 SSRF 校验之前：壳里包的私网地址同样要拦。"""
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, text=GOOD_BODY, headers={"content-type": "text/html"})

    result = _result(_bing_wrapper("http://127.0.0.1:9981/api/overview"))
    session = _make_session(result)
    async with _client(handler) as client:
        await session._fetch_all(client, [result])

    assert requested == [], "私网地址不得发起请求"
    assert result.content_fetched is False
    assert "阻止" in str(result.content)


async def test_js_redirect_shell_is_not_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_module, "validate_public_url_async", _allow_all)
    shell = (
        "<html><head><script>function l(){window.location.replace('https://x.com')}</script>"
        "</head><body></body></html>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=shell, headers={"content-type": "text/html"})

    result = _result("https://example.com/shell")
    session = _make_session(result)
    async with _client(handler) as client:
        await session._fetch_all(client, [result])

    assert result.content_fetched is False
    assert "壳" in str(result.content)


async def test_empty_body_is_not_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_module, "validate_public_url_async", _allow_all)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="", headers={"content-type": "text/html"})

    result = _result("https://example.com/empty")
    session = _make_session(result)
    async with _client(handler) as client:
        await session._fetch_all(client, [result])

    assert result.content_fetched is False


async def test_non_text_content_type_is_not_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(session_module, "validate_public_url_async", _allow_all)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"\x89PNG\r\n\x1a\n" + b"0" * 600, headers={"content-type": "image/png"}
        )

    result = _result("https://example.com/pic.png")
    session = _make_session(result)
    async with _client(handler) as client:
        await session._fetch_all(client, [result])

    assert result.content_fetched is False
    assert "非文本" in str(result.content)
