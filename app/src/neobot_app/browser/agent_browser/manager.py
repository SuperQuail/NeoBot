"""
agent-browser — AI 代理浏览器核心管理模块

基于 DrissionPage 的浏览器实例管理。
提供持久化会话、自动重连、有头/无头切换、跨平台兼容。
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import time
from pathlib import Path
import glob as _glob
from typing import Any, Optional

from DrissionPage import ChromiumOptions, ChromiumPage
from DrissionPage._pages.chromium_base import ChromiumBase
from DrissionPage._pages.chromium_tab import ChromiumTab
from DrissionPage.errors import PageDisconnectedError

_MAX_RETRIES = 2
_RETRY_INTERVAL = 1.0

_WINDOWS = platform.system() == "Windows"


def _playwright_chromium_path() -> str:
    """查找 Playwright 下载的 Chromium 路径。"""
    home = Path.home()
    if _WINDOWS:
        candidates = list((home / "AppData" / "Local" / "ms-playwright").glob("chromium-*/chrome-win/chrome.exe"))
    elif platform.system() == "Linux":
        candidates = list((home / ".cache" / "ms-playwright").glob("chromium-*/chrome-linux/chrome"))
    elif platform.system() == "Darwin":
        candidates = list((home / "Library" / "Caches" / "ms-playwright").glob("chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"))
    else:
        candidates = []
    # 取最新版本（按 revision 号排序）
    if candidates:
        return str(sorted(candidates, key=lambda p: str(p))[-1])
    return ""


def _find_chrome_binary() -> str:
    """跨平台查找 Chrome/Chromium 可执行路径。"""
    if path := os.getenv("CHROME_PATH"):
        return path

    # 1. 优先使用 Playwright 内嵌的 Chromium
    if pw_path := _playwright_chromium_path():
        return pw_path

    system = platform.system()
    candidates = []
    if system == "Windows":
        local_appdata = os.getenv("LOCALAPPDATA", "")
        chrome_local = Path(local_appdata) / "Google" / "Chrome" / "Application" / "chrome.exe" if local_appdata else None
        edge_local = Path(local_appdata) / "Microsoft" / "Edge" / "Application" / "msedge.exe" if local_appdata else None
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            str(chrome_local) if chrome_local else "",
            r"C:\Program Files\Chromium\Application\chrome.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            str(edge_local) if edge_local else "",
        ]
        # 也尝试通过 PATH 查找
        if chrome_path := shutil.which("chrome"):
            candidates.insert(0, chrome_path)
        if edge_path := shutil.which("msedge"):
            candidates.insert(0, edge_path)
    elif system == "Linux":
        candidates = [
            "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium", "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ]
        if which := shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser"):
            return which
    elif system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    for p in candidates:
        expanded = Path(os.path.expandvars(p))
        if expanded.exists():
            return str(expanded)
    return ""


class BrowserManager:
    """管理 DrissionPage 浏览器实例，提供持久化会话和自动重连。"""

    def __init__(
        self,
        headless: bool = True,
        user_data_dir: str | Path | None = None,
        port: int = 0,
        browser_path: str = "",
    ):
        self._headless = headless
        self._user_data_dir = str(user_data_dir or Path.cwd() / "browser_user_data")
        self._port = port
        self._browser_path = browser_path or _find_chrome_binary()
        self._page: ChromiumBase | None = None
        self._session_page: ChromiumPage | None = None
        self._chrome_pid: Optional[int] = None
        self._tab_pages: dict[str, ChromiumBase] = {}
        self._recording = False
        self._recording_frames: list[bytes] = []
        self._recording_task: asyncio.Task | None = None
        self._tabs: dict[int, Any] = {}
        self._tab_labels: dict[str, str] = {}
        self._init_scripts: dict[str, str] = {}
        Path(self._user_data_dir).mkdir(parents=True, exist_ok=True)
        self._cleanup_locks()

    def _cleanup_locks(self):
        """清理用户数据目录中 Chrome 残留的锁文件。"""
        ud = Path(self._user_data_dir)
        if not ud.exists():
            return
        for pattern in ("SingletonLock", "SingletonSocket", "lockfile"):
            for f in _glob.glob(str(ud / "**" / pattern), recursive=True):
                try:
                    Path(f).unlink(missing_ok=True)
                except Exception:
                    pass

    def _kill_orphaned_chrome(self) -> None:
        """杀死使用相同用户数据目录的残留 Chrome 进程（仅 Windows）。

        浏览器关闭后 Chrome 进程可能未完全退出，导致新实例初始化时出现
        'Chromium' object has no attribute '_dl_mgr' 等异常。
        """
        if not _WINDOWS:
            return
        try:
            import psutil as _psutil
            ud = self._user_data_dir.lower()
            for proc in _psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    name = proc.info["name"]
                    if not name or "chrome" not in name.lower():
                        continue
                    cmdline = proc.info.get("cmdline") or []
                    cmd = " ".join(cmdline)
                    if ud in cmd.lower():
                        p = _psutil.Process(proc.info["pid"])
                        p.kill()
                        p.wait(timeout=3)
                except (_psutil.NoSuchProcess, _psutil.AccessDenied, _psutil.TimeoutExpired):
                    pass
        except Exception:
            pass

    @property
    def user_data_dir(self) -> str:
        return self._user_data_dir

    @property
    def cookie_file(self) -> Path:
        return Path(self._user_data_dir) / "cookies.json"

    # ── 生命周期 ──

    async def start(self) -> None:
        """启动浏览器，自动重试处理残留进程。"""
        self._kill_orphaned_chrome()
        for attempt in range(3):
            try:
                self._page = await asyncio.to_thread(self._start_sync)
                self._session_page = self._page
                _ = self._page.url
                # 浏览器就绪后自动恢复 cookie 和 localStorage
                await self._restore_persisted_state()
                return
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(1.5)
                    if self._session_page:
                        try:
                            await asyncio.to_thread(self._session_page.quit)
                        except Exception:
                            pass
                    self._page = None
                    self._session_page = None
                    continue
                raise

    def _start_sync(self) -> ChromiumPage:
        page = ChromiumPage(addr_or_opts=self._make_options())
        try:
            self._chrome_pid = page.browser._process.pid
        except Exception:
            self._chrome_pid = None
        return page

    def _make_options(self) -> ChromiumOptions:
        co = ChromiumOptions()
        if self._browser_path:
            co.set_browser_path(self._browser_path)
        co.set_user_data_path(self._user_data_dir)
        if self._port:
            co.set_paths(local_port=self._port)
        co.set_argument("--disable-blink-features=AutomationControlled")
        co.ignore_certificate_errors(True)
        co.set_load_mode("eager")
        co.set_argument("--no-sandbox")
        if self._headless:
            co.headless(True)
            co.set_user_agent(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
            # headless 模式必须保留软件渲染能力，否则截图会失败
            co.set_argument("--disable-gpu")
        else:
            co.headless(False)
            co.set_argument("--start-maximized")
            co.set_argument("--window-position=0,0")
            co.set_argument("--window-size=1280,800")
            co.set_argument("--disable-gpu")
            co.set_argument("--disable-software-rasterizer")
            co.set_argument("--disable-gpu-compositing")
            co.set_argument("--disable-accelerated-2d-canvas")
            co.set_argument("--disable-accelerated-video-decode")
            co.set_argument("--disable-features=Vulkan,UseSkiaRenderer,VaapiVideoDecoder,DefaultANGLEVulkan")
            co.set_argument("--disable-background-mode")
            co.set_argument("--disable-background-networking")
        return co

    @property
    def page(self) -> ChromiumBase:
        assert self._page is not None, "请先调用 await start()"
        return self._page

    async def close(self) -> None:
        if self._recording:
            await self._recording_stop()
        self._tab_pages.clear()
        if self._session_page:
            # 关闭前持久化 cookie 和 localStorage，防止 Chrome 内部数据库损坏导致丢失
            try:
                await self._persist_state()
            except Exception:
                pass
            try:
                await asyncio.to_thread(self._session_page.quit, timeout=3, force=False)
            except Exception:
                pass
            # 等待进程自然退出
            if self._chrome_pid and _WINDOWS:
                try:
                    import psutil as _psutil
                    proc = _psutil.Process(self._chrome_pid)
                    proc.wait(timeout=5)
                except (_psutil.NoSuchProcess, _psutil.TimeoutExpired):
                    pass
                except Exception:
                    pass
                # 仅在进程残留时才强制终止
                if self._chrome_pid:
                    try:
                        import subprocess as _sp
                        _sp.run(
                            ["taskkill", "/F", "/PID", str(self._chrome_pid)],
                            capture_output=True, timeout=5,
                        )
                    except Exception:
                        pass
                self._chrome_pid = None
        self._page = None
        self._session_page = None

    async def _ensure_page(self) -> ChromiumBase:
        try:
            _ = self.page.url
        except (PageDisconnectedError, Exception):
            await self.close()
            await self.start()
        return self.page

    async def _navigate(self, url: str) -> None:
        page = await self._ensure_page()
        await asyncio.to_thread(page.get, url, timeout=15, retry=1, interval=1)

    # ── 启动模式 ──

    async def open(self, url: str = "") -> dict:
        """启动浏览器，可选导航到 URL。"""
        try:
            page = await self._ensure_page()
            if url:
                title = await self.navigate(url)
                return {"success": True, "action": "open", "url": url, "title": title}
            return {"success": True, "action": "open", "url": "about:blank", "title": page.title}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def connect(self, port: int) -> dict:
        """连接到已运行的浏览器 CDP 端口。"""
        try:
            if self._session_page:
                page = self._session_page
            else:
                page = await asyncio.to_thread(
                    lambda: ChromiumPage(addr_or_opts=f"127.0.0.1:{port}")
                )
                self._page = page
                self._session_page = page
            return {"success": True, "port": port, "url": page.url, "title": page.title}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def launch_headed(self, url: str | None = None) -> dict:
        """以有头模式启动浏览器。"""
        try:
            if self._session_page:
                await asyncio.to_thread(self._session_page.quit)
            self._headless = False
            await self.start()
            if url:
                await self._navigate(url)
            return {"success": True, "mode": "headed", "url": url or "about:blank"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 高可用页面操作包装 ──

    async def navigate(self, url: str) -> str:
        await self._navigate(url)
        return self.page.title

    async def current_url(self) -> str:
        return self.page.url

    async def wait(self, seconds: float = 2.0) -> dict:
        """等待指定秒数，让页面加载/渲染完成后返回页面信息。"""
        await asyncio.sleep(seconds)
        title = await self.get_title()
        url = self.page.url
        length = await self.get_text_length()
        return {"title": title, "url": url, "text_length": length}

    async def get_text(self) -> str:
        text = await asyncio.to_thread(self.page.run_js, "return document.body.innerText || ''")
        return text or ""

    async def get_text_range(self, offset: int = 0, limit: int = 2000) -> str:
        """获取页面文本的指定范围（offset 到 offset+limit），避免传输全文。"""
        js = f"return (document.body.innerText || '').substring({offset}, {offset + limit})"
        result = await asyncio.to_thread(self.page.run_js, js)
        return str(result or "")

    async def get_text_length(self) -> int:
        """仅返回文本总长度，不传输全文。"""
        js = "return (document.body.innerText || '').length"
        result = await asyncio.to_thread(self.page.run_js, js)
        try:
            return int(result)
        except (ValueError, TypeError):
            return 0

    async def get_page_info(self) -> dict:
        """获取页面结构信息：标题、URL、文本长度、各级标题列表。"""
        js = r"""
        (function() {
            var headings = [];
            var els = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
            for (var i = 0; i < els.length; i++) {
                var h = els[i];
                var level = parseInt(h.tagName.substring(1));
                var t = (h.innerText || '').trim().substring(0, 120);
                if (t) headings.push({level: level, text: t});
            }
            var links = document.querySelectorAll('a[href]');
            var linkCount = links.length;
            var tc = document.body.innerText || '';
            var words = tc.replace(/\s+/g, ' ').trim().split(' ').length;
            return JSON.stringify({
                title: document.title || '',
                url: location.href,
                text_length: tc.length,
                word_count: words,
                heading_count: headings.length,
                headings: headings,
                link_count: linkCount,
            });
        })()
        """
        result = await asyncio.to_thread(self.page.run_js, js)
        if not result:
            return {"title": "", "url": "", "text_length": 0, "word_count": 0, "heading_count": 0, "headings": [], "link_count": 0}
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"title": "", "url": "", "text_length": 0, "word_count": 0, "heading_count": 0, "headings": [], "link_count": 0}

    async def get_html(self, max_chars: int = 50000) -> str:
        if max_chars and max_chars < 200000:
            html = await asyncio.to_thread(
                self.page.run_js,
                f"return document.documentElement.outerHTML.substring(0, {max_chars})"
            )
            return html or ""
        return self.page.html

    async def get_title(self) -> str:
        return self.page.title

    async def execute_js(self, script: str) -> str:
        """执行 JS。先尝试语句模式，脚本无 return 且结果为空时尝试表达式模式。"""
        trimmed = script.strip()
        result = await asyncio.to_thread(self.page.run_js, script)
        if (result is None or str(result).strip() == ""
                or "SyntaxError" in str(result) or "Uncaught" in str(result)):
            if "return " not in trimmed:
                try:
                    expr_result = await asyncio.to_thread(self.page.run_js, script, as_expr=True)
                    if expr_result and "SyntaxError" not in str(expr_result) and "Uncaught" not in str(expr_result):
                        return str(expr_result)
                except Exception:
                    pass
        return str(result) if result is not None else ""

    async def pushstate(self, url: str) -> dict:
        """SPA 客户端导航。"""
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_js,
                f"window.history.pushState({{}}, '', '{url}'); "
                f"window.dispatchEvent(new PopStateEvent('popstate'));",
            )
            await asyncio.sleep(0.2)
            return {"success": True, "url": page.url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 元素交互 ──

    def _find_element(self, selector: str, timeout: float = 0):
        """同步查找元素，支持 @ref / CSS / text= / 模糊 text 回退。"""
        import re
        page = self.page
        if selector.startswith("@e"):
            from .snapshot import get_element_by_ref_sync
            return get_element_by_ref_sync(page, selector)
        if ":has-text(" in selector:
            m = re.search(r':has-text\(\s*["\']?([^"\')\s]+)["\']?\s*\)', selector)
            clean = re.sub(r':has-text\([^)]+\)', '', selector).strip()
            if clean:
                el = page.ele(f"css:{clean}", timeout=timeout)
                if el:
                    return el
            if m:
                return page.ele(f"text={m.group(1)}", timeout=timeout)
            return None
        if "," in selector:
            parts = [s.strip() for s in selector.split(",")]
            for part in parts:
                if part:
                    el = page.ele(f"css:{part}", timeout=timeout)
                    if el:
                        return el
            return None
        if selector.startswith(("tag:", "css:", "text:", "xpath:", "@")):
            el = page.ele(selector, timeout=timeout)
        else:
            el = page.ele(f"css:{selector}", timeout=timeout)
        if el is None:
            clean = re.sub(r'[#\.\[\]:>\s,=""()]', ' ', selector)
            words = [w for w in clean.split() if len(w) > 1]
            for w in words:
                el = page.ele(f"text={w}", timeout=timeout)
                if el:
                    return el
        return el

    async def _click_detected(self, page, url_before, el) -> bool:
        """检查点击是否已生效（URL 变化或元素脱离 DOM）。"""
        if page.url != url_before:
            return True
        try:
            attached = await asyncio.to_thread(
                page.run_js, "return document.body.contains(arguments[0])", el
            )
            return not attached
        except Exception:
            return False

    async def click(self, selector: str, index: int = 0) -> dict:
        """点击元素，多阶段回退策略确保 SPA 页面兼容。"""
        try:
            page = await self._ensure_page()

            match_count = 0
            if index > 0:
                css_sel = f"css:{selector}" if not selector.startswith(
                    ("tag:", "css:", "text:", "xpath:", "@")
                ) else selector
                els = await asyncio.to_thread(lambda: page.eles(css_sel, timeout=0))
                if not els:
                    return {"success": False, "error": f"未找到元素: {selector}"}
                if index >= len(els):
                    return {"success": False, "error": f"索引 {index} 超出范围 (共 {len(els)} 个匹配)"}
                el = els[index]
                match_count = len(els)
            else:
                el = await asyncio.to_thread(self._find_element, selector)
                if el is not None and not selector.startswith(("tag:", "text:", "xpath:", "@")):
                    try:
                        css_sel = f"css:{selector}" if not selector.startswith("css:") else selector
                        all_matches = await asyncio.to_thread(lambda: page.eles(css_sel, timeout=0))
                        match_count = len(all_matches)
                    except Exception:
                        pass

            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}

            tag = await asyncio.to_thread(lambda: el.tag)
            text = await asyncio.to_thread(lambda: el.text)
            url_before = page.url
            title_before = await asyncio.to_thread(lambda: page.title)
            tab_ids_before = len(page._browser.tab_ids)

            # Phase 1: 原生 DrissionPage click
            phase1_ok = True
            try:
                await asyncio.to_thread(el.click)
            except Exception:
                phase1_ok = False
            await asyncio.sleep(0.2)
            if await self._click_detected(page, url_before, el) or len(page._browser.tab_ids) > tab_ids_before:
                return {"success": True, "tag": tag, "text": (text or "")[:100], "url": page.url, "match_count": match_count}
            if phase1_ok:
                return {"success": True, "tag": tag, "text": (text or "")[:100], "url": page.url, "match_count": match_count}

            # Phase 2: 仅在 Phase 1 抛异常时执行
            await asyncio.to_thread(
                page.run_js,
                """(function(el) {
                    ['mousedown', 'mouseup', 'click'].forEach(function(type) {
                        el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
                    });
                })(arguments[0]);""",
                el,
            )
            await asyncio.sleep(0.2)
            if await self._click_detected(page, url_before, el) or len(page._browser.tab_ids) > tab_ids_before:
                return {"success": True, "tag": tag, "text": (text or "")[:100], "url": page.url, "match_count": match_count}

            # Phase 3: 向上查找可点击父元素并派发事件
            await asyncio.to_thread(
                page.run_js,
                """(function(el) {
                    var target = el.closest('a, button, [onclick], [role=button], .vui_tabs--nav-link, [data-click]');
                    if (target && target !== el) {
                        ['mousedown', 'mouseup', 'click'].forEach(function(type) {
                            target.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
                        });
                    }
                })(arguments[0]);""",
                el,
            )
            await asyncio.sleep(0.3)
            if await self._click_detected(page, url_before, el) or len(page._browser.tab_ids) > tab_ids_before:
                return {"success": True, "tag": tag, "text": (text or "")[:100], "url": page.url, "match_count": match_count}

            # Phase 4: 仅当元素本身是 <a> 标签时用 href 导航
            await asyncio.to_thread(
                page.run_js,
                """(function(el) {
                    if (el.tagName === 'A' && el.href && el.href !== '#' && !el.href.startsWith('javascript:')) {
                        location.href = el.href;
                    }
                })(arguments[0]);""",
                el,
            )
            await asyncio.sleep(0.5)

            return {"success": True, "tag": tag, "text": (text or "")[:100], "url": page.url, "match_count": match_count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def find_elements(self, keyword: str, max_results: int = 30) -> dict:
        """搜索当前页面中匹配关键词的元素，返回结构化列表供 AI 参考。"""
        try:
            page = await self._ensure_page()
            js = """(function(kw, limit) {
                var results = [];
                var all = document.querySelectorAll('a, button, input, textarea, select, [role=button], [onclick], label, span, li, img, h1, h2, h3, h4, p, div[class]');
                var kw_lower = kw.toLowerCase();
                var seen = new Set();
                for (var i = 0; i < all.length && results.length < limit; i++) {
                    var el = all[i];
                    if (seen.has(el)) continue;
                    var text = (el.innerText || '').trim();
                    var ph = el.placeholder || '';
                    var aria_label = el.getAttribute('aria-label') || '';
                    var value = el.value || '';
                    var alt = el.alt || '';
                    var title_attr = el.title || '';
                    var href = el.getAttribute('href') || '';
                    var cls = el.className || '';
                    if (typeof cls === 'object') cls = cls.baseVal || '';
                    var match_text = text.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_ph = ph.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_aria = aria_label.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_val = value.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_alt = alt.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_title = title_attr.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_href = href.toLowerCase().indexOf(kw_lower) !== -1;
                    var match_cls = cls.toLowerCase().indexOf(kw_lower) !== -1;
                    if (match_text || match_ph || match_aria || match_val || match_alt || match_title || match_href || match_cls) {
                        var rect = el.getBoundingClientRect();
                        var selector = el.tagName.toLowerCase();
                        if (el.id) selector += '#' + el.id;
                        else if (cls) {
                            var classPart = cls.split(/\\s+/).filter(function(c){return c && c.indexOf(':')===-1 && !c.startsWith('hover') && !c.startsWith('active');})[0];
                            if (classPart) selector += '.' + classPart;
                        }
                        var context = '';
                        var parent = el.parentElement;
                        for (var depth = 0; depth < 5 && parent && parent !== document.body; depth++) {
                            var pText = (parent.innerText || '').trim().substring(0, 120);
                            if (pText && pText !== text) {
                                context = pText;
                                break;
                            }
                            parent = parent.parentElement;
                        }
                        var siblingText = '';
                        var container = el.closest('[class*="card"], [class*="item"], [class*="list"], li, [class*="result"], [class*="search"]');
                        if (container) {
                            var containerText = (container.innerText || '').trim().substring(0, 200);
                            var selfText = text.substring(0, 100);
                            if (containerText.indexOf(selfText) !== -1) {
                                siblingText = containerText.replace(selfText, '[...]').substring(0, 120);
                            }
                        }
                        var dataAttrs = '';
                        var dataKeys = [];
                        for (var j = 0; j < el.attributes.length; j++) {
                            var attr = el.attributes[j];
                            if (attr.name.indexOf('data-') === 0 && attr.value) {
                                dataKeys.push(attr.name + '=' + attr.value.substring(0, 30));
                            }
                        }
                        if (dataKeys.length) dataAttrs = dataKeys.join('; ');
                        results.push({
                            tag: el.tagName.toLowerCase(),
                            text: text.substring(0, 100),
                            href: href,
                            placeholder: ph,
                            aria_label: aria_label,
                            selector: selector,
                            visible: rect.width > 0 && rect.height > 0,
                            top: Math.round(rect.top),
                            left: Math.round(rect.left),
                            index: i,
                            context: context.substring(0, 120),
                            sibling_text: siblingText.substring(0, 120),
                            data_attrs: dataAttrs,
                            exact: text.toLowerCase() === kw_lower,
                        });
                        var descendants = el.querySelectorAll('*');
                        for (var d = 0; d < descendants.length; d++) seen.add(descendants[d]);
                    }
                }
                return JSON.stringify(results);
            })(arguments[0], arguments[1]);"""
            raw = await asyncio.to_thread(page.run_js, js, keyword, max_results)
            if raw:
                items = json.loads(raw)
                return {"success": True, "items": items, "count": len(items)}
            return {"success": True, "items": [], "count": 0}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def click_new_tab(self, selector: str) -> dict:
        """点击元素并在新标签页中打开链接。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            href = await asyncio.to_thread(lambda: el.attr("href"))
            if href:
                result = await self.new_tab(href)
                return result
            await asyncio.to_thread(el.click, as_new_tab=True)
            await asyncio.sleep(0.15)
            return {"success": True, "action": "click_new_tab"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def dblclick(self, selector: str) -> dict:
        """双击元素。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            await asyncio.to_thread(
                self.page.run_js,
                "arguments[0].dispatchEvent(new MouseEvent('dblclick', {bubbles: true}))",
                el,
            )
            await asyncio.sleep(0.2)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def focus(self, selector: str) -> dict:
        """聚焦到元素。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            await asyncio.to_thread(el.focus)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def type_text(self, selector: str, text: str, clear: bool = True) -> dict:
        """在输入框中输入文本，失败时回退到 JS。"""
        try:
            page = await self._ensure_page()
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            if clear:
                try:
                    await asyncio.to_thread(el.clear)
                except Exception:
                    pass
            try:
                await asyncio.to_thread(el.input, text)
            except Exception:
                await asyncio.to_thread(
                    page.run_js,
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', {bubbles: true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));"
                    "arguments[0].dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));"
                    "arguments[0].dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', bubbles:true}));",
                    el, text,
                )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def press_key(self, keys: str) -> dict:
        """按下键盘按键（Enter, Escape, Tab 等）。"""
        try:
            page = await self._ensure_page()
            safe_key = keys.replace("'", "\\'")
            await asyncio.to_thread(
                page.run_js,
                f"""
                (() => {{
                    var el = document.activeElement;
                    if (!el) return;
                    el.dispatchEvent(new KeyboardEvent('keydown', {{key:'{safe_key}', bubbles:true, cancelable:true}}));
                    el.dispatchEvent(new KeyboardEvent('keypress', {{key:'{safe_key}', bubbles:true, cancelable:true}}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {{key:'{safe_key}', bubbles:true, cancelable:true}}));
                    if ('{safe_key}' === 'Enter') {{
                        var form = el.closest('form');
                        if (form) {{
                            form.dispatchEvent(new Event('submit', {{bubbles:true, cancelable:true}}));
                            var btn = form.querySelector('button[type=submit], input[type=submit]');
                            if (btn) btn.click();
                        }}
                    }}
                }})();
                """,
            )
            await asyncio.sleep(0.2)
            return {"success": True, "keys": keys}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def press_combo(self, combo: str) -> dict:
        """按下组合键，如 'Control+a', 'Alt+Tab'。"""
        try:
            page = await self._ensure_page()
            keys = combo.split("+")
            main_key = keys[-1]
            js = (
                f"document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', {{"
                f"key: '{main_key}', bubbles: true, cancelable: true, "
                f"ctrlKey: {'true' if any(k.lower()=='control' for k in keys) else 'false'}, "
                f"altKey: {'true' if any(k.lower()=='alt' for k in keys) else 'false'}, "
                f"shiftKey: {'true' if any(k.lower()=='shift' for k in keys) else 'false'}, "
                f"metaKey: {'true' if any(k.lower()=='meta' for k in keys) else 'false'}}}))"
            )
            await asyncio.to_thread(page.run_js, js)
            await asyncio.sleep(0.15)
            return {"success": True, "combo": combo}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def key_down(self, key: str) -> dict:
        """按住按键。"""
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_js,
                f"document.activeElement?.dispatchEvent(new KeyboardEvent('keydown', {{key: '{key}', bubbles: true}}))",
            )
            return {"success": True, "key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def key_up(self, key: str) -> dict:
        """释放按键。"""
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_js,
                f"document.activeElement?.dispatchEvent(new KeyboardEvent('keyup', {{key: '{key}', bubbles: true}}))",
            )
            return {"success": True, "key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def check(self, selector: str) -> dict:
        """勾选复选框。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            checked = await asyncio.to_thread(lambda: el.checked)
            if not checked:
                await asyncio.to_thread(el.click)
            return {"success": True, "checked": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def uncheck(self, selector: str) -> dict:
        """取消勾选复选框。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            checked = await asyncio.to_thread(lambda: el.checked)
            if checked:
                await asyncio.to_thread(el.click)
            return {"success": True, "checked": False}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def select_option(self, selector: str, option: str) -> dict:
        """选择下拉框选项（单选）。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            await asyncio.to_thread(el.select, option)
            return {"success": True, "value": option}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def select_multi(self, selector: str, options: list[str]) -> dict:
        """下拉框多选。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            for opt in options:
                await asyncio.to_thread(el.select, opt)
            return {"success": True, "values": options}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def hover(self, selector: str) -> dict:
        """悬停在元素上。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            await asyncio.to_thread(el.hover)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def scroll(self, direction: str = "down", amount: int = 500) -> dict:
        """滚动页面。"""
        try:
            page = await self._ensure_page()
            if direction == "top":
                await asyncio.to_thread(page.run_js, "window.scrollTo(0, 0)")
            elif direction == "bottom":
                await asyncio.to_thread(page.run_js, "window.scrollTo(0, document.body.scrollHeight)")
            elif direction == "down":
                await asyncio.to_thread(page.run_js, f"window.scrollBy(0, {amount})")
            elif direction == "up":
                await asyncio.to_thread(page.run_js, f"window.scrollBy(0, -{amount})")
            await asyncio.sleep(0.2)
            return {"success": True, "direction": direction}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def scrollintoview(self, selector: str) -> dict:
        """将元素滚动到可视区域。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            await asyncio.to_thread(el.run_js, "this.scrollIntoView({behavior: 'instant', block: 'center'})")
            await asyncio.sleep(0.2)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def drag_n_drop(self, source_selector: str, target_selector: str) -> dict:
        """拖拽元素到目标位置。"""
        try:
            page = await self._ensure_page()
            src = await asyncio.to_thread(self._find_element, source_selector)
            tgt = await asyncio.to_thread(self._find_element, target_selector)
            if src is None:
                return {"success": False, "error": f"未找到拖拽源: {source_selector}"}
            if tgt is None:
                return {"success": False, "error": f"未找到目标: {target_selector}"}
            src_rect = await asyncio.to_thread(lambda: src.rect)
            tgt_rect = await asyncio.to_thread(lambda: tgt.rect)
            js = (
                f"var src = document.elementFromPoint({src_rect['x'] + src_rect['width']/2}, {src_rect['y'] + src_rect['height']/2});"
                f"var evt = new MouseEvent('mousedown', {{bubbles: true}});"
                f"src?.dispatchEvent(evt);"
                f"var evt2 = new MouseEvent('mousemove', {{bubbles: true, clientX: {tgt_rect['x'] + tgt_rect['width']/2}, clientY: {tgt_rect['y'] + tgt_rect['height']/2}}});"
                f"document.dispatchEvent(evt2);"
                f"var evt3 = new MouseEvent('mouseup', {{bubbles: true}});"
                f"document.dispatchEvent(evt3);"
            )
            await asyncio.to_thread(page.run_js, js)
            await asyncio.sleep(0.2)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def upload_file(self, selector: str, filepath: str) -> dict:
        """上传文件到文件选择器。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            resolved = str(Path(filepath).resolve())
            if not Path(resolved).exists():
                return {"success": False, "error": f"文件不存在: {resolved}"}
            await asyncio.to_thread(el.input, resolved)
            return {"success": True, "file": resolved}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 元素查询 ──

    async def get_element_text(self, selector: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            text = await asyncio.to_thread(lambda: el.text)
            return {"success": True, "text": (text or "")[:5000]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_element_html(self, selector: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            html = await asyncio.to_thread(lambda: el.html)
            return {"success": True, "html": (html or "")[:10000]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_element_attr(self, selector: str, attr: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            value = await asyncio.to_thread(lambda: el.attr(attr))
            return {"success": True, "attribute": attr, "value": value or ""}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_element_value(self, selector: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            value = await asyncio.to_thread(lambda: el.value)
            return {"success": True, "value": value or ""}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_box(self, selector: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            rect = await asyncio.to_thread(lambda: el.rect)
            return {"success": True, "box": rect}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_count(self, selector: str) -> dict:
        try:
            page = await self._ensure_page()
            count = await asyncio.to_thread(lambda: len(page.eles(selector)))
            return {"success": True, "count": count, "selector": selector}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_styles(self, selector: str) -> dict:
        """获取元素的计算样式。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            styles = await asyncio.to_thread(
                self.page.run_js,
                "var s=window.getComputedStyle(arguments[0]);"
                "return JSON.stringify({color:s.color,backgroundColor:s.backgroundColor,"
                "fontSize:s.fontSize,fontFamily:s.fontFamily,fontWeight:s.fontWeight,"
                "display:s.display,visibility:s.visibility,opacity:s.opacity,"
                "width:s.width,height:s.height,margin:s.margin,padding:s.padding,"
                "border:s.border,textAlign:s.textAlign});",
                el,
            )
            return {"success": True, "styles": json.loads(styles) if styles else {}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 状态检查 ──

    async def is_visible(self, selector: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            displayed = await asyncio.to_thread(el.is_displayed)
            return {"success": True, "visible": displayed}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def is_enabled(self, selector: str) -> dict:
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            disabled = await asyncio.to_thread(el.attr, "disabled")
            return {"success": True, "enabled": disabled is None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def is_checked(self, selector: str) -> dict:
        """检查复选框/单选框是否选中。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            checked = await asyncio.to_thread(lambda: el.checked)
            return {"success": True, "checked": bool(checked)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 对话框处理 ──

    async def dialog_accept(self, text: str = "") -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.handle_alert, text or True)
            return {"success": True, "action": "accept"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def dialog_dismiss(self) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.handle_alert, False)
            return {"success": True, "action": "dismiss"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def dialog_status(self) -> dict:
        try:
            page = await self._ensure_page()
            has_alert = await asyncio.to_thread(
                page.run_js,
                "return window.__alertActive === true || false",
            )
            return {"success": True, "has_dialog": bool(has_alert)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Frame 切换 ──

    async def frame(self, selector_or_name: str) -> dict:
        try:
            page = await self._ensure_page()
            if selector_or_name == "main":
                await asyncio.to_thread(page.to_frame, None)
                return {"success": True, "frame": "main"}
            el = await asyncio.to_thread(self._find_element, selector_or_name)
            if el is None:
                return {"success": False, "error": f"未找到框架: {selector_or_name}"}
            await asyncio.to_thread(page.to_frame, el)
            return {"success": True, "frame": selector_or_name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 等待操作 ──

    async def wait(self, condition: str = "timeout", value: str = "", timeout: int = 20) -> dict:
        try:
            page = await self._ensure_page()
            if condition == "selector":
                await asyncio.to_thread(page.wait.ele_displayed, value, timeout=timeout)
            elif condition == "text":
                await asyncio.to_thread(page.wait.text_displayed, value, timeout=timeout)
            elif condition == "url":
                for _ in range(timeout):
                    if value in page.url:
                        break
                    await asyncio.sleep(1)
            elif condition == "network_idle":
                await asyncio.to_thread(page.wait.load_complete, timeout=timeout)
                await asyncio.sleep(1)
            elif condition == "fn":
                for _ in range(timeout):
                    ok = await asyncio.to_thread(page.run_js, f"return !!({value})")
                    if ok and str(ok) != "false":
                        return {"success": True, "condition": "fn", "value": value}
                    await asyncio.sleep(0.5)
                return {"success": False, "error": f"JS 条件超时: {value}"}
            elif condition == "timeout":
                await asyncio.sleep(min(int(value or "2"), 30))
            return {"success": True, "condition": condition, "value": value}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 浏览器设置 ──

    async def set_viewport(self, width: int, height: int, device_scale_factor: float = 1.0) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_cdp, "Emulation.setDeviceMetricsOverride",
                width=width, height=height,
                deviceScaleFactor=device_scale_factor, mobile=False,
            )
            return {"success": True, "viewport": f"{width}x{height}@{device_scale_factor}x"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_device(self, name: str) -> dict:
        """模拟移动设备。"""
        devices = {
            "iPhone 14": {"width": 390, "height": 844, "dsf": 3, "mobile": True},
            "iPhone 13": {"width": 390, "height": 844, "dsf": 3, "mobile": True},
            "iPhone 12": {"width": 390, "height": 844, "dsf": 3, "mobile": True},
            "iPhone SE": {"width": 375, "height": 667, "dsf": 2, "mobile": True},
            "Pixel 7": {"width": 412, "height": 915, "dsf": 2.625, "mobile": True},
            "Pixel 5": {"width": 393, "height": 851, "dsf": 2.75, "mobile": True},
            "iPad Pro": {"width": 1024, "height": 1366, "dsf": 2, "mobile": True},
            "iPad Mini": {"width": 768, "height": 1024, "dsf": 2, "mobile": True},
        }
        spec = devices.get(name)
        if not spec:
            return {"success": False, "error": f"未知设备: {name}，支持: {list(devices.keys())}"}
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_cdp, "Emulation.setDeviceMetricsOverride",
                width=spec["width"], height=spec["height"],
                deviceScaleFactor=spec["dsf"], mobile=spec["mobile"],
            )
            ua = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                  "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                  f"Mobile/15E148 Safari/604.1" if spec["mobile"] else "")
            if ua:
                await asyncio.to_thread(page.run_cdp, "Network.setUserAgentOverride", userAgent=ua)
            return {"success": True, "device": name}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_geolocation(self, latitude: float, longitude: float) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_cdp, "Emulation.setGeolocationOverride",
                latitude=latitude, longitude=longitude, accuracy=100,
            )
            return {"success": True, "lat": latitude, "lng": longitude}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_offline(self, offline: bool) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_cdp, "Network.emulateNetworkConditions",
                offline=offline, latency=0, downloadThroughput=0, uploadThroughput=0,
            )
            return {"success": True, "offline": offline}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_headers(self, headers: dict) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.run_cdp, "Network.enable")
            await asyncio.to_thread(page.run_cdp, "Network.setExtraHTTPHeaders", headers=headers)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_credentials(self, username: str, password: str) -> dict:
        """设置 HTTP Basic Auth。"""
        try:
            page = await self._ensure_page()
            encoded = __import__("base64").b64encode(f"{username}:{password}".encode()).decode()
            await asyncio.to_thread(page.run_cdp, "Network.enable")
            await asyncio.to_thread(
                page.run_cdp, "Network.setExtraHTTPHeaders",
                headers={"Authorization": f"Basic {encoded}"},
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def set_media(self, color_scheme: str = "", reduced_motion: str = "") -> dict:
        """模拟媒体特性（color-scheme, prefers-reduced-motion）。"""
        try:
            page = await self._ensure_page()
            features = []
            if color_scheme:
                features.append({"name": "prefers-color-scheme", "value": color_scheme})
            if reduced_motion:
                features.append({"name": "prefers-reduced-motion", "value": reduced_motion})
            if features:
                await asyncio.to_thread(
                    page.run_cdp, "Emulation.setEmulatedMedia",
                    features=features,
                )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 截图 ──

    async def screenshot(self, path: str | Path | None = None, full_page: bool = False) -> bytes:
        """截图，返回 JPEG bytes。

        使用 CDP Page.captureScreenshot 直接调用，避免 DrissionPage 的
        _run_cdp_loaded → wait.doc_loaded() 挂起问题（SPA 页面 readyState 可能卡在 loading）。
        """
        page = await self._ensure_page()

        if full_page:
            import json as _json
            js = "return JSON.stringify({w: document.body.scrollWidth, h: document.body.scrollHeight})"
            raw = await asyncio.to_thread(page.run_js, js)
            size = _json.loads(raw) if raw else {"w": 1280, "h": 720}
            args = {
                "format": "jpeg",
                "quality": 85,
                "clip": {"x": 0, "y": 0, "width": size["w"], "height": size["h"], "scale": 1},
                "captureBeyondViewport": True,
            }
        else:
            args = {"format": "jpeg", "quality": 85}

        import base64
        result = await asyncio.to_thread(lambda: page.run_cdp("Page.captureScreenshot", **args))
        jpg_bytes = base64.b64decode(result["data"])

        if path:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(jpg_bytes)

        return jpg_bytes

    async def screenshot_annotated(self, name: str = "") -> dict:
        """截图并标注元素编号。"""
        try:
            page = await self._ensure_page()
            from .snapshot import _collect_elements
            elements = await asyncio.to_thread(_collect_elements, page, interactive_only=True)
            shot_path = Path(self._user_data_dir) / f"annotated_{name or 'shot'}.png"
            await asyncio.to_thread(page.get_screenshot, path=str(shot_path), full_page=True)

            try:
                from PIL import Image, ImageDraw, ImageFont
                img = Image.open(shot_path).convert("RGB")
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.truetype("arial.ttf", 16)
                except Exception:
                    font = ImageFont.load_default()
                elements_data = []
                for el_data in elements:
                    rect = el_data.attrs if hasattr(el_data, 'attrs') else {}
                    elements_data.append({"rect": {}})  # simplified for annotation
                for i, el_data in enumerate(elements_data):
                    ref_num = i + 1
                    rect = el_data.get("rect", {})
                    x, y, w, h = rect.get("x", 0), rect.get("y", 0), rect.get("width", 0), rect.get("height", 0)
                    if w > 0 and h > 0:
                        cx, cy = x + w / 2, y + h / 2
                        r = 12
                        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill="red")
                        draw.text((cx - 5, cy - 7), str(ref_num), fill="white", font=font)
                stem = shot_path.stem
                anno_path = shot_path.with_name(stem + "_annotated.png")
                img.save(anno_path, "PNG")
                return {"success": True, "path": str(anno_path), "elements": len(elements)}
            except ImportError:
                return {"success": True, "path": str(shot_path), "elements": 0, "note": "PIL not available"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 标签页管理 ──

    async def new_tab(self, url: str = "") -> dict:
        """新建标签页并自动激活。"""
        try:
            page = await self._ensure_page()
            tab_ids_before = list(page._browser.tab_ids)
            await asyncio.to_thread(self._session_page.new_tab, url or None)
            await asyncio.sleep(0.2)
            tab_ids = list(page._browser.tab_ids)
            for tid in tab_ids:
                if tid not in tab_ids_before:
                    await asyncio.to_thread(page._browser.activate_tab, tid)
                    tab = self._session_page.get_tab(tid)
                    self._tab_pages[tid] = tab
                    self._page = tab
                    break
            return {"success": True, "url": url or "", "title": self.page.title}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def new_tab_label(self, label: str, url: str = "") -> dict:
        """新建标签页并命名（标签名可在后续切换时用）。"""
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page._browser.new_tab, url or None)
            await asyncio.sleep(0.2)
            tab_ids = page._browser.tab_ids
            self._tab_labels[label] = tab_ids[-1]
            return {"success": True, "label": label, "url": url}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def switch_tab(self, index: int) -> dict:
        try:
            if index < 0:
                return {"success": False, "error": f"索引 {index} 无效"}
            await self._ensure_page()
            sp = self._session_page
            tab_ids = list(sp._browser.tab_ids)
            if index >= len(tab_ids):
                return {"success": False, "error": f"索引 {index} 超出范围 (共 {len(tab_ids)} 个)"}
            target_id = tab_ids[index]
            await asyncio.to_thread(sp._browser.activate_tab, target_id)
            if target_id in self._tab_pages:
                self._page = self._tab_pages[target_id]
            else:
                tab = sp.get_tab(target_id)
                self._tab_pages[target_id] = tab
                self._page = tab
            return {"success": True, "index": index, "total": len(tab_ids),
                    "title": self.page.title}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def switch_tab_by_label(self, label: str) -> dict:
        """通过标签名切换标签页。"""
        try:
            target_id = self._tab_labels.get(label)
            if not target_id:
                return {"success": False, "error": f"未找到标签: {label}"}
            page = await self._ensure_page()
            await asyncio.to_thread(page._browser.activate_tab, target_id)
            if target_id in self._tab_pages:
                self._page = self._tab_pages[target_id]
            else:
                tab = self._session_page.get_tab(target_id)
                self._tab_pages[target_id] = tab
                self._page = tab
            await asyncio.sleep(0.2)
            return {"success": True, "label": label, "title": self.page.title}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def list_tabs(self) -> list[dict]:
        try:
            page = await self._ensure_page()
            tab_ids = page._browser.tab_ids
            target_infos = await asyncio.to_thread(
                lambda: page._browser._run_cdp('Target.getTargets')['targetInfos']
            )
            valid_ids = set(tab_ids)
            label_map = {v: k for k, v in self._tab_labels.items()}
            result = []
            idx = 0
            for info in target_infos:
                tid = info['targetId']
                if tid in valid_ids and info.get('type') in ('page', 'webview'):
                    result.append({
                        "index": idx,
                        "tab_id": tid,
                        "label": label_map.get(tid, ""),
                        "title": info.get('title', ''),
                        "url": info.get('url', ''),
                        "active": tid == page.tab_id,
                    })
                    idx += 1
            return result
        except Exception as e:
            return [{"error": str(e)}]

    async def close_tab(self, index: int) -> dict:
        try:
            page = await self._ensure_page()
            tab_ids = page._browser.tab_ids
            if index < 0 or index >= len(tab_ids):
                return {"success": False, "error": f"索引 {index} 超出范围"}
            target_id = tab_ids[index]
            is_active = target_id == page.tab_id
            await asyncio.to_thread(page.run_cdp, "Target.closeTarget", targetId=target_id)
            self._tab_pages.pop(target_id, None)
            for lbl, tid in list(self._tab_labels.items()):
                if tid == target_id:
                    del self._tab_labels[lbl]
            if is_active and len(tab_ids) > 1:
                remaining = [t for t in tab_ids if t != target_id]
                new_id = remaining[0]
                await asyncio.to_thread(page._browser.activate_tab, new_id)
                if new_id in self._tab_pages:
                    self._page = self._tab_pages[new_id]
                else:
                    tab = self._session_page.get_tab(new_id)
                    self._tab_pages[new_id] = tab
                    self._page = tab
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def close_tabs(self, indices: list[int] | None = None, others: bool = False) -> dict:
        """批量关闭标签页。"""
        try:
            page = await self._ensure_page()
            tab_ids = list(page._browser.tab_ids)

            if others:
                current_id = page.tab_id
                target_ids = [tid for tid in tab_ids if tid != current_id]
            elif indices:
                target_ids = []
                for idx in indices:
                    if 0 <= idx < len(tab_ids):
                        target_ids.append(tab_ids[idx])
            else:
                return {"success": False, "error": "请指定 indices 或设置 others=true"}

            if not target_ids:
                return {"success": True, "closed": 0}

            closed = 0
            for target_id in target_ids:
                try:
                    await asyncio.to_thread(page.run_cdp, "Target.closeTarget", targetId=target_id)
                    self._tab_pages.pop(target_id, None)
                    closed += 1
                except Exception:
                    pass

            current_id = page.tab_id
            remaining = [tid for tid in tab_ids if tid not in target_ids]
            if current_id in target_ids and remaining:
                new_id = remaining[0]
                await asyncio.to_thread(page._browser.activate_tab, new_id)
                if new_id in self._tab_pages:
                    self._page = self._tab_pages[new_id]
                else:
                    tab = self._session_page.get_tab(new_id)
                    self._tab_pages[new_id] = tab
                    self._page = tab

            return {"success": True, "closed": closed}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def close_current_tab(self) -> dict:
        """关闭当前标签页。"""
        try:
            page = await self._ensure_page()
            current_id = page.tab_id
            tab_ids = page._browser.tab_ids
            current_idx = tab_ids.index(current_id) if current_id in tab_ids else 0
            return await self.close_tab(current_idx)
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def window_new(self) -> dict:
        """新建浏览器窗口。"""
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.run_cdp, 'Target.createTarget', url='about:blank', newWindow=True)
            await asyncio.sleep(1)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def create_tab(self, url: str = "") -> Any:
        """创建新标签页，返回独立的 ChromiumTab 对象。"""
        await self._ensure_page()
        tab = await asyncio.to_thread(self._session_page.new_tab, url or None)
        try:
            tab.timeout = 2
        except Exception:
            pass
        return tab

    # ── Cookie 管理 ──

    async def save_cookies(self) -> int:
        cookies = self.page.cookies()
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        self.cookie_file.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(cookies)

    async def load_cookies(self) -> int:
        if not self.cookie_file.exists():
            return 0
        cookies = json.loads(self.cookie_file.read_text(encoding="utf-8"))
        for c in cookies:
            try:
                self.page.set.cookies(c)
            except Exception:
                pass
        return len(cookies)

    async def get_cookie_string(self, domain: str | None = None) -> str:
        cookies = self.page.cookies()
        if domain:
            cookies = [c for c in cookies if domain in str(c.get("domain", ""))]
        return "; ".join(f"{c['name']}={c['value']}" for c in cookies)

    async def get_all_cookies(self) -> list[dict]:
        return self.page.cookies()

    async def set_cookies(self, cookies: list[dict]) -> dict:
        try:
            page = await self._ensure_page()
            count = 0
            for c in cookies:
                try:
                    await asyncio.to_thread(page.set.cookies, c)
                    count += 1
                except Exception:
                    pass
            return {"success": True, "count": count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def clear_cookies(self) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_js,
                "document.cookie.split(';').forEach(c => { "
                "document.cookie = c.trim().split('=')[0] + '=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/'; "
                "})",
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def cookies_set_curl(self, filepath: str) -> dict:
        """从 cURL cookie 文件导入 cookie。"""
        try:
            page = await self._ensure_page()
            content = Path(filepath).read_text(encoding="utf-8")
            imported = 0
            if content.strip().startswith("[") or content.strip().startswith("{"):
                try:
                    data = json.loads(content)
                    if isinstance(data, dict):
                        data = [data]
                    return await self.set_cookies(data)
                except json.JSONDecodeError:
                    pass
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("HttpOnly"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    cookie = {
                        "name": parts[5], "value": parts[6],
                        "domain": parts[0], "path": parts[2],
                        "secure": parts[3] == "TRUE",
                    }
                    try:
                        await asyncio.to_thread(page.set.cookies, cookie)
                        imported += 1
                    except Exception:
                        pass
            return {"success": True, "count": imported}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 网络拦截 ──

    async def network_route(self, url_pattern: str, mock_body: str = "", abort: bool = False) -> dict:
        try:
            page = await self._ensure_page()
            if abort:
                page.listen.start(url_pattern)
                page.listen.wait()
            else:
                page.listen.start(url_pattern)
            return {"success": True, "pattern": url_pattern, "abort": abort}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def network_unroute(self, url_pattern: str = "") -> dict:
        """移除网络请求拦截。"""
        try:
            page = await self._ensure_page()
            page.listen.stop()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def network_requests(self, filter_str: str = "") -> dict:
        """查看已追踪的网络请求。"""
        try:
            page = await self._ensure_page()
            steps = page.listen.steps()
            requests_list = []
            for i, s in enumerate(steps):
                url = str(s.url) if hasattr(s, 'url') else ""
                if filter_str and filter_str not in url:
                    continue
                requests_list.append({
                    "index": i,
                    "url": url,
                    "method": s.method if hasattr(s, 'method') else "GET",
                    "status": s.status if hasattr(s, 'status') else 0,
                })
            return {"success": True, "requests": requests_list}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Storage 管理 ──

    async def storage_get(self, key: str = "") -> dict:
        try:
            page = await self._ensure_page()
            if key:
                value = await asyncio.to_thread(page.run_js, f"return localStorage.getItem('{key}')")
                return {"success": True, "key": key, "value": str(value) if value else ""}
            data = await asyncio.to_thread(page.run_js, "return JSON.stringify(window.localStorage)")
            return {"success": True, "all": json.loads(data) if data else {}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def storage_set(self, key: str, value: str) -> dict:
        try:
            page = await self._ensure_page()
            safe_val = json.dumps(value)
            await asyncio.to_thread(page.run_js, f"localStorage.setItem('{key}', {safe_val})")
            return {"success": True, "key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def storage_clear(self) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.run_js, "localStorage.clear()")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def storage_session_get(self, key: str = "") -> dict:
        try:
            page = await self._ensure_page()
            if key:
                value = await asyncio.to_thread(page.run_js, f"return sessionStorage.getItem('{key}')")
                return {"success": True, "key": key, "value": str(value) if value else ""}
            data = await asyncio.to_thread(page.run_js, "return JSON.stringify(window.sessionStorage)")
            return {"success": True, "all": json.loads(data) if data else {}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def storage_session_set(self, key: str, value: str) -> dict:
        try:
            page = await self._ensure_page()
            safe_val = json.dumps(value)
            await asyncio.to_thread(page.run_js, f"sessionStorage.setItem('{key}', {safe_val})")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def storage_session_clear(self) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.run_js, "sessionStorage.clear()")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Init Scripts ──

    async def add_init_script(self, js: str) -> dict:
        """添加页面加载前注入的 JS。"""
        try:
            page = await self._ensure_page()
            script_id = await asyncio.to_thread(
                page.run_cdp, "Page.addScriptToEvaluateOnNewDocument", source=js,
            )
            self._init_scripts[str(script_id.get("identifier", ""))] = js
            return {"success": True, "id": str(script_id.get("identifier", ""))}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def remove_init_script(self, script_id: str) -> dict:
        """移除注入脚本。"""
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(
                page.run_cdp, "Page.removeScriptToEvaluateOnNewDocument", identifier=script_id,
            )
            self._init_scripts.pop(script_id, None)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 状态持久化 ──

    async def state_save(self, filepath: str = "") -> dict:
        """保存浏览器状态（cookies + localStorage）。"""
        try:
            page = await self._ensure_page()
            path = Path(filepath) if filepath else Path(self._user_data_dir) / "browser_state.json"
            cookies = page.cookies()
            ls_data = await asyncio.to_thread(page.run_js, "return JSON.stringify(window.localStorage)")
            state = {
                "cookies": cookies,
                "localStorage": json.loads(ls_data) if ls_data else {},
                "url": page.url,
                "timestamp": time.time(),
            }
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            return {"success": True, "path": str(path), "cookie_count": len(cookies)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def state_load(self, filepath: str = "") -> dict:
        """恢复浏览器状态。"""
        try:
            page = await self._ensure_page()
            path = Path(filepath) if filepath else Path(self._user_data_dir) / "browser_state.json"
            if not path.exists():
                return {"success": False, "error": f"状态文件不存在: {path}"}
            state = json.loads(path.read_text(encoding="utf-8"))
            loaded = 0
            for c in state.get("cookies", []):
                try:
                    await asyncio.to_thread(page.set.cookies, c)
                    loaded += 1
                except Exception:
                    pass
            ls = state.get("localStorage", {})
            for k, v in ls.items():
                safe_val = json.dumps(str(v))
                await asyncio.to_thread(page.run_js, f"localStorage.setItem('{k}', {safe_val})")
            return {"success": True, "cookie_count": loaded, "ls_keys": len(ls)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @property
    def _state_file(self) -> Path:
        return Path(self._user_data_dir) / "browser_state.json"

    async def _persist_state(self) -> None:
        """内部方法：持久化 cookie 和 localStorage 到 JSON 文件（关闭前调用）。"""
        if self._page is None:
            return
        try:
            cookies = self._page.cookies()
            ls_data = await asyncio.to_thread(
                self._page.run_js, "return JSON.stringify(window.localStorage)"
            )
            state = {
                "cookies": cookies,
                "localStorage": json.loads(ls_data) if ls_data else {},
                "url": self._page.url,
                "timestamp": time.time(),
            }
            self._state_file.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    async def _restore_persisted_state(self) -> None:
        """内部方法：从 JSON 文件恢复 cookie 和 localStorage（启动后调用）。"""
        if not self._state_file.exists():
            return
        try:
            state = json.loads(self._state_file.read_text(encoding="utf-8"))
            for c in state.get("cookies", []):
                try:
                    self._page.set.cookies(c)
                except Exception:
                    pass
        except Exception:
            pass

    # ── 调试 ──

    async def get_console_logs(self) -> dict:
        """获取页面 console 日志。"""
        try:
            page = await self._ensure_page()
            logs = await asyncio.to_thread(
                page.run_js,
                "return (window.__consoleLogs || []).join('\\n')",
            )
            return {"success": True, "logs": str(logs) if logs else ""}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def clear_console_logs(self) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.run_js, "window.__consoleLogs = []")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_page_errors(self) -> dict:
        """获取页面错误。"""
        try:
            page = await self._ensure_page()
            errors = await asyncio.to_thread(
                page.run_js,
                "return (window.__pageErrors || []).join('\\n')",
            )
            return {"success": True, "errors": str(errors) if errors else ""}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def clear_page_errors(self) -> dict:
        try:
            page = await self._ensure_page()
            await asyncio.to_thread(page.run_js, "window.__pageErrors = []")
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def highlight_element(self, selector: str) -> dict:
        """在页面中高亮元素。"""
        try:
            el = await asyncio.to_thread(self._find_element, selector)
            if el is None:
                return {"success": False, "error": f"未找到元素: {selector}"}
            await asyncio.to_thread(
                el.run_js,
                "this.style.outline = '3px solid red';"
                "this.style.outlineOffset = '2px';"
                "this.scrollIntoView({behavior: 'smooth', block: 'center'});",
            )
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── 录屏 ──

    async def record_start(self, filepath: str = "") -> dict:
        """开始录屏。"""
        try:
            if self._recording:
                return {"success": False, "error": "已在录制中"}
            await self._ensure_page()
            self._recording = True
            self._recording_frames = []
            self._record_path = filepath or str(Path(self._user_data_dir) / f"recording_{int(time.time())}.gif")
            self._recording_task = asyncio.create_task(self._record_loop())
            return {"success": True, "output": self._record_path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def record_stop(self) -> dict:
        """停止录屏并保存。"""
        if not self._recording:
            return {"success": False, "error": "未在录制"}
        self._recording = False
        if self._recording_task:
            self._recording_task.cancel()
            self._recording_task = None
        frames = self._recording_frames
        self._recording_frames = []
        if not frames:
            return {"success": True, "frames": 0, "path": ""}
        try:
            from PIL import Image
            import io
            images = [Image.open(io.BytesIO(f)) for f in frames]
            out_path = self._record_path
            if out_path.endswith(".gif"):
                images[0].save(out_path, save_all=True, append_images=images[1:],
                               duration=500, loop=0, optimize=False)
            else:
                out_path = out_path.rsplit(".", 1)[0] + ".gif"
                images[0].save(out_path, save_all=True, append_images=images[1:],
                               duration=500, loop=0, optimize=False)
            return {"success": True, "frames": len(frames), "path": out_path}
        except ImportError:
            meta_path = self._record_path + ".json"
            Path(meta_path).write_text(json.dumps({"frames": len(frames)}), encoding="utf-8")
            return {"success": True, "frames": len(frames), "path": meta_path,
                    "note": "PIL not available, saved frame count only"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _recording_stop(self) -> None:
        """内部停止录屏（不返回结果）。"""
        self._recording = False
        if self._recording_task:
            self._recording_task.cancel()
            self._recording_task = None
        self._recording_frames = []

    async def _record_loop(self) -> None:
        """后台录屏循环。"""
        while self._recording:
            try:
                png = await self.screenshot()
                self._recording_frames.append(png)
                if len(self._recording_frames) > 600:
                    self._recording_frames.pop(0)
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1)

    async def record_restart(self, filepath: str = "") -> dict:
        """重启录屏（停止当前 + 开始新录制）。"""
        if self._recording:
            await self.record_stop()
        return await self.record_start(filepath)
