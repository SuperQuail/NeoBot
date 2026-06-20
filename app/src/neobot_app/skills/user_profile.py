"""UserProfileSkill — 用户资料查询与头像解析。"""

from __future__ import annotations

import asyncio
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

# ── Handlers ──

async def _handle_read_user_info(self: UserProfileSkill, args: dict) -> str:
    if self._profile_service is None:
        return _json({"ok": False, "error": "profile_service 未配置"})
    user_id = str(args.get("user_id", "")).strip()
    if not user_id:
        return _json({"ok": False, "error": "缺少 user_id"})
    try:
        profile = await self._profile_service.get_user(user_id)
        if profile is None:
            return _json({"ok": True, "info": None, "message": "该用户暂无资料"})
        info = {
            "nick_name": getattr(profile, "nick_name", None),
            "remark": getattr(profile, "remark", None),
            "profile": getattr(profile, "profile", None),
            "avatar_analysis": getattr(profile, "avatar_analysis", None),
            "sex": getattr(profile, "sex", None),
            "age": getattr(profile, "age", None),
            "city": getattr(profile, "city", None),
            "country": getattr(profile, "country", None),
            "long_nick": getattr(profile, "long_nick", None),
            "birthday": getattr(profile, "birthday", None),
            "favorability": getattr(profile, "favorability", 0),
            "relation_ship": getattr(profile, "relation_ship", None),
            "known_gender": getattr(profile, "known_gender", None),
            "labs": getattr(profile, "labs", None),
        }
        return _json({"ok": True, "info": info})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_analyze_user_avatar(self: UserProfileSkill, args: dict) -> str:
    if self._profile_service is None or self._adapter is None or self._image_parse_provider is None:
        return _json({"ok": False, "error": "avatar 解析服务未完整配置"})
    user_id = str(args.get("user_id", "")).strip()
    if not user_id:
        return _json({"ok": False, "error": "缺少 user_id"})
    group_id = str(args.get("group_id", "")).strip() or None
    requirement = str(args.get("requirement", "")).strip() or (
        "请简洁描述这个QQ头像中稳定、可作为长期记忆的视觉信息。"
        "只描述头像本身，不要推断真实身份、性格或敏感属性。"
    )

    # 获取头像 URL
    avatar_url: str | None = None
    try:
        params: dict = {"user_id": int(user_id)}
        if group_id:
            params["group_id"] = int(group_id)
        result = await asyncio.wait_for(
            self._adapter.call_api("get_qq_avatar", params),
            timeout=10.0,
        )
        if isinstance(result, dict):
            data = result.get("data", {})
            avatar_url = (data.get("url") if isinstance(data, dict) else None) or result.get("url")
        else:
            avatar_url = getattr(result, "url", None)
    except Exception:
        pass

    if not avatar_url:
        return _json({"ok": False, "error": f"无法获取用户 {user_id} 的头像 URL"})

    # 解析头像
    try:
        result = await self._image_parse_provider.chat([{
            "role": "user",
            "content": [
                {"type": "text", "text": requirement},
                {"type": "image", "source": {"type": "url", "url": avatar_url}},
            ],
        }])
        analysis = result.get("content", "") if isinstance(result, dict) else str(result)
        analysis = analysis.strip()
        if not analysis:
            return _json({"ok": False, "error": "头像解析返回空文本", "user_id": user_id})
        await self._profile_service.update_user_avatar_analysis(user_id, analysis)
        return _json({"ok": True, "user_id": user_id, "avatar_analysis": analysis[:2000]})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

_HANDLERS = {
    "read_user_info": _handle_read_user_info,
    "analyze_user_avatar": _handle_analyze_user_avatar,
}
