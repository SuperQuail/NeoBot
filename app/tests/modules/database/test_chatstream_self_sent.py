"""ChatStreamManager 软重启补齐：合并本地 Bot 自身消息并去重（bugfixes/feat(2) §11）。

覆盖：合并后 user/assistant 齐全且顺序正确、去重（不出现两条）、
不误伤他人消息、无 bot_account 时跳过、读写失败不反噬启动流程，
以及「回复落盘 -> 软重启 -> 灌入历史」的端到端场景。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest_asyncio

from neobot_adapter.model.response import (
    FriendData,
    GetHistoryMsgListData,
    GetHistoryMsgListResponse,
    GetSignalMsgData,
    GroupData,
)
from neobot_contracts.models import ConversationRef, IncomingMessage
from neobot_storage.engine import create_engine, sqlite_url
from neobot_storage.models import Base
from neobot_storage.uow import make_uow_factory

from neobot_app.database.chatstream import ChatStreamManager
from neobot_app.message.queue import MessageQueue
from neobot_app.prompt.role_messages import build_role_messages
from neobot_app.reply.sender import ReplySender

BOT_QQ = 10001
USER_QQ = 20001
GROUP_ID = 888888
FRIEND_QQ = 30001

#: 时间戳分隔符会向角色消息里插入额外的 user 条目；用例只关心消息顺序，
#: 因此把分隔间隔放大到用例时间跨度之上。
_NO_TIMESTAMP_INTERVAL = 10_000_000

_BASE = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _at(offset_seconds: int) -> datetime:
    return _BASE + timedelta(seconds=offset_seconds)


def _epoch(offset_seconds: int) -> int:
    return int(_at(offset_seconds).timestamp())


class FakeAdapter:
    """只回答历史消息查询的假适配器。"""

    def __init__(self, *, group_history=None, friend_history=None) -> None:
        self.group_history = group_history or {}
        self.friend_history = friend_history or {}

    async def get_group_msg_history(self, group_id, count=20, reverse_order=False):
        return _history_response(self.group_history.get(str(group_id), []))

    async def get_friend_msg_history(self, user_id, count=20, reverse_order=False):
        return _history_response(self.friend_history.get(str(user_id), []))


class ExplodingUowFactory:
    """调用即抛异常的 UoW 工厂，模拟数据库不可用。"""

    def __call__(self):
        raise RuntimeError("数据库不可用")


def _backend_message(message_id, user_id, text, time_, *, group_id=GROUP_ID):
    """构造一条后端历史消息（GetSignalMsgData，与真实适配器返回同型）。"""
    payload = {
        "message_id": message_id,
        "user_id": user_id,
        "time": time_,
        "raw_message": text,
        "message": [{"type": "text", "data": {"text": text}}],
        "sender": {"user_id": user_id, "nickname": f"U{user_id}"},
    }
    if group_id is not None:
        payload["group_id"] = group_id
    return GetSignalMsgData(**payload)


def _history_response(messages):
    return GetHistoryMsgListResponse(
        status="ok",
        retcode=0,
        data=GetHistoryMsgListData(messages=list(messages)),
    )


@pytest_asyncio.fixture
async def uow_factory(tmp_path):
    """每用例独立的临时 sqlite UoW 工厂（WAL + busy_timeout，与生产一致）。"""
    engine = create_engine(sqlite_url(tmp_path / "chatstream.db"))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield make_uow_factory(engine)
    await engine.dispose()


async def _save_bot_record(
    uow_factory,
    conversation: ConversationRef,
    text: str,
    occurred_at: datetime,
    *,
    event_id: str = "self:-1",
) -> None:
    """模拟 push_self_sent_message 的落库结果。"""
    async with uow_factory() as uow:
        await uow.messages.save_message(
            IncomingMessage(
                event_id=event_id,
                conversation=conversation,
                sender_id=str(BOT_QQ),
                sender_name="测试机器人",
                text=text,
                occurred_at=occurred_at,
            )
        )
        await uow.commit()


def _make_manager(adapter, uow_factory, *, bot_account=BOT_QQ):
    """构造只关心队列与 UoW 的 ChatStreamManager。"""
    group_queue = MessageQueue(
        max_size=50,
        timestamp_interval_seconds=_NO_TIMESTAMP_INTERVAL,
        bot_account=bot_account,
    )
    friend_queue = MessageQueue(
        max_size=50,
        timestamp_interval_seconds=_NO_TIMESTAMP_INTERVAL,
        bot_account=bot_account,
    )
    manager = ChatStreamManager(
        adapter=adapter,
        uow_factory=uow_factory,
        group_message_queue=group_queue,
        friend_message_queue=friend_queue,
    )
    return manager, group_queue, friend_queue


def _texts(queue, key):
    return [message.raw_message for message in queue.iterate_from_oldest(key)]


def _roles(queue, key):
    return [item["role"] for item in build_role_messages(queue, key, bot_account=BOT_QQ)]


async def test_group_history_merges_local_bot_record_in_time_order(uow_factory):
    """后端 3 条 user + 本地 1 条 Bot 记录：灌入后 user/assistant 齐全且顺序正确。"""
    conv = ConversationRef(kind="group", id=str(GROUP_ID))
    adapter = FakeAdapter(
        group_history={
            str(GROUP_ID): [
                _backend_message(1, USER_QQ, "早", _epoch(0)),
                _backend_message(2, USER_QQ, "在吗", _epoch(10)),
                _backend_message(3, USER_QQ, "喂", _epoch(60)),
            ]
        }
    )
    await _save_bot_record(uow_factory, conv, "在的", _at(20), event_id="self:-1111")
    manager, group_queue, _ = _make_manager(adapter, uow_factory)

    await manager._process_group_history(
        GroupData(group_id=GROUP_ID, group_name="测试群"), max_observations=20
    )

    assert _texts(group_queue, str(GROUP_ID)) == ["早", "在吗", "在的", "喂"]
    assert _roles(group_queue, str(GROUP_ID)) == ["user", "user", "assistant", "user"]


async def test_group_history_skips_bot_record_already_in_backend(uow_factory):
    """后端历史已含该 Bot 消息（相差 3s）时，合并后不得出现两条（验收 S5）。"""
    conv = ConversationRef(kind="group", id=str(GROUP_ID))
    adapter = FakeAdapter(
        group_history={
            str(GROUP_ID): [
                _backend_message(1, USER_QQ, "在吗", _epoch(0)),
                _backend_message(2, BOT_QQ, "在的", _epoch(20)),
            ]
        }
    )
    await _save_bot_record(uow_factory, conv, "在的", _at(23), event_id="self:-2222")
    manager, group_queue, _ = _make_manager(adapter, uow_factory)

    await manager._process_group_history(
        GroupData(group_id=GROUP_ID), max_observations=20
    )

    assert _texts(group_queue, str(GROUP_ID)) == ["在吗", "在的"]
    assert _roles(group_queue, str(GROUP_ID)) == ["user", "assistant"]


async def test_group_history_keeps_bot_record_outside_dedup_window(uow_factory):
    """与后端记录的落库时间相差超过 30s 时不算同一条，仍需补齐。"""
    conv = ConversationRef(kind="group", id=str(GROUP_ID))
    adapter = FakeAdapter(
        group_history={
            str(GROUP_ID): [
                _backend_message(1, USER_QQ, "在吗", _epoch(0)),
                _backend_message(2, BOT_QQ, "在的", _epoch(20)),
            ]
        }
    )
    await _save_bot_record(uow_factory, conv, "在的", _at(51), event_id="self:-3333")
    manager, group_queue, _ = _make_manager(adapter, uow_factory)

    await manager._process_group_history(GroupData(group_id=GROUP_ID), max_observations=20)

    assert _texts(group_queue, str(GROUP_ID)) == ["在吗", "在的", "在的"]
    assert _roles(group_queue, str(GROUP_ID)) == ["user", "assistant", "assistant"]


async def test_merge_never_dedups_other_senders(uow_factory):
    """同文本但发送者不是 Bot 时不得判重，他人的消息一条都不能丢。"""
    conv = ConversationRef(kind="group", id=str(GROUP_ID))
    adapter = FakeAdapter(
        group_history={
            str(GROUP_ID): [
                _backend_message(1, USER_QQ, "在的", _epoch(20)),
            ]
        }
    )
    await _save_bot_record(uow_factory, conv, "在的", _at(21), event_id="self:-4444")
    manager, group_queue, _ = _make_manager(adapter, uow_factory)

    await manager._process_group_history(GroupData(group_id=GROUP_ID), max_observations=20)

    messages = list(group_queue.iterate_from_oldest(str(GROUP_ID)))
    assert [message.user_id for message in messages] == [USER_QQ, BOT_QQ]
    assert _roles(group_queue, str(GROUP_ID)) == ["user", "assistant"]


async def test_friend_history_merges_local_bot_record(uow_factory):
    """私聊走同一条补齐路径。"""
    conv = ConversationRef(kind="private", id=str(FRIEND_QQ))
    adapter = FakeAdapter(
        friend_history={
            str(FRIEND_QQ): [
                _backend_message(1, FRIEND_QQ, "在吗", _epoch(0), group_id=None),
                _backend_message(2, FRIEND_QQ, "喂", _epoch(60), group_id=None),
            ]
        }
    )
    await _save_bot_record(uow_factory, conv, "在的", _at(20), event_id="self:-5555")
    manager, _, friend_queue = _make_manager(adapter, uow_factory)

    await manager._process_friend_history(
        FriendData(user_id=FRIEND_QQ, nickname="好友"), max_observations=20
    )

    assert _texts(friend_queue, str(FRIEND_QQ)) == ["在吗", "在的", "喂"]
    assert _roles(friend_queue, str(FRIEND_QQ)) == ["user", "assistant", "user"]


async def test_merge_failure_keeps_backend_history(uow_factory):
    """补齐阶段任何异常都必须被吞掉：后端历史照常入队，启动流程不被打断。"""
    adapter = FakeAdapter(
        group_history={
            str(GROUP_ID): [
                _backend_message(1, USER_QQ, "早", _epoch(0)),
                _backend_message(2, USER_QQ, "在吗", _epoch(10)),
            ]
        }
    )
    manager, group_queue, _ = _make_manager(adapter, ExplodingUowFactory())

    await manager._process_group_history(GroupData(group_id=GROUP_ID), max_observations=20)

    assert _texts(group_queue, str(GROUP_ID)) == ["早", "在吗"]


async def test_merge_skipped_without_bot_account(uow_factory):
    """队列未声明 bot_account 时无法识别自身发言，跳过补齐且不报错。"""
    conv = ConversationRef(kind="group", id=str(GROUP_ID))
    adapter = FakeAdapter(
        group_history={str(GROUP_ID): [_backend_message(1, USER_QQ, "在吗", _epoch(0))]}
    )
    await _save_bot_record(uow_factory, conv, "在的", _at(20), event_id="self:-6666")
    manager, group_queue, _ = _make_manager(adapter, uow_factory, bot_account=None)

    await manager._process_group_history(GroupData(group_id=GROUP_ID), max_observations=20)

    assert _texts(group_queue, str(GROUP_ID)) == ["在吗"]


async def test_reply_persisted_then_soft_restart_restores_assistant_block(uow_factory):
    """端到端：回复落盘 -> 软重启（新空队列）-> 灌入历史，assistant 块必须回来。

    这正是 §11 修复的核心场景：后端历史里没有 Bot 自己的消息，模型否则会把
    「最后一条用户消息」当成尚未回答过而重复回复。
    """
    conv = ConversationRef(kind="group", id=str(GROUP_ID))
    config = SimpleNamespace(bot=SimpleNamespace(account=BOT_QQ))
    sender = ReplySender(
        adapter=None,
        file_server=None,
        config=config,
        bot_name="测试机器人",
        self_sent_uow_factory=uow_factory,
    )
    task = sender.push_self_sent_message(
        FakeQueueLike(), FakeQueueLike(), str(GROUP_ID), conv, "在的"
    )
    assert task is not None
    await task

    # 软重启：队列被重建为空，后端历史只回得到用户消息。
    # 用贴近当前时间的时刻，避免队列按 timestamp_interval 插入时间戳分隔条目
    # （落库时间来自真实时钟 now_utc()）。
    recent = int(datetime.now(timezone.utc).timestamp()) - 60
    adapter = FakeAdapter(
        group_history={str(GROUP_ID): [_backend_message(1, USER_QQ, "在吗", recent)]}
    )
    manager, group_queue, _ = _make_manager(adapter, uow_factory)

    await manager._process_group_history(GroupData(group_id=GROUP_ID), max_observations=20)

    assert _texts(group_queue, str(GROUP_ID)) == ["在吗", "在的"]
    assert _roles(group_queue, str(GROUP_ID)) == ["user", "assistant"]


class FakeQueueLike:
    """丢弃式假队列（端到端用例只用它满足 push 接口）。"""

    def push(self, key: str, message: object, **_kwargs: object) -> None:
        pass
