"""BirthdaySkill 生日记录测试 — 日期解析/闰年钳制/跨年/限流。"""

from __future__ import annotations

import calendar
import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

from neobot_app.skills.birthday_skill import BirthdaySkill
from neobot_app.time_context import now_local, to_local
from neobot_contracts.models.scheduled_task import ScheduledTaskRecurrence
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base

PIPELINE_KEY = "private:123456"


def _config(*, max_repeating_tasks: int = 15):
    return SimpleNamespace(
        scheduled_task=SimpleNamespace(max_repeating_tasks=max_repeating_tasks)
    )


async def _make_skill(tmp_path, config=None):
    engine = create_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'birthday-test.sqlite3').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    uow_factory = make_uow_factory(engine)
    skill = BirthdaySkill(uow_factory=uow_factory, config=config or _config())
    return skill, engine, uow_factory


def _create_args(**overrides: Any) -> dict:
    args = {
        "person_name": "小明",
        "birthday": "12-25",
        "bindings": [{"kind": "private", "id": "123456"}],
        "celebration_style": "一起吃蛋糕",
        "relationship_context": "高中同学",
    }
    args.update(overrides)
    return args


async def test_create_birthday_mm_dd_creates_yearly_task(tmp_path):
    """正常路径：MM-DD 格式生日应创建 yearly 任务并返回下次发生时间。"""
    skill, engine, uow_factory = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("create_birthday_task", _create_args())
        )

        assert result["ok"] is True
        assert result["status"] == "birthday_task_created"
        task = result["task"]
        assert task["person_name"] == "小明"
        assert task["birthday"] == "12-25"
        assert "next_occurrence" in task

        async with uow_factory() as uow:
            record = await uow.scheduled_tasks.get(task["task_uuid"])
        assert record is not None
        assert record.recurrence == ScheduledTaskRecurrence.YEARLY
        assert record.metadata["type"] == "birthday"
        assert record.metadata["birthday"] == "12-25"
        assert record.metadata["one_shot_notification"] is True
    finally:
        await engine.dispose()


async def test_create_birthday_full_date_accepted(tmp_path):
    """正常路径：YYYY-MM-DD 完整日期应被接受并提取 MM-DD。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("create_birthday_task", _create_args(birthday="2026-05-20"))
        )

        assert result["ok"] is True
        assert result["task"]["birthday"] == "05-20"
    finally:
        await engine.dispose()


async def test_create_rejects_missing_person_name(tmp_path):
    """异常路径：person_name 为空时应被拒绝。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("create_birthday_task", _create_args(person_name="  "))
        )

        assert result["ok"] is False
        assert "person_name 不能为空" in result["error"]
    finally:
        await engine.dispose()


async def test_create_rejects_bad_birthday_format(tmp_path):
    """异常路径：长度或分隔符不符合 MM-DD/YYYY-MM-DD 时应返回格式错误。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("create_birthday_task", _create_args(birthday="2026-1-1"))
        )

        assert result["ok"] is False
        assert "birthday 格式错误" in result["error"]
    finally:
        await engine.dispose()


async def test_create_rejects_out_of_range_month_or_day(tmp_path):
    """异常路径：月份 13 或日期 32 等越界值应解析失败。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        for bad in ("13-01", "01-32"):
            result = json.loads(
                await skill.execute("create_birthday_task", _create_args(birthday=bad))
            )
            assert result["ok"] is False
            assert "无法解析生日日期" in result["error"]
    finally:
        await engine.dispose()


async def test_feb_29_never_creates_impossible_date_task(tmp_path):
    """边界：非闰年 02-29 要么被钳制到 2 月最后一天，要么被拒绝，绝不生成 2/29 任务。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        today = now_local().date()
        parse_year = today.year if (today.month, today.day) != (2, 29) else today.year

        result = json.loads(
            await skill.execute("create_birthday_task", _create_args(birthday="02-29"))
        )

        if result["ok"]:
            occurrence_date = to_local(
                datetime.fromisoformat(result["task"]["next_occurrence"])
            ).date()
            expected_day = calendar.monthrange(parse_year, 2)[1]
            assert occurrence_date.day == expected_day
        else:
            assert "无法解析生日日期" in result["error"]
    finally:
        await engine.dispose()


async def test_end_time_before_start_time_rolls_to_next_day(tmp_path):
    """边界：结束时间早于开始时间（如 06:00 跨天）应形成跨午夜的 8 小时窗口。"""
    skill, engine, uow_factory = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute(
                "create_birthday_task",
                _create_args(start_time="22:00", end_time="06:00"),
            )
        )

        assert result["ok"] is True
        async with uow_factory() as uow:
            record = await uow.scheduled_tasks.get(result["task"]["task_uuid"])
        assert (record.end_at - record.start_at) == timedelta(hours=8)
        assert to_local(record.end_at).date() > to_local(record.start_at).date()
    finally:
        await engine.dispose()


async def test_birthday_never_scheduled_in_the_past(tmp_path):
    """边界：生日已过的当天应把下次发生时间安排到当前日期之后。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        today = now_local().date()
        yesterday = today - timedelta(days=1)

        result = json.loads(
            await skill.execute(
                "create_birthday_task",
                _create_args(birthday=f"{yesterday.month:02d}-{yesterday.day:02d}"),
            )
        )

        assert result["ok"] is True
        occurrence = result["task"]["next_occurrence"]
        occurrence_date = datetime.fromisoformat(occurrence).date()
        assert occurrence_date >= today
    finally:
        await engine.dispose()


