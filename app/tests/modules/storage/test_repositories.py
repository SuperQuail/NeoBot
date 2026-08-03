"""neobot_storage repositories 测试: scheduled_task / profile / usage / emoji / message 等。"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from neobot_contracts.models import ConversationRef, IncomingMessage, MemoryRecord
from neobot_contracts.models.scheduled_task import ScheduledTaskRecurrence, ScheduledTaskState
from neobot_contracts.time_context import now_utc
from neobot_storage.engine import create_engine, sqlite_url
from neobot_storage.models import (
    Base,
    CompletedScheduledTaskData,
    ModelUsageRecord,
)
from neobot_storage.repositories.usage import SqlAlchemyUsageRepository
from neobot_storage.uow import make_uow_factory


@pytest_asyncio.fixture
async def engine(tmp_path):
    """每用例独立的临时 sqlite 引擎 (WAL + busy_timeout, 与生产一致)。"""
    eng = create_engine(sqlite_url(tmp_path / "repos.db"))
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def uow_factory(engine):
    """基于独立引擎的 UoW 工厂。"""
    return make_uow_factory(engine)


async def _create_task(
    uow,
    *,
    task_uuid: str,
    title: str = "任务",
    start_at=None,
    end_at=None,
    recurrence: ScheduledTaskRecurrence = ScheduledTaskRecurrence.ONCE,
):
    """在给定 UoW 中创建一条合法的定时任务并返回领域记录。"""
    start = start_at if start_at is not None else now_utc()
    end = end_at if end_at is not None else start + timedelta(hours=1)
    return await uow.scheduled_tasks.create(
        task_uuid=task_uuid,
        title=title,
        detail="",
        recurrence=recurrence,
        start_at=start,
        end_at=end,
        bindings=[ConversationRef(kind="group", id="g1")],
        metadata=None,
    )


async def test_scheduled_task_list_active_filters_disabled_and_orders_by_start_at(uow_factory):
    """list_active 必须排除 disabled 任务且按 start_at 升序返回。"""

    # Arrange
    base = now_utc()
    async with uow_factory() as uow:
        await _create_task(uow, task_uuid="t-last", title="last", start_at=base + timedelta(hours=3))
        await _create_task(uow, task_uuid="t-first", title="first", start_at=base + timedelta(hours=1))
        await _create_task(uow, task_uuid="t-mid", title="disabled", start_at=base + timedelta(hours=2))
        await uow.scheduled_tasks.update("t-mid", state=ScheduledTaskState.DISABLED)
        await uow.commit()

    # Act
    async with uow_factory() as uow:
        active = await uow.scheduled_tasks.list_active()

    # Assert
    assert [t.title for t in active] == ["first", "last"]


async def test_scheduled_task_update_bumps_version_and_dedupes_window_keys(uow_factory):
    """update 必须替换字段、version+1，且 completed_window_keys 去重保序。"""

    # Arrange
    async with uow_factory() as uow:
        created = await _create_task(uow, task_uuid="t-upd", title="旧标题")
        await uow.commit()
        assert created.version == 1

    # Act
    async with uow_factory() as uow:
        updated = await uow.scheduled_tasks.update(
            "t-upd",
            title="新标题",
            detail="新详情",
            state=ScheduledTaskState.DISABLED,
            completed_window_keys=["k1", "k2", "k1"],
            metadata={"a": 1},
        )
        await uow.commit()

    # Assert
    assert updated.title == "新标题"
    assert updated.detail == "新详情"
    assert updated.state == ScheduledTaskState.DISABLED
    assert updated.completed_window_keys == ("k1", "k2")
    assert updated.metadata == {"a": 1}
    assert updated.version == 2


async def test_scheduled_task_archive_completed_moves_row_and_preserves_payload(engine, uow_factory):
    """archive_completed 必须删除原任务并把完整载荷写入 completed 表。"""

    # Arrange
    async with uow_factory() as uow:
        await _create_task(uow, task_uuid="t-arch", title="归档任务")
        await uow.commit()

    # Act
    async with uow_factory() as uow:
        archived = await uow.scheduled_tasks.archive_completed(
            "t-arch", completed_at=now_utc(), completion_reason="到期归档"
        )
        await uow.commit()

    # Assert
    assert archived is not None
    async with uow_factory() as uow:
        assert await uow.scheduled_tasks.get("t-arch") is None
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                select(
                    CompletedScheduledTaskData.title,
                    CompletedScheduledTaskData.completion_reason,
                    CompletedScheduledTaskData.archived_payload_json,
                ).where(CompletedScheduledTaskData.task_uuid == "t-arch")
            )
        ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.title == "归档任务"
    assert row.completion_reason == "到期归档"
    assert row.archived_payload_json is not None
    assert row.archived_payload_json.count("t-arch") == 1
    assert '"state": "active"' in row.archived_payload_json


async def test_scheduled_task_archive_completed_returns_none_for_unknown_task(uow_factory):
    """归档不存在的任务时必须返回 None 且不产生任何副作用。"""

    # Arrange
    async with uow_factory() as uow:
        await _create_task(uow, task_uuid="t-keep")

    # Act
    async with uow_factory() as uow:
        result = await uow.scheduled_tasks.archive_completed(
            "no-such-task", completed_at=now_utc(), completion_reason="x"
        )
        await uow.commit()

    # Assert
    assert result is None


@pytest.mark.xfail(
    reason=(
        "BUG-002: archive_completed 为读-写非串行实现且 completed 表无 task_uuid "
        "唯一约束，双 UoW 并发归档同一任务时偶发写入两条 completed 记录（实测 10 次中约 4 次）"
    ),
    strict=False,
)
async def test_scheduled_task_archive_completed_concurrent_only_archives_once(engine, uow_factory):
    """双 UoW 并发归档同一任务时 completed 表必须只产生一条记录。"""

    # Arrange
    async with uow_factory() as uow:
        await _create_task(uow, task_uuid="t-race", title="并发任务")
        await uow.commit()

    async def archive_once() -> None:
        async with uow_factory() as uow:
            await uow.scheduled_tasks.archive_completed(
                "t-race", completed_at=now_utc(), completion_reason="done"
            )
            await uow.commit()

    # Act
    await asyncio.gather(archive_once(), archive_once())

    # Assert
    async with engine.connect() as conn:
        count = (
            await conn.execute(select(func.count()).select_from(CompletedScheduledTaskData))
        ).scalar_one()
    assert count == 1


async def test_profile_upsert_preserves_existing_fields(uow_factory):
    """重复 upsert 用户时只更新传入字段，其余已存字段必须保留。"""

    # Arrange
    async with uow_factory() as uow:
        await uow.profiles.upsert_user("u1", nick_name="娜娜", city="上海")
        await uow.commit()

    # Act
    async with uow_factory() as uow:
        await uow.profiles.upsert_user("u1", city="北京")
        await uow.commit()

    # Assert
    async with uow_factory() as uow:
        user = await uow.profiles.get_user("u1")
    assert user is not None
    assert user.nick_name == "娜娜"
    assert user.city == "北京"


async def test_profile_upsert_group_and_group_exists(uow_factory):
    """upsert_group 新写入后 group_exists 为 True 且字段可读回。"""

    # Arrange / Act
    async with uow_factory() as uow:
        await uow.profiles.upsert_group("g1", group_name="测试群", profile="简介")
        await uow.commit()

    # Assert
    async with uow_factory() as uow:
        assert await uow.profiles.group_exists("g1")
        group = await uow.profiles.get_group("g1")
    assert group is not None
    assert group.group_name == "测试群"


async def test_usage_stats_since_filters_and_orders_desc(engine):
    """stats_since 必须只返回 since 之后的记录且按 created_at 降序。"""

    # Arrange
    base = now_utc()
    records = [
        ModelUsageRecord(
            module_name="chat", model_name="m1", provider_name="p",
            input_tokens=10, output_tokens=5, created_at=base - timedelta(days=2),
        ),
        ModelUsageRecord(
            module_name="chat", model_name="m2", provider_name="p",
            input_tokens=20, output_tokens=10, created_at=base - timedelta(hours=1),
        ),
        ModelUsageRecord(
            module_name="image", model_name="m3", provider_name="p",
            input_tokens=30, output_tokens=15, created_at=base,
        ),
    ]
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        repo = SqlAlchemyUsageRepository(session)
        for record in records:
            await repo.add(record)
        await session.commit()

    # Act
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        repo = SqlAlchemyUsageRepository(session)
        result = await repo.stats_since(base - timedelta(days=1))

    # Assert
    assert [r.model_name for r in result] == ["m3", "m2"]
    assert result[0].input_tokens == 30


async def test_emoji_list_orders_by_file_name_default_and_by_use_count(uow_factory):
    """emoji list 默认按 file_name 排序, order_by_use_count=True 时按 use_count 升序。"""

    # Arrange
    async with uow_factory() as uow:
        await uow.emojis.set("h-b", file_name="b.png", file_path="/b.png")
        await uow.emojis.set("h-a", file_name="a.png", file_path="/a.png")
        await uow.emojis.set("h-c", file_name="c.png", file_path="/c.png")
        await uow.emojis.increment_usage("h-b")
        await uow.emojis.increment_usage("h-b")
        await uow.emojis.increment_usage("h-c")
        await uow.commit()

    # Act
    async with uow_factory() as uow:
        by_name = await uow.emojis.list()
        by_count = await uow.emojis.list(order_by_use_count=True)

    # Assert
    assert [e.file_name for e in by_name] == ["a.png", "b.png", "c.png"]
    assert [e.file_name for e in by_count] == ["a.png", "c.png", "b.png"]
    assert by_count[0].use_count == 0
    assert by_count[2].use_count == 2


async def test_emoji_increment_usage_increases_use_count(uow_factory):
    """increment_usage 每调用一次 use_count 必须 +1 且其余字段不变。"""

    # Arrange
    async with uow_factory() as uow:
        await uow.emojis.set("h-1", file_name="x.png", file_path="/x.png")
        await uow.commit()

    # Act
    async with uow_factory() as uow:
        await uow.emojis.increment_usage("h-1")
        await uow.commit()
    async with uow_factory() as uow:
        await uow.emojis.increment_usage("h-1")
        await uow.commit()

    # Assert
    async with uow_factory() as uow:
        record = await uow.emojis.get_by_hash("h-1")
    assert record is not None
    assert record.use_count == 2
    assert record.file_name == "x.png"


async def test_message_get_history_paginates_and_orders_chronologically(uow_factory):
    """get_history 必须按 limit 截断且返回最早在前的时间正序消息。"""

    # Arrange
    base = now_utc()
    conv = ConversationRef(kind="group", id="g1")
    async with uow_factory() as uow:
        for i in range(5):
            await uow.messages.save_message(
                IncomingMessage(
                    event_id=f"e{i}",
                    conversation=conv,
                    sender_id="s1",
                    sender_name="S",
                    text=f"m{i}",
                    occurred_at=base + timedelta(seconds=i * 10),
                )
            )
        await uow.commit()

    # Act
    async with uow_factory() as uow:
        limited = await uow.messages.get_history(conv, limit=2)
        full = await uow.messages.get_history(conv)

    # Assert
    assert [m.text for m in limited] == ["m3", "m4"]
    assert [m.text for m in full] == ["m0", "m1", "m2", "m3", "m4"]


async def test_memory_search_filters_by_conversation_and_query(uow_factory):
    """memory search 必须限定会话且按 created_at 降序命中内容包含查询词。"""

    # Arrange
    base = now_utc()
    g1 = ConversationRef(kind="group", id="g1")
    g2 = ConversationRef(kind="group", id="g2")
    async with uow_factory() as uow:
        await uow.memories.save(
            MemoryRecord(conversation=g1, speaker_id="a", content="今天天气不错", created_at=base)
        )
        await uow.memories.save(
            MemoryRecord(
                conversation=g1, speaker_id="b", content="今天吃火锅", created_at=base + timedelta(minutes=1)
            )
        )
        await uow.memories.save(
            MemoryRecord(conversation=g2, speaker_id="c", content="今天天气不错", created_at=base)
        )
        await uow.commit()

    # Act
    async with uow_factory() as uow:
        weather = await uow.memories.search(g1, "天气")
        today = await uow.memories.search(g1, "今天")

    # Assert
    assert [m.content for m in weather] == ["今天天气不错"]
    assert [m.content for m in today] == ["今天吃火锅", "今天天气不错"]


async def test_archive_memory_set_get_roundtrip_with_tags_and_version(uow_factory):
    """archive set/get 必须保留 value 与 tags，重复 set 必须 version+1 并更新值。"""

    # Arrange / Act
    async with uow_factory() as uow:
        first = await uow.archive.set("skills", "neko", "v1", tags=["猫", "neko"])
        second = await uow.archive.set("skills", "neko", "v2", tags=["猫"])
        await uow.commit()

    # Assert
    assert first.value == "v1"
    assert first.version == 1
    assert second.value == "v2"
    assert second.version == 2
    assert set(second.tags) == {"猫"}
    async with uow_factory() as uow:
        fetched = await uow.archive.get("skills", "neko")
        listed = await uow.archive.list("skills", tags=["猫"])
    assert fetched is not None
    assert fetched.value == "v2"
    assert fetched.tags == ["猫"]
    assert [e.key for e in listed] == ["neko"]


async def test_bilibili_link_create_find_delete(uow_factory):
    """bilibili 关联创建后可查可删，删除返回受影响行数。"""

    # Arrange / Act
    async with uow_factory() as uow:
        await uow.bilibili_link_repo.create(bilibili_uid=12345, qq_number="10001")
        await uow.commit()

    # Assert
    async with uow_factory() as uow:
        link = await uow.bilibili_link_repo.find_by_uid_and_qq(12345, "10001")
        by_qq = await uow.bilibili_link_repo.find_by_qq("10001")
        deleted = await uow.bilibili_link_repo.delete_one(12345, "10001")
        await uow.commit()
        gone = await uow.bilibili_link_repo.find_by_uid_and_qq(12345, "10001")
    assert link is not None
    assert by_qq == [{"bilibili_uid": 12345, "qq_number": "10001", "created_at": link.created_at.isoformat()}]
    assert deleted == 1
    assert gone is None
