"""计数器读写不应每条消息都重新读库 + 解析整个 blob。

record_message 每条消息都会读一次计数器，而计数器是一整个 JSON blob
（间隔 500 条 × 800 字符 ≈ 400KB）。修复后解析结果缓存复用，但写路径仍然
每条都落库（崩溃丢失窗口不变），且总结成功清零后缓存必须同步，不能读到旧内容。
"""

from __future__ import annotations

import json


from tests.modules.runtime.test_archive_memory_summary import (
    _FakeArchive,
    _make_service,
)


async def _record_many(service, count: int, *, kind: str = "group", cid: str = "1") -> None:
    for index in range(count):
        await service.record_message(
            conversation_kind=kind,
            conversation_id=cid,
            message_text=f"消息 {index}",
            sender_id="7",
            sender_name="tester",
        )


async def test_counter_is_parsed_once_and_still_persisted_every_message(
    monkeypatch,
) -> None:
    archive = _FakeArchive()
    service = _make_service(archive=archive, group_interval=10)

    loads = 0
    saves = 0
    original_load = service._load_counter
    original_save = service._save_counter

    async def _load(key):
        nonlocal loads
        loads += 1
        return await original_load(key)

    async def _save(key, state):
        nonlocal saves
        saves += 1
        return await original_save(key, state)

    monkeypatch.setattr(service, "_load_counter", _load)
    monkeypatch.setattr(service, "_save_counter", _save)

    await _record_many(service, 4)

    assert loads == 1, "计数器只需首次读库，之后走缓存"
    assert saves == 4, "写路径仍每条消息都落库"


async def test_cache_does_not_resurrect_after_summary_reset() -> None:
    archive = _FakeArchive()
    service = _make_service(archive=archive, group_interval=2)

    await _record_many(service, 2)  # 达到间隔 → 触发总结并清零

    stored = archive._items[("memory_counter", "group:1")]
    assert json.loads(stored["value"])["count"] == 0

    # 清零后缓存必须同步：下一条消息从 0 开始计数
    await _record_many(service, 1)
    stored = archive._items[("memory_counter", "group:1")]
    payload = json.loads(stored["value"])
    assert payload["count"] == 1
    assert [m["text"] for m in payload["messages"]] == ["消息 0"]


async def test_cache_is_per_conversation() -> None:
    archive = _FakeArchive()
    service = _make_service(archive=archive, group_interval=10)

    await _record_many(service, 1, cid="1")
    await _record_many(service, 2, cid="2")

    first = json.loads(archive._items[("memory_counter", "group:1")]["value"])
    second = json.loads(archive._items[("memory_counter", "group:2")]["value"])
    assert first["count"] == 1
    assert second["count"] == 2


def test_service_has_counter_cache_attribute() -> None:
    service = _make_service()
    assert service._counter_cache == {}


async def test_cache_ttl_revalidates_external_changes(monkeypatch) -> None:
    """外部删除/清零计数器后，本进程不能把陈旧 blob 整块写回。

    缓存永不失效时：外部删掉 memory_counter 行，下一条消息会把旧 messages
    全量写回（删除被撤销）。缓存带 TTL 后，过期即重新读库、尊重外部状态。
    """
    archive = _FakeArchive()
    service = _make_service(archive=archive, group_interval=100)
    await _record_many(service, 2)

    # 缓存有效期内不重读（这正是省开销的来源）
    loads = 0
    original_load = service._load_counter

    async def _counting_load(key):
        nonlocal loads
        loads += 1
        return await original_load(key)

    monkeypatch.setattr(service, "_load_counter", _counting_load)
    await _record_many(service, 1)
    assert loads == 0

    # 外部删除该计数器行；缓存过期后的下一条消息必须重新读库
    archive._items.pop(("memory_counter", "group:1"))
    monkeypatch.setattr(
        "neobot_app.runtime.archive_memory_summary._COUNTER_CACHE_TTL_SECONDS", 0.0
    )
    await _record_many(service, 1)

    assert loads == 1
    payload = json.loads(archive._items[("memory_counter", "group:1")]["value"])
    assert payload["count"] == 1
    # 关键：之前那条 blob 里的消息（外部删除的对象）没有被整块写回
    assert len(payload["messages"]) == 1
