"""archive_crud 的字符数工具测试（spec(4) Part C / §4.10.5，A35–A37 / A48）。

覆盖：
- list_archive 新语义：每条只给开头 500 字符 + total_chars + preview_truncated，不含 value；
- A48：默认 limit=5 时整份返回 < 4000 字符（不被 _bounded_tool_result 截断）、has_more 正确、hint 引导分页；
- archive_stats：复用服务层统计（与面板同一真相源，A35 / A36）、豁免表口径；
- instructions 与工具表同步（工具名与说明都在）。
"""

from __future__ import annotations

import json

import pytest_asyncio
from neobot_contracts.ports.logging import NullLogger
from neobot_memory import ArchiveMemoryService
from neobot_storage.models import Base
from neobot_storage.uow import make_uow_factory
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from neobot_app.builtin_plugins.dashboard import archives as archive_admin
from neobot_app.skills.archive_crud import ArchiveCRUDSkill

PREVIEW_CHARS = 500


@pytest_asyncio.fixture
async def service():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    service = ArchiveMemoryService(
        uow_factory=make_uow_factory(engine), logger=NullLogger()
    )
    service.configure_overflow_policy(max_total_chars=10000)
    try:
        yield service
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def skill(service):
    return ArchiveCRUDSkill(archive_service=service)


async def _seed(service: ArchiveMemoryService, table: str, key: str, value: str) -> None:
    await service.set_if_version(table, key, value, [], 0)


# ── A37：list_archive 只给开头 500 字符 ───────────────────────────


async def test_list_archive_returns_preview_only(skill, service) -> None:
    await _seed(service, "user_profile", "1", "x" * 5000)

    payload = json.loads(await skill.execute("list_archive", {"table_name": "user_profile"}))

    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["has_more"] is False
    item = payload["items"][0]
    assert "value" not in item
    assert item["total_chars"] == 5000
    assert len(item["preview"]) == PREVIEW_CHARS
    assert item["preview_chars"] == PREVIEW_CHARS
    assert item["preview_truncated"] is True
    assert item["preview"] == "x" * PREVIEW_CHARS


async def test_list_archive_marks_short_records_not_truncated(skill, service) -> None:
    await _seed(service, "user_profile", "1", "短档案")
    payload = json.loads(await skill.execute("list_archive", {"table_name": "user_profile"}))
    item = payload["items"][0]
    assert item["preview"] == "短档案"
    assert item["preview_truncated"] is False
    assert item["total_chars"] == len("短档案")


async def test_list_archive_filters_by_key_and_content(skill, service) -> None:
    await _seed(service, "user_profile", "qq-1", "喜欢豆浆")
    await _seed(service, "user_profile", "qq-2", "喜欢羽毛球")

    by_key = json.loads(
        await skill.execute("list_archive", {"table_name": "user_profile", "key_query": "qq-2"})
    )
    by_value = json.loads(
        await skill.execute(
            "list_archive", {"table_name": "user_profile", "value_query": "豆浆"}
        )
    )
    assert [item["key"] for item in by_key["items"]] == ["qq-2"]
    assert [item["key"] for item in by_value["items"]] == ["qq-1"]


# ── A48：默认 5 条 + 整份 < 4000 字符 + has_more ──────────────────


async def test_list_archive_default_limit_fits_tool_budget(skill, service) -> None:
    for index in range(6):
        await _seed(service, "user_profile", f"k{index}", "x" * 5000)

    raw = await skill.execute("list_archive", {"table_name": "user_profile"})
    payload = json.loads(raw)

    assert payload["count"] == 5  # 默认 limit 从 10 降到 5
    assert payload["has_more"] is True
    assert len(raw) < 4000  # 不被 _bounded_tool_result 截断
    hint = payload["hint"]
    assert "read_archive" in hint and "outline" in hint and "offset" in hint


async def test_list_archive_limit_is_capped_at_twenty(skill, service) -> None:
    for index in range(25):
        await _seed(service, "user_profile", f"k{index:02d}", "短")

    payload = json.loads(
        await skill.execute("list_archive", {"table_name": "user_profile", "limit": 50})
    )
    assert payload["count"] == 20  # 上限 20（10 条 ≈ 5.7KB 会被截断成半截 JSON）
    assert payload["has_more"] is True

    paged = json.loads(
        await skill.execute(
            "list_archive", {"table_name": "user_profile", "limit": 5, "offset": 5}
        )
    )
    assert len(paged["items"]) == 5
    assert [item["key"] for item in paged["items"]] == [
        item["key"] for item in payload["items"]
    ][5:10]


# ── A35 / A36：archive_stats 与面板对账 ───────────────────────────


