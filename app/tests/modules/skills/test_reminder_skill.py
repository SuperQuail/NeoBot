"""ReminderSkill 定时提醒测试 — 创建/查询/修改/策略/删除与并发限流。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any

from neobot_app.skills.reminder_skill import ReminderSkill
from neobot_contracts.models.scheduled_task import (
    ScheduledTaskRecurrence,
    ScheduledTaskState,
)
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base

START_AT = "2030-01-01T09:00:00+08:00"
END_AT = "2030-01-01T10:00:00+08:00"
PIPELINE_KEY = "group:888888"


def _config(*, max_repeating_tasks: int = 15, default_one_shot: bool = True):
    return SimpleNamespace(
        scheduled_task=SimpleNamespace(
            max_repeating_tasks=max_repeating_tasks,
            default_one_shot_notification=default_one_shot,
        )
    )


async def _make_skill(tmp_path, config=None):
    engine = create_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'reminder-test.sqlite3').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    uow_factory = make_uow_factory(engine)
    skill = ReminderSkill(uow_factory=uow_factory, config=config or _config())
    return skill, engine, uow_factory


def _create_args(**overrides: Any) -> dict:
    args = {
        "title": "喝水提醒",
        "detail": "该喝水了",
        "recurrence": "daily",
        "start_at": START_AT,
        "end_at": END_AT,
        "bindings": [{"kind": "group", "id": "888888"}],
    }
    args.update(overrides)
    return args


async def test_create_once_task_persists_fields(tmp_path):
    """正常路径：创建 once 任务应成功并持久化全部字段与默认通知策略。"""
    skill, engine, uow_factory = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("create_scheduled_task", _create_args(recurrence="once"))
        )

        assert result["ok"] is True
        assert result["status"] == "created"
        task = result["task"]
        assert task["title"] == "喝水提醒"
        assert task["recurrence"] == "once"
        assert task["state"] == "active"

        async with uow_factory() as uow:
            record = await uow.scheduled_tasks.get(task["task_uuid"])
        assert record is not None
        assert record.metadata["one_shot_notification"] is True
    finally:
        await engine.dispose()


async def test_create_uses_default_one_shot_from_config(tmp_path):
    """边界：config 默认 one_shot=False 时创建任务应写入 False 而非固定 True。"""
    skill, engine, uow_factory = await _make_skill(
        tmp_path, config=_config(default_one_shot=False)
    )
    try:
        result = json.loads(await skill.execute("create_scheduled_task", _create_args()))

        assert result["ok"] is True
        async with uow_factory() as uow:
            record = await uow.scheduled_tasks.get(result["task"]["task_uuid"])
        assert record.metadata["one_shot_notification"] is False
    finally:
        await engine.dispose()


async def test_create_rejects_invalid_recurrence(tmp_path):
    """异常路径：未知 recurrence 应返回错误且不落库。"""
    skill, engine, uow_factory = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute(
                "create_scheduled_task", _create_args(recurrence="hourly")
            )
        )

        assert result["ok"] is False
        assert "无效的 recurrence" in result["error"]
        async with uow_factory() as uow:
            assert await uow.scheduled_tasks.list(limit=100) == []
    finally:
        await engine.dispose()


async def test_create_rejects_end_at_before_start_at(tmp_path):
    """异常路径：end_at 不晚于 start_at 时应被拒绝。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute(
                "create_scheduled_task", _create_args(end_at=START_AT)
            )
        )

        assert result["ok"] is False
        assert "end_at 必须晚于 start_at" in result["error"]
    finally:
        await engine.dispose()


async def test_create_rejects_missing_title(tmp_path):
    """异常路径：title 为空时应被拒绝。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("create_scheduled_task", _create_args(title="  "))
        )

        assert result["ok"] is False
        assert "title 不能为空" in result["error"]
    finally:
        await engine.dispose()


async def test_create_rejects_malformed_datetime(tmp_path):
    """异常路径：start_at/end_at 非 ISO 8601 时应返回格式错误。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute(
                "create_scheduled_task", _create_args(start_at="not-a-date")
            )
        )

        assert result["ok"] is False
        assert "start_at/end_at 格式错误" in result["error"]
    finally:
        await engine.dispose()


