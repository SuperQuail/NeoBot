"""AgentDelegationSkill 测试 — 空 enum 省略、_delegate_context 剥离、参数透传过滤。"""

from __future__ import annotations

from typing import Any

import pytest

from neobot_app.skills.agent_delegation import AgentDelegationSkill


class _FakeRegistry:
    def __init__(self, names: list[str] | None = None) -> None:
        self._names = list(names or [])
        self.delegated: dict[str, Any] | None = None
        self.listed_agent: Any = None

    @property
    def names(self) -> list[str]:
        return list(self._names)

    def list_agents(self, name: str | None = None) -> str:
        self.listed_agent = name
        return "list-ok"

    async def delegate(self, **kwargs: Any) -> str:
        self.delegated = kwargs
        return "delegate-ok"


def _tools(skill: AgentDelegationSkill) -> dict[str, dict]:
    return {tool["function"]["name"]: tool["function"] for tool in skill.get_tools()}


def test_empty_registry_omits_enum() -> None:
    """没有注册 Agent 时 schema 不能带空 enum（OpenAI 系提供商会拒绝）。"""
    skill = AgentDelegationSkill(_FakeRegistry())
    tools = _tools(skill)
    props = tools["delegate"]["parameters"]["properties"]
    for prop in (
        props["agent"],
        props["tasks"]["items"]["properties"]["agent"],
        tools["list"]["parameters"]["properties"]["agent"],
    ):
        assert "enum" not in prop


def test_non_empty_registry_includes_enum() -> None:
    skill = AgentDelegationSkill(_FakeRegistry(["demo.echo", "demo.worker"]))
    tools = _tools(skill)
    props = tools["delegate"]["parameters"]["properties"]
    assert props["agent"]["enum"] == ["demo.echo", "demo.worker"]
    assert props["tasks"]["items"]["properties"]["agent"]["enum"] == [
        "demo.echo",
        "demo.worker",
    ]


async def test_execute_delegate_strips_injected_keys_and_filters_unknown() -> None:
    """_delegate_context/pipeline_key/_numbering_mapping 必须剥离，模型幻想的键不得透传。"""
    registry = _FakeRegistry(["demo.echo"])
    skill = AgentDelegationSkill(registry)

    result = await skill.execute(
        "delegate",
        {
            "agent": "demo.echo",
            "task": "hello",
            "previous_response": "prev",
            "_delegate_context": "chat-ctx",
            "pipeline_key": "group:1",
            "_numbering_mapping": {"1": "m1"},
            "hallucinated_key": 42,
        },
    )

    assert result == "delegate-ok"
    assert registry.delegated == {
        "agent": "demo.echo",
        "task": "hello",
        "previous_response": "prev",
        "context": "chat-ctx",
    }


async def test_execute_delegate_without_context_passes_empty() -> None:
    registry = _FakeRegistry(["demo.echo"])
    skill = AgentDelegationSkill(registry)

    result = await skill.execute("delegate", {"agent": "demo.echo"})

    assert result == "delegate-ok"
    assert registry.delegated == {"agent": "demo.echo", "context": ""}


async def test_execute_list_forwards_agent_param() -> None:
    registry = _FakeRegistry(["demo.echo"])
    skill = AgentDelegationSkill(registry)

    result = await skill.execute("list", {"agent": "demo.echo", "_delegate_context": "x"})

    assert result == "list-ok"
    assert registry.listed_agent == "demo.echo"


async def test_execute_unknown_tool_returns_error_text() -> None:
    skill = AgentDelegationSkill(_FakeRegistry())

    result = await skill.execute("hack", {})

    assert result == "Unknown agent tool: hack"


# ── SkillManager 注册校验（__ 分隔符歧义） ──────────────────────


class _NamedSkill(AgentDelegationSkill):
    """允许自定义 name 的假 Skill，用于注册校验测试。"""

    def __init__(self, name: str) -> None:
        self._skill_name = name

    @property
    def name(self) -> str:
        return self._skill_name

    @property
    def description(self) -> str:
        return "fake"

    def get_tools(self) -> list[dict]:
        return []

    async def execute(self, tool_name: str, args: dict) -> str:
        return "ok"


def test_skill_manager_register_rejects_double_underscore_name() -> None:
    """Skill 名称含 __ 会与 {skill}__{tool} 路由分隔符冲突，注册时必须拒绝。"""
    from neobot_app.skills.base import SkillManager

    mgr = SkillManager()
    with pytest.raises(ValueError, match="__"):
        mgr.register(_NamedSkill("a__b"))
    assert mgr.skill_names == []


def test_skill_manager_register_accepts_normal_name() -> None:
    from neobot_app.skills.base import SkillManager

    mgr = SkillManager()
    skill = _NamedSkill("weather")
    mgr.register(skill)
    assert mgr.skill_names == ["weather"]
