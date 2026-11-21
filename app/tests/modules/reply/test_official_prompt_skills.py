"""官方通道：技能索引 / 工具包清单 / 说明枚举不出现官方不可用的技能与工具。

官方协议没有 OneBot 的群管理、好友管理、合并转发、历史消息与任意 API 能力，
也没有真实 QQ 头像；这些技能与工具即使被注册也不能出现在提示词或
skills__view_instructions 枚举里，否则模型会按提示反复调用必失败的工具。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.orchestrator_parts.agent_prompt import AgentPromptMixin
from neobot_app.reply.orchestrator_parts.tool_text import (
    _official_hidden_skill_names,
    _official_tool_usable,
    _render_tool_package_index,
)
from neobot_app.reply.tools import ReplyToolExecutor
from neobot_app.skills.base import SkillManager


def _tool_def(name: str) -> dict:
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

    def get_tools(self) -> list[dict]:
        return self._tools

    async def execute(self, tool_name: str, args: dict) -> str:
        return "ok"


#: 注册用的本地工具名（SkillManager 会加 {skill}__ 前缀）。
_LOCAL_TOOLS_BY_SKILL = {
    "onebot": ["call", "doc"],
    "group_management": ["manage_group"],
    "friend_management": ["manage_friend"],
    "forward_message": ["read_forward_msg"],
    "chat_history": ["read_earlier_messages"],
    "user_profile": ["read_user_info", "analyze_user_avatar"],
    "cross_chat": ["cross_chat_send", "cross_chat_query"],
    "video": ["summarize"],
}
#: 注册后的最终工具名，断言用。
_TOOLS_BY_SKILL = {
    name: [f"{name}__{local}" for local in locals_]
    for name, locals_ in _LOCAL_TOOLS_BY_SKILL.items()
}
#: 整包不可用的技能：官方协议没有 OneBot 群/好友/转发/历史能力。
_HIDDEN_SKILLS = {
    "onebot",
    "group_management",
    "friend_management",
    "forward_message",
    "chat_history",
}


def _manager() -> SkillManager:
    # video 常驻，其余技能延后加载（这样技能索引与工具包清单两条路径都有内容）。
    manager = SkillManager(eager_tool_skills={"video"})
    for name, tools in _LOCAL_TOOLS_BY_SKILL.items():
        manager.register(_Skill(name, tools))
    return manager


class _IndexManager:
    """只实现索引/工具包过滤需要的接口。"""

    def __init__(self, skills: dict[str, list[str]]) -> None:
        self._tools = {name: list(tools) for name, tools in skills.items()}
        self.skill_names = list(skills)
        self.deferred_skill_names = list(skills)

    def skill_tool_names(self, name: str) -> list[str]:
        return list(self._tools.get(name, []))

    def get_tools(self, activated=None, resident=None) -> list:
        return []

    def is_tool_deferred(self, name: str) -> bool:
        return True


@pytest.mark.parametrize(
    "name",
    [
        "onebot__call",
        "group_management__manage_group",
        "friend_management__manage_friend",
        "forward_message__read_forward_msg",
        "chat_history__read_earlier_messages",
        "cross_chat__cross_chat_query",
        "user_profile__analyze_user_avatar",
        # dispatch 已有的官方隐藏工具
        "poke_user",
        "react_emoji",
        "search_qq_emoji",
    ],
)
def test_official_tool_usable_rejects_unsupported_tools(name: str) -> None:
    assert _official_tool_usable(name) is False


@pytest.mark.parametrize(
    "name",
    [
        "send_reply",
        "speak",
        "user_profile__read_user_info",
        "cross_chat__cross_chat_send",
        "video__summarize",
    ],
)
def test_official_tool_usable_keeps_supported_tools(name: str) -> None:
    assert _official_tool_usable(name) is True


def test_official_hidden_skill_names_are_derived_from_tool_capabilities() -> None:
    assert _official_hidden_skill_names(_manager()) == frozenset(_HIDDEN_SKILLS)


def test_tool_package_index_filters_official_entries() -> None:
    manager = _IndexManager(_TOOLS_BY_SKILL)

    plain = _render_tool_package_index(manager)
    for name in _TOOLS_BY_SKILL:
        assert f"- {name}: " in plain

    official = _render_tool_package_index(manager, official_platform=True)
    for name in _HIDDEN_SKILLS:
        assert f"- {name}: " not in official
    # 部分可用的技能保留，但只列官方可用的工具
    assert "- user_profile: user_profile__read_user_info" in official
    assert "user_profile__analyze_user_avatar" not in official
    assert "cross_chat__cross_chat_query" not in official
    assert "cross_chat__cross_chat_send" in official
    assert "- video: video__summarize" in official


def test_skill_index_hides_official_skills() -> None:
    manager = _manager()
    hidden = _official_hidden_skill_names(manager)

    plain = manager.get_instructions()
    for name in _HIDDEN_SKILLS:
        assert f"- {name}:" in plain

    filtered = manager.get_instructions(hidden=hidden)
    for name in _HIDDEN_SKILLS:
        assert f"- {name}:" not in filtered
    assert "- user_profile:" in filtered
    assert "- cross_chat:" in filtered


def _definitions(executor: ReplyToolExecutor) -> dict[str, dict]:
    return {item["function"]["name"]: item for item in executor.definitions()}


def test_view_instructions_enum_filters_official_hidden_skills() -> None:
    manager = _manager()
    official = _definitions(
        ReplyToolExecutor(skill_manager=manager, official_platform=True)
    )
    enum = official["skills__view_instructions"]["function"]["parameters"][
        "properties"
    ]["skill"]["enum"]
    assert set(enum) == set(_TOOLS_BY_SKILL) - _HIDDEN_SKILLS

    plain = _definitions(ReplyToolExecutor(skill_manager=manager))
    plain_enum = plain["skills__view_instructions"]["function"]["parameters"][
        "properties"
    ]["skill"]["enum"]
    assert set(plain_enum) == set(_TOOLS_BY_SKILL)


def test_view_instructions_refuses_hidden_skill_on_official() -> None:
    executor = ReplyToolExecutor(skill_manager=_manager(), official_platform=True)

    refused = executor._view_skill_instructions({"skill": "group_management"})
    assert "官方" in refused
    assert "不支持" in refused

    allowed = executor._view_skill_instructions({"skill": "user_profile"})
    assert "不支持" not in allowed


class _Prompt(AgentPromptMixin):
    """只保留 _prepare_agent_messages 依赖的最小桩，捕获动态提示词块。"""

    def __init__(self, manager: SkillManager, *, official: bool) -> None:
        self._config = None
        self._skill_manager = manager
        self._markdown_skills = None
        self._provider = SimpleNamespace(native_vision=False)
        self._prompt_store = None
        self._official = official
        self.dynamic: dict | None = None

    def _is_official_platform(self, event: ReplyEvent) -> bool:
        return self._official

    def _resolve_last_reply(self, queue, queue_key):
        return None, False

    async def _build_role_messages(
        self,
        event,
        queue,
        queue_key,
        *,
        numbering=None,
        last_reply_message_id=None,
        all_new=False,
    ):
        return []

    async def _build_prompt(self, event, queue, queue_key, **kwargs):
        self.dynamic = kwargs.get("dynamic")
        return "prompt"

    def _record_flow_prompt(self, *args, **kwargs) -> None: ...

    def _record_debug(self, *args, **kwargs) -> None: ...

    def _take_unsent_marker(self, event) -> bool:
        return False


class _Queue:
    def clone(self, key):
        return self


async def _prompt_dynamic(official: bool) -> dict:
    stub = _Prompt(_manager(), official=official)
    event = ReplyEvent()
    event.state = ReplyState.BUILDING_PROMPT
    await stub._prepare_agent_messages(event, _Queue(), "42")
    return stub.dynamic or {}


async def test_official_agent_prompt_omits_hidden_skills_and_tools() -> None:
    dynamic = await _prompt_dynamic(official=True)
    skill_index = dynamic.get("skill_instructions", "")
    package_index = dynamic.get("tool_package_index", "")

    for name in _HIDDEN_SKILLS:
        assert f"- {name}:" not in skill_index
        assert f"- {name}: " not in package_index
    assert "- user_profile:" in skill_index
    assert "user_profile__read_user_info" in package_index
    assert "user_profile__analyze_user_avatar" not in package_index
    assert "cross_chat__cross_chat_query" not in package_index


async def test_non_official_agent_prompt_keeps_all_skills_and_tools() -> None:
    dynamic = await _prompt_dynamic(official=False)
    skill_index = dynamic.get("skill_instructions", "")
    package_index = dynamic.get("tool_package_index", "")

    for name in _HIDDEN_SKILLS:
        assert f"- {name}:" in skill_index
    assert "chat_history__read_earlier_messages" in package_index
    assert "user_profile__analyze_user_avatar" in package_index
    assert "cross_chat__cross_chat_query" in package_index
