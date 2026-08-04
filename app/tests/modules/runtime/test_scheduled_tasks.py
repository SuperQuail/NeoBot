from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from neobot_app.bootstrap import _skills as skill_bootstrap
from neobot_app.runtime.scheduled_tasks import (
    ScheduledTaskConfig,
    ScheduledTaskManager,
    _occurrence_start,
)
from neobot_app.skills.birthday_skill import BirthdaySkill
from neobot_app.skills.reminder_skill import ReminderSkill
from neobot_contracts.models import ConversationRef
from neobot_contracts.models.scheduled_task import (
    ScheduledTaskRecord,
    ScheduledTaskRecurrence,
)
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base, CompletedScheduledTaskData


async def _make_storage(tmp_path):
    engine = create_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'scheduled-tasks.sqlite3').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, make_uow_factory(engine)


def test_build_skill_manager_forwards_uow_factory(monkeypatch):
    captured = {}
    sentinel = object()

    def fake_build_all_skills(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(skill_bootstrap, "build_all_skills", fake_build_all_skills)
    config = SimpleNamespace(
        agent=SimpleNamespace(skill=SimpleNamespace(disabled_skills=[]))
    )
    skill_bootstrap.build_skill_manager(
        config=config,
        adapter=None,
        archive_memory_service=None,
        profile_service=None,
        uow_factory=sentinel,
        emoji_service=None,
        vision_provider=None,
        file_server=None,
        willing_service=None,
        drawing_manager=None,
        scheduled_task_manager=None,
        notification_hub=None,
        markdown_image_converter=None,
        creator_image_service=None,
        sandbox_lock=None,
        sandbox_service=None,
        sandbox_maintenance_manager=None,
        browser_instance=None,
        browser_lifecycle_manager=None,
        problem_solver_manager=None,
        image_pool=None,
    )

    assert captured["uow_factory"] is sentinel


@pytest.mark.asyncio
async def test_reminder_skill_writes_are_committed_and_policy_is_persisted(tmp_path):
    engine, uow_factory = await _make_storage(tmp_path)
    config = SimpleNamespace(
        scheduled_task=SimpleNamespace(
            default_one_shot_notification=False,
            max_repeating_tasks=15,
        )
    )
    skill = ReminderSkill(uow_factory=uow_factory, config=config)

    try:
        created = json.loads(
            await skill.execute(
                "create_scheduled_task",
                {
                    "title": "五分钟后停止服务",
                    "detail": "宣布即将在本群停止服务",
                    "recurrence": "once",
                    "start_at": "2026-07-24T01:00:00",
                    "end_at": "2026-07-24T01:05:00",
                    "bindings": [{"kind": "group", "id": "234450817"}],
                },
            )
        )
        assert created["ok"] is True
        task_uuid = created["task"]["task_uuid"]

        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(task_uuid)
        assert persisted is not None
        assert persisted.start_at == datetime(2026, 7, 23, 17, 0, tzinfo=timezone.utc)
        assert persisted.metadata["one_shot_notification"] is False

        policy_result = json.loads(
            await skill.execute(
                "set_scheduled_task_notification_policy",
                {"task_uuid": task_uuid, "one_shot_notification": True},
            )
        )
        assert policy_result["ok"] is True

        updated = json.loads(
            await skill.execute(
                "update_scheduled_task",
                {
                    "task_uuid": task_uuid,
                    "title": "即将停止服务",
                    "metadata": {"reason": "maintenance"},
                },
            )
        )
        assert updated["ok"] is True

        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(task_uuid)
        assert persisted is not None
        assert persisted.title == "即将停止服务"
        assert persisted.metadata == {
            "one_shot_notification": True,
            "reason": "maintenance",
        }

        deleted = json.loads(
            await skill.execute("delete_scheduled_task", {"task_uuid": task_uuid})
        )
        assert deleted["ok"] is True
        async with uow_factory() as uow:
            assert await uow.scheduled_tasks.get(task_uuid) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_birthday_skill_commits_created_task(tmp_path):
    engine, uow_factory = await _make_storage(tmp_path)
    skill = BirthdaySkill(uow_factory=uow_factory)

    try:
        result = json.loads(
            await skill.execute(
                "create_birthday_task",
                {
                    "person_name": "弥音",
                    "birthday": "12-24",
                    "start_time": "06:00",
                    "end_time": "22:00",
                    "bindings": [{"kind": "group", "id": "234450817"}],
                },
            )
        )
        assert result["ok"] is True

        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(result["task"]["task_uuid"])
        assert persisted is not None
        assert (persisted.end_at - persisted.start_at).total_seconds() == 16 * 60 * 60
        assert persisted.metadata["one_shot_notification"] is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scheduled_task_repository_rejects_invalid_time_window(tmp_path):
    engine, uow_factory = await _make_storage(tmp_path)

    try:
        async with uow_factory() as uow:
            with pytest.raises(ValueError, match="end_at"):
                await uow.scheduled_tasks.create(
                    task_uuid="invalid-window",
                    title="invalid",
                    detail="",
                    recurrence="once",
                    start_at=datetime(2026, 7, 24, 1, 0, tzinfo=timezone.utc),
                    end_at=datetime(2026, 7, 24, 1, 0, tzinfo=timezone.utc),
                    bindings=(),
                )
    finally:
        await engine.dispose()


class _FakeHub:
    def __init__(self, fail_bindings: set[str] | None = None) -> None:
        self.published: list[dict] = []
        self._fail_bindings = fail_bindings or set()

    async def publish(self, **kwargs) -> bool:
        key = f"{kwargs['kind']}:{kwargs['conversation_id']}"
        if key in self._fail_bindings:
            raise RuntimeError("publish boom")
        self.published.append(dict(kwargs))
        return True


def _make_manager(uow_factory, hub) -> ScheduledTaskManager:
    return ScheduledTaskManager(
        uow_factory=uow_factory,
        config=ScheduledTaskConfig(
            poll_interval_seconds=60,
            reminder_cooldown_seconds=1,
        ),
        notification_hub=hub,
    )


async def _list_archived(engine) -> list[Any]:
    async with engine.begin() as connection:
        result = await connection.execute(select(CompletedScheduledTaskData))
        return list(result.fetchall())


@pytest.mark.asyncio
async def test_scan_due_tasks_notifies_expired_short_window_once_task(tmp_path):
    """BUG-0002: 窗口短于轮询间隔的 ONCE 任务仍应收到提醒，而非被静默归档为过期。"""
    engine, uow_factory = await _make_storage(tmp_path)
    hub = _FakeHub()
    manager = _make_manager(uow_factory, hub)
    now = datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc)

    try:
        created = await manager.create_task(
            title="短窗口一次性提醒",
            detail="",
            recurrence="once",
            start_at=now - timedelta(seconds=10),
            end_at=now - timedelta(seconds=5),
            bindings=[ConversationRef(kind="group", id="111")],
        )
        await manager.scan_due_tasks(now=now)

        assert len(hub.published) == 1
        async with uow_factory() as uow:
            assert await uow.scheduled_tasks.get(created.task_uuid) is None
        archived = await _list_archived(engine)
        assert [row.task_uuid for row in archived] == [created.task_uuid]
        assert archived[0].completion_reason == "one_shot_notification_sent"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scan_due_tasks_backfills_overdue_repeating_window(tmp_path):
    """BUG-0002: 早于任何扫描就已结束的重复窗口应补发提醒，再标记完成。"""
    engine, uow_factory = await _make_storage(tmp_path)
    hub = _FakeHub()
    manager = _make_manager(uow_factory, hub)
    now = datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc)

    try:
        created = await manager.create_task(
            title="每日提醒",
            detail="",
            recurrence="daily",
            start_at=now - timedelta(minutes=30),
            end_at=now - timedelta(minutes=20),
            bindings=[ConversationRef(kind="group", id="222")],
        )
        await manager.scan_due_tasks(now=now)

        assert len(hub.published) == 1
        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(created.task_uuid)
        assert persisted is not None
        assert len(persisted.completed_window_keys) == 1

        await manager.scan_due_tasks(now=now)
        assert len(hub.published) == 1
        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(created.task_uuid)
        assert persisted is not None
        assert len(persisted.completed_window_keys) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scan_due_tasks_isolates_binding_failures(tmp_path):
    """BUG-0012: 单个任务通知失败不得回滚或阻塞其他任务的完成。"""
    engine, uow_factory = await _make_storage(tmp_path)
    hub = _FakeHub(fail_bindings={"group:111"})
    manager = _make_manager(uow_factory, hub)
    now = datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc)

    try:
        task_a = await manager.create_task(
            title="会失败的任务",
            detail="",
            recurrence="once",
            start_at=now - timedelta(seconds=10),
            end_at=now - timedelta(seconds=5),
            bindings=[ConversationRef(kind="group", id="111")],
        )
        task_b = await manager.create_task(
            title="正常任务",
            detail="",
            recurrence="once",
            start_at=now - timedelta(seconds=10),
            end_at=now - timedelta(seconds=5),
            bindings=[ConversationRef(kind="group", id="222")],
        )

        await manager.scan_due_tasks(now=now)

        assert [p["conversation_id"] for p in hub.published] == ["222"]
        async with uow_factory() as uow:
            assert await uow.scheduled_tasks.get(task_a.task_uuid) is not None
            assert await uow.scheduled_tasks.get(task_b.task_uuid) is None
        archived = await _list_archived(engine)
        assert [row.task_uuid for row in archived] == [task_b.task_uuid]
    finally:
        await engine.dispose()


