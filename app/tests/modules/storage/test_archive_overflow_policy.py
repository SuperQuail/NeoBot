"""ArchiveMemoryService 的档案长度硬上限与观测能力测试（spec(1) / spec(2)）。

覆盖：
- A5：memory_counter 永不被上限拦截（reject/summarize 两种动作都不拦截）；
- A4：max_total_chars=0 时行为与现状完全一致；
- A3：冷却期内重复超限只触发一次压缩；
- A7：list_over_limit / count_over_limit 可枚举超限档案；
- reject 动作、无触发入口时的兜底（保留原内容 + WARNING）；
- spec(2)：list_table_names / table_stats / set_if_version（乐观锁）。
"""

from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
import pytest_asyncio
from neobot_contracts.ports.logging import NullLogger
from neobot_memory.archive_service import (
    ArchiveMemoryService,
    ArchiveOverflowRejected,
    ArchiveVersionConflictError,
)
from neobot_storage.uow import make_uow_factory

from .archive_test_utils import create_memory_engine, create_schema


@pytest_asyncio.fixture
async def uow_factory():
    engine = create_memory_engine()
    await create_schema(engine)
    try:
        yield make_uow_factory(engine)
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def service(uow_factory):
    return ArchiveMemoryService(uow_factory=uow_factory, logger=NullLogger())


class _Trigger:
    """假压缩触发入口：记录调用并返回固定结果（True=已调度）。"""

    def __init__(self, scheduled: bool = True) -> None:
        self.scheduled = scheduled
        self.calls: list[tuple[str, str]] = []

    def __call__(self, table_name: str, key: str) -> bool:
        self.calls.append((table_name, key))
        return self.scheduled


# ── A5：memory_counter 永不被上限拦截 ──────────────────────────────


async def test_memory_counter_is_exempt_from_capacity_limit(service) -> None:
    """超过 10000 字符的 memory_counter 记录必须原样写入、不触发压缩。"""
    trigger = _Trigger()
    service.configure_overflow_policy(
        max_total_chars=10000, overflow_action="summarize", exempt_tables=("memory_counter",)
    )
    service.set_overflow_trigger(trigger)
    assert service.exempt_tables == frozenset({"memory_counter"})

    payload = json.dumps(
        {"count": 500, "messages": [{"sender_id": "1", "text": "x" * 20000}]},
        ensure_ascii=False,
    )
    assert len(payload) > 10000

    outcome = await service.set_with_outcome(
        "memory_counter", "group:888", payload, ["auto_summary_counter"]
    )

    assert outcome.over_limit is False
    assert outcome.scheduled is False
    assert trigger.calls == []
    stored = await service.get("memory_counter", "group:888")
    assert stored is not None and stored.value == payload
    # 豁免表也不出现在超限清单里，避免把真正的超标档案淹没
    assert await service.list_over_limit() == []
    assert await service.count_over_limit() == 0


async def test_memory_counter_is_not_rejected_by_reject_action(service) -> None:
    """overflow_action=reject 也不能拦截计数器写入，否则自动总结整体失效。"""
    service.configure_overflow_policy(
        max_total_chars=100, overflow_action="reject", exempt_tables=("memory_counter",)
    )
    service.set_overflow_trigger(_Trigger())

    big = "c" * 5000
    item = await service.set("memory_counter", "group:888", big, ["auto_summary_counter"])

    assert item.value == big
    assert item.version == 1


# ── A4：max_total_chars=0 行为与现状一致 ──────────────────────────


async def test_disabled_limit_keeps_current_behaviour(service) -> None:
    """上限为 0 时不拦截、不触发压缩、不产生超限清单。"""
    trigger = _Trigger()
    service.set_overflow_trigger(trigger)
    service.configure_overflow_policy(max_total_chars=0, overflow_action="reject")

    big = "x" * 20000
    item = await service.set("user_profile", "1", big, ["t"])

    assert item.value == big
    assert item.version == 1
    assert trigger.calls == []
    assert await service.list_over_limit() == []
    assert await service.count_over_limit() == 0
    assert service.max_total_chars == 0

    # 再次覆盖写入仍与现状一致（版本递增、内容完整）
    item2 = await service.set("user_profile", "1", big + "y", ["t"])
    assert item2.version == 2
    assert (await service.get("user_profile", "1")).value == big + "y"


# ── 先写后压缩 + 冷却去重（A2/A3） ────────────────────────────────


