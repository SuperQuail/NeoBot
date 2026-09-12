"""archive_crud 写入路径必须把「超限 / 拒绝」如实回给模型（spec(1) R2 / 4.4）。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from neobot_app.skills.archive_crud import ArchiveCRUDSkill


class _OutcomeService:
    """返回 ArchiveWriteOutcome 风格结果的假档案服务。"""

    def __init__(
        self,
        *,
        stored: bool = True,
        over_limit: bool = False,
        scheduled: bool = False,
        action: str = "none",
        hint: str = "",
        error: str = "",
        chars: int = 0,
        max_total_chars: int = 0,
        old_value: str | None = None,
    ) -> None:
        self._stored = stored
        self.over_limit = over_limit
        self.scheduled = scheduled
        self.action = action
        self.hint = hint
        self.error = error
        self.chars = chars
        self.max_total_chars = max_total_chars
        self.old_value = old_value
        self.writes: list[tuple[str, str, str]] = []

    async def get(self, table_name: str, key: str):
        if self.old_value is None:
            return None
        return SimpleNamespace(
            table_name=table_name, key=key, value=self.old_value, tags=[], version=3
        )

    async def set_with_outcome(self, table_name: str, key: str, value: str, tags: Any):
        if self._stored:
            self.writes.append((table_name, key, value))
        item = (
            SimpleNamespace(table_name=table_name, key=key, value=value, version=5)
            if self._stored
            else None
        )
        return SimpleNamespace(
            item=item,
            over_limit=self.over_limit,
            action=self.action,
            scheduled=self.scheduled,
            chars=self.chars or len(value or ""),
            max_total_chars=self.max_total_chars,
            hint=self.hint,
            error=self.error,
        )


class _LegacyService:
    """只实现 set 的旧档案服务（退化为老路径）。"""

    def __init__(self) -> None:
        self.writes: list[tuple[str, str, str]] = []

    async def get(self, table_name: str, key: str):
        return None

    async def set(self, table_name: str, key: str, value: str, tags: Any):
        self.writes.append((table_name, key, value))
        return SimpleNamespace(table_name=table_name, key=key, value=value, version=1)


async def test_save_archive_reports_over_limit_and_compression_hint() -> None:
    """超限写入仍为 ok=True，但必须带 over_limit / compressing / hint。"""
    service = _OutcomeService(
        over_limit=True,
        scheduled=True,
        action="summarize",
        hint="档案已超过存储上限 10000 字（当前 12000 字），已触发后台自动压缩。",
        chars=12000,
        max_total_chars=10000,
    )
    skill = ArchiveCRUDSkill(archive_service=service)

    result = json.loads(
        await skill.execute(
            "save_archive", {"table_name": "user_profile", "key": "1", "value": "x" * 12000}
        )
    )

    assert result["ok"] is True
    assert result["over_limit"] is True
    assert result["compressing"] is True
    assert result["total_chars"] == 12000
    assert result["max_total_chars"] == 10000
    assert "压缩" in result["hint"]
    assert service.writes and len(service.writes[0][2]) == 12000  # 原文照常落库


async def test_save_archive_without_limit_has_no_overflow_fields() -> None:
    service = _OutcomeService()
    skill = ArchiveCRUDSkill(archive_service=service)

    result = json.loads(
        await skill.execute(
            "save_archive", {"table_name": "user_profile", "key": "1", "value": "短内容"}
        )
    )

    assert result["ok"] is True
    assert "over_limit" not in result
    assert "hint" not in result


async def test_save_archive_reject_returns_explicit_error() -> None:
    """overflow_action=reject：明确拒绝 + 压缩指引，且不写库。"""
    service = _OutcomeService(
        stored=False,
        over_limit=True,
        action="reject",
        hint="请先用 read_archive 的 outline/offset 分页阅读，再用 patch_archive 压缩。",
        error="档案超过存储上限 10000 字（当前 12000 字），已拒绝写入",
        chars=12000,
        max_total_chars=10000,
    )
    skill = ArchiveCRUDSkill(archive_service=service)

    result = json.loads(
        await skill.execute(
            "save_archive", {"table_name": "user_profile", "key": "1", "value": "x" * 12000}
        )
    )

    assert result["ok"] is False
    assert result["over_limit"] is True
    assert "拒绝写入" in result["error"]
    assert "patch_archive" in result["hint"]
    assert result["max_total_chars"] == 10000
    assert service.writes == []


async def test_patch_archive_reports_over_limit_with_applied_count() -> None:
    service = _OutcomeService(
        old_value="旧内容",
        over_limit=True,
        scheduled=False,
        action="summarize",
        hint="档案已超过存储上限 10 字（当前 15 字），原文已完整保留，下次写入会自动重试。",
        chars=15,
        max_total_chars=10,
    )
    skill = ArchiveCRUDSkill(archive_service=service)

    result = json.loads(
        await skill.execute(
            "patch_archive",
            {
                "table_name": "user_profile",
                "key": "1",
                "operations": [{"op": "append", "text": "新增内容"}],
            },
        )
    )

    assert result["ok"] is True
    assert result["over_limit"] is True
    assert result["compressing"] is False
    assert result["applied"] == 1
    assert result["total_chars"] == len("旧内容\n新增内容")
    assert "下次写入" in result["hint"]


async def test_patch_archive_reject_keeps_original_value() -> None:
    service = _OutcomeService(
        stored=False,
        old_value="原始内容",
        over_limit=True,
        action="reject",
        error="档案超过存储上限 10 字（当前 20 字），已拒绝写入",
        hint="请压缩后再写入。",
        max_total_chars=10,
    )
    skill = ArchiveCRUDSkill(archive_service=service)

    result = json.loads(
        await skill.execute(
            "patch_archive",
            {
                "table_name": "user_profile",
                "key": "1",
                "operations": [{"op": "append", "text": "很长的增量内容" * 3}],
            },
        )
    )

    assert result["ok"] is False
    assert "拒绝写入" in result["error"]
    assert service.writes == []


async def test_legacy_service_without_outcome_still_works() -> None:
    """档案服务只实现 set 时退化为老路径（不返回 over_limit 字段，也不报错）。"""
    service = _LegacyService()
    skill = ArchiveCRUDSkill(archive_service=service)

    result = json.loads(
        await skill.execute(
            "save_archive", {"table_name": "user_profile", "key": "1", "value": "内容"}
        )
    )

    assert result["ok"] is True
    assert result["version"] == 1
    assert "over_limit" not in result
    assert service.writes == [("user_profile", "1", "内容")]
