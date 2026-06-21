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

# ── Handlers ──

async def _handle_manage_friend(self: FriendManagementSkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    action = str(args.get("action", "")).strip()
    try:
        api_action, params = _friend_action_params(action, args)
        result = await self._adapter.call_api(api_action, params)
        return _json({"ok": True, "action": action, "api": api_action, "result": str(result)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

def _friend_action_params(action: str, args: dict) -> tuple[str, dict[str, Any]]:
    user_id = _as_int(args.get("user_id"))
    if action == "set_remark":
        return "set_friend_remark", {
            "user_id": _require(user_id, "user_id"),
            "remark": _require(_as_str(args.get("remark")), "remark"),
        }
    if action == "set_category":
        return "set_friend_category", {
            "user_id": _require(user_id, "user_id"),
            "category_id": _require(_as_int(args.get("category_id")), "category_id"),
        }
    if action == "delete_friend":
        return "delete_friend", {"user_id": _require(user_id, "user_id")}
    if action == "handle_add_request":
        return "set_friend_add_request", {
            "flag": _require(_as_str(args.get("flag")), "flag"),
            "approve": bool(args.get("approve", True)),
            "remark": _as_str(args.get("remark")) or "",
        }
    if action == "send_like":
        return "send_like", {
            "user_id": _require(user_id, "user_id"),
            "times": int(args.get("times") or 1),
        }
    raise ValueError(f"未知好友管理动作: {action}")

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
    "manage_friend": _handle_manage_friend,
}
