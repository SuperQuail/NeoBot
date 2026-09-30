"""浏览器脚本化检索通道（fix(9) 附录 B v2 §2）。

为什么需要它
------------
HTTP 侧的"内容类失败"（错配页）是**同一身份 + 同一缓存**的问题：实测换 HTTP 通道
（HTML↔RSS）拿到的是同一份错误缓存。换浏览器等于换身份 —— 仿真 12/12 成功、
壳 URL 0 条、复用会话后单次检索 ~1s（见 bugfixes/fix(9)-bing-search-rebuild/
search-fallback-redesign-v2.md §10）。

本模块只负责"拿到候选结果"，**不**做判据：出口仍走 urls.normalize_result_url 与
validate.classify_failure，与 HTTP 通道共用同一套质量闸门。

会话模型
--------
进程级单例（`get_browser_channel()`）：一个 Chromium + 一个 Context 跨多次搜索复用，
避免每次付 ~1.9s 预热；空闲超过 `idle_close_seconds` 自动关闭。

可用性
------
未安装 Playwright / 找不到 Chromium / 沙箱禁止子进程 → `available()` 为 False，
调用方**跳过本级**并继续回退，绝不让搜索抛错。
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neobot_app.web_search.models import SearchResponse, SearchResult
from neobot_app.web_search.urls import normalize_result_url
from neobot_app.web_search.validate import classify_failure

logger = logging.getLogger(__name__)

BING_HOME = "https://www.bing.com/"
SEARCH_URL = "https://www.bing.com/search?q={query}&setlang=zh-Hans&mkt=zh-CN"

#: 提取 li.b_algo 结果行。浏览器已解壳（href 是真实地址），raw href 另存。
_EXTRACT_JS = """
() => Array.from(document.querySelectorAll('li.b_algo')).map((li, i) => {
  const a = li.querySelector('h2 a') || li.querySelector('a');
  const cap = li.querySelector('.b_caption p, .b_captions, p');
  const cite = li.querySelector('cite');
  return {
    idx: i,
    title: a ? (a.innerText || a.textContent || '').trim().slice(0, 200) : '',
    href: a ? a.href : '',
    cite: cite ? (cite.innerText || cite.textContent || '').trim().slice(0, 200) : '',
    snippet: cap ? (cap.innerText || cap.textContent || '').trim().slice(0, 300) : '',
  };
}).filter(r => r.href)
"""

#: 翻页：标准 SERP 的 .b_pag 链接（HTTP 侧实测无效，浏览器内可点）。
_NEXT_PAGE_JS = """
() => {
  const links = Array.from(document.querySelectorAll('.b_pag a.sb_pagN, .b_pag a[title]'));
  const next = links.find(a => /下一页|Next/.test(a.innerText || a.getAttribute('title') || ''));
  if (next) { next.click(); return true; }
  const sb = document.querySelector('.sb_pagN');
  if (sb) { sb.click(); return true; }
  return false;
}
"""


def _resolve_chromium() -> str | None:
    """按项目已验证的回退链找 Chromium 可执行文件（D4）。

    顺序：headless shell（最新版本优先）→ 全量 chrome。找不到返回 None，
    调用方据此判定本级不可用（不抛错）。
    """
    root = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    if not root.exists():
        return None
    candidates: list[Path] = []
    for pattern in (
        "chromium_headless_shell-*/chrome-headless-shell-win64/chrome-headless-shell.exe",
        "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        "chromium_headless_shell-*/chrome-headless-shell-mac*/chrome-headless-shell",
        "chromium-*/chrome-win64/chrome.exe",
        "chromium-*/chrome-linux64/chrome",
        "chromium-*/chrome-win/chrome.exe",
    ):
        candidates.extend(sorted(root.glob(pattern), reverse=True))
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


@dataclass
class BrowserChannelStats:
    """会话级计数（供 A10「回退不放大」与 A11「会话复用」断言）。"""

    launches: int = 0
    searches: int = 0
    navigations: int = 0
    retries: int = 0
    idle_closes: int = 0
    last_used: float = 0.0


@dataclass
class _Session:
    playwright: Any
    browser: Any
    context: Any
    page: Any
    warmed: bool = False


class BrowserSearchChannel:
    """会话化的浏览器检索通道（进程级单例，见 `get_browser_channel`）。"""

    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        navigate_retries: int = 1,
        idle_close_seconds: float = 600.0,
        enable_paging: bool = True,
        max_pages: int = 2,
        headless: bool = True,
    ) -> None:
        self._timeout = float(timeout_seconds)
        self._navigate_retries = max(0, int(navigate_retries))
        self._idle_close = float(idle_close_seconds)
        self._enable_paging = bool(enable_paging)
        self._max_pages = max(1, int(max_pages))
        self._headless = bool(headless)
        self._session: _Session | None = None
        self._lock = asyncio.Lock()
        self.stats = BrowserChannelStats()

    # ── 可用性 ──────────────────────────────────────────────────────

    def available(self) -> bool:
        """依赖是否齐备（不启动浏览器、不产生副作用）。"""
        try:
            import playwright  # noqa: F401
        except Exception:
            return False
        return _resolve_chromium() is not None

    # ── 会话生命周期 ────────────────────────────────────────────────

    async def _ensure_session(self) -> _Session | None:
        session = self._session
        if session is not None:
            return session
        executable = _resolve_chromium()
        if executable is None:
            logger.warning("浏览器检索通道不可用：未找到 Chromium 可执行文件")
            return None
        try:
            from playwright.async_api import async_playwright

            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                headless=self._headless, executable_path=executable
            )
            context = await browser.new_context(
                locale="zh-CN", viewport={"width": 1280, "height": 900}
            )
            page = await context.new_page()
        except Exception as exc:
            logger.warning("浏览器检索通道启动失败，本次跳过本级: %s", exc)
            return None
        self.stats.launches += 1
        session = _Session(playwright=playwright, browser=browser, context=context, page=page)
        self._session = session
        return session

    async def _warmup(self, session: _Session) -> None:
        """每个会话一次：打开首页拿 Cookie / 通过地区提示。"""
        if session.warmed:
            return
        try:
            await session.page.goto(BING_HOME, wait_until="domcontentloaded", timeout=int(self._timeout * 1000))
            await asyncio.sleep(0.8)
            session.warmed = True
        except Exception as exc:
            logger.debug("浏览器通道预热失败（继续尝试检索）: %s", exc)
            session.warmed = True

    async def aclose(self) -> None:
        """关闭会话（幂等）。"""
        session, self._session = self._session, None
        if session is None:
            return
        for closer in (
            getattr(session.context, "close", None),
            getattr(session.browser, "close", None),
            getattr(session.playwright, "stop", None),
        ):
            if closer is None:
                continue
            try:
                result = closer()
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.debug("浏览器会话关闭失败: %s", exc)

    async def close_if_idle(self, now: float | None = None) -> bool:
        """空闲超阈值则关闭会话，返回是否关闭（供后台任务/测试调用）。"""
        session = self._session
        if session is None:
            return False
        current = time.monotonic() if now is None else float(now)
        if current - self.stats.last_used < self._idle_close:
            return False
        await self.aclose()
        self.stats.idle_closes += 1
        return True

    # ── 检索 ────────────────────────────────────────────────────────

    async def search(self, query: str, num_results: int = 10) -> SearchResponse:
        """执行一次浏览器检索；不可用或超时返回 error 非空的 SearchResponse。"""
        started = time.monotonic()
        self.stats.searches += 1
        async with self._lock:
            session = await self._ensure_session()
            if session is None:
                return SearchResponse(
                    query=query, results=[], engine="bing-browser",
                    error="浏览器检索通道不可用（未安装 Chromium 或启动失败）",
                    degraded=True,
                )
            await self._warmup(session)
            rows, error = await self._fetch_rows(session, query, num_results)
            self.stats.last_used = time.monotonic()

        results = self._to_results(rows)
        report = classify_failure(query, results, channel="browser")
        elapsed = (time.monotonic() - started) * 1000
        if not report.ok:
            return SearchResponse(
                query=query, results=[], engine="bing-browser",
                error=f"浏览器检索判失败（{report.describe()}）" + (f"; 抓取错误: {error}" if error else ""),
                degraded=True, search_time_ms=elapsed,
                signals={"validation": report.signals, "failure": report.kind.value},
            )
        return SearchResponse(
            query=query, results=results, engine="bing-browser",
            total_estimated=len(results), search_time_ms=elapsed,
            signals={"validation": report.signals, "failure": report.kind.value},
        )

    async def _fetch_rows(
        self, session: _Session, query: str, num_results: int
    ) -> tuple[list[dict[str, Any]], str | None]:
        """导航 + 等待 + 提取（含 1 次导航重试与可选翻页）。"""
        url = SEARCH_URL.format(query=query.replace(" ", "+"))
        timeout_ms = int(self._timeout * 1000)
        last_error: str | None = None
        rows: list[dict[str, Any]] = []
        for attempt in range(self._navigate_retries + 1):
            try:
                self.stats.navigations += 1
                await session.page.goto(url, wait_until="commit", timeout=timeout_ms)
                await session.page.wait_for_function(
                    "() => document.querySelectorAll('li.b_algo').length > 0",
                    timeout=timeout_ms,
                )
                rows = await session.page.evaluate(_EXTRACT_JS)
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt >= self._navigate_retries:
                    logger.warning("浏览器检索导航失败（已重试 %d 次）: %s", attempt, last_error)
                    return [], last_error
                # SERP 首次 goto 常 net::ERR_ABORTED（仿真实测 12/12 都需重试一次）
                self.stats.retries += 1
                await asyncio.sleep(0.5)

        if self._enable_paging and len(rows) < num_results:
            rows.extend(await self._fetch_next_page(session, num_results - len(rows)))
        return rows, None

    async def _fetch_next_page(  # noqa: D401 - 简单私有方法
        self, session: _Session, need: int
    ) -> list[dict[str, Any]]:
        """点下一页再抽一次（默认开启，最多 max_pages-1 次）。"""
        if need <= 0 or self._max_pages < 2:
            return []
        extra: list[dict[str, Any]] = []
        for _ in range(self._max_pages - 1):
            try:
                clicked = await session.page.evaluate(_NEXT_PAGE_JS)
                if not clicked:
                    break
                await session.page.wait_for_function(
                    "() => document.querySelectorAll('li.b_algo').length > 0",
                    timeout=int(self._timeout * 1000),
                )
                rows = await session.page.evaluate(_EXTRACT_JS)
                extra.extend(rows)
                if len(extra) >= need:
                    break
            except Exception as exc:
                logger.debug("浏览器翻页失败（忽略）: %s", exc)
                break
        return extra

    @staticmethod
    def _to_results(rows: list[dict[str, Any]]) -> list[SearchResult]:
        """归一化 + 去重（与 HTTP 通道共用 urls 模块）。"""
        results: list[SearchResult] = []
        seen: set[str] = set()
        for row in rows:
            display, raw = normalize_result_url(BING_HOME, str(row.get("href") or ""))
            if not display:
                continue
            key = display.split("#", 1)[0].lower()
            if key in seen:
                continue
            seen.add(key)
            results.append(
                SearchResult(
                    index=len(results) + 1,
                    title=str(row.get("title") or "").strip(),
                    url=display,
                    snippet=str(row.get("snippet") or row.get("cite") or "").strip(),
                    engine="bing-browser",
                    raw_url=raw or str(row.get("href") or ""),
                    channel="browser",
                    site_name=str(row.get("cite") or "").strip(),
                )
            )
        return results


_CHANNEL_KEY = "web_search.browser_channel"
_CHANNELS: dict[str, BrowserSearchChannel] = {}


def get_browser_channel(**kwargs: Any) -> BrowserSearchChannel:
    """进程级单例（同一进程内复用会话，避免每次付启动/预热成本）。"""
    channel = _CHANNELS.get(_CHANNEL_KEY)
    if channel is None:
        channel = BrowserSearchChannel(**kwargs)
        _CHANNELS[_CHANNEL_KEY] = channel
    return channel


def reset_browser_channel() -> None:
    """丢弃单例（测试用；调用方负责先 aclose）。"""
    _CHANNELS.pop(_CHANNEL_KEY, None)
