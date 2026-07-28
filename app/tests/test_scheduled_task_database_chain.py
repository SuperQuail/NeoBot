from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from neobot_app.bootstrap import _skills as skill_bootstrap
from neobot_app.skills.birthday_skill import BirthdaySkill
from neobot_app.skills.reminder_skill import ReminderSkill
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base


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
