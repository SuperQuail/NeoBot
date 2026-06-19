"""EmojiManagementSkill — 表情包管理（列/搜/增/改/重命名）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class EmojiManagementSkill(SkillModule):
    """表情包管理 Skill — 列出、搜索、添加、更新、重命名表情包。"""

    @property
    def name(self) -> str:
        return "emoji_management"

    @property
    def description(self) -> str:
        return "表情包管理：列出、搜索、添加、更新、重命名表情包库中的表情包"

    @property
    def instructions(self) -> str:
        return (
            "表情包管理 Skill 提供以下能力：\n\n"
            "  emoji_list — 列出表情包\n"
            "  emoji_search — 搜索表情包\n"
            "  emoji_add — 添加表情包\n"
            "  emoji_update — 更新表情包信息\n"
            "  emoji_rename — 重命名表情包\n\n"
            "注意：表情包发送请在 sticker skill 中操作。表情包文件对文件操作 agent 只读暴露。"
        )

    def __init__(self, emoji_service: Any = None) -> None:
        self._emoji_service = emoji_service

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "emoji_list",
                "列出表情包库中的表情包。",
                {
                    "properties": {
                        "page": {"type": "integer", "description": "页码，从1开始", "default": 1},
                        "page_size": {"type": "integer", "description": "每页数量", "default": 50},
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "emoji_search",
                "搜索表情包。",
                {
                    "properties": {
                        "keyword": {"type": "string", "description": "搜索关键词"},
                    },
                    "required": ["keyword"],
                },
            ),
            self._tool_def(
                "emoji_add",
                "添加新表情包。",
                {
                    "properties": {
                        "image_path": {"type": "string", "description": "本地图片路径"},
                        "description": {"type": "string", "description": "表情包描述/名称"},
                    },
                    "required": ["image_path"],
                },
            ),
            self._tool_def(
                "emoji_update",
                "更新表情包信息。",
                {
                    "properties": {
                        "emoji_id": {"type": "integer", "description": "表情包 ID"},
                        "description": {"type": "string", "description": "新的描述"},
                    },
                    "required": ["emoji_id"],
                },
            ),
            self._tool_def(
                "emoji_rename",
                "重命名表情包。",
                {
                    "properties": {
                        "emoji_id": {"type": "integer", "description": "表情包 ID"},
                        "name": {"type": "string", "description": "新的名称"},
                    },
                    "required": ["emoji_id", "name"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown emoji_management tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_emoji_list(self: EmojiManagementSkill, args: dict) -> str:
    if self._emoji_service is None:
        return _json({"ok": False, "error": "emoji_service 未配置"})
    page = int(args.get("page", 1))
    page_size = int(args.get("page_size", 50))
    try:
        result = await self._emoji_service.list_emoji(page=page, page_size=page_size)
        return _json({"ok": True, "result": str(result)[:2000]})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_emoji_search(self: EmojiManagementSkill, args: dict) -> str:
    if self._emoji_service is None:
        return _json({"ok": False, "error": "emoji_service 未配置"})
    keyword = str(args.get("keyword", "")).strip()
    try:
        result = await self._emoji_service.search_emoji(keyword)
        return _json({"ok": True, "result": str(result)[:2000]})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_emoji_add(self: EmojiManagementSkill, args: dict) -> str:
    return _json({"ok": False, "error": "emoji_service 未配置"})

async def _handle_emoji_update(self: EmojiManagementSkill, args: dict) -> str:
    return _json({"ok": False, "error": "emoji_service 未配置"})

async def _handle_emoji_rename(self: EmojiManagementSkill, args: dict) -> str:
    return _json({"ok": False, "error": "emoji_service 未配置"})


_HANDLERS = {
    "emoji_list": _handle_emoji_list,
    "emoji_search": _handle_emoji_search,
    "emoji_add": _handle_emoji_add,
    "emoji_update": _handle_emoji_update,
    "emoji_rename": _handle_emoji_rename,
}
