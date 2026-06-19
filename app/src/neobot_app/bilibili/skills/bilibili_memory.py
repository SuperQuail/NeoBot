"""BilibiliMemorySkill — B站长期记忆管理。

管理以 bv号/cv号/B站UID 为主键的长期记忆档案：
- bv_video: 按 BV号 存储视频相关记忆
- cv_column: 按 CV号 存储专栏相关记忆
- bilibili_user: 按 UID 存储B站用户相关记忆
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class BilibiliMemorySkill(SkillModule):
    """B站记忆 Skill — 管理视频/专栏/用户的长期记忆档案。"""

    _ALLOWED_TABLES = ("bv_video", "cv_column", "bilibili_user")

    @property
    def name(self) -> str:
        return "bilibili_memory"

    @property
    def description(self) -> str:
        return "B站长期记忆：管理视频(bv_video)、专栏(cv_column)、用户(bilibili_user)的记忆档案"

    @property
    def instructions(self) -> str:
        return (
            "B站记忆 Skill 提供对B站特定信息的长期记忆管理：\n\n"
            "  save_memory — 保存/更新记忆。table_name 可选: bv_video(键=BV号), cv_column(键=CV号), bilibili_user(键=UID)。更新已有条目时写入完整合并内容。\n"
            "  read_memory — 读取记忆。\n"
            "  list_memory — 列出记忆条目（支持分页和过滤）。\n"
            "  delete_memory — 删除记忆。\n\n"
            "使用场景：\n"
            "- 在评论区看到关于某个视频的有价值信息时，保存到 bv_video 表\n"
            "- 与某个B站用户多次互动后，将对ta的印象保存到 bilibili_user 表\n"
            "- 视频键使用 BV号（如 BV1xx411c7mD），专栏键使用 CV号，用户键使用纯数字UID\n"
            "- 你可以自主决定何时需要保存/更新/读取记忆"
        )

    def __init__(
        self,
        archive_service: Any = None,
        allowed_tables: tuple[str, ...] = (),
    ) -> None:
        self._archive = archive_service
        self._allowed = allowed_tables or self._ALLOWED_TABLES

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        if self._archive is None:
            return []
        return [
            self._tool_def(
                "save_memory",
                "保存或更新B站记忆档案。更新已有条目时请写入完整的合并内容（不要只写增量）。",
                {
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "表名: bv_video / cv_column / bilibili_user",
                            "enum": list(self._allowed),
                        },
                        "key": {
                            "type": "string",
                            "description": "主键: BV号 / CV号 / B站UID",
                        },
                        "value": {
                            "type": "string",
                            "description": "完整的档案内容文本",
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选标签列表",
                        },
                    },
                    "required": ["table_name", "key", "value"],
                },
            ),
            self._tool_def(
                "read_memory",
                "读取一条B站记忆档案。",
                {
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "表名",
                            "enum": list(self._allowed),
                        },
                        "key": {
                            "type": "string",
                            "description": "主键",
                        },
                    },
                    "required": ["table_name", "key"],
                },
            ),
            self._tool_def(
                "list_memory",
                "列出B站记忆条目，支持分页和关键词筛选。",
                {
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "表名",
                            "enum": list(self._allowed),
                        },
                        "key_query": {
                            "type": "string",
                            "description": "可选：对键名的模糊匹配",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回条数上限，默认10",
                            "default": 10,
                        },
                        "offset": {
                            "type": "integer",
                            "description": "分页偏移，默认0",
                            "default": 0,
                        },
                    },
                    "required": ["table_name"],
                },
            ),
            self._tool_def(
                "delete_memory",
                "删除一条B站记忆档案。",
                {
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "表名",
                            "enum": list(self._allowed),
                        },
                        "key": {
                            "type": "string",
                            "description": "主键",
                        },
                    },
                    "required": ["table_name", "key"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {
            "type": "function",
            "function": {"name": name, "description": desc, "parameters": p},
        }


# ── Handlers ──

async def _handle_save_memory(self: BilibiliMemorySkill, args: dict) -> str:
    table = str(args.get("table_name", "")).strip()
    key = str(args.get("key", "")).strip()
    value = str(args.get("value", "")).strip()
    tags = args.get("tags") or []

    if table not in self._allowed:
        return _json({"ok": False, "error": f"不允许的表名: {table}"})
    if not key or not value:
        return _json({"ok": False, "error": "缺少 key 或 value"})

    try:
        await self._archive.save(table, key, value, tags=list(tags))
        return _json({"ok": True, "table": table, "key": key})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_read_memory(self: BilibiliMemorySkill, args: dict) -> str:
    table = str(args.get("table_name", "")).strip()
    key = str(args.get("key", "")).strip()

    if table not in self._allowed:
        return _json({"ok": False, "error": f"不允许的表名: {table}"})
    if not key:
        return _json({"ok": False, "error": "缺少 key"})

    try:
        item = await self._archive.read(table, key)
        if item is None:
            return _json({"ok": True, "found": False, "item": None})
        return _json({
            "ok": True,
            "found": True,
            "item": {"key": item.get("key", key), "value": item.get("value", ""), "tags": item.get("tags", [])},
        })
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_list_memory(self: BilibiliMemorySkill, args: dict) -> str:
    table = str(args.get("table_name", "")).strip()
    key_query = str(args.get("key_query", "")).strip()
    limit = min(int(args.get("limit", 10)), 50)
    offset = max(int(args.get("offset", 0)), 0)

    if table not in self._allowed:
        return _json({"ok": False, "error": f"不允许的表名: {table}"})

    try:
        items = await self._archive.list_entries(
            table, key_query=key_query or None, limit=limit, offset=offset
        )
        return _json({"ok": True, "items": items, "count": len(items)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_delete_memory(self: BilibiliMemorySkill, args: dict) -> str:
    table = str(args.get("table_name", "")).strip()
    key = str(args.get("key", "")).strip()

    if table not in self._allowed:
        return _json({"ok": False, "error": f"不允许的表名: {table}"})
    if not key:
        return _json({"ok": False, "error": "缺少 key"})

    try:
        await self._archive.delete(table, key)
        return _json({"ok": True, "deleted": True})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


_HANDLERS = {
    "save_memory": _handle_save_memory,
    "read_memory": _handle_read_memory,
    "list_memory": _handle_list_memory,
    "delete_memory": _handle_delete_memory,
}
