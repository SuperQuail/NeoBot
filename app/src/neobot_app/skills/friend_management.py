"""FriendManagementSkill — 好友管理（备注/分组/删除/请求/点赞）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class FriendManagementSkill(SkillModule):
    """好友管理 Skill — 备注、分组、删除、好友请求、点赞。"""

    @property
    def name(self) -> str:
        return "friend_management"

    @property
    def description(self) -> str:
        return "好友管理：备注、分组、删除、好友请求处理、点赞用户QQ主页"

    @property
    def instructions(self) -> str:
        return (
            "好友管理 Skill 提供以下能力（manage_friend 工具）：\n\n"
            "  set_remark — 修改好友备注\n"
            "  set_category — 修改好友分组\n"
            "  delete_friend — 删除好友\n"
            "  handle_add_request — 处理好友请求\n"
            "  send_like — 点赞用户QQ主页/资料卡"
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
                "manage_friend",
                "好友管理：备注、分组、删除、好友请求、点赞用户主页（QQ资料卡）。",
                {
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "set_remark", "set_category", "delete_friend",
                                "handle_add_request", "send_like",
                            ],
                            "description": "要执行的好友管理动作。send_like=点赞用户QQ主页/资料卡",
                        },
                        "user_id": {"type": "integer", "description": "目标 QQ 号"},
                        "remark": {"type": "string", "description": "好友备注"},
                        "category_id": {"type": "integer", "description": "好友分组 ID"},
                        "flag": {"type": "string", "description": "好友请求 flag"},
                        "approve": {"type": "boolean", "description": "是否同意请求"},
                        "times": {"type": "integer", "description": "点赞次数，非VIP每日最多10次"},
                    },
                    "required": ["action"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown friend_management tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_manage_friend(self: FriendManagementSkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    action = str(args.get("action", "")).strip()
    action_params: dict[str, Any] = {"action": action}
    for key in ("user_id", "category_id", "times"):
        if key in args:
            action_params[key] = int(args[key])
    for key in ("approve",):
        if key in args:
            action_params[key] = bool(args[key])
    for key in ("remark", "flag"):
        if key in args:
            action_params[key] = str(args[key])
    try:
        result = await self._adapter.call_api("manage_friend", action_params)
        return _json({"ok": True, "result": str(result)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


_HANDLERS = {
    "manage_friend": _handle_manage_friend,
}
