"""浏览器可执行文件发现与本进程实例注册表（模块级状态与纯函数）。"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import sys
import threading
import weakref
from importlib.util import find_spec
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
        registry.setdefault(manager._user_data_dir.lower(), set()).add(weakref.ref(manager))


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


def _playwright_cache_directory() -> Path | None:
    """与 Python Playwright 安装器使用相同的缓存根目录。"""
    home = Path.home()
    env_cache = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if env_cache == "0":
        package = find_spec("playwright")
        if package is None or package.origin is None:
            return None
        return Path(package.origin).parent / "driver" / "package" / ".local-browsers"
    if env_cache:
        cache = Path(env_cache)
    elif _windows():
        cache = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / "ms-playwright"
    elif platform.system() == "Linux":
        cache = Path(os.environ.get("XDG_CACHE_HOME") or home / ".cache") / "ms-playwright"
    elif platform.system() == "Darwin":
        cache = home / "Library" / "Caches" / "ms-playwright"
    else:
        return None
    # Playwright 对相对路径优先使用安装器的 INIT_CWD，其次是当前工作目录。
    if not cache.is_absolute():
        cache = Path(os.environ.get("INIT_CWD") or Path.cwd()) / cache
    return cache.absolute()


def _playwright_chromium_path() -> str:
    """查找缓存中的完整 Chromium，优先选择最新修订号。"""
    browser_cache = _playwright_cache_directory()
    if browser_cache is None:
        return ""
    if _windows():
        # 新版 Playwright 在 Windows 上把完整浏览器放进 chrome-win64；
        # 只匹配 chrome-win 会让「刚下载完也被判定为没下载」，重启后反复重下。
        candidates = list(browser_cache.glob("chromium-*/chrome-win*/chrome.exe"))
    elif platform.system() == "Linux":
        candidates = list(browser_cache.glob("chromium-*/chrome-linux/chrome"))
        candidates.extend(browser_cache.glob("chromium-*/chrome-linux64/chrome"))
        candidates.extend(browser_cache.glob("chromium-*/chrome-linux-arm64/chrome"))
    elif platform.system() == "Darwin":
        candidates = list(browser_cache.glob("chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"))
        for layout in ("chrome-mac-arm64", "chrome-mac-x64"):
            for app in ("Chromium", "Google Chrome for Testing"):
                candidates.extend(browser_cache.glob(f"chromium-*/{layout}/{app}.app/Contents/MacOS/{app}"))
    else:
        candidates = []
    revisions = []
    for candidate in candidates:
        revision = candidate.relative_to(browser_cache).parts[0].removeprefix("chromium-")
        if revision.isdecimal() and candidate.is_file():
            revisions.append((int(revision), str(candidate)))
    return max(revisions)[1] if revisions else ""


def _windows_registry_browser_paths(executables: tuple[str, ...] = ("chrome.exe", "msedge.exe")) -> list[str]:
    """Windows App Paths 里登记的 chrome.exe / msedge.exe（不依赖固定安装盘符）。"""
    if not _windows():
        return []
    try:
        import winreg
    except ImportError:
        return []
    paths: list[str] = []
    for exe in executables:
        for hive, view in (
            (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
            (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
            (winreg.HKEY_CURRENT_USER, 0),
        ):
            key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
            try:
                with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ | view) as key:
                    value, _ = winreg.QueryValueEx(key, "")
            except OSError:
                continue
            text = str(value or "").strip().strip('"')
            if text and Path(text).is_file():
                paths.append(text)
    return paths


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
        program_files = os.getenv("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)")
        chrome_local = (
            Path(local_appdata) / "Google" / "Chrome" / "Application" / "chrome.exe" if local_appdata else None
        )
        edge_local = (
            Path(local_appdata) / "Microsoft" / "Edge" / "Application" / "msedge.exe" if local_appdata else None
        )
        candidates = [
            shutil.which("chrome") or "",
            *_windows_registry_browser_paths(("chrome.exe",)),
            str(Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe"),
            str(Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe"),
            str(chrome_local) if chrome_local else "",
            shutil.which("msedge") or "",
            *_windows_registry_browser_paths(("msedge.exe",)),
            str(Path(program_files) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
            str(Path(program_files_x86) / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
            str(edge_local) if edge_local else "",
            str(Path(program_files) / "Chromium" / "Application" / "chrome.exe"),
        ]
    elif system == "Linux":
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
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
        if expanded.is_file():
            return str(expanded)
    return ""
