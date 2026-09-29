"""浏览器脚本化检索通道的回归测试（fix(9) 附录 B v2 §2）。

用假 session 覆盖可离线验证的部分：启动不可用时的降级、出口归一化与去重、
导航重试计数（仿真发现 SERP 首次 goto 常 ERR_ABORTED）、翻页、判据接入、
空闲关闭。真实浏览器行为由 dev-test/review/scratch/lead/browser_search_probe.py
的仿真覆盖（12/12 成功）。
"""

from __future__ import annotations

from neobot_app.web_search.browser_channel import (
    BrowserSearchChannel,
    BrowserChannelStats,
    _Session,
)


class _FakePage:
    """按脚本返回 li.b_algo 行的假页面。"""

    def __init__(self, scripts: list[object]) -> None:
        self._scripts = list(scripts)
        self.gotos: list[str] = []
        self.evaluated = 0

    async def goto(self, url: str, **kwargs: object) -> None:
        self.gotos.append(url)
        script = self._scripts[0] if self._scripts else None
        if isinstance(script, Exception):
            raise script

    async def wait_for_function(self, expr: str, timeout: int = 0) -> None:
        script = self._scripts[0] if self._scripts else None
        if isinstance(script, Exception):
            raise script

    async def evaluate(self, expr: str):
        self.evaluated += 1
        if self._scripts:
            self._scripts.pop(0)
        return []


class _ScriptedPage(_FakePage):
    """更细粒度：goto/evaluate 各自可脚本化。"""

    def __init__(self, *, goto_errors: list[object] | None = None, rows: list[list[dict]]) -> None:
        super().__init__([])
        self._goto_errors = list(goto_errors or [])
        self._rows = list(rows)

    async def goto(self, url: str, **kwargs: object) -> None:
        self.gotos.append(url)
        if self._goto_errors:
            err = self._goto_errors.pop(0)
            if isinstance(err, Exception):
                raise err

    async def wait_for_function(self, expr: str, timeout: int = 0) -> None:
        return None

    async def evaluate(self, expr: str):
        self.evaluated += 1
        if self._rows:
            return self._rows.pop(0)
        return []


def _inject(channel: BrowserSearchChannel, page: _FakePage) -> BrowserSearchChannel:
    """把假 session 塞进通道，绕过真实 Chromium 启动。"""
    session = _Session(playwright=object(), browser=object(), context=object(), page=page)
    session.warmed = True

    async def _ensure():
        return session

    channel._ensure_session = _ensure  # type: ignore[method-assign]
    return channel


def test_available_reflects_chromium_presence(monkeypatch) -> None:
    channel = BrowserSearchChannel()
    monkeypatch.setattr(
        "neobot_app.web_search.browser_channel._resolve_chromium", lambda: None
    )
    assert channel.available() is False
    monkeypatch.setattr(
        "neobot_app.web_search.browser_channel._resolve_chromium", lambda: "C:/x/chrome.exe"
    )
    assert channel.available() is True


async def test_unavailable_returns_degraded_without_raising(monkeypatch) -> None:
    channel = BrowserSearchChannel()
    monkeypatch.setattr(
        "neobot_app.web_search.browser_channel._resolve_chromium", lambda: None
    )
    response = await channel.search("任意查询")
    assert response.success is False
    assert response.degraded is True
    assert "不可用" in (response.error or "")


async def test_navigation_is_retried_once_then_succeeds() -> None:
    """仿真结论：SERP 首次 goto 常 net::ERR_ABORTED，重试一次即可成功。"""
    rows = [
        {"idx": 0, "title": "清华大学", "href": "https://www.tsinghua.edu.cn/", "cite": "tsinghua.edu.cn", "snippet": "清华大学官网"},
        {"idx": 1, "title": "清华新闻", "href": "https://news.tsinghua.edu.cn/", "cite": "news.tsinghua.edu.cn", "snippet": "新闻"},
    ]
    page = _ScriptedPage(goto_errors=[RuntimeError("net::ERR_ABORTED")], rows=[rows])
    channel = _inject(BrowserSearchChannel(timeout_seconds=1.0), page)

    response = await channel.search("清华大学 官网", num_results=10)

    assert response.success is True, response.error
    assert channel.stats.retries == 1
    assert channel.stats.navigations == 2
    assert len(page.gotos) == 2


