"""沙箱维护周期必须离开事件循环。

_maintenance_cycle 是同步文件系统工作（整树 rglob、rmtree、shutil.move），
却由 async 方法直接执行：后台协程每 3 小时触发一次，跑在事件循环上的话整个
Bot（含所有会话、通知、心跳）会停顿数秒。
"""

from __future__ import annotations

import threading
from pathlib import Path

from neobot_app.runtime.sandbox_maintenance import SandboxMaintenanceManager


class _Logger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def warning(self, message: str, **kw) -> None:
        self.messages.append(message)

    def info(self, message: str, **kw) -> None:
        pass

    def debug(self, message: str, **kw) -> None:
        pass

    def error(self, message: str, **kw) -> None:
        pass

    def exception(self, message: str, **kw) -> None:
        pass


def _manager(root: Path) -> SandboxMaintenanceManager:
    return SandboxMaintenanceManager(sandbox_root=root, logger=_Logger())


async def test_maintenance_cycle_runs_in_worker_thread(tmp_path: Path) -> None:
    loop_thread = threading.get_ident()
    root = tmp_path / "sandbox"
    root.mkdir()
    manager = _manager(root)

    seen: list[int] = []
    original = manager._maintenance_cycle_sync

    def _spy(*, force: bool = False):
        seen.append(threading.get_ident())
        return original(force=force)

    manager._maintenance_cycle_sync = _spy  # type: ignore[method-assign]

    result = await manager.run_once(force=True)

    assert result["ok"] is True
    assert seen and seen[0] != loop_thread


async def test_maintenance_cycle_still_reports_skips(tmp_path: Path) -> None:
    """线程化不改语义：无变更且未强制时仍返回 skipped。"""
    root = tmp_path / "sandbox"
    root.mkdir()
    manager = _manager(root)

    await manager.run_once(force=True)  # 建立基线标记
    second = await manager.run_once()

    assert second["ok"] is True
    assert second.get("skipped") is True
