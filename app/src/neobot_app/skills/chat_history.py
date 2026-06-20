"""ChatHistorySkill — 历史消息拉取。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class ChatHistorySkill(SkillModule):
    """历史消息 Skill — 读取更早的聊天记录。"""

    @property
    def name(self) -> str:
        return "chat_history"

    @property
    def description(self) -> str:
        return "历史消息：读取更早的聊天记录以获取上下文"

    @property
    def instructions(self) -> str:
        return (
            "历史消息 Skill 提供以下能力：\n\n"
            "  read_earlier_messages — 读取更早的聊天记录。"
            "自动记忆触发时，如果近期消息含义不明确，使用它拉取更多上下文后再决定是否写入记忆。"
        )

    def __init__(self, adapter: Any = None) -> None:
        self._adapter = adapter

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        if self._adapter is None:
            return []
        return [
            self._tool_def(
                "read_earlier_messages",
                "读取更早的聊天记录。自动记忆触发时，如果近期消息含义不明确，"
                "使用它拉取更多上下文后再决定是否写入记忆。",
                {
                    "properties": {
                        "conversation_kind": {
                            "type": "string",
                            "enum": ["group", "private"],
                            "description": "会话类型",
                        },
                        "conversation_id": {"type": "string", "description": "群号或好友QQ号"},
                        "message_seq": {"type": "integer", "description": "可选，历史起点 message_seq", "default": 0},
                        "count": {"type": "integer", "description": "读取条数，默认20，最大50", "default": 20},
                        "reverse_order": {"type": "boolean", "description": "是否反向排序"},
                    },
                    "required": ["conversation_kind", "conversation_id"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown chat_history tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_read_earlier_messages(self: ChatHistorySkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    conv_kind = str(args.get("conversation_kind", "")).strip()
    conv_id = str(args.get("conversation_id", "")).strip()
    count = min(int(args.get("count", 20)), 50)
    message_seq = int(args.get("message_seq", 0))
    reverse_order = bool(args.get("reverse_order", False))
    try:
        if conv_kind == "private":
            messages = await self._adapter.get_friend_msg_history(
                int(conv_id), message_seq=message_seq, count=count, reverse_order=reverse_order,
            )
        else:
            messages = await self._adapter.get_group_msg_history(
                int(conv_id), message_seq=message_seq, count=count, reverse_order=reverse_order,
            )
        return _json({"ok": True, "count": len(messages), "messages": str(messages)[:3000]})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


_HANDLERS = {
    "read_earlier_messages": _handle_read_earlier_messages,
}
