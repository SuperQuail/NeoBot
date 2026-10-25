"""BilibiliMemorySkill 测试：三类档案的增查列删与表名白名单。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from neobot_app.skills.bilibili_memory import BilibiliMemorySkill


class FakeArchive:
    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], SimpleNamespace] = {}
        self.deleted: list[tuple[str, str]] = []
        self.last_list: dict = {}

    async def get(self, table, key):
        return self.entries.get((table, key))

    async def set(self, table, key, value, tags):
        self.entries[(table, key)] = SimpleNamespace(
            table_name=table, key=key, value=value, tags=list(tags)
        )

    async def list(self, table, *, key_query=None, limit=50, offset=0):
        self.last_list = {"table": table, "key_query": key_query, "limit": limit, "offset": offset}
        items = [
            item
            for (table_name, _key), item in self.entries.items()
            if table_name == table
        ]
        return items[offset : offset + limit]

    async def delete(self, table, key):
        existed = self.entries.pop((table, key), None)
        self.deleted.append((table, key))
        return existed is not None


def _skill(archive=None) -> BilibiliMemorySkill:
    return BilibiliMemorySkill(archive_service=archive or FakeArchive())


async def test_save_read_roundtrip() -> None:
    archive = FakeArchive()
    skill = _skill(archive)

    saved = json.loads(
        await skill.execute(
            "save_memory",
            {
                "table_name": "bv_video",
                "key": "BV1xx411c7mD",
                "value": "鬼畜视频",
                "tags": ["鬼畜"],
            },
        )
    )
    read = json.loads(
        await skill.execute(
            "read_memory", {"table_name": "bv_video", "key": "BV1xx411c7mD"}
        )
    )

    assert saved["ok"] is True
    assert read["found"] is True
    assert read["item"]["value"] == "鬼畜视频"
    assert read["item"]["tags"] == ["鬼畜"]


async def test_read_missing_returns_found_false() -> None:
    result = json.loads(
        await _skill().execute("read_memory", {"table_name": "cv_column", "key": "CV1"})
    )

    assert result["ok"] is True
    assert result["found"] is False


async def test_list_memory_clamps_limit_and_passes_filter() -> None:
    archive = FakeArchive()
    await archive.set("bilibili_user", "77", "记忆", [])
    skill = _skill(archive)

    result = json.loads(
        await skill.execute(
            "list_memory",
            {"table_name": "bilibili_user", "key_query": "7", "limit": 100},
        )
    )

    assert result["count"] == 1
    assert archive.last_list["limit"] == 50
    assert archive.last_list["key_query"] == "7"


async def test_delete_memory() -> None:
    archive = FakeArchive()
    await archive.set("bv_video", "BV1", "x", [])
    skill = _skill(archive)

    result = json.loads(
        await skill.execute("delete_memory", {"table_name": "bv_video", "key": "BV1"})
    )

    assert result["ok"] is True
    assert result["deleted"] is True
    assert ("bv_video", "BV1") in archive.deleted


async def test_table_allowlist_rejects_other_tables() -> None:
    skill = _skill()

    result = json.loads(
        await skill.execute(
            "save_memory", {"table_name": "user_profile", "key": "1", "value": "x"}
        )
    )

    assert result["ok"] is False
    assert "不允许的表名" in result["error"]


async def test_missing_required_fields() -> None:
    skill = _skill()

    assert json.loads(
        await skill.execute("save_memory", {"table_name": "bv_video", "key": "", "value": ""})
    )["ok"] is False
    assert json.loads(
        await skill.execute("read_memory", {"table_name": "bv_video", "key": ""})
    )["ok"] is False
    assert json.loads(
        await skill.execute("delete_memory", {"table_name": "bv_video", "key": ""})
    )["ok"] is False


def test_no_archive_means_no_tools() -> None:
    assert BilibiliMemorySkill().get_tools() == []


async def test_save_memory_splits_comma_separated_tags() -> None:
    archive = FakeArchive()
    skill = _skill(archive)

    saved = json.loads(
        await skill.execute(
            "save_memory",
            {
                "table_name": "bv_video",
                "key": "BV1xx411c7mD",
                "value": "鬼畜视频",
                "tags": "鬼畜, 合集",
            },
        )
    )
    assert saved["ok"] is True
    assert archive.entries[("bv_video", "BV1xx411c7mD")].tags == ["鬼畜", "合集"]

    read = json.loads(
        await skill.execute(
            "read_memory", {"table_name": "bv_video", "key": "BV1xx411c7mD"}
        )
    )
    assert read["item"]["tags"] == ["鬼畜", "合集"]


async def test_save_memory_drops_unusable_tags() -> None:
    archive = FakeArchive()
    skill = _skill(archive)

    await skill.execute(
        "save_memory",
        {"table_name": "bv_video", "key": "BV2", "value": "x", "tags": 123},
    )
    assert archive.entries[("bv_video", "BV2")].tags == []

    await skill.execute(
        "save_memory",
        {"table_name": "bv_video", "key": "BV3", "value": "x", "tags": ["  ", None, "搞笑"]},
    )
    assert archive.entries[("bv_video", "BV3")].tags == ["搞笑"]
