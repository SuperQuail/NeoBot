from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from neobot_chat.schema.exceptions import ToolError
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import ToolAccessPolicy, ToolAccessRule, ToolDefinition, ToolGuardContext
from neobot_chat.tools.registry import AgentRegistry
from neobot_chat.tools.shell import PersistentShell
from neobot_chat.tools.toolset import ToolSpec, Toolset


def _tool_def(name: str, description: str, parameters: dict) -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", **parameters},
        },
    }


def _default_resolver(
    args: dict, context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    return policy.default_rule


def _path_resolver(
    args: dict, context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    raw_path = str(args.get("path") or ".")
    candidate = Path(raw_path).expanduser()
    base = context.cwd or Path.cwd()
    resolved = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
    in_scope = any(
        resolved == allowed or resolved.is_relative_to(allowed)
        for allowed in context.allowed_paths
    )
    return policy.path_in_scope_rule if in_scope else policy.path_out_of_scope_rule


def _command_resolver(
    args: dict, context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    command = str(args.get("command") or "")
    if not context.allowed_commands:
        return policy.command_disallowed_rule
    try:
        import shlex
        from fnmatch import fnmatch

        parts = shlex.split(command)
    except ValueError:
        parts = []
    if parts and any(fnmatch(parts[0], pattern) for pattern in context.allowed_commands):
        return policy.command_allowed_rule
    return policy.command_disallowed_rule


def _list_agents_resolver(
    args: dict, context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    return policy.list_agents_rule


def _delegate_resolver(
    args: dict, context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    return policy.delegate_rule


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
        self.allowed_commands = list(allowed_commands or [])
        self._shell = PersistentShell(self.cwd, command_timeout)
        self._dispatch: dict[str, Any] = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_files": self._list_files,
            "execute_command": self._execute_command,
            "list_agents": self._list_agents,
            "delegate": self._delegate,
        }

    def _base_tools(self) -> list[ToolDefinition]:
        return [
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
                        "content": {"type": "string", "description": "Content to write"},
                    },
                    "required": ["path", "content"],
                },
            ),
            _tool_def(
                "list_files",
                "List files and directories under a path. Relative paths resolve from current working directory.",
                {
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to list", "default": "."}
                    },
                },
            ),
            _tool_def(
                "execute_command",
                f"Execute a shell command. Current working directory: {self.cwd}",
                {
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to execute"},
                        "cwd": {"type": "string", "description": "Working directory (optional, overrides session cwd)"},
                        "timeout": {"type": "integer", "description": f"Timeout in seconds (default: {self.command_timeout})"},
                    },
                    "required": ["command"],
                },
            ),
        ]

    def definitions(self) -> list[ToolDefinition]:
        tools = self._base_tools()
        if self.agent_registry:
            names = self.agent_registry.names
            tools.append(
                _tool_def(
                    "list_agents",
                    "List agents info. No params: list all agents. With agent param: list that agent's tools",
                    {
                        "properties": {
                            "agent": {"type": "string", "enum": names, "description": "Agent name to list tools for"},
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

    def _resolve_path(self, path: str) -> Path:
        candidate = Path(path).expanduser()
        return candidate.resolve() if candidate.is_absolute() else (self.cwd / candidate).resolve()

    async def _read_file(self, path: str) -> str:
        try:
            resolved = self._resolve_path(path)
            return await asyncio.to_thread(resolved.read_text, encoding="utf-8")
        except FileNotFoundError:
            return f"Error: File not found: {path}"
        except Exception as exc:
            return f"Error reading file: {exc}"

    async def _write_file(self, path: str, content: str) -> str:
        try:
            resolved = self._resolve_path(path)
            await asyncio.to_thread(resolved.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(resolved.write_text, content, encoding="utf-8")
            return f"Successfully wrote to {resolved}"
        except Exception as exc:
            return f"Error writing file: {exc}"

    async def _list_files(self, path: str = ".") -> str:
        try:
            resolved = self._resolve_path(path)
            if not resolved.exists():
                return f"Error: Path not found: {path}"
            if resolved.is_file():
                return resolved.name
            entries = await asyncio.to_thread(lambda: sorted(resolved.iterdir()))
            if not entries:
                return "(empty directory)"
            return "\n".join(f"{entry.name}{'/' if entry.is_dir() else ''}" for entry in entries)
        except Exception as exc:
            return f"Error listing files: {exc}"

    async def _execute_command(self, command: str, cwd: str | None = None, timeout: int | None = None) -> str:
        if cwd:
            cwd_path = Path(cwd).resolve()
            if cwd_path != self.cwd:
                return await self._execute_in_temp_process(command, cwd, timeout)
        return await self._shell.execute(command)

    async def _execute_in_temp_process(self, command: str, cwd: str, timeout: int | None = None) -> str:
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
        except Exception as exc:
            return f"Error executing command: {exc}"

    async def close(self) -> None:
        await self._shell.close()

    async def _list_agents(self, agent: str | None = None) -> str:
        return self.agent_registry.list_agents(agent)

    async def _delegate(self, agent: str | None = None, task: str | None = None, tasks: list[dict] | None = None) -> str:
        return await self.agent_registry.delegate(agent=agent, task=task, tasks=tasks)


def build_builtin_toolset(
    *,
    agent_registry: AgentRegistry | None = None,
    cwd: str | Path | None = None,
    command_timeout: int = 30,
    allowed_paths: list[Path] | None = None,
    allowed_commands: list[str] | None = None,
    policy: ToolAccessPolicy | None = None,
) -> Toolset:
    executor = BuiltinTools(
        agent_registry=agent_registry,
        cwd=cwd,
        command_timeout=command_timeout,
        allowed_paths=allowed_paths,
        allowed_commands=allowed_commands,
    )
    definitions = executor.definitions()
    resolvers = {
        "read_file": _path_resolver,
        "write_file": _path_resolver,
        "list_files": _path_resolver,
        "execute_command": _command_resolver,
        "list_agents": _list_agents_resolver,
        "delegate": _delegate_resolver,
    }
    specs = [
        ToolSpec(definition=definition, access_resolver=resolvers.get(definition["function"]["name"], _default_resolver))
        for definition in definitions
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())