async def test_invalid_start_time_format_rejected(tmp_path):
    """异常路径：start_time 非 HH:MM 格式应被拒绝。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("create_birthday_task", _create_args(start_time="早上"))
        )

        assert result["ok"] is False
        assert "start_time/end_time 格式错误" in result["error"]
    finally:
        await engine.dispose()


async def test_out_of_range_hour_rejected(tmp_path):
    """异常路径：start_time 小时越界（25:00）应返回错误而不是落库。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("create_birthday_task", _create_args(start_time="25:00"))
        )

        assert result["ok"] is False
    finally:
        await engine.dispose()


async def test_missing_bindings_rejected(tmp_path):
    """异常路径：bindings 与 pipeline_key 均缺失时应被拒绝。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        args = _create_args()
        args.pop("bindings")

        result = json.loads(await skill.execute("create_birthday_task", args))

        assert result["ok"] is False
        assert "bindings 为空" in result["error"]
    finally:
        await engine.dispose()


async def test_pipeline_key_used_as_default_binding(tmp_path):
    """正常路径：未传 bindings 时应用 pipeline_key 作为庆祝聊天流。"""
    skill, engine, uow_factory = await _make_skill(tmp_path)
    try:
        args = _create_args()
        args.pop("bindings")
        args["pipeline_key"] = PIPELINE_KEY

        result = json.loads(await skill.execute("create_birthday_task", args))

        assert result["ok"] is True
        async with uow_factory() as uow:
            record = await uow.scheduled_tasks.get(result["task"]["task_uuid"])
        assert [(b.kind, str(b.id)) for b in record.bindings] == [("private", "123456")]
    finally:
        await engine.dispose()


async def test_repeating_limit_reached_rejected(tmp_path):
    """边界：达到重复任务上限后继续记录生日应被拒绝。"""
    skill, engine, _ = await _make_skill(tmp_path, config=_config(max_repeating_tasks=1))
    try:
        first = json.loads(await skill.execute("create_birthday_task", _create_args()))
        assert first["ok"] is True

        second = json.loads(
            await skill.execute("create_birthday_task", _create_args(person_name="小红"))
        )

        assert second["ok"] is False
        assert "已达上限" in second["error"]
    finally:
        await engine.dispose()


async def test_celebration_style_and_relationship_in_detail(tmp_path):
    """正常路径：庆祝方式与关系背景应写入任务 detail 与 metadata。"""
    skill, engine, uow_factory = await _make_skill(tmp_path)
    try:
        result = json.loads(await skill.execute("create_birthday_task", _create_args()))

        assert result["ok"] is True
        async with uow_factory() as uow:
            record = await uow.scheduled_tasks.get(result["task"]["task_uuid"])
        assert "庆祝方式：一起吃蛋糕" in record.detail
        assert "关系背景：高中同学" in record.detail
        assert record.metadata["celebration_style"] == "一起吃蛋糕"
        assert record.metadata["relationship_context"] == "高中同学"
    finally:
        await engine.dispose()


async def test_unknown_tool_rejected(tmp_path):
    """异常路径：未知工具名应返回 unknown birthday tool 错误。"""
    skill, engine, _ = await _make_skill(tmp_path)
    try:
        result = json.loads(await skill.execute("no_such_tool", {}))

        assert result["ok"] is False
        assert "unknown birthday tool" in result["error"]
    finally:
        await engine.dispose()


async def test_unconfigured_uow_factory_rejected():
    """异常路径：未注入 uow_factory 时应返回配置缺失错误。"""
    skill = BirthdaySkill(uow_factory=None)

    result = json.loads(await skill.execute("create_birthday_task", _create_args()))

    assert result["ok"] is False
    assert "uow_factory 未配置" in result["error"]
