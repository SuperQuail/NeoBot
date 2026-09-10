from __future__ import annotations

from typing import Any

import pytest

from neobot_app.skills.base import SkillManager


def _tool(
    name: str = "run", parameters: dict[str, Any] | None = None
) -> dict[str, Any]:
    function: dict[str, Any] = {"name": name, "description": name}
    if parameters is not None:
        function["parameters"] = parameters
    return {"type": "function", "function": function}


class _Skill:
    description = "test skill"
    instructions = "test instructions"

    def __init__(
        self,
        name: str,
        tools: list[dict[str, Any]] | None = None,
        *,
        session_tools: set[str] | None = None,
        result: str = "ok",
    ) -> None:
        self.name = name
        self.tools = [] if tools is None else tools
        self.session_tools = set() if session_tools is None else session_tools
        self.result = result
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get_tools(self) -> list[dict[str, Any]]:
        return self.tools

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        self.calls.append((tool_name, args))
        return self.result

    def reset(self) -> None:
        pass


@pytest.mark.parametrize(
    "name",
    ["has space", "技能", "x" * 65, "part__part", "trailing_"],
)
def test_zero_tool_registration_rejects_invalid_skill_names(name: str) -> None:
    manager = SkillManager()

    with pytest.raises(ValueError, match="Skill 名称"):
        manager.register(_Skill(name))

    assert manager.skill_names == []


def test_zero_tool_registration_accepts_maximum_length_skill_name() -> None:
    manager = SkillManager()
    manager.register(_Skill("x" * 64))

    assert manager.skill_names == ["x" * 64]


async def test_registered_skill_with_unknown_local_tool_returns_unknown_tool() -> None:
    skill = _Skill("demo", [_tool()])
    manager = SkillManager()
    manager.register(skill)

    result = await manager.execute("demo__missing", {})

    assert result == "未知工具: demo__missing"
    assert skill.calls == []


def test_get_skill_tools_returns_prefixed_deep_copies() -> None:
    """get_skill_tools 返回带 {name}__ 前缀的副本，供子 agent 挂载工具时使用。"""
    manager = SkillManager()
    manager.register(_Skill("demo", [_tool()]))

    tools = manager.get_skill_tools("demo")

    assert [tool["function"]["name"] for tool in tools] == ["demo__run"]
    tools[0]["function"]["name"] = "mutated"
    assert manager.get_skill_tools("demo")[0]["function"]["name"] == "demo__run"
    assert manager.get_skill_tools("missing") == []


def test_pattern_properties_regex_keys_are_validated() -> None:
    valid = {
        "type": "object",
        "properties": {
            "labels": {
                "type": "object",
                "patternProperties": {r"^[a-z][a-z0-9_]*$": {"type": "string"}},
            }
        },
        "required": [],
    }
    SkillManager().register(_Skill("valid_pattern", [_tool(parameters=valid)]))

    invalid = {
        "type": "object",
        "patternProperties": {"[": {"type": "string"}},
        "required": [],
    }
    with pytest.raises(ValueError, match="patternProperties regex"):
        SkillManager().register(_Skill("invalid_pattern", [_tool(parameters=invalid)]))


@pytest.mark.parametrize(
    "array_schema",
    [
        {"type": "array", "items": [{"type": "string"}]},
        {
            "type": "array",
            "prefixItems": [{"type": "string"}],
            "items": False,
        },
    ],
)
def test_tuple_schemas_are_rejected_with_clear_policy(
    array_schema: dict[str, Any],
) -> None:
    parameters = {
        "type": "object",
        "properties": {"values": array_schema},
        "required": [],
    }

    with pytest.raises(ValueError, match="unsupported tuple schema"):
        SkillManager().register(_Skill("tuple_schema", [_tool(parameters=parameters)]))


def test_recursive_ref_is_rejected_with_clear_policy() -> None:
    parameters = {
        "type": "object",
        "properties": {"next": {"$ref": "#"}},
        "required": [],
    }

    with pytest.raises(ValueError, match="unsupported recursive ref"):
        SkillManager().register(
            _Skill("recursive_schema", [_tool(parameters=parameters)])
        )


def test_non_recursive_local_ref_remains_supported() -> None:
    parameters = {
        "type": "object",
        "properties": {"value": {"$ref": "#/$defs/Value"}},
        "$defs": {"Value": {"type": "string"}},
        "required": ["value"],
    }

    SkillManager().register(_Skill("local_ref", [_tool(parameters=parameters)]))


def test_missing_parameters_and_boolean_schema_forms_remain_supported() -> None:
    manager = SkillManager()
    manager.register(_Skill("no_parameters", [_tool()]))
    assert manager.get_tools()[0]["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "required": [],
    }

    parameters = {
        "type": "object",
        "properties": {
            "values": {"type": "array", "items": True},
            "metadata": {"type": "object", "additionalProperties": False},
        },
        "required": [],
    }
    SkillManager().register(_Skill("boolean_schema", [_tool(parameters=parameters)]))


def test_registration_is_atomic_and_session_tools_must_be_declared() -> None:
    manager = SkillManager()

    with pytest.raises(ValueError, match="undeclared tools"):
        manager.register(_Skill("atomic", [_tool()], session_tools={"missing"}))

    assert manager.skill_names == []
    assert manager.get_tools() == []


def test_registered_definitions_are_immutable_snapshots() -> None:
    definition = _tool()
    skill = _Skill("snapshot", [definition])
    manager = SkillManager()
    manager.register(skill)

    definition["function"]["description"] = "changed at source"
    exposed = manager.get_tools()
    exposed[0]["function"]["description"] = "changed by caller"

    stored = manager.get_tools()[0]
    assert stored["function"]["name"] == "snapshot__run"
    assert stored["function"]["description"] == "run"


async def test_execution_token_becomes_stale_after_replacement() -> None:
    old = _Skill("replace", [_tool()], result="old")
    manager = SkillManager()
    manager.register(old)
    token = manager.capture_execution_token("replace__run")
    assert token is not None

    manager.unregister("replace")
    new = _Skill("replace", [_tool()], result="new")
    manager.register(new)

    result = await manager.execute("replace__run", {}, token=token)

    assert result == "工具不可用或已更新 [replace__run]"
    assert old.calls == []
    assert new.calls == []


@pytest.mark.parametrize(
    "skill",
    [
        _Skill("skills", [_tool("read_manifest")]),
        _Skill("duplicate", [_tool(), _tool()]),
    ],
)
def test_reserved_and_duplicate_final_names_are_rejected(skill: _Skill) -> None:
    manager = SkillManager()

    with pytest.raises(ValueError):
        manager.register(skill)

    assert manager.skill_names == []
