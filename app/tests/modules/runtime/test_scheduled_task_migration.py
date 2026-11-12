"""旧定时任务绑定迁移：真实群号/QQ号 → 官方合成 ID。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_app.runtime.scheduled_tasks import ScheduledTaskManager
from neobot_app.user_identity import bind_user_identity, link_group_number, link_user_qq


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.debugs: list[str] = []
        self.infos: list[tuple[str, dict]] = []

    def warning(self, message: str, **kwargs) -> None:
        self.warnings.append(message)

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


async def _async_value(value):
    return value
