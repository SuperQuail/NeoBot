"""独立 Agent 的技能工具集：常驻精简集 + skills__load_tools 按需加载。"""

from __future__ import annotations

from typing import Any

from neobot_app.skills.agent_toolset import LiveToolset, SkillToolsetExecutor
from neobot_app.skills.activation import LOADER_TOOL_NAME
from neobot_app.skills.base import SkillManager, SkillModule


def _tool_def(name: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }


class _Skill(SkillModule):
    def __init__(self, name: str, tools: list[str]) -> None:
        self._name = name
        self._tools = [_tool_def(item) for item in tools]
        self.calls: list[tuple[str, dict]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"{self._name} 描述"

    def get_tools(self) -> list[dict]:
        return self._tools

    async def execute(self, tool_name: str, args: dict) -> str:
        self.calls.append((tool_name, args))
        return f"ok:{tool_name}"


def _manager() -> SkillManager:
    manager = SkillManager(eager_tool_skills=set())
    manager.register(_Skill("sandbox_maintenance", ["scan", "clean"]))
    manager.register(_Skill("file_storage", ["read_doc"]))
    manager.register(_Skill("gallery", ["list", "search"]))
    manager.register(_Skill("browser", ["open"]))
    return manager


def _names(definitions: list[dict]) -> set[str]:
    return {item["function"]["name"] for item in definitions}


def test_resident_skills_come_with_loader_but_nothing_else():
    executor = SkillToolsetExecutor(
        _manager(), resident={"sandbox_maintenance", "file_storage"}
    )
    names = _names(executor.definitions())

    assert names == {
        "sandbox_maintenance__scan",
        "sandbox_maintenance__clean",
        "file_storage__read_doc",
        LOADER_TOOL_NAME,
    }


def test_loading_a_skill_adds_its_tools_immediately():
    executor = SkillToolsetExecutor(_manager(), resident={"file_storage"})

    result = executor.activation.load({"skills": ["gallery"]})

    assert "已加载技能工具" in result
    assert "gallery__list" in result
    assert {"gallery__list", "gallery__search"} <= _names(executor.definitions())


def test_loader_enum_lists_only_pending_skills():
    executor = SkillToolsetExecutor(
        _manager(), resident={"file_storage", "sandbox_maintenance"}
    )
    definition = next(
        item for item in executor.definitions()
        if item["function"]["name"] == LOADER_TOOL_NAME
    )
    enum = definition["function"]["parameters"]["properties"]["skills"]["items"]["enum"]
    assert set(enum) == {"gallery", "browser"}

    executor.activation.load({"skills": ["gallery"]})
    definition = next(
        item for item in executor.definitions()
        if item["function"]["name"] == LOADER_TOOL_NAME
    )
    enum = definition["function"]["parameters"]["properties"]["skills"]["items"]["enum"]
    assert set(enum) == {"browser"}


async def test_executor_routes_loader_and_skill_tools():
    manager = _manager()
    executor = SkillToolsetExecutor(manager, resident={"file_storage"})

    loaded = await executor.execute(LOADER_TOOL_NAME, {"skills": ["gallery"]})
    assert "gallery__list" in loaded

    assert await executor.execute("gallery__list", {"page": 1}) == "ok:list"
    assert manager.get("gallery").calls == [("list", {"page": 1})]

    # 未知技能名必须报错而不是静默成功
    assert "未知技能名" in await executor.execute(LOADER_TOOL_NAME, {"skills": ["nope"]})
    assert (await executor.execute(LOADER_TOOL_NAME, {})).startswith("Error")


def test_live_toolset_reflects_activation_changes():
    """维护 Agent 的 Toolset 每轮都会重新取定义，加载后立即可见。"""
    executor = SkillToolsetExecutor(_manager(), resident={"file_storage"})
    toolset = LiveToolset(executor=executor)

    assert "gallery__list" not in _names(toolset.definitions())
    executor.activation.load({"skills": ["gallery"]})
    assert "gallery__list" in _names(toolset.definitions())


def test_live_toolset_matches_plain_toolset_shape():
    """LiveToolset 必须仍是 Toolset（Agent 依赖其接口）。"""
    from neobot_chat.tools.toolset import Toolset

    executor = SkillToolsetExecutor(_manager(), resident={"file_storage"})
    toolset = LiveToolset(executor=executor)
    assert isinstance(toolset, Toolset)
    assert toolset.executor is executor