async def test_create_derives_bindings_from_pipeline_key(tmp_path):
    """边界：未传 bindings 时应回退使用 pipeline_key 构造默认绑定。"""
    skill, engine, uow_factory = await _make_skill(tmp_path)
    try:
        args = _create_args()
        args.pop("bindings")
        args["pipeline_key"] = PIPELINE_KEY

        result = json.loads(await skill.execute("create_scheduled_task", args))

        assert result["ok"] is True
        async with uow_factory() as uow:
            record = await uow.scheduled_tasks.get(result["task"]["task_uuid"])
        assert [(b.kind, str(b.id)) for b in record.bindings] == [("group", "888888")]
    finally:
        await engine.dispose()


async def test_create_rejects_missing_bindings(tmp_path):
    """异常路径：bindings 与 pipeline_key 均缺失时应被拒绝。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        args = _create_args()
        args.pop("bindings")

        result = json.loads(await skill.execute("create_scheduled_task", args))

        assert result["ok"] is False
        assert "bindings 为空" in result["error"]
    finally:
        await engine.dispose()


async def test_create_rejects_repeating_over_limit(tmp_path):
    """边界：重复任务数量达到上限后继续创建应被拒绝。"""
    skill, engine, _ = await _make_skill(tmp_path, config=_config(max_repeating_tasks=1))
    try:
        first = json.loads(await skill.execute("create_scheduled_task", _create_args()))
        assert first["ok"] is True

        second = json.loads(await skill.execute("create_scheduled_task", _create_args()))

        assert second["ok"] is False
        assert "已达上限" in second["error"]
    finally:
        await engine.dispose()


async def test_update_changes_title_and_detail(tmp_path):
    """正常路径：update 应覆盖 title/detail 并保持任务可查询。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        created = json.loads(await skill.execute("create_scheduled_task", _create_args()))
        uuid = created["task"]["task_uuid"]

        result = json.loads(
            await skill.execute("update_scheduled_task", {
                "task_uuid": uuid,
                "title": "新标题",
                "detail": "新内容",
            })
        )

        assert result["ok"] is True
        assert result["task"]["title"] == "新标题"
    finally:
        await engine.dispose()


async def test_update_unknown_task_returns_not_found(tmp_path):
    """异常路径：修改不存在的任务应返回未找到错误。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("update_scheduled_task", {
                "task_uuid": "ghost-0000",
                "title": "x",
            })
        )

        assert result["ok"] is False
        assert "未找到任务" in result["error"]
    finally:
        await engine.dispose()


async def test_update_without_fields_rejected(tmp_path):
    """异常路径：未提供任何修改字段时应被拒绝。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        created = json.loads(await skill.execute("create_scheduled_task", _create_args()))

        result = json.loads(
            await skill.execute("update_scheduled_task", {
                "task_uuid": created["task"]["task_uuid"],
            })
        )

        assert result["ok"] is False
        assert "没有提供需要修改的字段" in result["error"]
    finally:
        await engine.dispose()


async def test_set_state_disabled_hides_from_default_list(tmp_path):
    """正常路径：禁用后默认列表不可见，include_disabled=True 时可见。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        created = json.loads(await skill.execute("create_scheduled_task", _create_args()))
        uuid = created["task"]["task_uuid"]

        disabled = json.loads(
            await skill.execute("set_scheduled_task_state", {
                "task_uuid": uuid,
                "state": "disabled",
            })
        )
        assert disabled["ok"] is True
        assert disabled["task"]["state"] == "disabled"

        visible = json.loads(await skill.execute("list_scheduled_tasks", {}))
        assert visible["ok"] is True
        assert all(t["task_uuid"] != uuid for t in visible["tasks"])

        with_disabled = json.loads(
            await skill.execute("list_scheduled_tasks", {"include_disabled": True})
        )
        assert any(t["task_uuid"] == uuid for t in with_disabled["tasks"])
    finally:
        await engine.dispose()


async def test_set_state_invalid_value_rejected(tmp_path):
    """异常路径：非 active/disabled 的 state 值应被拒绝。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("set_scheduled_task_state", {
                "task_uuid": "any",
                "state": "paused",
            })
        )

        assert result["ok"] is False
        assert "无效的 state" in result["error"]
    finally:
        await engine.dispose()


async def test_set_notification_policy_updates_metadata(tmp_path):
    """正常路径：设置持续通知应写入 metadata 并清空已完成窗口。"""
    skill, engine, uow_factory = await _make_skill(tmp_path)
    try:
        created = json.loads(await skill.execute("create_scheduled_task", _create_args()))
        uuid = created["task"]["task_uuid"]

        result = json.loads(
            await skill.execute("set_scheduled_task_notification_policy", {
                "task_uuid": uuid,
                "one_shot_notification": False,
            })
        )

        assert result["ok"] is True
        assert result["one_shot_notification"] is False
        async with uow_factory() as uow:
            record = await uow.scheduled_tasks.get(uuid)
        assert record.metadata["one_shot_notification"] is False
    finally:
        await engine.dispose()


