"""ArchiveMemoryAutoSummaryService 计数器、摘要失败语义、flush_all 与锁生命周期测试。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from neobot_app.runtime.archive_memory_summary import (
    MAX_STORED_MESSAGE_CHARS,
    ArchiveMemoryAutoSummaryService,
)


class _FakeArchive:
    """内存版 ArchiveMemoryService：实现 get/set/list，按 (table, key) 存储。"""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], dict[str, Any]] = {}

    async def get(self, table_name: str, key: str):
        entry = self._items.get((table_name, key))
        if entry is None:
            return None
        return self._to_model(table_name, key, entry)

    async def set(self, table_name: str, key: str, value: str, tags: list[str]):
        self._items[(table_name, key)] = {"value": value, "tags": list(tags)}
        return self._to_model(table_name, key, self._items[(table_name, key)])

    async def list(
        self,
        table_name: str,
        *,
        tags: list[str] | None = None,
        key_query: str | None = None,
        value_query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        result = []
        for (table, key), entry in self._items.items():
            if table != table_name:
                continue
            if tags and not any(tag in entry["tags"] for tag in tags):
                continue
            result.append(self._to_model(table_name, key, entry))
        return result[offset : offset + limit]

    def raw(self, table_name: str, key: str) -> dict[str, Any] | None:
        return self._items.get((table_name, key))

    @staticmethod
    def _to_model(table_name: str, key: str, entry: dict[str, Any]):
        from neobot_contracts.models.memory import ArchiveMemory

        return ArchiveMemory(
            id=1,
            table_name=table_name,
            key=key,
            value=entry["value"],
            tags=entry["tags"],
            created_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
            updated_at=datetime(2026, 8, 3, tzinfo=timezone.utc),
            version=1,
        )


class _FakeProvider:
    """可配置失败行为的假 LLM Provider，记录每次 chat 调用。"""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[list[dict]] = []

    async def chat(self, messages, tools=None):
        self.calls.append(messages)
        if self.fail:
            raise RuntimeError("provider boom")
        return {"role": "assistant", "content": "ok", "tool_calls": None}

    async def close(self) -> None:
        pass


def _make_config(group_interval: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        agent=SimpleNamespace(
            memory=SimpleNamespace(
                trigger=SimpleNamespace(
                    group_interval=group_interval,
                    private_interval=group_interval,
                )
            )
        )
    )


def _make_service(
    archive: _FakeArchive | None = None,
    provider: _FakeProvider | None = None,
    group_interval: int = 3,
) -> ArchiveMemoryAutoSummaryService:
    return ArchiveMemoryAutoSummaryService(
        archive_memory_service=archive or _FakeArchive(),
        provider=provider or _FakeProvider(),
        config=_make_config(group_interval),
    )


@pytest.mark.asyncio
async def test_record_message_increments_counter_and_triggers_at_interval():
    """Arrange 间隔为 3 的群聊服务，Act 逐条 record 三条消息，
    Assert 前两条只累计计数不触发摘要，第三条达到阈值触发一次摘要并复位为 0。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=3)

    await service.record_message(
        conversation_kind="group",
        conversation_id="111",
        message_text="  你好，世界  ",
        sender_id="10001",
        sender_name="小弥",
    )
    await service.record_message(
        conversation_kind="group",
        conversation_id="111",
        message_text="第二条",
    )

    state = json.loads(archive.raw("memory_counter", "group:111")["value"])
    assert state["count"] == 2
    assert state["messages"][0] == {
        "sender_id": "10001",
        "sender_name": "小弥",
        "text": "你好，世界",
    }
    assert len(provider.calls) == 0

    await service.record_message(
        conversation_kind="group",
        conversation_id="111",
        message_text="第三条",
    )

    assert len(provider.calls) == 1
    state = json.loads(archive.raw("memory_counter", "group:111")["value"])
    assert state == {"count": 0, "messages": []}


@pytest.mark.xfail(
    reason="BUG-0036 摘要失败后计数器被清空为 0，已累计消息永久丢失，无法保留待重试",
    strict=False,
)
@pytest.mark.asyncio
async def test_summary_failure_keeps_counter_for_retry():
    """Arrange provider 必然失败的间隔 3 服务并累计三条消息，Act 触发摘要失败，
    Assert 计数器必须保留 count=3 与全部消息以便后续重试，不得清空丢失。"""
    archive = _FakeArchive()
    provider = _FakeProvider(fail=True)
    service = _make_service(archive=archive, provider=provider, group_interval=3)

    for i in range(3):
        await service.record_message(
            conversation_kind="group",
            conversation_id="222",
            message_text=f"消息 {i}",
        )

    assert len(provider.calls) == 1
    state = json.loads(archive.raw("memory_counter", "group:222")["value"])
    assert state["count"] == 3
    assert len(state["messages"]) == 3


