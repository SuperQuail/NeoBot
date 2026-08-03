"""GiftSkill 测试 — 路径安全、定时任务集成与并发查重。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from neobot_app.runtime.sandbox_service import SandboxService
from neobot_app.runtime.scheduled_tasks import ScheduledTaskManager
from neobot_app.skills.gift_skill import (
    GIFT_MD,
    _build_gift_md,
    GiftSkill,
)
from neobot_contracts.models import ConversationRef
from neobot_contracts.models.scheduled_task import ScheduledTaskRecurrence
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base

TRIGGER_DATE = "2030-01-01T09:00:00+08:00"


async def _make_gift_skill(tmp_path):
    engine = create_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'gift-test.sqlite3').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    uow_factory = make_uow_factory(engine)
    skill = GiftSkill(
        sandbox_service=SandboxService(sandbox_root=tmp_path / "sandbox"),
        scheduled_task_manager=ScheduledTaskManager(uow_factory=uow_factory),
        notification_hub=None,
    )
    return skill, engine, uow_factory


async def test_path_traversal_create_rejected(tmp_path):
    """异常路径：user_id='..' 时创建礼物必须被拒绝且不产生目录（当前 src 已回归）。"""
    skill, engine, _ = await _make_gift_skill(tmp_path)
    try:
        victim = tmp_path / "sandbox" / "victim"
        victim.mkdir(parents=True)
        (victim / "secret.txt").write_text("keep me", encoding="utf-8")

        result = json.loads(
            await skill.execute("create_gift", {
                "user_id": "..",
                "idea": "test",
                "trigger_type": "manual",
                "trigger_date": TRIGGER_DATE,
            })
        )
        assert result["ok"] is False
        assert "user_id 非法" in result["error"]
        assert (victim / "secret.txt").is_file()
    finally:
        await engine.dispose()


async def test_path_traversal_cancel_rejected(tmp_path):
    """异常路径：user_id='..' 时取消礼物必须被拒绝且不删除越界目录（当前 src 已回归）。"""
    skill, engine, _ = await _make_gift_skill(tmp_path)
    try:
        victim = tmp_path / "sandbox" / "victim"
        victim.mkdir(parents=True)
        (victim / "secret.txt").write_text("keep me", encoding="utf-8")

        result = json.loads(await skill.execute("cancel_gift", {"user_id": ".."}))
        assert result["ok"] is False
        assert "user_id 非法" in result["error"]
        assert (victim / "secret.txt").is_file()
    finally:
        await engine.dispose()


async def test_path_traversal_mark_sent_rejected(tmp_path):
    """异常路径：user_id='../..' 时标记发送必须被拒绝且不删除越界目录（当前 src 已回归）。"""
    skill, engine, _ = await _make_gift_skill(tmp_path)
    try:
        victim = tmp_path / "sandbox" / "victim"
        victim.mkdir(parents=True)
        (victim / "secret.txt").write_text("keep me", encoding="utf-8")

        result = json.loads(await skill.execute("mark_gift_sent", {"user_id": "../.."}))
        assert result["ok"] is False
        assert "user_id 非法" in result["error"]
        assert (victim / "secret.txt").is_file()
    finally:
        await engine.dispose()


async def test_non_digit_user_id_rejected_for_cancel(tmp_path):
    """异常路径：非数字 user_id 取消礼物时应被拒绝（当前 src 仅按不存在处理）。"""
    skill, engine, _ = await _make_gift_skill(tmp_path)
    try:
        result = json.loads(await skill.execute("cancel_gift", {"user_id": "abc"}))
        assert result["ok"] is False
        assert "user_id 非法" in result["error"]
    finally:
        await engine.dispose()


def test_user_gift_dir_defends_against_traversal(tmp_path):
    """边界：_user_gift_dir 必须拒绝越界 user_id（当前 src 已移除防护）。"""
    sandbox = SandboxService(sandbox_root=tmp_path / "sandbox")
    skill = GiftSkill(sandbox_service=sandbox)
    with pytest.raises(PermissionError):
        skill._user_gift_dir("..")
    with pytest.raises(PermissionError):
        skill._user_gift_dir("../victim")
    with pytest.raises(PermissionError):
        skill._user_gift_dir("123/../../victim")
    assert skill._user_gift_dir("123456") == (
        (tmp_path / "sandbox" / "gift" / "123456").resolve()
    )


async def test_create_writes_task_uuid_into_gift_md_and_cancel_deletes(tmp_path):
    """正常路径：创建后 gift.md 应含任务 UUID，取消应删除任务与目录（当前 src 已回归）。"""
    skill, engine, uow_factory = await _make_gift_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("create_gift", {
                "user_id": "123456",
                "idea": "手写祝福卡片",
                "trigger_type": "birthday",
                "trigger_date": TRIGGER_DATE,
                "group_id": "888888",
            })
        )
        assert result["ok"] is True
        task_uuid = result["task_uuid"]

        user_dir = tmp_path / "sandbox" / "gift" / "123456"
        assert user_dir.is_dir()
        gift_md = (user_dir / GIFT_MD).read_text("utf-8")
        assert f"定时任务UUID：{task_uuid}" in gift_md
        assert "手写祝福卡片" in gift_md

        cancel = json.loads(await skill.execute("cancel_gift", {"user_id": "123456"}))
        assert cancel["ok"] is True
        assert cancel["task_deleted"] is True
        assert not user_dir.exists()

        async with uow_factory() as uow:
            assert await uow.scheduled_tasks.get(task_uuid) is None
    finally:
        await engine.dispose()


async def test_cancel_deletes_task_by_metadata_when_uuid_missing(tmp_path):
    """异常路径：gift.md 无 UUID 时应按 metadata 反查删除定时任务（当前 src 已回归）。"""
    skill, engine, uow_factory = await _make_gift_skill(tmp_path)
    try:
        user_dir = tmp_path / "sandbox" / "gift" / "123456"
        user_dir.mkdir(parents=True)
        (user_dir / GIFT_MD).write_text(
            _build_gift_md(
                user_id="123456",
                idea="卡片",
                trigger_type="manual",
                trigger_date=TRIGGER_DATE,
            ),
            encoding="utf-8",
        )
        async with uow_factory() as uow:
            await uow.scheduled_tasks.create(
                task_uuid="gift-task-0001",
                title="送出给 123456 的礼物",
                detail="gift",
                recurrence=ScheduledTaskRecurrence.ONCE,
                start_at=datetime(2030, 1, 1, 1, 0, tzinfo=timezone.utc),
                end_at=datetime(2030, 1, 1, 17, 0, tzinfo=timezone.utc),
                bindings=(ConversationRef(kind="private", id="123456"),),
                metadata={
                    "type": "gift",
                    "user_id": "123456",
                    "gift_dir": "gift/123456",
                    "one_shot_notification": False,
                },
            )
            await uow.commit()

        result = json.loads(await skill.execute("cancel_gift", {"user_id": "123456"}))
        assert result["ok"] is True
        assert result["task_deleted"] is True
        assert not user_dir.exists()

        async with uow_factory() as uow:
            assert await uow.scheduled_tasks.get("gift-task-0001") is None
    finally:
        await engine.dispose()


async def test_mark_sent_deletes_task_when_uuid_missing(tmp_path):
    """异常路径：gift.md 无 UUID 时标记发送应反查删除定时任务（当前 src 已回归）。"""
    skill, engine, uow_factory = await _make_gift_skill(tmp_path)
    try:
        user_dir = tmp_path / "sandbox" / "gift" / "123456"
        user_dir.mkdir(parents=True)
        (user_dir / GIFT_MD).write_text(
            _build_gift_md(
                user_id="123456",
                idea="卡片",
                trigger_type="manual",
                trigger_date=TRIGGER_DATE,
            ),
            encoding="utf-8",
        )
        async with uow_factory() as uow:
            await uow.scheduled_tasks.create(
                task_uuid="gift-task-0002",
                title="送出给 123456 的礼物",
                detail="gift",
                recurrence=ScheduledTaskRecurrence.ONCE,
                start_at=datetime(2030, 1, 1, 1, 0, tzinfo=timezone.utc),
                end_at=datetime(2030, 1, 1, 17, 0, tzinfo=timezone.utc),
                bindings=(ConversationRef(kind="private", id="123456"),),
                metadata={
                    "type": "gift",
                    "user_id": "123456",
                    "gift_dir": "gift/123456",
                },
            )
            await uow.commit()

        result = json.loads(await skill.execute("mark_gift_sent", {"user_id": "123456"}))
        assert result["ok"] is True
        assert result["cleaned"] is True
        assert result["task_deleted"] is True
        assert not user_dir.exists()

        async with uow_factory() as uow:
            assert await uow.scheduled_tasks.get("gift-task-0002") is None
    finally:
        await engine.dispose()


async def test_cancel_deletes_task_when_uuid_in_gift_md(tmp_path):
    """正常路径：gift.md 含任务 UUID 时 cancel 应删除任务与目录。"""
    skill, engine, uow_factory = await _make_gift_skill(tmp_path)
    try:
        user_dir = tmp_path / "sandbox" / "gift" / "123456"
        user_dir.mkdir(parents=True)
        (user_dir / GIFT_MD).write_text(
            _build_gift_md(
                user_id="123456",
                idea="卡片",
                trigger_type="manual",
                trigger_date=TRIGGER_DATE,
                task_uuid="gift-task-0003",
            ),
            encoding="utf-8",
        )
        async with uow_factory() as uow:
            await uow.scheduled_tasks.create(
                task_uuid="gift-task-0003",
                title="送出给 123456 的礼物",
                detail="gift",
                recurrence=ScheduledTaskRecurrence.ONCE,
                start_at=datetime(2030, 1, 1, 1, 0, tzinfo=timezone.utc),
                end_at=datetime(2030, 1, 1, 17, 0, tzinfo=timezone.utc),
                bindings=(ConversationRef(kind="private", id="123456"),),
                metadata={
                    "type": "gift",
                    "user_id": "123456",
                    "gift_dir": "gift/123456",
                },
            )
            await uow.commit()

        result = json.loads(await skill.execute("cancel_gift", {"user_id": "123456"}))

        assert result["ok"] is True
        assert result["task_deleted"] is True
        assert not user_dir.exists()

        async with uow_factory() as uow:
            assert await uow.scheduled_tasks.get("gift-task-0003") is None
    finally:
        await engine.dispose()


def test_build_gift_md_embeds_task_uuid():
    """正常路径：_build_gift_md 应嵌入任务 UUID 与 prepared 标记。"""
    content = _build_gift_md(
        user_id="123456",
        idea="卡片",
        trigger_type="birthday",
        trigger_date=TRIGGER_DATE,
        prepared=True,
        task_uuid="abc-123",
    )
    assert "定时任务UUID：abc-123" in content
    assert "prepared: true" in content


async def test_concurrent_create_same_user_only_one_succeeds(tmp_path):
    """并发：同一用户同时发起两次创建，应只有一个成功、另一个被查重拒绝。"""
    skill, engine, uow_factory = await _make_gift_skill(tmp_path)
    try:
        args = {
            "user_id": "123456",
            "idea": "手写祝福卡片",
            "trigger_type": "birthday",
            "trigger_date": TRIGGER_DATE,
        }

        results = await asyncio.gather(
            skill.execute("create_gift", dict(args)),
            skill.execute("create_gift", dict(args)),
        )

        parsed = [json.loads(r) for r in results]
        ok_count = sum(1 for r in parsed if r["ok"])
        assert ok_count == 1
        rejected = next(r for r in parsed if not r["ok"])
        assert "已有活跃礼物" in rejected["error"]

        async with uow_factory() as uow:
            active = await uow.scheduled_tasks.list_active(limit=100)
        assert len(active) == 1
    finally:
        await engine.dispose()


async def test_create_rejects_invalid_trigger_date_format(tmp_path):
    """异常路径：trigger_date 不是合法 ISO 时间时应返回格式错误且不创建目录。"""
    skill, engine, _ = await _make_gift_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("create_gift", {
                "user_id": "123456",
                "idea": "卡片",
                "trigger_type": "manual",
                "trigger_date": "2030-13-45T09:00:00+08:00",
            })
        )

        assert result["ok"] is False
        assert "trigger_date 格式无效" in result["error"]
        assert not (tmp_path / "sandbox" / "gift" / "123456").exists()
    finally:
        await engine.dispose()


async def test_create_missing_trigger_date_rejected(tmp_path):
    """异常路径：缺少 trigger_date 时应返回缺少必要参数错误。"""
    skill, engine, _ = await _make_gift_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("create_gift", {
                "user_id": "123456",
                "idea": "卡片",
                "trigger_type": "manual",
            })
        )

        assert result["ok"] is False
        assert "缺少必要参数" in result["error"]
    finally:
        await engine.dispose()


async def test_create_naive_trigger_date_treated_as_local_plus_08(tmp_path):
    """边界：无时区 trigger_date 应按本地 +08:00 解析，任务窗口为 16 小时。"""
    skill, engine, uow_factory = await _make_gift_skill(tmp_path)
    try:
        result = json.loads(
            await skill.execute("create_gift", {
                "user_id": "123456",
                "idea": "卡片",
                "trigger_type": "manual",
                "trigger_date": "2030-01-01T09:00:00",
            })
        )

        assert result["ok"] is True
        async with uow_factory() as uow:
            task = await uow.scheduled_tasks.get(result["task_uuid"])
        assert task.start_at == datetime(2030, 1, 1, 1, 0, tzinfo=timezone.utc)
        assert task.end_at == datetime(2030, 1, 1, 17, 0, tzinfo=timezone.utc)
        assert (task.end_at - task.start_at) == timedelta(hours=16)
    finally:
        await engine.dispose()
