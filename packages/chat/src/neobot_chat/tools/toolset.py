from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from neobot_chat.schema.exceptions import ToolError
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import (
    ToolAccessPolicy,
    ToolAccessRule,
    ToolDefinition,
    ToolGuardContext,
)
from neobot_chat.tools.composite import CompositeToolExecutor

AccessResolver = Callable[[dict, ToolGuardContext, ToolAccessPolicy], ToolAccessRule]


@dataclass(frozen=True)
class ToolSpec:
    definition: ToolDefinition
    access_resolver: AccessResolver

    @property
    def name(self) -> str:
        return self.definition["function"]["name"]


class SelectedToolExecutor(ToolExecutor):
    def __init__(self, executor: ToolExecutor, names: set[str]):
        self._executor = executor
        self._names = names

    def definitions(self) -> list[ToolDefinition]:
        return [
            tool
            for tool in self._executor.definitions()
            if tool["function"]["name"] in self._names
        ]

    async def execute(self, name: str, args: dict) -> str:
        if name not in self._names:
            raise ToolError(f"Unknown tool: {name}")
        return await self._executor.execute(name, args)

    async def close(self) -> None:
        await self._executor.close()


@dataclass(frozen=True)
class Toolset:
    executor: ToolExecutor
    specs: list[ToolSpec] = field(default_factory=list)
    policy: ToolAccessPolicy = field(default_factory=ToolAccessPolicy)

    def definitions(self) -> list[ToolDefinition]:
        return [spec.definition for spec in self.specs]

    @classmethod
    def merge(cls, toolsets: list[Toolset | None]) -> Toolset:
        active_toolsets = [toolset for toolset in toolsets if toolset is not None]
        if not active_toolsets:
            return cls(executor=CompositeToolExecutor([]), specs=[])

        selected_specs: dict[str, tuple[ToolSpec, int]] = {}
        for index, toolset in enumerate(active_toolsets):
            for spec in toolset.specs:
                selected_specs[spec.name] = (spec, index)

        ordered_specs: list[ToolSpec] = []
        seen_names: set[str] = set()
        for toolset in reversed(active_toolsets):
            for spec in reversed(toolset.specs):
                selected = selected_specs.get(spec.name)
                if selected is None or selected[0] is not spec or spec.name in seen_names:
                    continue
                seen_names.add(spec.name)
                ordered_specs.append(spec)
        ordered_specs.reverse()

        executors: list[ToolExecutor] = []
        for index, toolset in enumerate(active_toolsets):
            names = {
                spec.name
                for spec, owner_index in selected_specs.values()
                if owner_index == index
            }
            if names:
                executors.append(SelectedToolExecutor(toolset.executor, names))

        merged_executor = CompositeToolExecutor(executors)
        return cls(executor=merged_executor, specs=ordered_specs)
