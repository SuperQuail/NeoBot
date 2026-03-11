from __future__ import annotations

import asyncio
import os
import shlex
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from neobot_chat.schema.exceptions import ToolError
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.tools.registry import AgentRegistry
from neobot_chat.tools.shell import PersistentShell
from neobot_chat.schema.types import ToolDefinition


def _tool_def(name: str, description: str, parameters: dict) -> ToolDefinition:
    """构造 OpenAI function tool 定义"""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", **parameters},
        },
    }


class BuiltinTools(ToolExecutor):
    """内置工具，带会话状态（cwd 持久化）"""

    def __init__(
        self,
        agent_registry: AgentRegistry | None = None,
        cwd: str | Path | None = None,
        command_timeout: int = 30,
        allowed_paths: list[Path] | None = None,
        allowed_commands: list[str] | None = None,
    ):
        self.agent_registry = agent_registry or AgentRegistry()
        self.cwd = Path(cwd or os.getcwd()).resolve()
        self.command_timeout = command_timeout
        self.allowed_paths = [self.cwd] + (allowed_paths or [])
        self.allowed_commands = allowed_commands
        self._shell = (
            PersistentShell(self.cwd, command_timeout) if allowed_commands else None
        )
        self._dispatch: dict[str, Any] = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_agents": self._list_agents,
            "delegate": self._delegate,
        }
        if allowed_commands:
            self._dispatch["execute_command"] = self._execute_command

    def _is_path_allowed(self, path: Path) -> bool:
        """检查路径是否在允许访问的范围内"""
        path = path.resolve()
        return any(
            path == allowed or path.is_relative_to(allowed)
            for allowed in self.allowed_paths
        )

    def _is_command_allowed(self, command: str) -> tuple[bool, str]:
        """检查命令是否在白名单中，返回 (是否允许, 命令名)"""
        try:
            parts = shlex.split(command)
            if not parts:
                return False, ""
            cmd = parts[0]
            # 支持通配符匹配
            for pattern in self.allowed_commands:
                if fnmatch(cmd, pattern):
                    return True, cmd
            return False, cmd
        except ValueError:
            return False, ""

    def _base_tools(self) -> list[ToolDefinition]:
        tools = [
            _tool_def(
                "read_file",
                "Read file contents. Relative paths resolve from current working directory.",
                {
                    "properties": {
                        "path": {"type": "string", "description": "File path to read"}
                    },
                    "required": ["path"],
                },
            ),
            _tool_def(
                "write_file",
                "Write content to a file. Relative paths resolve from current working directory.",
                {
                    "properties": {
                        "path": {"type": "string", "description": "File path to write"},
                        "content": {
                            "type": "string",
                            "description": "Content to write",
                        },
                    },
                    "required": ["path", "content"],
                },
            ),
        ]

        if self.allowed_commands:
            tools.append(
                _tool_def(
                    "execute_command",
                    f"Execute a shell command. Current working directory: {self.cwd}",
                    {
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Shell command to execute",
                            },
                            "cwd": {
                                "type": "string",
                                "description": "Working directory (optional, overrides session cwd)",
                            },
                            "timeout": {
                                "type": "integer",
                                "description": f"Timeout in seconds (default: {self.command_timeout})",
                            },
                        },
                        "required": ["command"],
                    },
                )
            )

        return tools

    def definitions(self) -> list[ToolDefinition]:
        """返回所有工具定义（OpenAI function calling 格式）"""
        tools = self._base_tools()

        if self.agent_registry:
            names = self.agent_registry.names
            tools.append(
                _tool_def(
                    "list_agents",
                    "List agents info. No params: list all agents. With agent param: list that agent's tools",
                    {
                        "properties": {
                            "agent": {
                                "type": "string",
                                "enum": names,
                                "description": "Agent name to list tools for",
                            },
                        },
                    },
                )
            )
            tools.append(
                _tool_def(
                    "delegate",
                    "Delegate task(s) to agent(s). Single: use agent+task. Parallel: use tasks array",
                    {
                        "properties": {
                            "agent": {"type": "string", "enum": names},
                            "task": {"type": "string"},
                            "tasks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "agent": {"type": "string", "enum": names},
                                        "task": {"type": "string"},
                                    },
                                    "required": ["agent", "task"],
                                },
                            },
                        },
                    },
                )
            )

        return tools

    async def execute(self, name: str, args: dict) -> str:
        handler = self._dispatch.get(name)
        if handler is None:
            raise ToolError(f"Unknown tool: {name}")
        return await handler(**args)

    # ── 工具实现 ──

    def _resolve_path(self, path: str) -> Path:
        p = Path(path).expanduser()
        resolved = p.resolve() if p.is_absolute() else (self.cwd / p).resolve()
        return resolved

    async def _read_file(self, path: str) -> str:
        try:
            resolved = self._resolve_path(path)
            if not self._is_path_allowed(resolved):
                return f"Error: Access denied to path: {path}"
            return await asyncio.to_thread(resolved.read_text, encoding="utf-8")
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except Exception as e:
            return f"Error reading file: {e}"

    async def _write_file(self, path: str, content: str) -> str:
        try:
            p = self._resolve_path(path)
            if not self._is_path_allowed(p):
                return f"Error: Access denied to path: {path}"
            await asyncio.to_thread(p.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(p.write_text, content, encoding="utf-8")
            return f"Successfully wrote to {p}"
        except Exception as e:
            return f"Error writing file: {e}"

    async def _execute_command(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int | None = None,
    ) -> str:
        # 检查命令白名单
        allowed, cmd_name = self._is_command_allowed(command)
        if not allowed:
            return f"Error: Command not allowed: {cmd_name or command}"

        # 验证 cwd 路径
        if cwd:
            cwd_path = Path(cwd).resolve()
            if not self._is_path_allowed(cwd_path):
                return f"Error: Access denied to directory: {cwd}"
            if cwd_path != self.cwd:
                return await self._execute_in_temp_process(command, cwd, timeout)

        # 使用持久 shell
        return await self._shell.execute(command)

    async def _execute_in_temp_process(
        self, command: str, cwd: str, timeout: int | None = None
    ) -> str:
        """在临时进程中执行命令（用于指定不同 cwd 的情况）"""
        timeout = timeout or self.command_timeout
        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            out = stdout.decode("utf-8", errors="replace")
            if stderr:
                out += "\n" + stderr.decode("utf-8", errors="replace")
            return out.strip() or "(no output)"
        except asyncio.TimeoutError:
            if proc and proc.returncode is None:
                proc.kill()
                await proc.wait()
            return f"Error: Command timed out after {timeout}s"
        except Exception as e:
            return f"Error executing command: {e}"

    async def close(self) -> None:
        """关闭持久 shell 进程"""
        if self._shell is not None:
            await self._shell.close()

    async def _list_agents(self, agent: str | None = None) -> str:
        return self.agent_registry.list_agents(agent)

    async def _delegate(
        self,
        agent: str | None = None,
        task: str | None = None,
        tasks: list[dict] | None = None,
    ) -> str:
        return await self.agent_registry.delegate(agent=agent, task=task, tasks=tasks)
