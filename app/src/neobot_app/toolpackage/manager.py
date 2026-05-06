from __future__ import annotations

import copy
from collections.abc import Callable, Awaitable
from dataclasses import dataclass
from typing import Any

ToolDefinition = dict[str, Any]
ToolExecutorFn = Callable[[str, dict[str, Any]], Awaitable[str]]


@dataclass
class ToolPackage:
    """工具包：将一组相关工具打包，可动态解锁/关闭。

    Attributes:
        id: 工具包 ASCII 标识符，用于工具名前缀，如 "web_search"
        name: 工具包显示名称，如 "联网搜索工具包"
        description: 工具包功能描述，用于解锁时展示
        tools: 包内工具的定义列表（使用原始工具名）
        executor: 工具执行函数 (tool_name, args) -> result_str
        locked: 初始锁定状态，默认 True
    """

    id: str
    name: str
    description: str
    tools: list[ToolDefinition]
    executor: ToolExecutorFn
    locked: bool = True


class ToolPackageManager:
    """工具包管理器 — 作为动态 ToolExecutor 使用。

    提供 unlock / relock 管理工具，以及自动组装解锁后工具包中的所有工具。
    definitions() 和 execute() 均为动态方法，会根据当前解锁状态变化。
    """

    SEPARATOR = "__"

    def __init__(self, packages: list[ToolPackage] | None = None) -> None:
        self._packages: dict[str, ToolPackage] = {}
        for pkg in packages or []:
            self._packages[pkg.id] = pkg

    @property
    def locked_packages(self) -> list[ToolPackage]:
        return [p for p in self._packages.values() if p.locked]

    @property
    def unlocked_packages(self) -> list[ToolPackage]:
        return [p for p in self._packages.values() if not p.locked]

    def make_tool_name(self, package_id: str, tool_name: str) -> str:
        return f"{package_id}{self.SEPARATOR}{tool_name}"

    def parse_tool_name(self, full_name: str) -> tuple[str, str] | None:
        if self.SEPARATOR in full_name:
            idx = full_name.index(self.SEPARATOR)
            pkg_id = full_name[:idx]
            tool_name = full_name[idx + len(self.SEPARATOR):]
            if pkg_id in self._packages:
                return pkg_id, tool_name
        return None

    def definitions(self) -> list[ToolDefinition]:
        result: list[ToolDefinition] = []

        locked = self.locked_packages
        if locked:
            result.append(self._build_unlock_def(locked))

        unlocked = self.unlocked_packages
        if unlocked:
            result.append(self._build_relock_def(unlocked))
            for pkg in unlocked:
                for tool_def in pkg.tools:
                    result.append(self._prefix_tool_def(pkg.id, tool_def))

        return result

    def _build_unlock_def(self, locked: list[ToolPackage]) -> ToolDefinition:
        pkg_list = "\n".join(
            f"  - `{p.id}` ({p.name}): {p.description}" for p in locked
        )
        return {
            "type": "function",
            "function": {
                "name": "unlock",
                "description": (
                    f"解锁指定的工具包，解锁后即可使用该包内的所有工具。\n"
                    f"解锁后的工具名称格式为: 工具包ID__工具名 (如 web_search__search)。\n"
                    f"当前可解锁的工具包：\n{pkg_list}\n"
                    f"请根据任务需求选择合适的工具包解锁。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "package_id": {
                            "type": "string",
                            "description": "要解锁的工具包 ID（从上述可解锁列表中选择）",
                        }
                    },
                    "required": ["package_id"],
                },
            },
        }

    def _build_relock_def(self, unlocked: list[ToolPackage]) -> ToolDefinition:
        pkg_list = "\n".join(f"  - `{p.id}` ({p.name})" for p in unlocked)
        return {
            "type": "function",
            "function": {
                "name": "relock",
                "description": (
                    f"关闭已解锁的工具包，移除其所有工具。\n"
                    f"当前可关闭的工具包：\n{pkg_list}\n"
                    f"任务完成后建议关闭不再需要的工具包以保持工具列表整洁。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "package_id": {
                            "type": "string",
                            "description": "要关闭的工具包 ID（从上述可关闭列表中选择）",
                        }
                    },
                    "required": ["package_id"],
                },
            },
        }

    def _prefix_tool_def(
        self, package_id: str, tool_def: ToolDefinition
    ) -> ToolDefinition:
        new_def = copy.deepcopy(tool_def)
        original_name = new_def["function"]["name"]
        new_def["function"]["name"] = self.make_tool_name(package_id, original_name)
        return new_def

    async def execute(self, name: str, args: dict[str, Any]) -> str:
        if name == "unlock":
            return await self._handle_unlock(args.get("package_id", ""))
        if name == "relock":
            return await self._handle_relock(args.get("package_id", ""))

        parsed = self.parse_tool_name(name)
        if parsed:
            package_id, tool_name = parsed
            pkg = self._packages.get(package_id)
            if pkg is None:
                return f"错误：未找到工具包 '{package_id}'"
            if pkg.locked:
                return (
                    f"错误：工具包 '{pkg.name}' 当前处于关闭状态。"
                    f"请先使用 unlock 工具解锁该工具包。"
                )
            return await pkg.executor(tool_name, args)

        return f"未知工具: {name}"

    async def _handle_unlock(self, package_id: str) -> str:
        if not package_id:
            available = ", ".join(f"`{p.id}` ({p.name})" for p in self.locked_packages)
            return f"未指定工具包 ID。当前可解锁：{available}"

        pkg = self._packages.get(package_id)
        if pkg is None:
            available = ", ".join(p.id for p in self.locked_packages) or "(无)"
            return f"未找到工具包 '{package_id}'。当前可解锁的 ID：{available}"

        if not pkg.locked:
            return f"工具包 '{pkg.name}' 已经解锁，无需重复操作。"

        pkg.locked = False
        tool_names = [
            self.make_tool_name(package_id, t["function"]["name"])
            for t in pkg.tools
        ]
        return (
            f"工具包 '{pkg.name}' (ID: {package_id}) 已解锁！\n"
            f"现在可以使用以下工具：\n  " + "\n  ".join(tool_names)
        )

    async def _handle_relock(self, package_id: str) -> str:
        if not package_id:
            available = ", ".join(f"`{p.id}` ({p.name})" for p in self.unlocked_packages)
            return f"未指定工具包 ID。当前可关闭：{available}"

        pkg = self._packages.get(package_id)
        if pkg is None:
            available = ", ".join(p.id for p in self.unlocked_packages) or "(无)"
            return f"未找到工具包 '{package_id}'。当前可关闭的 ID：{available}"

        if pkg.locked:
            return f"工具包 '{pkg.name}' 已经关闭，无需重复操作。"

        pkg.locked = True
        return f"工具包 '{pkg.name}' (ID: {package_id}) 已关闭，其所有工具已不可用。"
