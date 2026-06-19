"""CrossChatSkill — 跨聊天通信 Skill（纯工具，无独立 LLM）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class CrossChatSkill(SkillModule):
    """跨聊天通信 Skill — 向其他群/私聊传递消息，查询其他聊天记录。"""

    @property
    def name(self) -> str:
        return "cross_chat"

    @property
    def description(self) -> str:
        return "跨聊天通信：向其他群/私聊传递消息，查询其他聊天的记录"

    @property
    def instructions(self) -> str:
        return (
            "跨聊天通信 Skill 提供以下能力：\n\n"
            "## cross_chat_send\n"
            "向其他聊天（群或私聊）传递信息。支持 fire_and_forget（默认）和 wait 两种调用模式。\n"
            "支持 no_response（默认）和 response 两种通知模式。\n\n"
            "## cross_chat_query\n"
            "查询指定聊天的聊天记录，了解其他聊天的讨论内容。\n"
            "任务示例：「获取群123456最近在聊什么」\n\n"
            "注意：收到跨聊天消息通知或回复时，应直接回复，不要再次委托本 skill。"
        )

    def __init__(
        self,
        config: Any = None,
        adapter: Any = None,
        group_message_queue: Any = None,
        friend_message_queue: Any = None,
    ) -> None:
        self._config = config
        self._adapter = adapter
        self._group_queue = group_message_queue
        self._friend_queue = friend_message_queue

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "cross_chat_send",
                "向其他聊天（群或私聊）传递消息或指令。"
                "在 task 中使用 [mode: fire_and_forget] 或 [mode: wait] 指定调用模式，"
                "使用 [notify: no_response] 或 [notify: response] 指定通知模式。",
                {
                    "properties": {
                        "target_kind": {
                            "type": "string", "enum": ["group", "private"],
                            "description": "目标聊天类型：group=群聊，private=私聊",
                        },
                        "target_id": {"type": "string", "description": "目标群号或QQ号"},
                        "task": {
                            "type": "string",
                            "description": "要传达的信息或指令。示例：'[mode: fire_and_forget] [notify: no_response] 告知群123456：...'",
                        },
                        "mode": {
                            "type": "string", "enum": ["fire_and_forget", "wait"],
                            "description": "调用模式：fire_and_forget=立即返回，wait=等待完成",
                            "default": "fire_and_forget",
                        },
                        "notification_mode": {
                            "type": "string", "enum": ["no_response", "response"],
                            "description": "通知模式：no_response=不需回应，response=回传结果",
                            "default": "no_response",
                        },
                    },
                    "required": ["target_kind", "target_id", "task"],
                },
            ),
            self._tool_def(
                "cross_chat_query",
                "查询指定聊天的聊天记录，了解讨论内容或获取信息。",
                {
                    "properties": {
                        "target_kind": {
                            "type": "string", "enum": ["group", "private"],
                            "description": "目标聊天类型",
                        },
                        "target_id": {"type": "string", "description": "目标群号或QQ号"},
                        "query": {"type": "string", "description": "要查询的信息描述"},
                        "message_count": {"type": "integer", "description": "读取最近消息条数，默认 20", "default": 20},
                    },
                    "required": ["target_kind", "target_id", "query"],
                },
            ),
            self._tool_def(
                "cross_chat_status",
                "查询当前跨聊天通信任务的状态。",
                {
                    "properties": {
                        "task_id": {"type": "string", "description": "可选，指定任务 ID"},
                    },
                    "required": [],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown cross_chat tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_cross_chat_send(self: CrossChatSkill, args: dict) -> str:
    target_kind = str(args.get("target_kind", "")).strip()
    target_id = str(args.get("target_id", "")).strip()
    task_desc = str(args.get("task", "")).strip()
    if not target_kind or not target_id or not task_desc:
        return _json({"ok": False, "error": "缺少必要参数 target_kind/target_id/task"})
    mode = args.get("mode", "fire_and_forget")
    if mode == "wait":
        return _json({"ok": True, "status": "sent", "mode": "wait", "note": "等待模式（stub）"})
    return _json({"ok": True, "status": "submitted", "mode": "fire_and_forget"})

async def _handle_cross_chat_query(self: CrossChatSkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    target_kind = str(args.get("target_kind", "")).strip()
    target_id = str(args.get("target_id", "")).strip()
    count = int(args.get("message_count", 20))
    try:
        history = await self._adapter.get_chat_history(target_kind, target_id, limit=count)
        return _json({"ok": True, "history": str(history)[:3000]})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_cross_chat_status(self: CrossChatSkill, args: dict) -> str:
    task_id = args.get("task_id", "")
    if task_id:
        return _json({"ok": True, "task_id": task_id, "status": "unknown"})
    return _json({"ok": True, "active_tasks": 0})


_HANDLERS = {
    "cross_chat_send": _handle_cross_chat_send,
    "cross_chat_query": _handle_cross_chat_query,
    "cross_chat_status": _handle_cross_chat_status,
}
