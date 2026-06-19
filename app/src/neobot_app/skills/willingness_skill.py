"""WillingnessSkill — 回复意愿控制（系数/黑名单/状态查看）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class WillingnessSkill(SkillModule):
    """回复意愿控制 Skill — 运行时回复系数调整与会话黑名单管理。"""

    @property
    def name(self) -> str:
        return "willingness"

    @property
    def description(self) -> str:
        return "回复意愿控制：调整运行时回复概率系数（会话级/用户级/全局）和临时黑名单"

    @property
    def instructions(self) -> str:
        return (
            "回复意愿 Skill 提供以下能力，所有调整仅存于内存，重启后重置：\n\n"
            "## 会话系数\n"
            "  set_session_coefficient — 设置当前会话回复概率系数 (0.0~1.0)\n"
            "  remove_session_coefficient — 移除会话系数，恢复默认\n\n"
            "## 会话用户系数\n"
            "  set_session_user_coefficient — 设置指定会话内指定用户的系数\n"
            "  remove_session_user_coefficient — 移除指定用户的会话系数\n\n"
            "## 用户全局系数\n"
            "  set_user_global_coefficient — 设置指定用户的全局系数\n"
            "  remove_user_global_coefficient — 移除指定用户的全局系数\n\n"
            "## 黑名单\n"
            "  add_session_blacklist — 当前会话加入临时黑名单\n"
            "  remove_session_blacklist — 从临时黑名单移除\n\n"
            "## 状态查看\n"
            "  get_willingness_status — 查看当前所有意愿设置"
        )

    def __init__(self, willing_service: Any = None) -> None:
        self._willing = willing_service

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "get_willingness_status",
                "查看当前运行时回复意愿设置，包括全局、会话、用户全局、会话用户系数和临时黑名单。",
                {"properties": {}, "required": []},
            ),
            self._tool_def(
                "set_session_coefficient",
                "设置当前会话的运行时回复概率系数（0.0~1.0）。0.0=完全不想回复，1.0=正常。",
                {
                    "properties": {
                        "value": {"type": "number", "description": "回复概率系数，范围 0.0~1.0"},
                    },
                    "required": ["value"],
                },
            ),
            self._tool_def(
                "remove_session_coefficient",
                "移除当前会话的运行时回复概率系数，恢复默认行为。",
                {"properties": {}, "required": []},
            ),
            self._tool_def(
                "set_session_user_coefficient",
                "设置指定聊天流中指定用户的运行时回复概率系数（0.0~1.0）。conv_id 不填时使用当前会话。",
                {
                    "properties": {
                        "user_id": {"type": "string", "description": "目标用户 QQ 号"},
                        "value": {"type": "number", "description": "回复概率系数，范围 0.0~1.0"},
                        "conv_id": {"type": "string", "description": "可选，目标聊天流 ID"},
                    },
                    "required": ["user_id", "value"],
                },
            ),
            self._tool_def(
                "remove_session_user_coefficient",
                "移除指定聊天流中指定用户的运行时回复概率系数。",
                {
                    "properties": {
                        "user_id": {"type": "string", "description": "目标用户 QQ 号"},
                        "conv_id": {"type": "string", "description": "可选，目标聊天流 ID"},
                    },
                    "required": ["user_id"],
                },
            ),
            self._tool_def(
                "set_user_global_coefficient",
                "设置指定用户的全局运行时回复概率系数（0.0~1.0），影响该用户在所有聊天流中的意愿计算。",
                {
                    "properties": {
                        "user_id": {"type": "string", "description": "目标用户 QQ 号"},
                        "value": {"type": "number", "description": "回复概率系数，范围 0.0~1.0"},
                    },
                    "required": ["user_id", "value"],
                },
            ),
            self._tool_def(
                "remove_user_global_coefficient",
                "移除指定用户的全局运行时回复概率系数，恢复默认行为。",
                {
                    "properties": {
                        "user_id": {"type": "string", "description": "目标用户 QQ 号"},
                    },
                    "required": ["user_id"],
                },
            ),
            self._tool_def(
                "add_session_blacklist",
                "将当前会话加入临时黑名单，Bot 将不再回复该会话的消息。重启后自动清除。",
                {"properties": {}, "required": []},
            ),
            self._tool_def(
                "remove_session_blacklist",
                "将当前会话从临时黑名单中移除，恢复 Bot 对该会话的回复。",
                {"properties": {}, "required": []},
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown willingness tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_get_willingness_status(self: WillingnessSkill, args: dict) -> str:
    if self._willing is None:
        return _json({"ok": True, "note": "willing_service 未配置，所有设置均为默认"})
    return self._willing.get_runtime_config_summary()

async def _handle_set_session_coefficient(self: WillingnessSkill, args: dict) -> str:
    if self._willing is None:
        return _json({"ok": False, "error": "willing_service 未配置"})
    value = float(args.get("value", 1.0))
    return self._willing.set_runtime_conversation_coefficient("current", value)

async def _handle_remove_session_coefficient(self: WillingnessSkill, args: dict) -> str:
    if self._willing is None:
        return _json({"ok": False, "error": "willing_service 未配置"})
    return self._willing.remove_runtime_conversation_coefficient("current")

async def _handle_set_session_user_coefficient(self: WillingnessSkill, args: dict) -> str:
    if self._willing is None:
        return _json({"ok": False, "error": "willing_service 未配置"})
    user_id = str(args.get("user_id", "")).strip()
    value = float(args.get("value", 1.0))
    conv_id = str(args.get("conv_id", "current")).strip()
    return self._willing.set_runtime_conversation_user_coefficient(conv_id, user_id, value)

async def _handle_remove_session_user_coefficient(self: WillingnessSkill, args: dict) -> str:
    if self._willing is None:
        return _json({"ok": False, "error": "willing_service 未配置"})
    user_id = str(args.get("user_id", "")).strip()
    conv_id = str(args.get("conv_id", "current")).strip()
    return self._willing.remove_runtime_conversation_user_coefficient(conv_id, user_id)

async def _handle_set_user_global_coefficient(self: WillingnessSkill, args: dict) -> str:
    if self._willing is None:
        return _json({"ok": False, "error": "willing_service 未配置"})
    user_id = str(args.get("user_id", "")).strip()
    value = float(args.get("value", 1.0))
    return self._willing.set_runtime_user_global_coefficient(user_id, value)

async def _handle_remove_user_global_coefficient(self: WillingnessSkill, args: dict) -> str:
    if self._willing is None:
        return _json({"ok": False, "error": "willing_service 未配置"})
    user_id = str(args.get("user_id", "")).strip()
    return self._willing.remove_runtime_user_global_coefficient(user_id)

async def _handle_add_session_blacklist(self: WillingnessSkill, args: dict) -> str:
    if self._willing is None:
        return _json({"ok": True, "note": "模拟：当前会话已加入临时黑名单"})
    return self._willing.add_runtime_blacklist("current")

async def _handle_remove_session_blacklist(self: WillingnessSkill, args: dict) -> str:
    if self._willing is None:
        return _json({"ok": True, "note": "模拟：当前会话已从临时黑名单移除"})
    return self._willing.remove_runtime_blacklist("current")


_HANDLERS = {
    "get_willingness_status": _handle_get_willingness_status,
    "set_session_coefficient": _handle_set_session_coefficient,
    "remove_session_coefficient": _handle_remove_session_coefficient,
    "set_session_user_coefficient": _handle_set_session_user_coefficient,
    "remove_session_user_coefficient": _handle_remove_session_user_coefficient,
    "set_user_global_coefficient": _handle_set_user_global_coefficient,
    "remove_user_global_coefficient": _handle_remove_user_global_coefficient,
    "add_session_blacklist": _handle_add_session_blacklist,
    "remove_session_blacklist": _handle_remove_session_blacklist,
}
