"""BrowserManager 生命周期、实例注册表与并发语义测试。

覆盖: _INSTANCE_REGISTRY 注册/注销/大小写归一/weakref 失效清理、
_kill_orphaned_chrome 跳过与匹配杀进程、_operation_lock 共享与互斥、
close 幂等、_ensure_page 异常恢复、截图/录屏文件路径与目录生成。

全部用例以 unittest.mock 替代真实浏览器（ChromiumPage/psutil/_start_sync），
不启动任何真实 Chrome 进程。
"""
from __future__ import annotations

import asyncio
import base64
import builtins
import gc
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest
from DrissionPage.errors import PageDisconnectedError

from neobot_app.browser.agent_browser import manager as manager_module
from neobot_app.browser.agent_browser.manager import BrowserManager


@pytest.fixture(autouse=True)
def _reset_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个用例前重置模块级实例注册表，保证用例间隔离。"""
    monkeypatch.setattr(manager_module, "_INSTANCE_REGISTRY", {})


class _FakePage:
    """仅暴露 run_cdp/run_js/url 的假页面，替代 ChromiumBase。"""

    def __init__(self, url: str = "https://example.test/ok") -> None:
        self.url = url

    def run_cdp(self, method: str, **kwargs) -> dict:
        return {"data": base64.b64encode(b"fake-jpeg-bytes").decode("ascii")}

    def run_js(self, script: str, *args) -> str:
        return '{"w": 800, "h": 600}'


class _BrokenPage:
    """url 读取抛 PageDisconnectedError 的假页面。"""

    @property
    def url(self) -> str:
        raise PageDisconnectedError("page gone")


class _HealthyPage:
    url = "https://example.test/healthy"


async def _async_noop(self) -> None:
    """替代 _record_loop 的空协程，避免测试中产生真实录屏循环。"""


# ── 实例注册表 ──


def test_registry_register_and_unregister_instance(tmp_path: pytest.TempPathFactory):
    """实例构造后必须注册到注册表，close/注销后必须从注册表移除且重复注销安全。"""
    ud = tmp_path / "prof"
    mgr = BrowserManager(user_data_dir=ud, browser_path="C:/nonexistent/chrome.exe")

    key = str(ud).lower()
    refs = manager_module._INSTANCE_REGISTRY.get(key)

    assert refs is not None and len(refs) == 1
    assert list(refs)[0]() is mgr

    manager_module._unregister_instance(mgr)

    assert key not in manager_module._INSTANCE_REGISTRY

    manager_module._unregister_instance(mgr)


def test_registry_key_is_normalized_to_lowercase(tmp_path: pytest.TempPathFactory):
    """注册表按 user_data_dir 小写分组，不同大小写的路径必须命中同一桶。"""

    class _FakeMgr:
        _user_data_dir = str(tmp_path / "PROF")

    manager_module._register_instance(_FakeMgr())

    key = str(tmp_path / "prof").lower()

    assert key in manager_module._INSTANCE_REGISTRY
    assert len(manager_module._INSTANCE_REGISTRY[key]) == 1


def test_registry_cleans_dead_weakrefs(tmp_path: pytest.TempPathFactory):
    """实例被回收后，注册表中的失效弱引用必须被 _has_other_live_instances 清理。"""
    ud = tmp_path / "prof"
    mgr1 = BrowserManager(user_data_dir=ud, browser_path="C:/nonexistent/chrome.exe")
    mgr2 = BrowserManager(user_data_dir=ud, browser_path="C:/nonexistent/chrome.exe")

    del mgr1
    gc.collect()

    assert not manager_module._has_other_live_instances(mgr2)

    key = str(ud).lower()
    live = [ref for ref in manager_module._INSTANCE_REGISTRY[key] if ref() is not None]

    assert len(live) == 1
    assert live[0]() is mgr2


# ── 残留 Chrome 进程清理 ──


def test_kill_orphaned_chrome_skipped_when_other_live_instance(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    """同 profile 仍有存活实例时，_kill_orphaned_chrome 必须直接返回且不 import psutil。"""
    monkeypatch.setattr(manager_module, "_WINDOWS", True)
    monkeypatch.setattr(manager_module, "_has_other_live_instances", lambda mgr: True)
    seen: list[str] = []
    real_import = builtins.__import__

    def guarded_import(name: str, *args, **kwargs):
        if name == "psutil":
            seen.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    mgr = object.__new__(BrowserManager)
    mgr._user_data_dir = str(tmp_path / "prof")

    mgr._kill_orphaned_chrome()

    assert seen == []


def test_kill_orphaned_chrome_skipped_on_non_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    """非 Windows 平台 _kill_orphaned_chrome 必须直接返回，不执行任何进程枚举。"""
    monkeypatch.setattr(manager_module, "_WINDOWS", False)
    seen: list[str] = []
    real_import = builtins.__import__

    def guarded_import(name: str, *args, **kwargs):
        if name == "psutil":
            seen.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    mgr = object.__new__(BrowserManager)
    mgr._user_data_dir = str(tmp_path / "prof")

    mgr._kill_orphaned_chrome()

    assert seen == []


def test_kill_orphaned_chrome_kills_matching_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    """无存活实例时，只杀 cmdline 包含该 user_data_dir 的 chrome 进程，跳过无关进程。"""
    monkeypatch.setattr(manager_module, "_WINDOWS", True)
    monkeypatch.setattr(manager_module, "_has_other_live_instances", lambda mgr: False)
    fake_psutil = MagicMock()
    chrome_proc = MagicMock()
    chrome_proc.info = {
        "pid": 1234,
        "name": "chrome.exe",
        "cmdline": [f"--user-data-dir={tmp_path / 'prof'}"],
    }
    other_proc = MagicMock()
    other_proc.info = {"pid": 99, "name": "notepad.exe", "cmdline": ["C:\\n.exe"]}
    fake_psutil.process_iter.return_value = [chrome_proc, other_proc]
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    mgr = object.__new__(BrowserManager)
    mgr._user_data_dir = str(tmp_path / "prof")

    mgr._kill_orphaned_chrome()

    fake_psutil.process_iter.assert_called_once_with(["pid", "name", "cmdline"])
    victim = fake_psutil.Process.return_value
    victim.kill.assert_called_once()
    victim.wait.assert_called_once()


# ── _operation_lock 共享与串行化 ──


def test_operation_lock_passed_in_is_stored_shared(tmp_path: pytest.TempPathFactory):
    """外部传入的 operation_lock 必须被原样保存，不能新建替代实例。"""
    lock = asyncio.Lock()

    mgr = BrowserManager(user_data_dir=tmp_path / "p", operation_lock=lock)

    assert mgr._operation_lock is lock


async def test_operation_lock_serializes_concurrent_critical_sections(
    tmp_path: pytest.TempPathFactory,
):
    """两个共享同一把 operation_lock 的实例并发执行临界区时，必须严格互斥。"""
    lock = asyncio.Lock()
    mgr_a = BrowserManager(user_data_dir=tmp_path / "a", operation_lock=lock)
    mgr_b = BrowserManager(user_data_dir=tmp_path / "b", operation_lock=lock)
    events: list[str] = []

    async def op(name: str, mgr: BrowserManager) -> None:
        async with mgr._operation_lock:
            events.append(f"{name}-in")
            await asyncio.sleep(0.02)
            events.append(f"{name}-out")

    await asyncio.gather(op("a", mgr_a), op("b", mgr_b))

    assert events == ["a-in", "a-out", "b-in", "b-out"]


# ── close 幂等 ──


async def test_close_is_idempotent_and_unregisters(tmp_path: pytest.TempPathFactory):
    """close 后实例从注册表移除并清空页面引用；重复 close 必须是无副作用空操作。"""
    ud = tmp_path / "prof"
    mgr = BrowserManager(user_data_dir=ud, browser_path="C:/nonexistent/chrome.exe")
    fake_session = MagicMock()
    mgr._session_page = fake_session
    mgr._chrome_pid = None
    key = str(ud).lower()

    await mgr.close()

    assert fake_session.quit.call_count == 1
    assert key not in manager_module._INSTANCE_REGISTRY
    assert mgr._page is None
    assert mgr._session_page is None

    await mgr.close()

    assert fake_session.quit.call_count == 1
    assert mgr._page is None


async def test_close_cancels_active_recording(tmp_path: pytest.TempPathFactory):
    """录制中调用 close 必须停止录屏任务并复位录制状态。"""
    mgr = BrowserManager(user_data_dir=tmp_path / "prof", browser_path="C:/nonexistent/chrome.exe")
    mgr._recording = True
    task = asyncio.create_task(asyncio.sleep(30))
    mgr._recording_task = task
    mgr._session_page = None

    await mgr.close()
    await asyncio.sleep(0)

    assert task.cancelled() is True
    assert mgr._recording is False
    assert mgr._recording_task is None


# ── _ensure_page 异常恢复 ──


async def test_ensure_page_recovers_when_page_disconnected():
    """页面断线（PageDisconnectedError）时 _ensure_page 必须 close+start 重建并返回新页面。"""
    mgr = object.__new__(BrowserManager)
    mgr._page = _BrokenPage()
    healthy = _HealthyPage()
    mgr.close = AsyncMock()
    mgr.start = AsyncMock(side_effect=lambda: setattr(mgr, "_page", healthy))

    page = await mgr._ensure_page()

    assert page is healthy
    mgr.close.assert_awaited_once()
    mgr.start.assert_awaited_once()


async def test_ensure_page_recovers_from_any_exception():
    """当前实现下任意 url 读取异常（含非断线异常）都会触发整机重启恢复。"""

    class _FailingPage:
        @property
        def url(self) -> str:
            raise RuntimeError("boom")

    mgr = object.__new__(BrowserManager)
    mgr._page = _FailingPage()
    healthy = _HealthyPage()
    mgr.close = AsyncMock()
    mgr.start = AsyncMock(side_effect=lambda: setattr(mgr, "_page", healthy))

    page = await mgr._ensure_page()

    assert page is healthy
    mgr.close.assert_awaited_once()
    mgr.start.assert_awaited_once()


async def test_ensure_page_keeps_healthy_page():
    """页面正常时 _ensure_page 必须直接返回当前页面，不触发 close/start。"""
    mgr = object.__new__(BrowserManager)
    healthy = _HealthyPage()
    mgr._page = healthy
    mgr.close = AsyncMock()
    mgr.start = AsyncMock()

    page = await mgr._ensure_page()

    assert page is healthy
    mgr.close.assert_not_awaited()
    mgr.start.assert_not_awaited()


# ── 截图文件路径 ──


async def test_screenshot_writes_jpeg_bytes_to_requested_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    """screenshot(path=...) 必须把 CDP 返回的 base64 解码后写入指定文件并返回 bytes。"""
    mgr = BrowserManager(user_data_dir=tmp_path / "prof", browser_path="C:/nonexistent/chrome.exe")
    fake = _FakePage()
    monkeypatch.setattr(mgr, "_ensure_page", AsyncMock(return_value=fake))

    jpg = await mgr.screenshot(path=tmp_path / "shots" / "a.jpg")

    assert jpg == b"fake-jpeg-bytes"
    assert (tmp_path / "shots" / "a.jpg").read_bytes() == b"fake-jpeg-bytes"


async def test_screenshot_full_page_includes_clip_region(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    """full_page=True 时必须读取页面尺寸并给 CDP 传 clip 区域参数。"""
    mgr = BrowserManager(user_data_dir=tmp_path / "prof", browser_path="C:/nonexistent/chrome.exe")
    fake = _FakePage()
    calls: list[tuple[str, dict]] = []

    def run_cdp(method: str, **kwargs) -> dict:
        calls.append((method, kwargs))
        return {"data": base64.b64encode(b"fake-jpeg-bytes").decode("ascii")}

    fake.run_cdp = run_cdp
    monkeypatch.setattr(mgr, "_ensure_page", AsyncMock(return_value=fake))

    await mgr.screenshot(full_page=True)

    assert calls[0][0] == "Page.captureScreenshot"
    assert calls[0][1]["clip"]["width"] == 800
    assert calls[0][1]["clip"]["height"] == 600


# ── 录屏路径与并发 ──


async def test_record_start_uses_default_gif_path_under_user_data_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    """未指定路径时 record_start 必须生成 user_data_dir 下的 gif 路径并进入录制态。"""
    ud = tmp_path / "prof"
    mgr = BrowserManager(user_data_dir=ud, browser_path="C:/nonexistent/chrome.exe")
    monkeypatch.setattr(mgr, "_ensure_page", AsyncMock(return_value=_FakePage()))
    monkeypatch.setattr(manager_module.BrowserManager, "_record_loop", _async_noop)

    result = await mgr.record_start()

    assert result["success"] is True
    assert str(result["output"]).startswith(str(ud))
    assert str(result["output"]).endswith(".gif")
    assert mgr._record_path == result["output"]
    assert mgr._recording is True

    stop = await mgr.record_stop()

    assert stop["success"] is True
    assert stop["frames"] == 0
    assert mgr._recording is False


async def test_record_start_accepts_explicit_filepath(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    """显式传入 filepath 时 record_start 必须原样使用该路径。"""
    mgr = BrowserManager(user_data_dir=tmp_path / "prof", browser_path="C:/nonexistent/chrome.exe")
    monkeypatch.setattr(mgr, "_ensure_page", AsyncMock(return_value=_FakePage()))
    monkeypatch.setattr(manager_module.BrowserManager, "_record_loop", _async_noop)

    result = await mgr.record_start(filepath=str(tmp_path / "custom.gif"))

    assert result["success"] is True
    assert result["output"] == str(tmp_path / "custom.gif")

    await mgr.record_stop()


async def test_record_start_rejects_second_recording_sequentially(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    """顺序调用时，录制中再次 record_start 必须返回「已在录制中」错误。"""
    mgr = BrowserManager(user_data_dir=tmp_path / "prof", browser_path="C:/nonexistent/chrome.exe")
    monkeypatch.setattr(mgr, "_ensure_page", AsyncMock(return_value=_FakePage()))
    monkeypatch.setattr(manager_module.BrowserManager, "_record_loop", _async_noop)
    await mgr.record_start()

    second = await mgr.record_start()

    assert second == {"success": False, "error": "已在录制中"}

    await mgr.record_stop()


@pytest.mark.xfail(
    reason="BUG-002 record_start 的录制状态检查与状态设置之间没有任何锁或 await 屏障，"
    "asyncio.gather 并发双任务可同时通过检查并双双进入录制态",
    strict=False,
)
async def test_concurrent_record_start_is_serialized(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    """并发双任务调用 record_start 必须互斥：仅一个成功，另一个返回「已在录制中」。"""
    mgr = BrowserManager(user_data_dir=tmp_path / "prof", browser_path="C:/nonexistent/chrome.exe")

    async def slow_ensure():
        await asyncio.sleep(0)
        return _FakePage()

    monkeypatch.setattr(mgr, "_ensure_page", slow_ensure)
    monkeypatch.setattr(manager_module.BrowserManager, "_record_loop", _async_noop)

    first, second = await asyncio.gather(mgr.record_start(), mgr.record_start())

    assert not (first["success"] and second["success"])

    mgr._recording = False
    await mgr.record_stop()