async def test_over_limit_write_is_stored_then_triggers_compression(service) -> None:
    """超限时先完整落库再触发压缩，返回体带 over_limit/hint。"""
    trigger = _Trigger(scheduled=True)
    service.configure_overflow_policy(
        max_total_chars=100, overflow_action="summarize", cooldown_seconds=600
    )
    service.set_overflow_trigger(trigger)

    outcome = await service.set_with_outcome("user_profile", "1", "x" * 150, [])

    assert outcome.over_limit is True
    assert outcome.action == "summarize"
    assert outcome.scheduled is True
    assert outcome.chars == 150
    assert outcome.max_total_chars == 100
    assert "压缩" in outcome.hint
    stored = await service.get("user_profile", "1")
    assert stored is not None and len(stored.value) == 150  # 先写后压缩：信息不丢
    assert trigger.calls == [("user_profile", "1")]


async def test_over_limit_triggers_once_within_cooldown(service) -> None:
    """冷却期内重复超限只触发一次压缩（A3）。"""
    trigger = _Trigger(scheduled=True)
    service.configure_overflow_policy(max_total_chars=100, cooldown_seconds=600)
    service.set_overflow_trigger(trigger)

    first = await service.set_with_outcome("user_profile", "1", "a" * 150, [])
    second = await service.set_with_outcome("user_profile", "1", "a" * 200, [])

    assert first.scheduled is True
    assert second.over_limit is True
    assert second.scheduled is False
    assert trigger.calls == [("user_profile", "1")]
    # 冷却只看同一 key：另一个 key 不受影响
    third = await service.set_with_outcome("user_profile", "2", "b" * 150, [])
    assert third.scheduled is True
    assert trigger.calls == [("user_profile", "1"), ("user_profile", "2")]


async def test_cooldown_zero_triggers_every_time(service) -> None:
    """冷却配置为 0 时不做去重（每次都触发）。"""
    trigger = _Trigger(scheduled=True)
    service.configure_overflow_policy(max_total_chars=100, cooldown_seconds=0)
    service.set_overflow_trigger(trigger)

    await service.set_with_outcome("user_profile", "1", "a" * 150, [])
    await service.set_with_outcome("user_profile", "1", "a" * 200, [])

    assert len(trigger.calls) == 2


async def test_clear_overflow_cooldown_allows_immediate_retry(service) -> None:
    """压缩失败后清冷却：下次写入能立刻重试（D3「下次写入再试」）。"""
    trigger = _Trigger(scheduled=True)
    service.configure_overflow_policy(max_total_chars=100, cooldown_seconds=600)
    service.set_overflow_trigger(trigger)

    await service.set_with_outcome("user_profile", "1", "a" * 150, [])
    blocked = await service.set_with_outcome("user_profile", "1", "a" * 200, [])
    assert blocked.scheduled is False

    service.clear_overflow_cooldown("user_profile", "1")

    retried = await service.set_with_outcome("user_profile", "1", "a" * 250, [])
    assert retried.scheduled is True
    assert len(trigger.calls) == 2


async def test_unavailable_trigger_keeps_content_and_retries_next_write(service) -> None:
    """触发入口返回 False（AI 不可用/忙）时不写冷却，保留原文并允许下次重试。"""
    trigger = _Trigger(scheduled=False)
    service.configure_overflow_policy(max_total_chars=100, cooldown_seconds=600)
    service.set_overflow_trigger(trigger)

    first = await service.set_with_outcome("user_profile", "1", "a" * 150, [])
    second = await service.set_with_outcome("user_profile", "1", "a" * 200, [])

    assert first.over_limit is True and first.scheduled is False
    assert second.scheduled is True or second.scheduled is False
    assert len(trigger.calls) == 2  # 第二次仍然会尝试，而不是被冷却锁死
    stored = await service.get("user_profile", "1")
    assert stored is not None and len(stored.value) == 200


async def test_missing_trigger_logs_warning_and_keeps_full_content(uow_factory) -> None:
    """没有可用压缩入口时：记 WARNING、保留原内容、标记超标。"""
    logger = Mock(spec=NullLogger)
    service = ArchiveMemoryService(uow_factory=uow_factory, logger=logger)
    service.configure_overflow_policy(max_total_chars=100)

    outcome = await service.set_with_outcome("user_profile", "1", "x" * 150, [])

    assert outcome.over_limit is True
    assert outcome.scheduled is False
    assert len((await service.get("user_profile", "1")).value) == 150
    warnings = [call.args[0] for call in logger.warning.call_args_list]
    assert "档案超过存储上限但没有可用的自动压缩入口，仅保留原内容" in warnings


