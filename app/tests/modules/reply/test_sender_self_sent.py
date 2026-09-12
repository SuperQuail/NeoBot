"""ReplySender 软重启补齐：Bot 自身消息落盘（bugfixes/feat(2) §11）。

覆盖：持久化写入、event_id 与队列消息 id 对齐、空文本跳过、
无事件循环时只入队不落盘、落盘异常不反噬调用方。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest_asyncio

from neobot_contracts.models import ConversationRef
from neobot_storage.engine import create_engine, sqlite_url
from neobot_storage.models import Base
from neobot_storage.uow import make_uow_factory

from neobot_app.reply.sender import ReplySender, self_sent_event_id


class FakeQueue:
    """只记录 push 调用的假消息队列。"""

    def __init__(self) -> None:
        self.pushed: list[tuple[str, object]] = []

    def push(self, key: str, message: object, **_kwargs: object) -> None:
        self.pushed.append((key, message))


class ExplodingUowFactory:
    """调用即抛异常的 UoW 工厂，模拟数据库不可用。"""

    def __call__(self):
        raise RuntimeError("数据库不可用")


@pytest_asyncio.fixture
async def uow_factory(tmp_path):
    """每用例独立的临时 sqlite UoW 工厂（WAL + busy_timeout，与生产一致）。"""
    engine = create_engine(sqlite_url(tmp_path / "self_sent.db"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield make_uow_factory(engine)
    await engine.dispose()


def _make_sender(
    uow_factory=None,
    *,
    bot_qq: int = 10001,
    bot_name: str = "测试机器人",
) -> ReplySender:
    """构造注入了临时存储的 ReplySender。"""
    config = SimpleNamespace(bot=SimpleNamespace(account=bot_qq))
    return ReplySender(
        adapter=None,
        file_server=None,
        config=config,
        bot_name=bot_name,
        self_sent_uow_factory=uow_factory,
    )


async def test_push_self_sent_message_persists_bot_message(uow_factory):
    """push 之后 MessageData 里必须出现该 Bot 自身消息，且内存队列照常收到。"""
    sender = _make_sender(uow_factory)
    queue, queue_copy = FakeQueue(), FakeQueue()
    conv = ConversationRef(kind="group", id="888888")

    task = sender.push_self_sent_message(queue, queue_copy, "888888", conv, "我记住了")
    assert task is not None
    await task

    async with uow_factory() as uow:
        records = await uow.messages.get_recent_by_sender(conv, "10001", limit=10)

    assert len(records) == 1
    record = records[0]
    assert record.sender_id == "10001"
    assert record.sender_name == "测试机器人"
    assert record.text == "我记住了"
    assert record.conversation == conv
    # 内存队列与快照队列都必须收到同一条消息（原行为不变）
    assert [key for key, _ in queue.pushed] == ["888888"]
    assert [key for key, _ in queue_copy.pushed] == ["888888"]


async def test_persisted_event_id_matches_queue_message_id(uow_factory):
    """落库的 event_id 必须是 self:<合成消息id>，与入队消息的 id 对齐。"""
    sender = _make_sender(uow_factory)
    queue = FakeQueue()
    conv = ConversationRef(kind="private", id="30001")

    task = sender.push_self_sent_message(queue, FakeQueue(), "30001", conv, "在的")
    assert task is not None
    await task

    message = queue.pushed[0][1]
    assert message.message_id < 0
    assert message.user_id == 10001

    async with uow_factory() as uow:
        records = await uow.messages.get_recent_by_sender(conv, "10001", limit=10)
    assert [r.event_id for r in records] == [self_sent_event_id(message.message_id)]


async def test_persist_skips_blank_text(uow_factory):
    """空白文本不落盘：没有内容可补齐的 assistant 块。"""
    sender = _make_sender(uow_factory)
    conv = ConversationRef(kind="group", id="888888")

    await sender.persist_self_sent_message(conv, "   ")

    async with uow_factory() as uow:
        records = await uow.messages.get_recent_by_sender(conv, "10001", limit=10)
    assert records == []


def test_push_self_sent_message_without_event_loop_skips_persist(uow_factory):
    """同步上下文（无运行中的事件循环）只入队，不落盘且不抛异常。"""
    sender = _make_sender(uow_factory)
    queue = FakeQueue()

    result = sender.push_self_sent_message(
        queue, FakeQueue(), "1", ConversationRef(kind="private", id="1"), "在的"
    )

    assert result is None
    assert len(queue.pushed) == 1


async def test_persist_swallows_store_errors():
    """UoW 工厂抛异常时必须被吞掉并记日志，不能反噬发送路径。"""
    sender = _make_sender(ExplodingUowFactory())
    conv = ConversationRef(kind="group", id="888888")

    # 不抛异常即为通过
    await sender.persist_self_sent_message(conv, "在的")


async def test_push_self_sent_message_survives_store_errors():
    """落盘任务失败时 push_self_sent_message 仍必须正常返回并入队。"""
    sender = _make_sender(ExplodingUowFactory())
    queue = FakeQueue()

    task = sender.push_self_sent_message(
        queue, FakeQueue(), "888888", ConversationRef(kind="group", id="888888"), "在的"
    )

    assert task is not None
    await task
    assert len(queue.pushed) == 1
