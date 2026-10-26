"""浏览器可执行文件发现与本进程实例注册表（模块级状态与纯函数）。"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import sys
import threading
import weakref
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .manager import BrowserManager

_MAX_RETRIES = 2
_RETRY_INTERVAL = 1.0

_WINDOWS = platform.system() == "Windows"

_logger = logging.getLogger("neobot.browser")

# 本进程内所有存活 BrowserManager 实例的注册表（按 user_data_dir 小写分组）。
# DrissionPage 某些版本取不到 chrome 主进程 pid，因此无法按 pid 判定归属；
# 这里用实例弱引用判定"该用户数据目录是否仍有存活实例持有"。
# _kill_orphaned_chrome 只清理"没有任何存活实例"的目录下的残留进程，
# 避免并发/先后启动的实例互相杀死对方刚启动的浏览器。
_INSTANCE_REGISTRY: dict[str, set[weakref.ReferenceType]] = {}
_REGISTRY_LOCK = threading.Lock()


def _facade_attr(name: str, default: Any) -> Any:
    """读门面模块属性：测试会 monkeypatch 门面上的注册表/平台开关，拆分后必须仍生效。"""
    facade = sys.modules.get("neobot_app.browser.agent_browser.manager")
    if facade is None or not hasattr(facade, name):
        return default
    return getattr(facade, name)


def _windows() -> bool:
    return bool(_facade_attr("_WINDOWS", _WINDOWS))


def _register_instance(manager: "BrowserManager") -> None:
    registry = _facade_attr("_INSTANCE_REGISTRY", _INSTANCE_REGISTRY)
    with _facade_attr("_REGISTRY_LOCK", _REGISTRY_LOCK):
        registry.setdefault(manager._user_data_dir.lower(), set()).add(
            weakref.ref(manager)
        )


def _unregister_instance(manager: "BrowserManager") -> None:
    registry = _facade_attr("_INSTANCE_REGISTRY", _INSTANCE_REGISTRY)
    with _facade_attr("_REGISTRY_LOCK", _REGISTRY_LOCK):
        refs = registry.get(manager._user_data_dir.lower())
        if refs is None:
            return
        for ref in list(refs):
            if ref() is manager:
                refs.discard(ref)
        if not refs:
            registry.pop(manager._user_data_dir.lower(), None)


def _has_other_live_instances(manager: "BrowserManager") -> bool:
    """该用户数据目录下是否存在除 manager 之外仍存活的实例。"""
    registry = _facade_attr("_INSTANCE_REGISTRY", _INSTANCE_REGISTRY)
    with _facade_attr("_REGISTRY_LOCK", _REGISTRY_LOCK):
        ud = manager._user_data_dir.lower()
        refs = registry.get(ud)
        if not refs:
            return False
        live = {ref for ref in refs if ref() is not None}
        if len(live) != len(refs):
            if live:
                registry[ud] = live
            else:
                registry.pop(ud, None)
        return any(ref() is not manager for ref in live)


def _other_live_instances(manager: "BrowserManager") -> bool:
    """按门面模块取判定函数：测试会在门面上替换 _has_other_live_instances。"""
    checker = _facade_attr("_has_other_live_instances", _has_other_live_instances)
    return bool(checker(manager))


def _playwright_chromium_path() -> str:
    """查找 Playwright 下载的 Chromium 路径。"""
    home = Path.home()
    if _windows():
        candidates = list((home / "AppData" / "Local" / "ms-playwright").glob("chromium-*/chrome-win/chrome.exe"))
    elif platform.system() == "Linux":
        browser_cache = home / ".cache" / "ms-playwright"
        candidates = list(browser_cache.glob("chromium-*/chrome-linux/chrome"))
        candidates.extend(browser_cache.glob("chromium-*/chrome-linux64/chrome"))
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
