"""旧定时任务绑定迁移：真实群号/QQ号 → 官方合成 ID。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_app.runtime.scheduled_tasks import ScheduledTaskManager
from neobot_app.user_identity import bind_user_identity, link_group_number, link_user_qq


class _Logger:
    def __init__(self) -> None:
        self.warnings: list[str] = []
        self.infos: list[str] = []

    def warning(self, message: str, **kwargs) -> None:
        self.warnings.append(message)

    def info(self, message: str, **kwargs) -> None:
        self.infos.append(message)


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
    bind_user_identity(tmp_path)
    yield
    bind_user_identity(None)


async def test_migrate_legacy_bindings_rewrites_mapped_targets() -> None:
    assert link_group_number(8000000000003, 123456789, channel="official", trusted=True)[0]
    assert link_user_qq(9000000000003, 3514733681, trusted=True)[0]
    updates: list[dict] = []
    store = _Store(updates)
    manager = ScheduledTaskManager(
        uow_factory=lambda: _Uow(store),
        logger=_Logger(),
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


async def test_migrate_legacy_bindings_warns_missing_mapping() -> None:
    updates: list[dict] = []
    logger = _Logger()
    manager = ScheduledTaskManager(uow_factory=lambda: _Uow(_Store(updates)), logger=logger)
    manager._orchestrator = SimpleNamespace(_adapter=SimpleNamespace(active_channels=("official",)))
    task = SimpleNamespace(task_uuid="t2", bindings=(SimpleNamespace(kind="group", id="222222222"),))
    manager._list_active_tasks = lambda: _async_value([task])  # type: ignore[method-assign]
    await manager.migrate_legacy_bindings()

    assert updates == []
    assert logger.warnings


async def _async_value(value):
    return value
