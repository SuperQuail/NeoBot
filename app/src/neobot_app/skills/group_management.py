"""GroupManagementSkill — 群管理（管理员/禁言/踢人/群名/精华/撤回等）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class GroupManagementSkill(SkillModule):
    """群管理 Skill — 管理员、禁言、踢人、群名/备注、头衔、加群请求、精华、撤回。"""

    @property
    def name(self) -> str:
        return "group_management"

    @property
    def description(self) -> str:
        return "群管理：管理员设置、禁言、踢人、群名/备注/名片/头衔、加群请求、精华消息、撤回"

    @property
    def instructions(self) -> str:
        return (
            "群管理 Skill 提供以下能力（manage_group 工具）：\n\n"
            "  set_admin — 设置/取消管理员（需群主权限）\n"
            "  set_ban — 禁言用户（duration 秒）\n"
            "  set_whole_ban — 全员禁言\n"
            "  kick — 踢出群\n"
            "  set_card — 修改群名片\n"
            "  set_group_name / set_group_remark — 修改群名/备注\n"
            "  set_special_title — 设置头衔\n"
            "  handle_add_request — 处理加群请求\n"
            "  set_essence / delete_essence — 精华消息管理\n"
            "  delete_msg — 撤回消息"
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
                "manage_group",
                "群管理：管理员、禁言、踢人、群名/群备注/群名片/头衔、加群请求、精华、撤回。",
                {
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": [
                                "set_admin", "set_ban", "set_whole_ban", "kick",
                                "set_card", "set_group_name", "set_group_remark",
                                "set_special_title", "handle_add_request",
                                "set_essence", "delete_essence", "delete_msg",
                            ],
                            "description": "要执行的群管理动作。",
                        },
                        "group_id": {"type": "integer", "description": "群号"},
                        "user_id": {"type": "integer", "description": "目标 QQ 号"},
                        "enable": {"type": "boolean", "description": "是否启用/设为管理员/全员禁言"},
                        "duration": {"type": "integer", "description": "禁言秒数"},
                        "reject_add_request": {"type": "boolean", "description": "踢人后是否拒绝再次加群"},
                        "text": {"type": "string", "description": "群名、备注、名片或头衔"},
                        "flag": {"type": "string", "description": "加群请求 flag"},
                        "approve": {"type": "boolean", "description": "是否同意请求"},
                        "reason": {"type": "string", "description": "拒绝理由"},
                        "message_id": {"type": "integer", "description": "消息 ID，用于撤回/精华"},
                    },
                    "required": ["action"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown group_management tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_manage_group(self: GroupManagementSkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    action = str(args.get("action", "")).strip()
    action_params: dict[str, Any] = {"action": action}
    for key in ("group_id", "user_id"):
        if key in args:
            action_params[key] = int(args[key])
    for key in ("enable", "reject_add_request", "approve"):
        if key in args:
            action_params[key] = bool(args[key])
    for key in ("duration", "message_id"):
        if key in args:
            action_params[key] = int(args[key])
    for key in ("text", "flag", "reason"):
        if key in args:
            action_params[key] = str(args[key])
    try:
        result = await self._adapter.call_api("manage_group", action_params)
        return _json({"ok": True, "result": str(result)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


_HANDLERS = {
    "manage_group": _handle_manage_group,
}
