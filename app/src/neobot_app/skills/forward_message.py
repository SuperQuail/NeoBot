"""ForwardMessageSkill — 合并转发消息解析。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

class ForwardMessageSkill(SkillModule):
    """合并转发 Skill — 读取合并转发消息内容。"""

    @property
    def name(self) -> str:
        return "forward_message"

    @property
    def description(self) -> str:
        return "合并转发消息：读取合并转发消息的具体内容"

    @property
    def instructions(self) -> str:
        return (
            "合并转发 Skill 提供以下能力：\n\n"
            "  read_forward_msg — 读取合并转发消息的具体内容。"
            "传入消息 ID（来自 [合并转发:ID=xxx] 中的 ID），返回转发消息中的节点列表。"
        )

    def __init__(
        self,
        adapter: Any = None,
        display_threshold: int = 50,
        max_nesting: int = 10,
    ) -> None:
        self._adapter = adapter
        self._display_threshold = display_threshold
        self._max_nesting = max_nesting

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        if self._adapter is None:
            return []
        return [
            self._tool_def(
                "read_forward_msg",
                "读取合并转发消息的具体内容。传入消息 ID（来自 [合并转发:ID=xxx] 中的 ID），返回转发消息中的节点列表。支持嵌套转发的递归展开。",
                {
                    "properties": {
                        "message_id": {
                            "type": "string",
                            "description": "合并转发消息的 ID，来自聊天记录中 [合并转发:ID=xxx] 的 ID 部分。",
                        },
                    },
                    "required": ["message_id"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown forward_message tool: {tool_name}"})
        return await handler(self, args)

# ── Handlers ──

async def _handle_read_forward_msg(self: ForwardMessageSkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    message_id = str(args.get("message_id", "")).strip()
    if not message_id:
        return _json({"ok": False, "error": "缺少 message_id"})
    try:
        result = await self._adapter.get_forward_msg(message_id)
        data = result.get("data", result) if isinstance(result, dict) else {}
        messages = data.get("messages", []) if isinstance(data, dict) else []
        return _json({"ok": True, "message_id": message_id, "node_count": len(messages), "content": str(messages[:20])})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

_HANDLERS = {
    "read_forward_msg": _handle_read_forward_msg,
}