@pytest.mark.asyncio
async def test_flush_all_summarizes_partial_counters_and_resets():
    """Arrange 一个未达阈值(2/3)、一个空计数、一个已达标(3/3)和一个畸形 key 的计数器，
    Act 调用 flush_all，Assert 只对部分计数器摘要并复位，其余状态原样保留。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=3)
    await archive.set(
        "memory_counter",
        "group:111",
        json.dumps({"count": 2, "messages": [{"text": "a"}, {"text": "b"}]}),
        ["auto_summary_counter"],
    )
    await archive.set(
        "memory_counter",
        "group:222",
        json.dumps({"count": 0, "messages": []}),
        ["auto_summary_counter"],
    )
    await archive.set(
        "memory_counter",
        "group:333",
        json.dumps({"count": 3, "messages": [{"text": "x"}]}),
        ["auto_summary_counter"],
    )
    await archive.set(
        "memory_counter",
        "nocolon",
        json.dumps({"count": 1, "messages": [{"text": "y"}]}),
        ["auto_summary_counter"],
    )

    await service.flush_all()

    assert len(provider.calls) == 1
    assert json.loads(archive.raw("memory_counter", "group:111")["value"]) == {
        "count": 0,
        "messages": [],
    }
    assert json.loads(archive.raw("memory_counter", "group:222")["value"])["count"] == 0
    assert json.loads(archive.raw("memory_counter", "group:333")["value"])["count"] == 3
    assert json.loads(archive.raw("memory_counter", "nocolon")["value"])["count"] == 1


@pytest.mark.asyncio
async def test_flush_all_skips_counters_without_pending_messages():
    """Arrange 空计数与已达标(3/3)两个计数器，Act 调用 flush_all，
    Assert 不产生任何摘要调用且状态保持不变。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=3)
    await archive.set(
        "memory_counter",
        "group:111",
        json.dumps({"count": 0, "messages": []}),
        ["auto_summary_counter"],
    )
    await archive.set(
        "memory_counter",
        "group:222",
        json.dumps({"count": 3, "messages": [{"text": "x"}]}),
        ["auto_summary_counter"],
    )

    await service.flush_all()

    assert len(provider.calls) == 0
    assert json.loads(archive.raw("memory_counter", "group:222")["value"])["count"] == 3


@pytest.mark.asyncio
async def test_flush_all_concurrent_calls_summarize_each_counter_once():
    """Arrange 两个部分计数(3/5)计数器，Act 用 asyncio.gather 并发调用两次 flush_all，
    Assert 每个计数器只被摘要一次，总调用数恰为 2（per-key 锁互斥）。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=5)
    for cid in ("111", "222"):
        await archive.set(
            "memory_counter",
            f"group:{cid}",
            json.dumps(
                {
                    "count": 3,
                    "messages": [{"text": "a"}, {"text": "b"}, {"text": "c"}],
                }
            ),
            ["auto_summary_counter"],
        )

    await asyncio.gather(service.flush_all(), service.flush_all())

    assert len(provider.calls) == 2
    assert json.loads(archive.raw("memory_counter", "group:111")["value"])["count"] == 0
    assert json.loads(archive.raw("memory_counter", "group:222")["value"])["count"] == 0


@pytest.mark.asyncio
async def test_lock_is_released_after_summarize():
    """Arrange 间隔 2 的服务，Act 两条消息触发摘要后再连记两条消息，
    Assert 摘要完成后 per-key 锁已释放，后续消息可继续计数并可再次触发。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=2)

    await service.record_message(conversation_kind="group", conversation_id="333", message_text="一")
    await service.record_message(conversation_kind="group", conversation_id="333", message_text="二")

    assert len(provider.calls) == 1
    lock = service._locks["group:333"]
    assert not lock.locked()

    await service.record_message(conversation_kind="group", conversation_id="333", message_text="三")
    assert len(provider.calls) == 1
    await service.record_message(conversation_kind="group", conversation_id="333", message_text="四")
    assert len(provider.calls) == 2


@pytest.mark.xfail(
    reason="BUG-0036 _locks 注册表随会话数无限增长，摘要完成后从不回收锁",
    strict=False,
)
@pytest.mark.asyncio
async def test_locks_registry_is_cleaned_after_summarize():
    """Arrange 三个会话各触发一次摘要，Act 全部完成后检查注册表，
    Assert _locks 中不再残留任何会话锁（防无界增长）。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=2)

    for cid in ("111", "222", "333"):
        await service.record_message(conversation_kind="group", conversation_id=cid, message_text="一")
        await service.record_message(conversation_kind="group", conversation_id=cid, message_text="二")

    assert len(provider.calls) == 3
    assert len(service._locks) == 0


@pytest.mark.asyncio
async def test_record_message_truncates_long_text_to_max_stored_chars():
    """Arrange 一条 2×MAX_STORED_MESSAGE_CHARS 的超长消息，Act record_message，
    Assert 计数器存储的文本被截断到 MAX_STORED_MESSAGE_CHARS。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider, group_interval=10)

    await service.record_message(
        conversation_kind="group",
        conversation_id="444",
        message_text="长" * (MAX_STORED_MESSAGE_CHARS * 2),
    )

    state = json.loads(archive.raw("memory_counter", "group:444")["value"])
    assert len(state["messages"]) == 1
    assert len(state["messages"][0]["text"]) == MAX_STORED_MESSAGE_CHARS


@pytest.mark.asyncio
async def test_record_message_ignores_unknown_conversation_kind():
    """Arrange 合法服务，Act 记录一条未知会话类型（channel）的消息，
    Assert 直接忽略，不产生任何计数状态也不触发摘要。"""
    archive = _FakeArchive()
    provider = _FakeProvider()
    service = _make_service(archive=archive, provider=provider)

    await service.record_message(
        conversation_kind="channel",
        conversation_id="555",
        message_text="x",
    )

    assert archive.raw("memory_counter", "channel:555") is None
    assert len(provider.calls) == 0
