"""StickerSkill — 表情包发送。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class StickerSkill(SkillModule):
    """表情包发送 Skill — 从表情包库选择并发送表情包。"""

    @property
    def name(self) -> str:
        return "sticker"

    @property
    def description(self) -> str:
        return "表情包发送：从表情包库选择并发送表情包到指定会话"

    @property
    def instructions(self) -> str:
        return (
            "表情包 Skill 提供以下能力：\n\n"
            "  send_sticker — 从表情包库选择并发送一个表情包图片到指定会话\n\n"
            "注意：表情包管理（增删改查）请在 emoji_management skill 中操作。"
        )

    def __init__(self, emoji_service: Any = None, file_server: Any = None) -> None:
        self._emoji_service = emoji_service
        self._file_server = file_server

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        if self._emoji_service is None:
            return []
        return [
            self._tool_def(
                "send_sticker",
                "从表情包库中选择并发送一个表情包图片到指定会话。",
                {
                    "properties": {
                        "number": {"type": "integer", "description": "表情包编号，从可用表情包列表中选取。"},
                        "text": {"type": "string", "description": "可选，随表情包一起发送的文字。"},
                        "group_id": {"type": "string", "description": "目标群号，群聊场景使用。"},
                        "user_id": {"type": "string", "description": "目标QQ号，私聊场景使用。"},
                    },
                    "required": ["number"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown sticker tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_send_sticker(self: StickerSkill, args: dict) -> str:
    if self._emoji_service is None:
        return _json({"ok": False, "error": "emoji_service 未配置"})
    number = args.get("number")
    if number is None:
        return _json({"ok": False, "error": "缺少表情包编号"})
    text = args.get("text", "")
    group_id = args.get("group_id", "")
    user_id = args.get("user_id", "")
    try:
        result = await self._emoji_service.send_sticker(number, text=text, group_id=group_id, user_id=user_id)
        return _json({"ok": True, "result": str(result)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


_HANDLERS = {
    "send_sticker": _handle_send_sticker,
}
