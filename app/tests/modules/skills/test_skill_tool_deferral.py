"""技能工具定义按需加载:默认不注入提示词,由 skills__load_tools 显式激活。"""

from __future__ import annotations

from typing import Any

from neobot_app.skills.base import SkillManager


def _tool_def(name: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }


class _Skill:
    instructions = ""

    def __init__(self, name: str, tools: list[str]) -> None:
        self.name = name
        self.description = f"{name} 描述"
        self._tools = [_tool_def(item) for item in tools]

    def get_tools(self) -> list[dict[str, Any]]:
        return self._tools

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        return "ok"


def _manager(*, eager: set[str] | None) -> SkillManager:
    manager = SkillManager(eager_tool_skills=eager)
    manager.register(_Skill("always", ["ping"]))
    manager.register(_Skill("lazy", ["fetch", "store"]))
    return manager


def _names(tools: list[dict[str, Any]]) -> set[str]:
    return {tool["function"]["name"] for tool in tools}


def test_without_eager_list_all_skill_tools_stay_resident():
    """未配置常驻列表时保持历史行为：全部技能工具都注入。"""
    manager = _manager(eager=None)
    assert manager.is_tool_deferred("lazy") is False
    assert manager.deferred_skill_names == []
    assert _names(manager.get_tools()) == {"always__ping", "lazy__fetch", "lazy__store"}


def test_deferred_skill_tools_are_absent_until_activated():
    """配置常驻列表后，未激活技能的工具定义不得出现在提示词里。"""
    manager = _manager(eager={"always"})

    assert manager.is_tool_deferred("lazy") is True
    assert manager.deferred_skill_names == ["lazy"]
    assert _names(manager.get_tools()) == {"always__ping"}

    activated = _names(manager.get_tools({"lazy"}))
    assert activated == {"always__ping", "lazy__fetch", "lazy__store"}


def test_activating_unknown_skill_does_not_add_tools():
    manager = _manager(eager={"always"})
    assert _names(manager.get_tools({"missing"})) == {"always__ping"}


def test_get_all_tools_ignores_deferral_for_standalone_agents():
    """独立 Agent(沙箱维护等)自建工具集时必须一次拿到全部工具。"""
    manager = _manager(eager={"always"})
    assert _names(manager.get_all_tools()) == {
        "always__ping",
        "lazy__fetch",
        "lazy__store",
    }


def test_skill_tool_names_are_prefixed_and_complete():
    manager = _manager(eager=set())
    assert manager.skill_tool_names("lazy") == ["lazy__fetch", "lazy__store"]
    assert manager.skill_tool_names("missing") == []


def test_instructions_still_list_every_skill():
    """工具定义被延后不影响一行摘要索引：模型必须仍能发现技能。"""
    manager = _manager(eager={"always"})
    instructions = manager.get_instructions()
    assert "- always: always 描述" in instructions
    assert "- lazy: lazy 描述" in instructions


def test_full_injection_payload_shrinks_after_deferral():
    """按需加载的核心收益：注入的 schema 体积显著下降。"""
    manager = SkillManager()
    for index in range(6):
        manager.register(
            _Skill(f"skill{index}", [f"tool{index}_{n}" for n in range(4)])
        )
    eager_only = SkillManager(eager_tool_skills={"skill0"})
    for index in range(6):
        eager_only.register(
            _Skill(f"skill{index}", [f"tool{index}_{n}" for n in range(4)])
        )

    import json

    full = len(json.dumps(manager.get_tools(), ensure_ascii=False))
    deferred = len(json.dumps(eager_only.get_tools(), ensure_ascii=False))
    assert deferred < full
