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

# ── Handlers ──

async def _handle_manage_group(self: GroupManagementSkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    action = str(args.get("action", "")).strip()
    try:
        api_action, params = _group_action_params(action, args)
        result = await self._adapter.call_api(api_action, params)
        return _json({"ok": True, "action": action, "api": api_action, "result": str(result)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

def _group_action_params(action: str, args: dict) -> tuple[str, dict[str, Any]]:
    group_id = _as_int(args.get("group_id"))
    user_id = _as_int(args.get("user_id"))
    message_id = _as_int(args.get("message_id"))
    text = _as_str(args.get("text"))

    if action == "set_admin":
        return "set_group_admin", {
            "group_id": _require(group_id, "group_id"),
            "user_id": _require(user_id, "user_id"),
            "enable": bool(args.get("enable")),
        }
    if action == "set_ban":
        return "set_group_ban", {
            "group_id": _require(group_id, "group_id"),
            "user_id": _require(user_id, "user_id"),
            "duration": _require(_as_int(args.get("duration")), "duration"),
        }
    if action == "set_whole_ban":
        return "set_group_whole_ban", {
            "group_id": _require(group_id, "group_id"),
            "enable": bool(args.get("enable", True)),
        }
    if action == "kick":
        return "set_group_kick", {
            "group_id": _require(group_id, "group_id"),
            "user_id": _require(user_id, "user_id"),
            "reject_add_request": bool(args.get("reject_add_request", False)),
        }
    if action == "set_card":
        return "set_group_card", {
            "group_id": _require(group_id, "group_id"),
            "user_id": _require(user_id, "user_id"),
            "card": _require(text, "text"),
        }
    if action == "set_group_name":
        return "set_group_name", {
            "group_id": _require(group_id, "group_id"),
            "group_name": _require(text, "text"),
        }
    if action == "set_group_remark":
        return "set_group_remark", {
            "group_id": _require(group_id, "group_id"),
            "remark": _require(text, "text"),
        }
    if action == "set_special_title":
        return "set_group_special_title", {
            "group_id": _require(group_id, "group_id"),
            "user_id": _require(user_id, "user_id"),
            "special_title": _require(text, "text"),
        }
    if action == "handle_add_request":
        return "set_group_add_request", {
            "flag": _require(_as_str(args.get("flag")), "flag"),
            "approve": bool(args.get("approve", True)),
            "reason": _as_str(args.get("reason")) or "",
        }
    if action == "set_essence":
        return "set_essence_msg", {"message_id": _require(message_id, "message_id")}
    if action == "delete_essence":
        return "delete_essence_msg", {"message_id": _require(message_id, "message_id")}
    if action == "delete_msg":
        return "delete_msg", {"message_id": _require(message_id, "message_id")}
    raise ValueError(f"未知群管理动作: {action}")

def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)

def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

def _require(value: Any, name: str) -> Any:
    if value is None or value == "":
        raise ValueError(f"缺少参数 {name}")
    return value

_HANDLERS = {
    "manage_group": _handle_manage_group,
}
