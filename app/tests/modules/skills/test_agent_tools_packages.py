"""技能工具包：共享前缀、主 Agent 暴露开关与 agent_tools 按需子包。"""

from __future__ import annotations

from typing import Any

import pytest

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
    def __init__(
        self,
        name: str,
        tools: list[str],
        *,
        prefix: str = "",
        exposed: bool = True,
    ) -> None:
        self._name = name
        self._prefix = prefix
        self._exposed = exposed
        self._tools = [_tool_def(item) for item in tools]
        self.calls: list[tuple[str, dict]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"{self._name} 描述"

    @property
    def tool_prefix(self) -> str:
        return self._prefix

    @property
    def exposed_to_main_agent(self) -> bool:
        return self._exposed

    def get_tools(self) -> list[dict]:
        return self._tools

    async def execute(self, tool_name: str, args: dict) -> str:
        self.calls.append((tool_name, args))
        return f"ok:{tool_name}"


def _names(tools: list[dict]) -> set[str]:
    return {tool["function"]["name"] for tool in tools}


# ── 共享前缀 ─────────────────────────────────────────────────────


def test_shared_prefix_lets_several_skills_publish_one_namespace():
    manager = SkillManager()
    manager.register(_Skill("pkg_a", ["read", "write"], prefix="tools"))
    manager.register(_Skill("pkg_b", ["grep"], prefix="tools"))

    assert _names(manager.get_tools()) == {"tools__read", "tools__write", "tools__grep"}


@pytest.mark.asyncio
async def test_shared_prefix_routes_by_final_tool_name():
    manager = SkillManager()
    first = _Skill("pkg_a", ["read"], prefix="tools")
    second = _Skill("pkg_b", ["grep"], prefix="tools")
    manager.register(first)
    manager.register(second)

    assert await manager.execute("tools__grep", {}) == "ok:grep"
    assert second.calls == [("grep", {})]
    assert first.calls == []


def test_duplicate_final_tool_name_across_shared_prefix_is_rejected():
    manager = SkillManager()
    manager.register(_Skill("pkg_a", ["read"], prefix="tools"))

    with pytest.raises(ValueError, match="重复的最终工具定义"):
        manager.register(_Skill("pkg_b", ["read"], prefix="tools"))


def test_invalid_tool_prefix_is_rejected():
    manager = SkillManager()
    with pytest.raises(ValueError, match="工具前缀"):
        manager.register(_Skill("bad", ["read"], prefix="has space"))


# ── 主 Agent 暴露开关 ────────────────────────────────────────────


def test_unexposed_skill_never_reaches_main_agent():
    manager = SkillManager()
    manager.register(_Skill("hidden", ["run"], exposed=False))
    manager.register(_Skill("shown", ["run"]))

    assert _names(manager.get_tools()) == {"shown__run"}
    # 显式激活也拿不到：它不属于主 Agent 的呈现层
    assert _names(manager.get_tools(["hidden"])) == {"shown__run"}
    assert "hidden" not in manager.deferred_skill_names
    assert "- hidden:" not in manager.get_instructions()
    # 独立 Agent 自建工具集仍可取全量
    assert _names(manager.get_all_tools()) == {"hidden__run", "shown__run"}


# ── agent_tools 按需子包 ─────────────────────────────────────────


class _FakeRuntime:
    def definitions(self, *, mode: str | None = None, **_: Any) -> list[dict]:
        return [
            _tool_def(name)
            for name in ("read", "write", "edit", "glob", "grep", "run_python",
                         "pwsh", "web_search", "web_fetch", "todo_write",
                         "ask_user_question", "lsp", "read_image", "skill")
        ]


class _FakeOwner(SkillModule):
    """替代 AgentToolsSkill：只提供 runtime.definitions 与执行入口。"""

    def __init__(self) -> None:
        self.runtime = _FakeRuntime()
        self.calls: list[tuple[str, dict]] = []

    @property
    def name(self) -> str:
        return "agent_tools"

    @property
    def description(self) -> str:
        return "owner"

    @property
    def exposed_to_main_agent(self) -> bool:
        return False

    def get_tools(self) -> list[dict]:
        return []

    async def execute(self, tool_name: str, args: dict) -> str:
        self.calls.append((tool_name, args))
        return f"executed:{tool_name}"


def _packages_manager(eager: set[str] | None = None) -> tuple[SkillManager, _FakeOwner]:
    from neobot_app.skills.agent_tools_packages import build_agent_tool_packages

    manager = SkillManager(eager_tool_skills=eager)
    owner = _FakeOwner()
    manager.register(owner)
    for package in build_agent_tool_packages(owner):
        manager.register(package)
    return manager, owner


def test_packages_are_not_resident_by_default():
    """生产默认常驻名单里不应出现 agent_tools 及其任何子包。"""
    from neobot_app.skills import DEFAULT_EAGER_TOOL_SKILLS

    assert not any(name.startswith("agent_tools") for name in DEFAULT_EAGER_TOOL_SKILLS)

    manager, _ = _packages_manager(eager=set(DEFAULT_EAGER_TOOL_SKILLS))
    assert _names(manager.get_tools()) == set()


def test_packages_share_the_agent_tools_namespace():
    """加载后工具名必须与 umbrella 时代完全一致，模型无需感知拆包。"""
    manager, _ = _packages_manager(eager=set())

    assert _names(manager.get_tools()) == set()
    loaded = _names(manager.get_tools(["agent_tools_files", "agent_tools_web"]))
    assert loaded == {
        "agent_tools__read",
        "agent_tools__write",
        "agent_tools__edit",
        "agent_tools__glob",
        "agent_tools__grep",
        "agent_tools__web_search",
        "agent_tools__web_fetch",
    }


def test_packages_cover_every_native_leaf_exactly_once():
    """拆包不得漏掉或重复任何叶子工具。"""
    manager, owner = _packages_manager(eager=set())
    every = _names(manager.get_all_tools())
    expected = {f"agent_tools__{d['function']['name']}" for d in _FakeRuntime().definitions()}
    assert every == expected


@pytest.mark.asyncio
async def test_package_execution_delegates_to_shared_runtime_owner():
    manager, owner = _packages_manager(eager=set())

    result = await manager.execute("agent_tools__todo_write", {"todos": []})
    assert result == "executed:todo_write"
    assert owner.calls == [("todo_write", {"todos": []})]

    # 技能名本身不是工具名：直接调技能名必须报未知工具，不能误路由
    assert (await manager.execute("agent_tools_plan", {})).startswith("未知工具")
