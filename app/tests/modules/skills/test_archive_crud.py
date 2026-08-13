"""ArchiveCRUDSkill 测试:完整保存不截断、摘要生成、offset 分页阅读。"""

from __future__ import annotations

import json
from types import SimpleNamespace

from neobot_app.skills.archive_crud import (
    ArchiveCRUDSkill,
    _read_item_payload,
)


def _item(value: str) -> SimpleNamespace:
    return SimpleNamespace(table_name="group_profile", key="42", value=value, version=1)


def _long_text(lines: int = 10, line_len: int = 100) -> str:
    return "\n".join(f"第{i}行-" + "x" * line_len for i in range(1, lines + 1))


# ── 保存:完整写入,不截断 ─────────────────────────────────────────


async def test_save_archive_keeps_full_value() -> None:
    """保存超长档案时不得截断,原始内容完整入库。"""
    saved: list[tuple] = []

    class _FakeService:
        async def set(self, table_name, key, value, tags):
            saved.append((table_name, key, value, tags))
            return SimpleNamespace(
                table_name=table_name, key=key, value=value, version=7
            )

    skill = ArchiveCRUDSkill(
        archive_service=_FakeService(),
        max_chars={"user_profile": 300, "group_profile": 1500},
    )
    value = "x" * 5000
    result = json.loads(await skill.execute("save_archive", {"table_name": "group_profile", "key": "42", "value": value}))

    assert result["ok"] is True
    assert result["version"] == 7
    assert "truncated" not in result
    assert saved[0][2] == value  # 完整保留


# ── 摘要生成 ─────────────────────────────────────────────────────


def test_build_summary_keeps_tail_within_limit() -> None:
    text = _long_text()
    summary, truncated = ArchiveCRUDSkill.build_summary(text, 500)

    assert truncated is True
    assert len(summary) <= 500
    assert summary.startswith("第")  # 从完整行开始


def test_build_summary_short_text_unchanged() -> None:
    summary, truncated = ArchiveCRUDSkill.build_summary("short", 1500)

    assert truncated is False
    assert summary == "short"


# ── 分页读取 ─────────────────────────────────────────────────────


def test_read_item_payload_without_offset_returns_full() -> None:
    value = _long_text()
    payload = _read_item_payload(_item(value), offset=None)

    assert payload["value"] == value
    assert payload["total_chars"] == len(value)
    assert "offset" not in payload


def test_read_item_payload_positive_offset_pages() -> None:
    value = _long_text(lines=10, line_len=100)  # 每行约 106 字,共约 1060 字
    first = _read_item_payload(_item(value), offset=0)
    second = _read_item_payload(_item(value), offset=1)

    assert first["offset"] == 0
    assert len(first["value"]) <= 500
    assert first["value"].startswith("第1行")
    assert first["has_more_forward"] is True
    assert first["has_more_backward"] is False
    assert second["value"].startswith("第")
    assert second["value"] != first["value"]
    assert second["has_more_backward"] is True


def test_read_item_payload_negative_offset_reads_tail() -> None:
    value = _long_text(lines=10, line_len=100)
    last = _read_item_payload(_item(value), offset=-1)
    prev = _read_item_payload(_item(value), offset=-2)

    # 最后一项包含档案末尾(最新内容)
    assert value.endswith(last["value"]) or last["value"].endswith(value.splitlines()[-1])
    assert last["has_more_forward"] is False
    assert last["has_more_backward"] is True
    # 倒数第二页在最后一页之前
    tail_pos = value.find(last["value"])
    prev_pos = value.find(prev["value"])
    assert prev_pos < tail_pos


def test_read_item_payload_offset_out_of_range() -> None:
    value = _long_text(lines=2, line_len=50)
    payload = _read_item_payload(_item(value), offset=99)

    assert payload["value"] == ""
    assert payload["has_more_forward"] is False
    assert payload["has_more_backward"] is True


def test_read_item_payload_aligns_line_boundaries() -> None:
    # 构造 500 字符整页,确保正偏移 1 的页从完整行开始且不以半行结尾
    value = _long_text(lines=20, line_len=100)
    second = _read_item_payload(_item(value), offset=1)

    content = second["value"]
    if content:
        # 行首对齐(以"第"开头)或为空
        assert content.startswith("第") or content == ""
        # 行尾对齐:结尾是换行或到达档案末尾
        assert content.endswith("\n") or second["has_more_forward"] is False


async def test_read_archive_handler_supports_offset() -> None:
    class _FakeService:
        async def get(self, table_name, key):
            return _item("第1行\n" + "y" * 2000)

    skill = ArchiveCRUDSkill(archive_service=_FakeService())
    result = json.loads(
        await skill.execute(
            "read_archive", {"table_name": "group_profile", "key": "42", "offset": -1}
        )
    )

    assert result["ok"] is True
    item = result["item"]
    assert item["offset"] == -1
    assert item["total_chars"] > 500
    assert len(item["value"]) <= 500
    assert item["has_more_forward"] is False
    assert item["has_more_backward"] is True
    assert item["value"].endswith("y" * 500)


async def test_read_archive_handler_bad_offset_rejected() -> None:
    skill = ArchiveCRUDSkill(archive_service=object())
    result = json.loads(
        await skill.execute(
            "read_archive", {"table_name": "group_profile", "key": "42", "offset": "abc"}
        )
    )

    assert result["ok"] is False
    assert "offset" in result["error"]
