"""LifecycleMixin：拆分自 manager.py"""

from __future__ import annotations

import asyncio
import glob as _glob
from pathlib import Path
from typing import Any, Optional

from .._compat import (
    ChromiumBase,
    ChromiumOptions,
    ChromiumPage,
    PageDisconnectedError,
    require_drissionpage,
)
from .process import (
    _find_chrome_binary,
    _logger,
    _other_live_instances,
    _register_instance,
    _unregister_instance,
    _windows,
)


class LifecycleMixin:
    """浏览器实例的构造、启动/关闭、启动模式与高可用页面包装。"""

    def __init__(
        self,
        headless: bool = True,
        user_data_dir: str | Path | None = None,
        port: int = 0,
        browser_path: str = "",
        operation_lock: asyncio.Lock | None = None,
    ):
        self._headless = headless
        self._user_data_dir = str(user_data_dir or Path.cwd() / "browser_user_data")
        self._port = port
        self._browser_path = browser_path or _find_chrome_binary()
        self._operation_lock = operation_lock if operation_lock is not None else asyncio.Lock()
        self._page: ChromiumBase | None = None
        self._session_page: ChromiumPage | None = None
        self._chrome_pid: Optional[int] = None
        # 最近一次 start() 的重试诊断（fix(26)）：失败定位用，不含敏感信息。
        self._start_attempts = 0
        self._start_first_error = ""
        self._start_last_error = ""
        self._tab_pages: dict[str, ChromiumBase] = {}
        self._recording = False
        self._recording_frames: list[bytes] = []
        self._recording_task: asyncio.Task | None = None
        self._recording_lock = asyncio.Lock()
        self._tabs: dict[int, Any] = {}
        self._tab_labels: dict[str, str] = {}
        self._init_scripts: dict[str, str] = {}
        self._device_metrics_override: dict[str, Any] | None = None
        Path(self._user_data_dir).mkdir(parents=True, exist_ok=True)
        self._cleanup_locks()
        _register_instance(self)

    def _cleanup_locks(self):
        """清理用户数据目录中 Chrome 残留的锁文件。"""
        ud = Path(self._user_data_dir)
        if not ud.exists():
            return
        for pattern in ("SingletonLock", "SingletonSocket", "lockfile"):
            for f in _glob.glob(str(ud / "**" / pattern), recursive=True):
                try:
                    Path(f).unlink(missing_ok=True)
                except Exception as exc:
                    _logger.debug("清理浏览器锁文件失败 %s: %s", f, exc)

    def _kill_orphaned_chrome(self) -> None:
        """清理使用相同用户数据目录的残留 Chrome 进程（仅 Windows）。

        浏览器关闭后 Chrome 进程可能未完全退出，导致新实例初始化时出现
        'Chromium' object has no attribute '_dl_mgr' 等异常。
        若该用户数据目录仍有其他存活实例（并发/先后启动的共享实例），
        则不清理任何进程，避免互相误杀。
        """
        if not _windows():
            return
        if _other_live_instances(self):
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
                except (_psutil.NoSuchProcess, _psutil.AccessDenied, _psutil.TimeoutExpired) as exc:
                    _logger.debug("跳过残留浏览器进程 %s: %s", proc.info.get("pid"), exc)
        except Exception as exc:
            _logger.debug("清理残留浏览器进程失败: %s", exc)

    @property
    def user_data_dir(self) -> str:
        return self._user_data_dir

    @property
    def cookie_file(self) -> Path:
        return Path(self._user_data_dir) / "cookies.json"

    @property
    def start_diagnostics(self) -> dict[str, Any]:
        """最近一次 start() 的重试诊断：attempts / first_error / last_error。"""
        return {
            "attempts": self._start_attempts,
            "first_error": self._start_first_error,
            "last_error": self._start_last_error,
        }

    # ── 生命周期 ──

    async def start(self) -> None:
        """启动浏览器，自动重试处理残留进程。"""
        # DrissionPage 不可用（常见：装成了 5.x，顶层没有 ChromiumPage）时，
        # 在这里就抛出带修复指引的错误，而不是等到调用某个属性才炸。
        require_drissionpage()
        self._kill_orphaned_chrome()
        self._start_attempts = 0
        self._start_first_error = ""
        self._start_last_error = ""
        for attempt in range(3):
            self._start_attempts = attempt + 1
            try:
                self._page = await asyncio.to_thread(self._start_sync)
                self._session_page = self._page
                _ = self._page.url
                # 浏览器就绪后自动恢复 cookie 和 localStorage
                await self._restore_persisted_state()
                return
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                if not self._start_first_error:
                    self._start_first_error = error
                self._start_last_error = error
                if attempt < 2:
                    _logger.warning(
                        "浏览器启动第 %s/3 次失败，1.5s 后重试: %s", attempt + 1, error
                    )
                    await asyncio.sleep(1.5)
                    if self._session_page:
                        try:
                            await asyncio.to_thread(self._session_page.quit)
                        except Exception as cleanup_exc:
                            _logger.debug("浏览器重试前关闭旧实例失败: %s", cleanup_exc)
                    self._page = None
                    self._session_page = None
                    self._chrome_pid = None
                    continue
                _logger.error("浏览器启动连续 3 次失败，最后一次: %s", error)
                # 最后一次失败：清引用后清理孤儿进程，再抛出原异常。
                self._page = None
                self._session_page = None
                self._chrome_pid = None
                try:
                    self._kill_orphaned_chrome()
                except Exception as cleanup_exc:
                    _logger.debug("浏览器启动失败后的孤儿进程清理失败: %s", cleanup_exc)
                exc.add_note(
                    f"浏览器启动重试 {self._start_attempts} 次仍失败；"
                    f"首次错误：{self._start_first_error}"
                )
                raise

    def _start_sync(self) -> ChromiumPage:
        page = ChromiumPage(addr_or_opts=self._make_options())
        # DrissionPage 4.x 的 Chromium 对象只有 process_id；旧版才暴露 _process.pid。
        browser = getattr(page, "browser", None)
        pid = getattr(browser, "process_id", None)
        if pid is None:
            pid = getattr(getattr(browser, "_process", None), "pid", None)
        try:
            self._chrome_pid = int(pid) if pid else None
        except (TypeError, ValueError):
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
            if self._chrome_pid and _windows():
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
        # pid 重置必须无条件执行：否则 _session_page 为空时旧 pid 会跨 start/close 残留。
        self._chrome_pid = None
        _unregister_instance(self)
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
