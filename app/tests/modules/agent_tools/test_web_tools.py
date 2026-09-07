from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from neobot_app.agent_tools.contracts import AgentToolError, ToolContext
from neobot_app.agent_tools.web import WebTools


CTX = ToolContext("group:1:main", "group:1")


class Search:
    async def search(self, query, num_results=10):
        return SimpleNamespace(success=True, results=[SimpleNamespace(url="https://example.com", title=query, snippet="result")])


async def test_search_structured_dedup():
    result = await WebTools(search_factory=Search).execute("web_search", {"queries": ["one", "two", "one"]}, CTX)
    assert len(result["sources"]) == 1
    assert result["untrusted"] is True


@pytest.mark.parametrize("queries", [[], [" "], [1], ["x"] * 5, "query"])
async def test_search_validates_queries(queries):
    with pytest.raises(AgentToolError):
        await WebTools().execute("web_search", {"queries": queries}, CTX)


async def test_private_and_credential_urls_rejected(monkeypatch):
    async def private(url):
        return False
    monkeypatch.setattr("neobot_app.agent_tools.web.validate_public_url_async", private)
    tools = WebTools()
    for url in ("http://127.0.0.1", "file:///secret", "https://user:pass@example.com"):
        with pytest.raises(AgentToolError):
            await tools.execute("web_fetch", {"url": url}, CTX)


async def test_dns_destination_pinned_and_sni_preserved(monkeypatch):
    async def public(url):
        return True
    async def resolve(*args, **kwargs):
        return [(2, 1, 6, "", ("93.184.216.34", 443))]
    monkeypatch.setattr("neobot_app.agent_tools.web.validate_public_url_async", public)
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    seen = []
    async def response(request):
        seen.append(request)
        return httpx.Response(200, headers={"content-type": "text/plain"}, content="你好世界".encode())
    tools = WebTools(max_text=6, client_factory=lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(response), **kw))
    result = await tools.execute("web_fetch", {"url": "https://example.com/path"}, CTX)
    assert seen[0].url.host == "93.184.216.34"
    assert seen[0].headers["host"] == "example.com"
    assert seen[0].extensions["sni_hostname"] == "example.com"
    assert result["body"]["content"] == "你好"
    assert result["truncated"] is True


async def test_rebinding_private_answer_rejected(monkeypatch):
    async def public(url):
        return True
    async def resolve(*args, **kwargs):
        return [(2, 1, 6, "", ("127.0.0.1", 443))]
    monkeypatch.setattr("neobot_app.agent_tools.web.validate_public_url_async", public)
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    with pytest.raises(AgentToolError, match="public"):
        await WebTools().execute("web_fetch", {"url": "https://example.com"}, CTX)


async def test_cross_origin_redirect_not_followed(monkeypatch):
    tools = WebTools()
    async def pinned(url):
        return httpx.URL(url), "example.com", "example.com"
    tools._pinned_url = pinned
    seen = []
    async def response(request):
        seen.append(request)
        return httpx.Response(302, headers={"location": "https://other.example.com"})
    tools.client_factory = lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(response), **kw)
    with pytest.raises(AgentToolError, match="Cross-origin"):
        await tools.execute("web_fetch", {"url": "https://example.com"}, CTX)
    assert len(seen) == 1
