"""SleepSkill 测试:工具定义、睡眠/唤醒/状态查询与使用原则。"""

from __future__ import annotations

import json

from neobot_app.runtime.sleep_service import SleepService
from neobot_app.skills.base import SkillManager
from neobot_app.skills.sleep_skill import SleepSkill


def _make() -> tuple[SleepSkill, SleepService]:
    service = SleepService()
    return SleepSkill(sleep_service=service), service


def test_skill_tool_names_and_prefixing() -> None:
    skill, _ = _make()
    names = [tool["function"]["name"] for tool in skill.get_tools()]
    assert names == ["go_to_sleep", "wake_up", "get_sleep_status"]

    manager = SkillManager()
    manager.register(skill)
    prefixed = [tool["function"]["name"] for tool in manager.get_tools()]
    assert "sleep__go_to_sleep" in prefixed
    assert "sleep__wake_up" in prefixed
    assert "sleep__get_sleep_status" in prefixed


def test_instructions_include_guidance() -> None:
    skill, _ = _make()
    assert "尽量不要去睡觉" in skill.instructions
    assert "12 小时" in skill.instructions


async def test_go_to_sleep() -> None:
    skill, service = _make()
    result = json.loads(await skill.execute("go_to_sleep", {"duration": "2h"}))
    assert result["ok"] is True
    assert result["duration_seconds"] == 7200
    assert service.is_sleeping()


async def test_go_to_sleep_invalid_duration() -> None:
    skill, service = _make()
    result = json.loads(
        await skill.execute("go_to_sleep", {"duration": "13h"})
    )
    assert result["ok"] is False
    assert "12" in result["error"]
    assert not service.is_sleeping()


async def test_go_to_sleep_missing_duration() -> None:
    skill, service = _make()
    result = json.loads(await skill.execute("go_to_sleep", {}))
    assert result["ok"] is False
    assert not service.is_sleeping()


async def test_wake_up() -> None:
    skill, service = _make()
    service.sleep(3600)
    result = json.loads(await skill.execute("wake_up", {}))
    assert result["ok"] is True
    assert result["was_sleeping"] is True
    assert not service.is_sleeping()


async def test_get_sleep_status() -> None:
    skill, service = _make()
    status = json.loads(await skill.execute("get_sleep_status", {}))
    assert status["sleeping"] is False
    assert status["remaining_seconds"] == 0

    service.sleep(3600)
    status = json.loads(await skill.execute("get_sleep_status", {}))
    assert status["sleeping"] is True
    assert status["remaining_seconds"] > 0
    assert status["wake_up_at_text"]


async def test_manager_execution() -> None:
    skill, service = _make()
    manager = SkillManager()
    manager.register(skill)

    result = json.loads(
        await manager.execute("sleep__go_to_sleep", {"duration": "30m"})
    )
    assert result["ok"] is True
    assert service.is_sleeping()

    status = json.loads(await manager.execute("sleep__get_sleep_status", {}))
    assert status["sleeping"] is True

    await manager.execute("sleep__wake_up", {})
    assert not service.is_sleeping()


async def test_skill_without_service_reports_unavailable() -> None:
    skill = SleepSkill(sleep_service=None)
    result = json.loads(await skill.execute("go_to_sleep", {"duration": "1h"}))
    assert result["ok"] is False
    assert "未配置" in result["error"]


async def test_unknown_tool() -> None:
    skill, _ = _make()
    result = json.loads(await skill.execute("fly_to_moon", {}))
    assert result["ok"] is False
