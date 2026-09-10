"""把 SkillManager 暴露成独立 Agent 的 Toolset（支持按需加载）。

主回复管线走 ReplyToolExecutor；沙箱维护等自建 Agent 只为「技能」建工具集，
因此这里提供同一套按需加载语义的最小实现。
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from neobot_chat.tools.toolset import Toolset

from neobot_app.skills.activation import LOADER_TOOL_NAME, SkillToolActivation


class SkillToolsetExecutor:
    """技能工具执行器：常驻精简集 + `skills__load_tools` 按需加载。"""

    def __init__(
        self,
        skill_manager: Any,
        *,
        resident: Collection[str] | None = None,
    ) -> None:
        self._manager = skill_manager
        self._activation = SkillToolActivation(skill_manager, resident=resident)

    @property
    def activation(self) -> SkillToolActivation:
        return self._activation

    def definitions(self) -> list[dict]:
        tools = list(self._activation.tools())
        loader = self._activation.loader_definition()
        if loader:
            tools.append(loader)
        return tools

    async def execute(self, name: str, args: dict) -> str:
        if name == LOADER_TOOL_NAME:
            return self._activation.load(dict(args or {}))
        return await self._manager.execute(name, args)

    async def close(self) -> None:
        return None


class LiveToolset(Toolset):
    """definitions() 每次从执行器重算的工具集。

    Toolset 默认把 specs 固定在建库时刻；按需加载会改变工具集合，
    因此这里改为实时读取（Agent 每一轮都会调用 definitions()）。
    """

    def definitions(self) -> list[dict]:
        return list(self.executor.definitions())
