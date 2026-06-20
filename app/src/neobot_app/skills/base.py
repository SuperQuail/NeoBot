"""Skill 核心 — SkillModule 协议与 SkillManager。"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from typing import Any


_SEPARATOR = "__"


class SkillModule(ABC):
    """Skill 模块基类。

    子类需实现：
      name, description, get_tools(), execute()
    可选：
      instructions  — 注入到系统提示词的说明文本
      reset()       — 跨会话状态复位
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Skill 唯一标识符，用作工具名前缀。"""

    @property
    @abstractmethod
    def description(self) -> str:
        """简短描述，用于索引和日志。"""

    @property
    def instructions(self) -> str:
        """可选：注入到系统提示词的操作说明。"""
        return ""

    @property
    def session_tools(self) -> set[str]:
        """返回需要以 Session 模式（提交后立即返回，后台执行完成后通知）执行的无前缀工具名集合。"""
        return set()

    @abstractmethod
    def get_tools(self) -> list[dict]:
        """返回 OpenAI function-calling 格式的工具定义列表。

        工具名建议简短（如 search、navigate），
        SkillManager 会按 ``{skill_name}__{tool_name}`` 自动加前缀。
        """

    @abstractmethod
    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        """执行工具并返回结果字符串。

        Args:
            tool_name: 去前缀后的原始工具名（不含 ``{skill_name}__``）
            args: 工具参数字典
        """

    @staticmethod
    def _tool_def(name: str, description: str, parameters: dict | None = None) -> dict:
        """统一工具定义格式（OpenAI function-calling）。"""
        params: dict = {"type": "object", "properties": {}, "required": []}
        if parameters:
            params["properties"] = parameters.get("properties", {})
            params["required"] = parameters.get("required", [])
        return {
            "type": "function",
            "function": {"name": name, "description": description, "parameters": params},
        }

    def reset(self) -> None:
        """复位内部状态（新会话时调用）。"""


class SkillManager:
    """Skill 管理器 — 注册、聚合、路由。

    用法::

        mgr = SkillManager()
        mgr.register(browser_skill)
        mgr.register(web_search_skill)

        # 聚合所有工具定义（自动加名前缀）
        tools = mgr.get_tools()

        # 聚合所有说明文本
        instructions = mgr.get_instructions()

        # 路由执行
        result = await mgr.execute("browser__navigate", {"url": "..."})
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillModule] = {}
        self._session_tools: set[str] = set()

    def register(self, skill: SkillModule) -> None:
        """注册一个 Skill 模块。"""
        if skill.name in self._skills:
            raise ValueError(f"Skill '{skill.name}' 已注册")
        self._skills[skill.name] = skill
        for tool_name in skill.session_tools:
            self._session_tools.add(f"{skill.name}{_SEPARATOR}{tool_name}")

    def unregister(self, name: str) -> None:
        """注销指定 Skill。"""
        self._skills.pop(name, None)

    def get(self, name: str) -> SkillModule | None:
        return self._skills.get(name)

    @property
    def all_skills(self) -> list[SkillModule]:
        return list(self._skills.values())

    @property
    def skill_names(self) -> list[str]:
        return list(self._skills.keys())

    def get_tools(self) -> list[dict]:
        """聚合所有 Skill 的工具定义，自动加 ``{name}__`` 前缀。"""
        tools: list[dict] = []
        for skill in self._skills.values():
            for tool_def in skill.get_tools():
                prefixed = _deep_copy(tool_def)
                original_name = prefixed["function"]["name"]
                prefixed["function"]["name"] = f"{skill.name}{_SEPARATOR}{original_name}"
                tools.append(prefixed)
        return tools

    def get_instructions(self) -> str:
        """聚合所有 Skill 的操作说明。"""
        parts: list[str] = []
        for skill in self._skills.values():
            instr = skill.instructions
            if instr:
                parts.append(f"## {skill.name}\n{instr}")
        return "\n\n".join(parts)

    async def execute(self, prefixed_name: str, args: dict[str, Any]) -> str:
        """路由执行：解析 ``{name}__{tool}`` 并分派到对应的 Skill。"""
        parsed = self._parse_name(prefixed_name)
        if parsed is None:
            available = ", ".join(self._skills)
            return (
                f"未知工具: {prefixed_name}\n"
                f"可用工具名前缀: {available}\n"
                f"格式: {{skill_name}}{_SEPARATOR}{{tool_name}}"
            )

        skill_name, tool_name = parsed
        skill = self._skills.get(skill_name)
        if skill is None:
            return f"错误：未找到 Skill '{skill_name}'"

        try:
            return await skill.execute(tool_name, args)
        except Exception as exc:
            return f"工具执行失败 [{prefixed_name}]: {exc}"

    def reset_all(self) -> None:
        """复位所有 Skill 的状态。"""
        for skill in self._skills.values():
            skill.reset()

    def is_session_tool(self, prefixed_name: str) -> bool:
        """检查指定前缀工具名是否已声明为 Session 模式执行。"""
        return prefixed_name in self._session_tools

    def _parse_name(self, prefixed_name: str) -> tuple[str, str] | None:
        if _SEPARATOR in prefixed_name:
            idx = prefixed_name.index(_SEPARATOR)
            skill_name = prefixed_name[:idx]
            tool_name = prefixed_name[idx + len(_SEPARATOR):]
            if skill_name in self._skills:
                return skill_name, tool_name
        return None


def _deep_copy(d: dict) -> dict:
    return copy.deepcopy(d)
