"""旧定时任务绑定迁移：真实群号/QQ号 → 官方合成 ID。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from neobot_app.runtime.scheduled_tasks import ScheduledTaskManager
from neobot_app.user_identity import bind_user_identity, link_group_number, link_user_qq


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.warning_fields: list[dict] = []
        self.debugs: list[str] = []
        self.infos: list[tuple[str, dict]] = []

    def warning(self, message: str, **kwargs) -> None:
        self.warnings.append(message)
        self.warning_fields.append(kwargs)

    def debug(self, message: str, **kwargs) -> None:
        self.debugs.append(message)

    def info(self, message: str, **kwargs) -> None:
        self.infos.append((message, kwargs))


class _Store:
    def __init__(self, updates: list[dict]) -> None:
        self._updates = updates

    async def update(self, task_uuid: str, **kwargs) -> None:
        self._updates.append({"task_uuid": task_uuid, **kwargs})


class _Uow:
    def __init__(self, store: _Store) -> None:
        self.scheduled_tasks = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.fixture(autouse=True)
def _identity(tmp_path):
    from neobot_app.runtime import legacy_bindings

    bind_user_identity(tmp_path)
    legacy_bindings._LOGGED.clear()
    yield
    bind_user_identity(None)


async def test_migrate_legacy_bindings_rewrites_mapped_targets() -> None:
    assert link_group_number(8000000000003, 123456789, channel="official", trusted=True)[0]
    assert link_user_qq(9000000000003, 3514733681, trusted=True)[0]
    updates: list[dict] = []
    logger = _Logger()
    store = _Store(updates)
    manager = ScheduledTaskManager(
        uow_factory=lambda: _Uow(store),
        logger=logger,
    )
    manager._orchestrator = SimpleNamespace(_adapter=SimpleNamespace(active_channels=("official",)))
    task = SimpleNamespace(
        task_uuid="t1",
        bindings=(
            SimpleNamespace(kind="group", id="123456789"),
            SimpleNamespace(kind="private", id="3514733681"),
            SimpleNamespace(kind="group", id="9500000000005"),
        ),
    )
    manager._list_active_tasks = lambda: _async_value([task])  # type: ignore[method-assign]
    await manager.migrate_legacy_bindings()

    assert len(updates) == 1
    ids = [binding.id for binding in updates[0]["bindings"]]
    assert ids == ["8000000000003", "9000000000003", "9500000000005"]
    assert logger.warnings == []
    assert any("已迁移" in message for message, _kw in logger.infos)
    # 没有缺映射目标时不记「未迁移」汇总
    assert not any("未迁移" in message for message, _kw in logger.infos)


async def test_migrate_legacy_bindings_summarizes_missing_mappings() -> None:
    updates: list[dict] = []
    logger = _Logger()
    manager = ScheduledTaskManager(uow_factory=lambda: _Uow(_Store(updates)), logger=logger)
    manager._orchestrator = SimpleNamespace(_adapter=SimpleNamespace(active_channels=("official",)))
    # 两个任务指向同一个缺映射目标：按「目标」计数一次，不是按任务/绑定计数
    tasks = [
        SimpleNamespace(task_uuid="t2", bindings=(SimpleNamespace(kind="group", id="222222222"),)),
        SimpleNamespace(task_uuid="t3", bindings=(SimpleNamespace(kind="group", id="222222222"),)),
    ]
    manager._list_active_tasks = lambda: _async_value(tasks)  # type: ignore[method-assign]
    await manager.migrate_legacy_bindings()

    assert updates == []
    # 逐条只记 DEBUG（且同一目标去重一次），不再逐条 WARNING
    assert logger.warnings == []
    assert len(logger.debugs) == 1
    summaries = [(message, kw) for message, kw in logger.infos if "未迁移" in message]
    assert len(summaries) == 1
    assert summaries[0][1]["targets"] == 1


# ── 迁移任务纳入 shutdown 管理 ──────────────────────────────────────


async def test_set_orchestrator_tracks_and_shutdown_cancels_migration() -> None:
    """set_orchestrator 启动的迁移任务有引用；shutdown 取消并等待它真正退出。"""
    started = asyncio.Event()
    release = asyncio.Event()
    manager = ScheduledTaskManager(uow_factory=lambda: _Uow(_Store([])), logger=_Logger())

    async def blocking_migration() -> None:
        started.set()
        await release.wait()

    manager.migrate_legacy_bindings = blocking_migration  # type: ignore[method-assign]

    manager.set_orchestrator(
        SimpleNamespace(_adapter=SimpleNamespace(active_channels=("official",)))
    )
    task = manager._legacy_migration_task
    assert task is not None
    await asyncio.wait_for(started.wait(), timeout=1)

    await manager.shutdown()

    # cancelled 只有在任务真正收到取消并退出后才为 True：证明 shutdown 等到了 gather。
    assert task.cancelled()
    assert manager._legacy_migration_task is None


async def test_migration_task_exception_logged_and_not_raised_from_shutdown() -> None:
    """迁移任务意外异常记 WARNING，不冒泡到 shutdown/事件循环。"""
    logger = _Logger()
    manager = ScheduledTaskManager(uow_factory=lambda: _Uow(_Store([])), logger=logger)

    async def failing_migration() -> None:
        raise RuntimeError("migration exploded")

    manager.migrate_legacy_bindings = failing_migration  # type: ignore[method-assign]
    manager.set_orchestrator(
        SimpleNamespace(_adapter=SimpleNamespace(active_channels=("official",)))
    )
    task = manager._legacy_migration_task
    assert task is not None

    for _ in range(100):
        if logger.warnings:
            break
        await asyncio.sleep(0)
    assert task.done()
    assert logger.warnings == ["旧定时任务绑定迁移任务异常"]
    assert logger.warning_fields[-1]["error_type"] == "RuntimeError"
    assert "migration exploded" in logger.warning_fields[-1]["error"]

    # 已由 done callback 回收的异常不能再从 shutdown 冒出来
    await manager.shutdown()


async def _async_value(value):
    return value