async def test_results_are_normalized_and_deduplicated() -> None:
    shell = (
        "https://www.bing.com/ck/a?!&&p=abc&u=a1aHR0cHM6Ly9leGFtcGxlLmNvbS9h&ntb=1"
    )
    # 注意：通道出口会跑真实判据（C3 相关性），因此标题/摘要必须与查询相关，
    # 否则会（正确地）被判成 content 失败 —— 这里被测的是归一化与去重。
    rows = [
        {"idx": 0, "title": "Python 官方文档", "href": shell, "cite": "python.org", "snippet": "Python 官方文档与教程"},
        {"idx": 1, "title": "Python 官方文档（重复）", "href": "https://example.com/a", "cite": "python.org", "snippet": "Python 官方文档与教程"},
    ]
    page = _ScriptedPage(rows=[rows])
    channel = _inject(BrowserSearchChannel(timeout_seconds=1.0), page)

    response = await channel.search("Python 官方文档", num_results=2)

    assert response.success is True, response.error
    assert len(response.results) == 1, "去壳后同一 URL 应去重"
    assert response.results[0].url == "https://example.com/a"
    assert response.results[0].channel == "browser"
    assert response.results[0].engine == "bing-browser"


async def test_paging_disabled_does_not_click_next() -> None:
    rows = [
        {"idx": 0, "title": "Python 官方文档", "href": "https://www.python.org/doc/", "cite": "python.org", "snippet": "Python 官方文档"},
    ]
    page = _ScriptedPage(rows=[rows])
    channel = _inject(BrowserSearchChannel(timeout_seconds=1.0, enable_paging=False), page)

    response = await channel.search("Python 官方文档", num_results=10)

    assert response.success is True, response.error
    assert page.evaluated == 1, "关闭翻页时只应提取一次"


async def test_paging_enabled_fetches_second_page() -> None:
    page1 = [
        {"idx": 0, "title": "Python 官方文档", "href": "https://www.python.org/doc/", "cite": "python.org", "snippet": "Python 官方文档"},
    ]
    page2 = [
        {"idx": 0, "title": "Python 教程", "href": "https://docs.python.org/zh-cn/3/tutorial/", "cite": "docs.python.org", "snippet": "Python 官方教程"},
    ]
    page = _ScriptedPage(rows=[page1, True, page2])
    channel = _inject(
        BrowserSearchChannel(timeout_seconds=1.0, enable_paging=True, max_pages=2), page
    )

    response = await channel.search("Python 官方文档", num_results=10)

    assert response.success is True, response.error
    urls = {r.url for r in response.results}
    assert urls == {"https://www.python.org/doc/", "https://docs.python.org/zh-cn/3/tutorial/"}


async def test_failure_returns_degraded_with_classification() -> None:
    """提取到内容但判据不过 → degraded + 失败分级写进 signals。"""
    page = _ScriptedPage(rows=[[{"idx": 0, "title": "无关", "href": "https://zhihu.com/x", "cite": "zhihu.com", "snippet": "完全无关"}], []])
    channel = _inject(BrowserSearchChannel(timeout_seconds=1.0, enable_paging=False), page)

    response = await channel.search("京东 购物", num_results=10)

    assert response.success is False
    assert response.degraded is True
    assert "判失败" in (response.error or "")
    assert response.signals.get("failure") in {"content", "structure", "empty"}


async def test_close_if_idle_only_closes_after_threshold() -> None:
    channel = _inject(BrowserSearchChannel(idle_close_seconds=600.0), _ScriptedPage(rows=[]))

    class _Closer:
        closed = 0

        async def close(self) -> None:
            _Closer.closed += 1

    channel._session = _Session(playwright=object(), browser=_Closer(), context=_Closer(), page=_ScriptedPage(rows=[]))
    channel.stats.last_used = 1000.0

    assert await channel.close_if_idle(now=1000.0 + 10) is False
    assert channel._session is not None
    assert await channel.close_if_idle(now=1000.0 + 601) is True
    assert channel._session is None
    assert channel.stats.idle_closes == 1


def test_singleton_is_reused_and_resettable() -> None:
    from neobot_app.web_search.browser_channel import (
        get_browser_channel,
        reset_browser_channel,
    )

    reset_browser_channel()
    first = get_browser_channel()
    assert get_browser_channel() is first
    reset_browser_channel()
    assert get_browser_channel() is not first
    reset_browser_channel()


def test_stats_dataclass_defaults() -> None:
    stats = BrowserChannelStats()
    assert stats.launches == 0 and stats.searches == 0 and stats.retries == 0