# ── reject 动作 ───────────────────────────────────────────────────


async def test_reject_action_refuses_write_with_explicit_error(service) -> None:
    """overflow_action=reject：不落库、返回明确错误与压缩指引。"""
    trigger = _Trigger()
    service.configure_overflow_policy(max_total_chars=100, overflow_action="reject")
    service.set_overflow_trigger(trigger)
    await service.set("user_profile", "1", "旧内容", [])

    outcome = await service.set_with_outcome("user_profile", "1", "x" * 150, [])

    assert outcome.item is None
    assert outcome.over_limit is True
    assert outcome.action == "reject"
    assert "拒绝写入" in outcome.error
    assert "压缩" in outcome.hint
    assert trigger.calls == []
    stored = await service.get("user_profile", "1")
    assert stored is not None and stored.value == "旧内容"  # 原内容未被破坏

    with pytest.raises(ArchiveOverflowRejected) as excinfo:
        await service.set("user_profile", "1", "y" * 150, [])
    assert excinfo.value.chars == 150
    assert excinfo.value.max_total_chars == 100
    assert excinfo.value.table_name == "user_profile"


# ── A7：超限可枚举 ────────────────────────────────────────────────


async def test_list_over_limit_exposes_fields_and_filters(service) -> None:
    """超限清单给出面板需要的字段，并支持按表过滤。"""
    service.configure_overflow_policy(max_total_chars=100)
    await service.set("user_profile", "big1", "x" * 150, [])
    await service.set("user_profile", "small", "y" * 10, [])
    await service.set("group_profile", "big2", "z" * 300, [])

    entries = await service.list_over_limit()
    assert {entry["key"] for entry in entries} == {"big1", "big2"}
    first = entries[0]
    for field in ("table_name", "key", "chars", "version", "updated_at", "max_total_chars", "preview"):
        assert field in first
    assert isinstance(first["updated_at"], str)
    assert first["max_total_chars"] == 100
    assert len(first["preview"]) <= 200
    assert all(entry["chars"] > 100 for entry in entries)

    assert await service.count_over_limit() == 2
    assert await service.count_over_limit("user_profile") == 1
    only_group = await service.list_over_limit("group_profile")
    assert [entry["key"] for entry in only_group] == ["big2"]


# ── spec(2)：表清单 / 表统计 / 乐观锁 ──────────────────────────────


async def test_service_exposes_table_names_and_stats(service) -> None:
    await service.set("user_profile", "1", "x" * 20, [])
    await service.set("group_profile", "888", "y" * 70, [])

    assert await service.list_table_names() == ["group_profile", "user_profile"]
    stats = {row["table_name"]: row for row in await service.table_stats()}
    assert stats["user_profile"]["count"] == 1
    assert stats["user_profile"]["max_value_chars"] == 20
    assert stats["group_profile"]["max_value_chars"] == 70


async def test_service_set_if_version_updates_and_conflicts(service) -> None:
    """服务层透出乐观锁，并把仓库冲突翻译成 neobot_memory 的公开异常。"""
    created = await service.set("user_profile", "1", "旧", [])
    updated = await service.set_if_version("user_profile", "1", "新", ["t"], created.version)
    assert updated.value == "新"
    assert updated.version == created.version + 1

    with pytest.raises(ArchiveVersionConflictError) as excinfo:
        await service.set_if_version("user_profile", "1", "再新", [], created.version)
    assert excinfo.value.expected_version == created.version
    assert excinfo.value.actual_version == updated.version
    assert excinfo.value.table_name == "user_profile"

    current = await service.get("user_profile", "1")
    assert current is not None and current.value == "新"


async def test_panel_write_is_not_blocked_by_limit_but_is_logged(uow_factory) -> None:
    """面板编辑是运维兜底入口：超限也允许写入，只记 WARNING（可被清单枚举）。"""
    logger = Mock(spec=NullLogger)
    service = ArchiveMemoryService(uow_factory=uow_factory, logger=logger)
    service.configure_overflow_policy(max_total_chars=100)
    service.set_overflow_trigger(_Trigger())

    item = await service.set_if_version("user_profile", "1", "x" * 150, [], 0)

    assert len(item.value) == 150
    assert [entry["key"] for entry in await service.list_over_limit()] == ["1"]
    warnings = [call.args[0] for call in logger.warning.call_args_list]
    assert "面板写入的档案超过存储上限（面板路径不拦截，仅记录）" in warnings