async def test_archive_stats_matches_panel_totals(skill, service) -> None:
    await _seed(service, "user_profile", "1", "x" * 30)
    await _seed(service, "user_profile", "2", "y" * 12000)
    await _seed(service, "group_profile", "888", "z" * 50)

    payload = json.loads(await skill.execute("archive_stats", {}))
    assert payload["ok"] is True

    # 面板侧真相源（同一服务方法）
    tables = {row["table_name"]: row for row in payload["tables"]}
    panel_tables = await archive_admin.list_tables(service)
    panel_rows = {row["table_name"]: row for row in panel_tables["items"]}
    assert tables["user_profile"]["count"] == panel_rows["user_profile"]["count"] == 2
    assert (
        tables["user_profile"]["max_value_chars"]
        == panel_rows["user_profile"]["max_value_chars"]
        == 12000
    )
    assert panel_tables["max_total_chars"] == payload["max_total_chars"] == 10000
    assert payload["over_limit_count"] == await service.count_over_limit() == 1

    # A35：指定表时 items[] 的 total_chars 与面板 list_items 完全一致
    scoped = json.loads(
        await skill.execute("archive_stats", {"table_name": "user_profile"})
    )
    panel_items = await archive_admin.list_items(service, table="user_profile", limit=50)
    panel_chars = {row["key"]: row["total_chars"] for row in panel_items["items"]}
    stats_chars = {row["key"]: row["total_chars"] for row in scoped["items"]}
    assert stats_chars == panel_chars == {"1": 30, "2": 12000}
    assert scoped["count"] == 2
    assert scoped["total_chars"] == 12030


async def test_archive_stats_over_limit_matches_panel_listing(skill, service) -> None:
    await _seed(service, "user_profile", "1", "x" * 12000)
    await _seed(service, "user_profile", "2", "y" * 13000)
    await _seed(service, "group_profile", "888", "z" * 20)

    payload = json.loads(
        await skill.execute("archive_stats", {"over_limit_only": True})
    )
    panel = await archive_admin.list_over_limit(service, limit=100)

    # A36：超限条目及各自字数与 GET /api/archives/over-limit 完全一致
    assert [(row["table_name"], row["key"], row["total_chars"]) for row in payload["items"]] == [
        (row["table_name"], row["key"], row["chars"]) for row in panel["items"]
    ]
    assert payload["over_limit_count"] == 2
    assert payload["total_chars"] == 25000


async def test_archive_stats_excludes_exempt_tables_from_items(skill, service) -> None:
    await _seed(service, "memory_counter", "group:888", "{" + "x" * 20000 + "}")
    await _seed(service, "user_profile", "1", "y" * 12000)

    payload = json.loads(await skill.execute("archive_stats", {}))

    tables = {row["table_name"]: row for row in payload["tables"]}
    assert tables["memory_counter"]["internal"] is True
    assert tables["user_profile"]["internal"] is False
    assert payload["internal_tables"] == ["memory_counter"]
    # 内部表天然超限：绝不出现在 items[]，否则会淹没真正的超标档案
    assert all(row["table_name"] != "memory_counter" for row in payload["items"])
    assert [row["key"] for row in payload["items"]] == ["1"]


async def test_archive_stats_scoped_to_one_table(skill, service) -> None:
    await _seed(service, "user_profile", "1", "x" * 12000)
    await _seed(service, "group_profile", "888", "y" * 12000)

    payload = json.loads(
        await skill.execute("archive_stats", {"table_name": "group_profile"})
    )
    assert [row["table_name"] for row in payload["tables"]] == ["group_profile"]
    assert [row["key"] for row in payload["items"]] == ["888"]
    assert payload["over_limit_count"] == 1


async def test_archive_stats_without_capacity_governance(skill, service) -> None:
    service.configure_overflow_policy(max_total_chars=0)
    await _seed(service, "user_profile", "1", "x" * 12000)
    payload = json.loads(await skill.execute("archive_stats", {}))
    assert payload["max_total_chars"] == 0
    assert payload["over_limit_count"] == 0
    assert payload["tables"][0]["count"] == 1


# ── 工具表与说明书同步 ────────────────────────────────────────────


def test_tools_and_instructions_are_in_sync() -> None:
    skill = ArchiveCRUDSkill()
    names = [tool["function"]["name"] for tool in skill.get_tools()]
    assert "archive_stats" in names
    assert "list_archive" in names
    instructions = skill.instructions
    assert "archive_stats" in instructions
    assert "list_archive" in instructions
    assert PREVIEW_CHARS.__str__() in instructions or "500" in instructions
    assert "read_archive" in instructions and "outline" in instructions


def test_list_archive_schema_advertises_new_limits() -> None:
    skill = ArchiveCRUDSkill()
    tool = next(
        item for item in skill.get_tools() if item["function"]["name"] == "list_archive"
    )
    assert "500" in tool["function"]["description"]
    assert "5" in tool["function"]["parameters"]["properties"]["limit"]["description"]
    stats = next(
        item for item in skill.get_tools() if item["function"]["name"] == "archive_stats"
    )
    props = stats["function"]["parameters"]["properties"]
    assert set(props) == {"table_name", "over_limit_only", "limit"}
