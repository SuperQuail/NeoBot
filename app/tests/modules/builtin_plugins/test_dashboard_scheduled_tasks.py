"""真实技能管理器与数据库驱动的面板定时任务回归测试。"""

from pathlib import Path

import httpx

from neobot_app.skills.base import SkillManager
from neobot_app.skills.reminder_skill import ReminderSkill
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base

from test_dashboard_api import _login
from test_dashboard_management import _Services, _start_management_panel


async def test_scheduled_task_crud_with_registered_reminder(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{(tmp_path / 'tasks.sqlite3').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    uow_factory = make_uow_factory(engine)
    # 工具定义尚未向 Agent 展开，也应当能从面板管理任务。
    manager = SkillManager(eager_tool_skills=[])
    manager.register(ReminderSkill(uow_factory=uow_factory))
    server, base = await _start_management_panel(tmp_path, services=_Services({"skill_manager": manager}))
    try:
        token, csrf = await _login(base)
        async with httpx.AsyncClient(base_url=base, headers={"X-Token": token, "X-CSRF-Token": csrf}) as client:
            created = await client.post(
                "/api/scheduled-tasks/action",
                json={
                    "action": "create",
                    "title": "喝水提醒",
                    "detail": "每天喝水",
                    "recurrence": "daily",
                    "start_at": "2030-01-01T09:00:00+08:00",
                    "end_at": "2030-01-01T10:00:00+08:00",
                    "bindings": [{"kind": "group", "id": "888"}],
                },
            )
            assert created.status_code == 200, created.text
            task_uuid = created.json()["result"]["task"]["task_uuid"]
            for action, fields in (
                ("update", {"title": "新的提醒"}),
                ("set_state", {"state": "disabled"}),
                ("set_notification_policy", {"one_shot_notification": False}),
            ):
                response = await client.post(
                    "/api/scheduled-tasks/action",
                    json={"action": action, "task_uuid": task_uuid, **fields},
                )
                assert response.status_code == 200, response.text
                assert response.json()["ok"] is True

            async with uow_factory() as uow:
                task = await uow.scheduled_tasks.get(task_uuid)
            assert task.title == "新的提醒"
            assert task.state.value == "disabled"
            assert task.metadata["one_shot_notification"] is False

            deleted = await client.post(
                "/api/scheduled-tasks/action",
                json={"action": "delete", "task_uuid": task_uuid},
            )
            assert deleted.status_code == 200, deleted.text
            async with uow_factory() as uow:
                assert await uow.scheduled_tasks.get(task_uuid) is None

            # 禁用或卸载技能后必须明确报不可用，不能偷偷创建另一个技能实例。
            manager.unregister("reminder")
            unavailable = await client.post(
                "/api/scheduled-tasks/action",
                json={"action": "delete", "task_uuid": task_uuid},
            )
            assert unavailable.status_code == 503
            assert "reminder skill 未加载" in unavailable.json()["error"]
    finally:
        await server.stop()
        await engine.dispose()
