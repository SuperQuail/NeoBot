"""命令注册表与文本解析。"""

from __future__ import annotations

import re
import shlex

from neobot_app.commands.model import Command

# 命令文本模式:/ 前只允许空白,命令名后跟空白分隔参数
_COMMAND_TEXT_RE = re.compile(r"^\s*/(?P<name>\S+)(?P<rest>\s+.*)?$")


class CommandRegistry:
    """命令注册表:注册/查找/解析。"""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        if command.name in self._commands:
            raise ValueError(f"命令已注册: /{command.name}")
        for alias in command.aliases:
            if alias in self._commands:
                raise ValueError(f"命令别名冲突: /{alias}")
        self._commands[command.name] = command
        for alias in command.aliases:
            self._commands[alias] = command

    def unregister(self, name: str) -> bool:
        command = self._commands.pop(name, None)
        if command is None:
            return False
        for alias in command.aliases:
            self._commands.pop(alias, None)
        return True

    def get(self, name: str) -> Command | None:
        return self._commands.get(name)

    def commands(self) -> list[Command]:
        """列出所有命令(去重,别名不重复)。"""
        seen: set[int] = set()
        result: list[Command] = []
        for command in self._commands.values():
            if id(command) in seen:
                continue
            seen.add(id(command))
            result.append(command)
        return result

    def names(self) -> list[str]:
        return [command.name for command in self.commands()]

    def match(self, text: str) -> tuple[Command | None, str, list[str]] | None:
        """解析命令文本。

        Returns:
            None — 文本不是命令形态(不以 / 开头,或 / 前有非空白字符)
            (None, raw_args, args) — 是 / 形态但命令未注册
            (command, raw_args, args) — 命令命中
        """
        stripped = text.strip()
        if not stripped.startswith("/"):
            return None
        match = _COMMAND_TEXT_RE.match(text)
        if match is None:
            # / 前存在非空白字符:不属于命令形态(例如 "大家 /help")
            return None
        name = match.group("name")
        raw_args = (match.group("rest") or "").strip()
        args: list[str] = []
        if raw_args:
            try:
                args = shlex.split(raw_args)
            except ValueError:
                args = raw_args.split()
        command = self._commands.get(name)
        return command, raw_args, args
