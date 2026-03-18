from __future__ import annotations

from neobot_chat.schema.exceptions import ToolError
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import ToolDefinition


class CompositeToolExecutor(ToolExecutor):
    """组合多个工具执行器。"""

    def __init__(self, executors: list[ToolExecutor] | None = None):
        self._executors = list(executors or [])
        self._tool_owners: dict[str, ToolExecutor] = {}

    def add_executor(self, executor: ToolExecutor) -> None:
        self._executors.append(executor)
        self._tool_owners.clear()

    def definitions(self) -> list[ToolDefinition]:
        definitions: list[ToolDefinition] = []
        owners: dict[str, ToolExecutor] = {}

        for executor in self._executors:
            for tool in executor.definitions():
                name = tool["function"]["name"]
                if name in owners:
                    raise ToolError(f"Duplicate tool definition: {name}")
                owners[name] = executor
                definitions.append(tool)

        self._tool_owners = owners
        return definitions

    async def execute(self, name: str, args: dict) -> str:
        if not self._tool_owners:
            self.definitions()

        executor = self._tool_owners.get(name)
        if executor is None:
            raise ToolError(f"Unknown tool: {name}")
        return await executor.execute(name, args)

    async def close(self) -> None:
        for executor in self._executors:
            await executor.close()
