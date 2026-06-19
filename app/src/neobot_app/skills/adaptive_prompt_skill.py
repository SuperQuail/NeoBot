"""AdaptivePromptSkill — 自适应提示词管理 Skill。

Agent 可自主维护的"永久记忆"：确认可信且需要一直知道的信息，
写入自适应提示词文件，在每次对话的系统提示词中注入。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class AdaptivePromptSkill(SkillModule):
    """自适应提示词管理 Skill — 读写 agent 永久记忆提示词。"""

    @property
    def name(self) -> str:
        return "adaptive_prompt"

    @property
    def description(self) -> str:
        return "自适应提示词管理：更新/读取长期记忆提示词"

    @property
    def instructions(self) -> str:
        return (
            "自适应提示词 Skill 用于管理 agent 的「永久记忆」。\n\n"
            "## 用途\n"
            "对于你自己需要的、确认可信且需要一直知道的信息（如用户偏好、重要事实、"
            "关系变化、长期约定等），记录在自适应提示词中。\n"
            "该内容会被自动注入到每一次对话的系统提示词中，确保你不会遗忘。\n\n"
            "## 规则\n"
            "1. 只记录经过对话确认的、可信的信息，不要记录推测或一次性内容\n"
            "2. 内容应简洁，只保留关键信息\n"
            "3. 信息过时时，应主动更新或删除对应条目\n"
            f"4. 总长度有上限（默认 {self._max_chars} 字符），超出会自动截断\n\n"
            "## 工具列表\n"
            "  update_adaptive_prompt — 追加或更新自适应提示词内容\n"
            "  read_adaptive_prompt — 读取当前自适应提示词全文"
        )

    def __init__(
        self,
        data_dir: str | Path | None = None,
        max_chars: int = 200,
        enabled: bool = True,
    ) -> None:
        self._data_dir = Path(data_dir) if data_dir else Path("data")
        self._max_chars = max_chars
        self._enabled = enabled
        self._path = self._data_dir / "自适应提示词.txt"
        self._lock = asyncio.Lock()

    def reset(self) -> None:
        pass

    @property
    def file_path(self) -> Path:
        return self._path

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "update_adaptive_prompt",
                "追加或更新自适应提示词（永久记忆）。"
                "对于你自己需要的、确认可信且需要一直知道的信息，记录在此。"
                "该内容会被自动注入到每次对话的系统提示词中。"
                "传入 content 为要追加的内容；若 action=replace 则替换全文。"
                "若总长度超出上限，尾部内容会被自动截断。",
                {
                    "properties": {
                        "content": {"type": "string", "description": "要记录的提示词内容"},
                        "action": {
                            "type": "string",
                            "enum": ["append", "replace"],
                            "description": "append=追加到末尾；replace=替换全文。默认 append",
                        },
                    },
                    "required": ["content"],
                },
            ),
            self._tool_def(
                "read_adaptive_prompt",
                "读取当前自适应提示词全文。",
                {"properties": {}, "required": []},
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        if tool_name == "update_adaptive_prompt":
            return await _handle_update(self, args)
        if tool_name == "read_adaptive_prompt":
            return await _handle_read(self, args)
        return _json({"ok": False, "error": f"unknown adaptive_prompt tool: {tool_name}"})

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


async def _handle_update(self: AdaptivePromptSkill, args: dict) -> str:
    content = str(args.get("content", "")).strip()
    action = str(args.get("action", "append")).strip()
    if not content:
        return _json({"ok": False, "error": "content 不能为空"})

    try:
        async with self._lock:
            old = ""
            if self._path.is_file() and action == "append":
                old = self._path.read_text("utf-8").strip()
                if old:
                    old += "\n"

            if action == "replace":
                new_content = content
            else:
                new_content = old + content

            truncated = False
            if len(new_content) > self._max_chars:
                new_content = new_content[: self._max_chars]
                truncated = True

            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(".tmp")
            tmp_path.write_text(new_content, encoding="utf-8")
            tmp_path.replace(self._path)

        return _json({
            "ok": True,
            "action": action,
            "length": len(new_content),
            "max_chars": self._max_chars,
            "truncated": truncated,
        })
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_read(self: AdaptivePromptSkill, args: dict) -> str:
    try:
        if not self._path.is_file():
            return _json({"ok": True, "content": "", "length": 0})
        content = self._path.read_text("utf-8").strip()
        return _json({
            "ok": True,
            "content": content,
            "length": len(content),
            "max_chars": self._max_chars,
        })
    except Exception as e:
        return _json({"ok": False, "error": str(e)})