def _make_record(
    *,
    start_at: datetime,
    recurrence: ScheduledTaskRecurrence,
) -> ScheduledTaskRecord:
    return ScheduledTaskRecord(
        id=1,
        task_uuid="task-uuid",
        title="t",
        detail="",
        recurrence=recurrence,
        start_at=start_at,
        end_at=start_at + timedelta(hours=1),
        bindings=(ConversationRef(kind="group", id="1"),),
    )


def test_occurrence_start_clamps_feb29_in_non_leap_year():
    """BUG-0023: 02-29 年度复现在非闰年回退到 02-28。"""
    task = _make_record(
        start_at=datetime(2024, 2, 29, 10, 0, tzinfo=timezone.utc),
        recurrence=ScheduledTaskRecurrence.YEARLY,
    )
    occurrence = _occurrence_start(task, datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc))
    assert occurrence == datetime(2026, 2, 28, 10, 0, tzinfo=timezone.utc)


def test_occurrence_start_feb29_in_leap_year():
    task = _make_record(
        start_at=datetime(2024, 2, 29, 10, 0, tzinfo=timezone.utc),
        recurrence=ScheduledTaskRecurrence.YEARLY,
    )
    occurrence = _occurrence_start(task, datetime(2028, 3, 1, 0, 0, tzinfo=timezone.utc))
    assert occurrence == datetime(2028, 2, 29, 10, 0, tzinfo=timezone.utc)


