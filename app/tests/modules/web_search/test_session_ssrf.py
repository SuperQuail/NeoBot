"""搜索结果页面抓取的 SSRF 防护测试。

搜索结果里的 URL 来自第三方页面（可被 SEO / 恶意内容影响），抓取前必须
按公网地址校验，否则可以被引导去探测内网、本机面板(9981)或文件服务器(8765)。
"""

from __future__ import annotations

from neobot_app.web_search.models import SearchResult
from neobot_app.web_search.session import SearchSession


class _RecordingClient:
    """记录实际发起的请求；测试里私有地址不应产生任何请求。"""

    def __init__(self) -> None:
        self.requested: list[str] = []

    async def get(self, url: str, **_kwargs: object) -> object:
        self.requested.append(url)
        raise RuntimeError("request attempted")


def _make_session(*results: SearchResult) -> SearchSession:
    """绕过 SearchManager（需要搜索引擎依赖）构造一个只用于抓取测试的会话。"""
    session = SearchSession.__new__(SearchSession)
    session._results_index = {index: r for index, r in enumerate(results)}
    session._read_urls = set()
    session._rounds = []
    session._read_timeout = 5.0
    return session


def _result(url: str, index: int = 0) -> SearchResult:
    return SearchResult(
        index=index, title="t", url=url, snippet="s", engine="fake"
    )


async def test_loopback_url_is_blocked_before_request() -> None:
    result = _result("http://127.0.0.1:9981/api/overview")
    session = _make_session(result)
    client = _RecordingClient()

    await session._fetch_all(client, [result])  # type: ignore[arg-type]

    assert result.content_fetched is False
    assert "阻止" in str(result.content)
    assert client.requested == []


async def test_metadata_endpoint_is_blocked() -> None:
    """云元数据地址（169.254.169.254）尤其不能被抓取。"""
    result = _result("http://169.254.169.254/latest/meta-data/")
    session = _make_session(result)
    client = _RecordingClient()

    await session._fetch_all(client, [result])  # type: ignore[arg-type]

    assert result.content_fetched is False
    assert client.requested == []


async def test_private_network_url_is_blocked() -> None:
    result = _result("http://10.1.2.3/internal")
    session = _make_session(result)
    client = _RecordingClient()

    await session._fetch_all(client, [result])  # type: ignore[arg-type]

    assert result.content_fetched is False
    assert client.requested == []


async def test_public_ip_literal_is_still_fetched() -> None:
    """公网地址（IP 字面量，避免依赖 DNS）不应被误拦。"""
    result = _result("http://93.184.216.34/page")
    session = _make_session(result)
    client = _RecordingClient()

    await session._fetch_all(client, [result])  # type: ignore[arg-type]

    assert client.requested == ["http://93.184.216.34/page"]
    # 抓取本身失败（假 client 抛错），但失败原因是请求而不是被拦截
    assert result.content_fetched is False
    assert "获取失败" in str(result.content)
