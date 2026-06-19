"""UserProfileSkill — 用户资料查询与头像解析。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class UserProfileSkill(SkillModule):
    """用户资料 Skill — 查询用户资料、解析用户头像。"""

    @property
    def name(self) -> str:
        return "user_profile"

    @property
    def description(self) -> str:
        return "用户资料：读取用户资料表、解析用户QQ头像并写入资料"

    @property
    def instructions(self) -> str:
        return (
            "用户资料 Skill 提供以下能力：\n\n"
            "  read_user_info — 读取数据库用户资料表中的资料，包含好友备注 remark 和头像解析记忆 avatar_analysis\n"
            "  analyze_user_avatar — 获取并解析用户QQ头像，结果写入用户资料表 avatar_analysis\n"
        )

    def __init__(
        self,
        profile_service: Any = None,
        adapter: Any = None,
        image_parse_provider: Any = None,
    ) -> None:
        self._profile_service = profile_service
        self._adapter = adapter
        self._image_parse_provider = image_parse_provider

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        tools = []
        if self._profile_service is not None:
            tools.append(
                self._tool_def(
                    "read_user_info",
                    "读取数据库用户资料表中的资料，包含好友备注 remark 和头像解析记忆 avatar_analysis。"
                    "查询某个QQ号的好友备注或头像记忆时优先使用此工具。",
                    {
                        "properties": {
                            "user_id": {"type": "string", "description": "QQ号"},
                        },
                        "required": ["user_id"],
                    },
                ),
            )

        if self._profile_service and self._adapter and self._image_parse_provider:
            tools.append(
                self._tool_def(
                    "analyze_user_avatar",
                    "获取并解析指定用户QQ头像，将解析结果写入用户资料表 avatar_analysis。",
                    {
                        "properties": {
                            "user_id": {"type": "string", "description": "目标QQ号"},
                            "group_id": {"type": "string", "description": "可选，群号"},
                            "requirement": {"type": "string", "description": "可选，头像解析要求"},
                        },
                        "required": ["user_id"],
                    },
                ),
            )

        return tools

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown user_profile tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_read_user_info(self: UserProfileSkill, args: dict) -> str:
    if self._profile_service is None:
        return _json({"ok": False, "error": "profile_service 未配置"})
    user_id = str(args.get("user_id", "")).strip()
    if not user_id:
        return _json({"ok": False, "error": "缺少 user_id"})
    try:
        info = await self._profile_service.get_user_info(user_id)
        return _json({"ok": True, "info": info})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_analyze_user_avatar(self: UserProfileSkill, args: dict) -> str:
    return _json({"ok": False, "error": "avatar 解析服务未完整配置"})


_HANDLERS = {
    "read_user_info": _handle_read_user_info,
    "analyze_user_avatar": _handle_analyze_user_avatar,
}