def test_occurrence_start_clamps_monthly_31st_to_short_month():
    task = _make_record(
        start_at=datetime(2026, 1, 31, 9, 0, tzinfo=timezone.utc),
        recurrence=ScheduledTaskRecurrence.MONTHLY,
    )
    occurrence = _occurrence_start(task, datetime(2026, 2, 15, 0, 0, tzinfo=timezone.utc))
    assert occurrence == datetime(2026, 2, 28, 9, 0, tzinfo=timezone.utc)


def test_current_window_duration_has_poll_interval_floor():
    """BUG-0002: 窗口时长不得短于 2 倍轮询间隔。"""
    manager = ScheduledTaskManager(config=ScheduledTaskConfig(poll_interval_seconds=60))
    start_at = datetime(2026, 8, 3, 9, 0, 0, tzinfo=timezone.utc)
    task = ScheduledTaskRecord(
        id=1,
        task_uuid="task-uuid",
        title="t",
        detail="",
        recurrence=ScheduledTaskRecurrence.ONCE,
        start_at=start_at,
        end_at=start_at + timedelta(seconds=5),
        bindings=(ConversationRef(kind="group", id="1"),),
    )
    window = manager._current_window(task, start_at + timedelta(seconds=1))
    assert window is not None
    assert (window.end - window.start).total_seconds() == 120


