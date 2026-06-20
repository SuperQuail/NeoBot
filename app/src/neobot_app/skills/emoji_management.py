"""EmojiManagementSkill — 表情包管理（列/搜/增/改/重命名）。"""

from __future__ import annotations

import json
from pathlib import Path
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
                        "return_paths": {"type": "boolean", "description": "是否返回文件路径", "default": False},
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
                        "return_paths": {"type": "boolean", "description": "是否返回文件路径", "default": False},
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
                        "emoji_id": {"type": "integer", "description": "表情包编号"},
                        "description": {"type": "string", "description": "新的描述"},
                    },
                    "required": ["emoji_id", "description"],
                },
            ),
            self._tool_def(
                "emoji_rename",
                "重命名表情包。",
                {
                    "properties": {
                        "emoji_id": {"type": "integer", "description": "表情包编号"},
                        "name": {"type": "string", "description": "新的文件名称"},
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

# ── Handlers ──

async def _handle_emoji_list(self: EmojiManagementSkill, args: dict) -> str:
    if self._emoji_service is None:
        return _json({"ok": False, "error": "emoji_service 未配置"})
    page = int(args.get("page", 1))
    page_size = int(args.get("page_size", 50))
    return_paths = bool(args.get("return_paths", False))
    try:
        offset = (page - 1) * page_size
        items_result, total, has_more = self._emoji_service.list_entries_paginated(
            offset=offset, limit=page_size
        )
        items = []
        for number, entry in items_result:
            item = {
                "number": number,
                "file_name": entry.file_name,
                "description": entry.analysis_text,
                "use_count": entry.use_count,
            }
            if return_paths:
                item["path"] = str(entry.file_path)
            items.append(item)
        return _json({
            "ok": True, "items": items, "total": total, "has_more": has_more,
        })
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_emoji_search(self: EmojiManagementSkill, args: dict) -> str:
    if self._emoji_service is None:
        return _json({"ok": False, "error": "emoji_service 未配置"})
    keyword = str(args.get("keyword", "")).strip()
    return_paths = bool(args.get("return_paths", False))
    try:
        entries = self._emoji_service.search_entries(keyword)
        items = []
        for number, entry in entries:
            item = {
                "number": number,
                "file_name": entry.file_name,
                "description": entry.analysis_text,
                "use_count": entry.use_count,
            }
            if return_paths:
                item["path"] = str(entry.file_path)
            items.append(item)
        return _json({"ok": True, "items": items, "total": len(items)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_emoji_add(self: EmojiManagementSkill, args: dict) -> str:
    if self._emoji_service is None:
        return _json({"ok": False, "error": "emoji_service 未配置"})
    image_path = str(args.get("image_path", "")).strip()
    description = args.get("description", None)
    if not image_path:
        return _json({"ok": False, "error": "缺少 image_path"})
    path = Path(image_path)
    if not path.exists():
        return _json({"ok": False, "error": f"文件不存在: {image_path}"})
    try:
        image_bytes = path.read_bytes()
        result = await self._emoji_service.add_image_bytes(
            image_bytes,
            file_name=path.name,
            analysis_text=description,
            image_source="skill_import",
        )
        return _json({
            "ok": True, "number": result.number,
            "file_name": result.entry.file_name,
            "description": result.entry.analysis_text,
        })
    except ValueError as e:
        return _json({"ok": False, "error": str(e)})
    except Exception as e:
        return _json({"ok": False, "error": f"添加失败: {e}"})

async def _handle_emoji_update(self: EmojiManagementSkill, args: dict) -> str:
    if self._emoji_service is None:
        return _json({"ok": False, "error": "emoji_service 未配置"})
    emoji_id = int(args.get("emoji_id", 0))
    description = str(args.get("description", "")).strip()
    if not emoji_id or not description:
        return _json({"ok": False, "error": "缺少 emoji_id 或 description"})
    try:
        entry = await self._emoji_service.update_entry_description(emoji_id, description)
        return _json({
            "ok": True, "number": emoji_id,
            "description": entry.analysis_text,
        })
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_emoji_rename(self: EmojiManagementSkill, args: dict) -> str:
    if self._emoji_service is None:
        return _json({"ok": False, "error": "emoji_service 未配置"})
    emoji_id = int(args.get("emoji_id", 0))
    name = str(args.get("name", "")).strip()
    if not emoji_id or not name:
        return _json({"ok": False, "error": "缺少 emoji_id 或 name"})
    try:
        entry = await self._emoji_service.rename_entry(emoji_id, name)
        return _json({
            "ok": True, "number": emoji_id,
            "file_name": entry.file_name,
        })
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

_HANDLERS = {
    "emoji_list": _handle_emoji_list,
    "emoji_search": _handle_emoji_search,
    "emoji_add": _handle_emoji_add,
    "emoji_update": _handle_emoji_update,
    "emoji_rename": _handle_emoji_rename,
}