async def test_set_notification_policy_unknown_task_not_found(tmp_path):
    """异常路径：对不存在的任务设置通知策略应返回未找到错误。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("set_scheduled_task_notification_policy", {
                "task_uuid": "ghost-0000",
                "one_shot_notification": False,
            })
        )

        assert result["ok"] is False
        assert "未找到任务" in result["error"]
    finally:
        await engine.dispose()


async def test_delete_task_then_delete_again(tmp_path):
    """正常路径：删除任务应成功；重复删除应返回未找到。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        created = json.loads(await skill.execute("create_scheduled_task", _create_args()))
        uuid = created["task"]["task_uuid"]

        deleted = json.loads(
            await skill.execute("delete_scheduled_task", {"task_uuid": uuid})
        )
        assert deleted["ok"] is True
        assert deleted["status"] == "deleted"

        again = json.loads(
            await skill.execute("delete_scheduled_task", {"task_uuid": uuid})
        )
        assert again["ok"] is False
        assert "未找到任务" in again["error"]
    finally:
        await engine.dispose()


async def test_list_empty_returns_ok(tmp_path):
    """边界：无任何任务时 list 应返回 ok=True 与空列表。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(await skill.execute("list_scheduled_tasks", {}))

        assert result["ok"] is True
        assert result["tasks"] == []
    finally:
        await engine.dispose()


async def test_unknown_tool_rejected(tmp_path):
    """异常路径：未知工具名应返回 unknown reminder tool 错误。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(await skill.execute("no_such_tool", {}))

        assert result["ok"] is False
        assert "unknown reminder tool" in result["error"]
    finally:
        await engine.dispose()


async def test_unconfigured_uow_factory_rejected():
    """异常路径：未注入 uow_factory 时所有数据操作应返回配置缺失错误。"""
    skill = ReminderSkill(uow_factory=None)

    result = json.loads(await skill.execute("create_scheduled_task", _create_args()))

    assert result["ok"] is False
    assert "uow_factory 未配置" in result["error"]


class _FakeScheduledTaskRecord:
    """假任务记录，模拟仓储 create 的返回值。"""

    def __init__(
        self,
        task_uuid: str,
        title: str,
        recurrence: ScheduledTaskRecurrence,
        start_at: datetime,
        end_at: datetime,
    ) -> None:
        self.task_uuid = task_uuid
        self.title = title
        self.recurrence = recurrence
        self.start_at = start_at
        self.end_at = end_at
        self.state = ScheduledTaskState.ACTIVE


class _FakeRepo:
    """内存假仓储：count 与 create 之间让出事件循环以暴露竞态窗口。"""

    def __init__(self) -> None:
        self.records: dict[str, _FakeScheduledTaskRecord] = {}

    async def count_repeating_active(self) -> int:
        await asyncio.sleep(0)
        return sum(
            1
            for r in self.records.values()
            if r.recurrence != ScheduledTaskRecurrence.ONCE
        )

    async def create(self, **kwargs: Any) -> _FakeScheduledTaskRecord:
        await asyncio.sleep(0)
        record = _FakeScheduledTaskRecord(
            task_uuid=kwargs["task_uuid"],
            title=kwargs["title"],
            recurrence=ScheduledTaskRecurrence(kwargs["recurrence"]),
            start_at=kwargs["start_at"],
            end_at=kwargs["end_at"],
        )
        self.records[record.task_uuid] = record
        return record


class _FakeUow:
    def __init__(self, repo: _FakeRepo) -> None:
        self.scheduled_tasks = repo

    async def commit(self) -> None:
        return None

    async def __aenter__(self) -> "_FakeUow":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None


async def test_concurrent_create_can_exceed_repeating_limit():
    """并发：limit=2 时同时创建 3 个重复任务，成功数不得超过上限。"""
    repo = _FakeRepo()
    skill = ReminderSkill(uow_factory=lambda: _FakeUow(repo), config=_config(max_repeating_tasks=2))
    args = _create_args(recurrence="daily")
    args.pop("bindings")
    args["pipeline_key"] = PIPELINE_KEY

    results = await asyncio.gather(
        *(skill.execute("create_scheduled_task", dict(args)) for _ in range(3))
    )

    parsed = [json.loads(r) for r in results]
    ok_count = sum(1 for r in parsed if r["ok"])
    assert ok_count <= 2, f"并发创建成功 {ok_count} 个，超出上限 2"