@pytest.mark.asyncio
async def test_birthday_skill_accepts_feb29(tmp_path):
    """BUG-0023: 创建 02-29 生日必须成功；年度复现在非闰年钳位到 02-28。"""
    engine, uow_factory = await _make_storage(tmp_path)
    skill = BirthdaySkill(uow_factory=uow_factory)

    try:
        result = json.loads(
            await skill.execute(
                "create_birthday_task",
                {
                    "person_name": "闰儿",
                    "birthday": "02-29",
                    "start_time": "06:00",
                    "end_time": "22:00",
                    "bindings": [{"kind": "group", "id": "234450817"}],
                },
            )
        )
        assert result["ok"] is True
        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(result["task"]["task_uuid"])
        assert persisted is not None
        assert persisted.metadata["birthday"] == "02-29"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_birthday_skill_feb29_occurrence_respects_leap_year(tmp_path, monkeypatch):
    """BUG-0023: 闰年保留 02-29，非闰年回退到 02-28。"""
    from neobot_app.skills import birthday_skill

    engine, uow_factory = await _make_storage(tmp_path)
    skill = BirthdaySkill(uow_factory=uow_factory)

    def _run(today_local, expected_start_utc):
        async def _create():
            monkeypatch.setattr(birthday_skill, "now_local", lambda: today_local)
            return json.loads(
                await skill.execute(
                    "create_birthday_task",
                    {
                        "person_name": "闰儿",
                        "birthday": "02-29",
                        "start_time": "06:00",
                        "end_time": "22:00",
                        "bindings": [{"kind": "group", "id": "234450817"}],
                    },
                )
            )

        return _create()

    try:
        result = await _run(
            datetime(2027, 12, 31, 12, 0),  # next occurrence lands in 2028 (leap)
            datetime(2028, 2, 28, 22, 0, tzinfo=timezone.utc),
        )
        assert result["ok"] is True
        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(result["task"]["task_uuid"])
        assert persisted is not None
        assert persisted.start_at == datetime(2028, 2, 28, 22, 0, tzinfo=timezone.utc)

        result = await _run(
            datetime(2026, 1, 15, 12, 0),  # next occurrence lands in 2026 (non-leap)
            datetime(2026, 2, 27, 22, 0, tzinfo=timezone.utc),
        )
        assert result["ok"] is True
        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(result["task"]["task_uuid"])
        assert persisted is not None
        assert persisted.start_at == datetime(2026, 2, 27, 22, 0, tzinfo=timezone.utc)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scan_due_tasks_concurrent_scans_do_not_double_notify(tmp_path):
    """Arrange 一个超期每日任务，Act 用 asyncio.gather 并发执行两次扫描，
    Assert 同一触发窗口只发布一次通知（进程内 _last_reminder_at 冷却抑制重复），
    completed_window_keys 只含一个 key。"""
    engine, uow_factory = await _make_storage(tmp_path)
    hub = _FakeHub()
    manager = _make_manager(uow_factory, hub)
    now = datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc)

    try:
        created = await manager.create_task(
            title="每日提醒",
            detail="",
            recurrence="daily",
            start_at=now - timedelta(minutes=30),
            end_at=now - timedelta(minutes=20),
            bindings=[ConversationRef(kind="group", id="333")],
        )

        await asyncio.gather(
            manager.scan_due_tasks(now=now),
            manager.scan_due_tasks(now=now),
        )

        assert len(hub.published) == 1
        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(created.task_uuid)
        assert persisted is not None
        assert len(persisted.completed_window_keys) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scan_due_tasks_backfill_completed_key_persists_across_instances(tmp_path):
    """Arrange 超期每日任务由第一个 manager 补发并标记完成，Act 用全新 manager
    实例再次扫描，Assert completed_window_keys 持久化在 DB 中且不会重复通知。"""
    engine, uow_factory = await _make_storage(tmp_path)
    now = datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc)

    try:
        first_hub = _FakeHub()
        first = _make_manager(uow_factory, first_hub)
        created = await first.create_task(
            title="每日提醒",
            detail="",
            recurrence="daily",
            start_at=now - timedelta(minutes=30),
            end_at=now - timedelta(minutes=20),
            bindings=[ConversationRef(kind="group", id="444")],
        )

        await first.scan_due_tasks(now=now)
        assert len(first_hub.published) == 1
        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(created.task_uuid)
        assert persisted is not None
        assert len(persisted.completed_window_keys) == 1

        second_hub = _FakeHub()
        second = _make_manager(uow_factory, second_hub)
        await second.scan_due_tasks(now=now)
        assert len(second_hub.published) == 0
        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(created.task_uuid)
        assert persisted is not None
        assert len(persisted.completed_window_keys) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scan_due_tasks_window_floor_keeps_short_window_open_for_repeat(tmp_path):
    """Arrange 原生窗口仅 5 秒的每日任务（poll_interval=60 下限 120 秒），
    Act 在 +10s 与 +70s 各扫描一次，Assert 均按窗口下限内的 in-window 路径提醒
    两次且 completed_window_keys 保持为空（未被误判为超期补发标记完成）。"""
    engine, uow_factory = await _make_storage(tmp_path)
    hub = _FakeHub()
    manager = _make_manager(uow_factory, hub)
    start = datetime(2026, 8, 3, 9, 0, 0, tzinfo=timezone.utc)

    try:
        created = await manager.create_task(
            title="短窗每日提醒",
            detail="",
            recurrence="daily",
            start_at=start,
            end_at=start + timedelta(seconds=5),
            bindings=[ConversationRef(kind="group", id="555")],
            metadata={"one_shot_notification": False},
        )

        await manager.scan_due_tasks(now=start + timedelta(seconds=10))
        assert len(hub.published) == 1
        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(created.task_uuid)
        assert persisted is not None
        assert persisted.completed_window_keys == ()

        await manager.scan_due_tasks(now=start + timedelta(seconds=70))
        assert len(hub.published) == 2
        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(created.task_uuid)
        assert persisted is not None
        assert persisted.completed_window_keys == ()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scan_due_tasks_archives_notified_once_task_as_expired_after_window(tmp_path):
    """Arrange 一个已通知过但未归档的 ONCE 任务（one_shot_notification=False），
    Act 在窗口结束后再扫描，Assert 不再重复通知并直接以 expired_auto_completed 归档。"""
    engine, uow_factory = await _make_storage(tmp_path)
    hub = _FakeHub()
    manager = _make_manager(uow_factory, hub)
    now = datetime(2026, 8, 3, 10, 0, 0, tzinfo=timezone.utc)
    start_at = now - timedelta(hours=2)
    end_at = now + timedelta(hours=1)

    try:
        created = await manager.create_task(
            title="一次性任务",
            detail="",
            recurrence="once",
            start_at=start_at,
            end_at=end_at,
            bindings=[ConversationRef(kind="group", id="666")],
            metadata={"one_shot_notification": False},
        )

        await manager.scan_due_tasks(now=now)
        assert len(hub.published) == 1
        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(created.task_uuid)
        assert persisted is not None

        await manager.scan_due_tasks(now=now + timedelta(hours=2))
        assert len(hub.published) == 1
        async with uow_factory() as uow:
            assert await uow.scheduled_tasks.get(created.task_uuid) is None
        archived = await _list_archived(engine)
        assert [row.task_uuid for row in archived] == [created.task_uuid]
        assert archived[0].completion_reason == "expired_auto_completed"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_scan_due_tasks_monthly_31st_occurrence_clamps_in_short_month(tmp_path):
    """Arrange 每月 31 号触发的月度任务，Act 在 2026-02-28（短月）窗口内扫描，
    Assert 触发时间被钳位到 2 月 28 日并正常发布一次通知且标记窗口完成。"""
    engine, uow_factory = await _make_storage(tmp_path)
    hub = _FakeHub()
    manager = _make_manager(uow_factory, hub)
    start_at = datetime(2026, 1, 31, 9, 0, 0, tzinfo=timezone.utc)

    try:
        created = await manager.create_task(
            title="月末任务",
            detail="",
            recurrence="monthly",
            start_at=start_at,
            end_at=start_at + timedelta(hours=2),
            bindings=[ConversationRef(kind="group", id="777")],
        )

        await manager.scan_due_tasks(
            now=datetime(2026, 2, 28, 9, 30, 0, tzinfo=timezone.utc)
        )

        assert len(hub.published) == 1
        assert "2026-02-28T09:00" in hub.published[0]["metadata"]["window_key"]
        async with uow_factory() as uow:
            persisted = await uow.scheduled_tasks.get(created.task_uuid)
        assert persisted is not None
        assert len(persisted.completed_window_keys) == 1
        assert "2026-02-28T09:00" in persisted.completed_window_keys[0]
    finally:
        await engine.dispose()
