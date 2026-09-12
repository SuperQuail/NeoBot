"""归档记忆仓库新增能力的测试：表清单、表统计、乐观锁、超限清单。

对应 spec(2) §2.5/§4.1/§4.3 的存储层缺口与 spec(1) 的 A7（超限可枚举）。
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from neobot_storage.repositories.archive import ArchiveVersionConflictError
from neobot_storage.uow import make_uow_factory

from .archive_test_utils import create_memory_engine, create_schema


@pytest_asyncio.fixture
async def uow_factory():
    """每个用例一个独立的内存库 + UoW 工厂。"""
    engine = create_memory_engine()
    await create_schema(engine)
    try:
        yield make_uow_factory(engine)
    finally:
        await engine.dispose()


async def test_list_table_names_reflects_actual_tables(uow_factory) -> None:
    """表清单必须来自库内真实数据，而不是静态常量（spec2 A1）。"""
    async with uow_factory() as uow:
        assert await uow.archive.list_table_names() == []
        await uow.archive.set("user_profile", "10001", "甲", [])
        await uow.archive.set("group_profile", "888", "群", [])
        await uow.archive.set("item_archive", "game_x", "物品", [])
        await uow.commit()

    async with uow_factory() as uow:
        names = await uow.archive.list_table_names()
    assert names == ["group_profile", "item_archive", "user_profile"]

    # 新表（此前不存在于任何静态清单里）刷新后立刻可见
    async with uow_factory() as uow:
        await uow.archive.set("brand_new_table", "k", "v", [])
        await uow.commit()
    async with uow_factory() as uow:
        names = await uow.archive.list_table_names()
    assert "brand_new_table" in names


async def test_table_stats_reports_count_and_max_value_chars(uow_factory) -> None:
    """每张表的条目数与最大 value 长度（面板列表 + 超限可视化复用）。"""
    async with uow_factory() as uow:
        await uow.archive.set("user_profile", "1", "x" * 30, [])
        await uow.archive.set("user_profile", "2", "y" * 12000, [])
        await uow.archive.set("group_profile", "888", "短", [])
        await uow.commit()

    async with uow_factory() as uow:
        stats = {row["table_name"]: row for row in await uow.archive.table_stats()}

    assert stats["user_profile"]["count"] == 2
    assert stats["user_profile"]["max_value_chars"] == 12000
    assert stats["group_profile"]["count"] == 1
    assert stats["group_profile"]["max_value_chars"] == len("短")


async def test_set_if_version_updates_when_version_matches(uow_factory) -> None:
    """版本一致时写入成功，版本号 +1（面板保存路径）。"""
    async with uow_factory() as uow:
        created = await uow.archive.set("user_profile", "1", "旧内容", [])
        await uow.commit()
    assert created.version == 1

    async with uow_factory() as uow:
        updated = await uow.archive.set_if_version("user_profile", "1", "新内容", ["t"], 1)
        await uow.commit()
    assert updated.value == "新内容"
    assert updated.version == 2
    assert updated.tags == ["t"]

    async with uow_factory() as uow:
        current = await uow.archive.get("user_profile", "1")
    assert current is not None and current.value == "新内容" and current.version == 2


async def test_set_if_version_conflict_raises_and_does_not_write(uow_factory) -> None:
    """版本过期必须抛明确异常且不落库（面板据此返回 409，A5）。"""
    async with uow_factory() as uow:
        await uow.archive.set("user_profile", "1", "被后写的版本", [])
        await uow.commit()

    async with uow_factory() as uow:
        with pytest.raises(ArchiveVersionConflictError) as excinfo:
            await uow.archive.set_if_version("user_profile", "1", "覆盖内容", [], 0)
        await uow.rollback()

    assert excinfo.value.expected_version == 0
    assert excinfo.value.actual_version == 1
    assert excinfo.value.table_name == "user_profile"

    async with uow_factory() as uow:
        current = await uow.archive.get("user_profile", "1")
    assert current is not None and current.value == "被后写的版本"


async def test_set_if_version_creates_only_with_zero(uow_factory) -> None:
    """条目不存在时只有 expected_version=0 才算新建，其余一律冲突。"""
    async with uow_factory() as uow:
        created = await uow.archive.set_if_version("user_profile", "9", "新条目", [], 0)
        await uow.commit()
    assert created.version == 1

    async with uow_factory() as uow:
        with pytest.raises(ArchiveVersionConflictError):
            await uow.archive.set_if_version("user_profile", "404", "x", [], 3)
        await uow.rollback()

    async with uow_factory() as uow:
        assert await uow.archive.get("user_profile", "404") is None


async def test_over_limit_queries_filter_by_table_and_exempt_list(uow_factory) -> None:
    """超限清单/计数支持按表过滤与豁免表排除（内部计数表天然超限）。"""
    async with uow_factory() as uow:
        await uow.archive.set("user_profile", "big", "x" * 200, [])
        await uow.archive.set("group_profile", "big", "y" * 300, [])
        await uow.archive.set("user_profile", "small", "z" * 10, [])
        await uow.archive.set("memory_counter", "group:1", "c" * 5000, [])
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.archive.count_over_limit(100) == 3
        assert await uow.archive.count_over_limit(100, exclude_tables=("memory_counter",)) == 2
        assert await uow.archive.count_over_limit(100, table_name="user_profile") == 1

        rows = await uow.archive.list_over_limit(
            100, exclude_tables=("memory_counter",), limit=10
        )
        filtered = await uow.archive.list_over_limit(100, table_name="group_profile", limit=10)

    assert {(row.table_name, row.key) for row in rows} == {
        ("user_profile", "big"),
        ("group_profile", "big"),
    }
    assert [row.key for row in filtered] == ["big"]
