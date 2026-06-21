"""ArchiveCRUDSkill — 长期记忆档案 CRUD（存档增查改删）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

class ArchiveCRUDSkill(SkillModule):
    """长期记忆档案管理 — 档案增查改删。"""

    @property
    def name(self) -> str:
        return "archive_crud"

    @property
    def description(self) -> str:
        return "长期记忆档案管理：创建/读取/列出/删除档案条目"

    @property
    def instructions(self) -> str:
        return (
            "档案管理 Skill 提供以下能力：\n\n"
            "  save_archive — 创建或更新一条档案记忆（如 user_profile, group_summary）\n"
            "  read_archive — 读取档案记忆\n"
            "  list_archive — 列出档案条目，支持按内容/标签筛选\n"
            "  delete_archive — 删除档案记忆\n\n"
            "注意：保存档案时，修改已有档案必须写回整合后的完整内容，不要只写增量。"
        )

    def __init__(
        self,
        archive_service: Any = None,
        allow_delete: bool = False,
        allowed_tables: tuple[str, ...] = (),
    ) -> None:
        self._archive_service = archive_service
        self._allow_delete = allow_delete
        self._allowed_tables = allowed_tables

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        read_item_schema = {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "档案表名"},
                "key": {"type": "string", "description": "条目键"},
            },
            "required": ["table_name", "key"],
        }
        return [
            self._tool_def(
                "save_archive",
                "创建或更新一条档案记忆。修改已有档案时，必须写回整合后的完整内容，不要只写增量。",
                {
                    "properties": {
                        "table_name": {"type": "string", "description": "档案表名，例如 user_profile 或 group_summary"},
                        "key": {"type": "string", "description": "条目键，例如 QQ 号或群号"},
                        "value": {"type": "string", "description": "整合更新后的完整档案内容"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "可选标签"},
                    },
                    "required": ["table_name", "key", "value"],
                },
            ),
            self._tool_def(
                "read_archive",
                "读取档案记忆。可传单条 table_name 加 key，也可传 items 批量读取多条。",
                {
                    "properties": {
                        "table_name": {"type": "string", "description": "单条读取时的档案表名"},
                        "key": {"type": "string", "description": "单条读取时的条目键"},
                        "items": {"type": "array", "items": read_item_schema, "description": "批量读取时的条目列表"},
                    },
                },
            ),
            self._tool_def(
                "list_archive",
                "列出档案记忆条目。默认一次返回10条。",
                {
                    "properties": {
                        "table_name": {"type": "string", "description": "档案表名"},
                        "key_query": {"type": "string", "description": "可选的键筛选条件"},
                        "value_query": {"type": "string", "description": "可选的内容筛选条件"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "可选的标签筛选条件"},
                        "limit": {"type": "integer", "description": "本次返回条数，默认10"},
                        "offset": {"type": "integer", "description": "分页偏移量"},
                    },
                    "required": ["table_name"],
                },
            ),
            self._tool_def(
                "delete_archive",
                "按表名和键删除一条档案记忆。",
                {
                    "properties": {
                        "table_name": {"type": "string", "description": "档案表名"},
                        "key": {"type": "string", "description": "条目键"},
                    },
                    "required": ["table_name", "key"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown archive_crud tool: {tool_name}"})
        return await handler(self, args)

# ── Handlers ──

async def _handle_save_archive(self: ArchiveCRUDSkill, args: dict) -> str:
    if self._archive_service is None:
        return _json({"ok": False, "error": "archive_service 未配置"})
    table_name = str(args.get("table_name", "")).strip()
    key = str(args.get("key", "")).strip()
    value = str(args.get("value", "")).strip()
    if not table_name or not key or not value:
        return _json({"ok": False, "error": "缺少必要参数"})
    try:
        item = await self._archive_service.set(table_name, key, value, args.get("tags"))
        return _json({"ok": True, "table_name": item.table_name, "key": item.key, "version": item.version})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_read_archive(self: ArchiveCRUDSkill, args: dict) -> str:
    if self._archive_service is None:
        return _json({"ok": False, "error": "archive_service 未配置"})
    try:
        items_raw = args.get("items")
        if items_raw:
            results = []
            for it in items_raw:
                item = await self._archive_service.get(it["table_name"], it["key"])
                if item:
                    results.append({"table_name": item.table_name, "key": item.key, "value": item.value})
            return _json({"ok": True, "items": results})
        table_name = args.get("table_name")
        key = args.get("key")
        if table_name and key:
            item = await self._archive_service.get(table_name, key)
            if item:
                return _json({"ok": True, "item": {"table_name": item.table_name, "key": item.key, "value": item.value}})
            return _json({"ok": False, "error": "条目不存在"})
        return _json({"ok": False, "error": "传入 table_name+key 或 items"})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_list_archive(self: ArchiveCRUDSkill, args: dict) -> str:
    if self._archive_service is None:
        return _json({"ok": False, "error": "archive_service 未配置"})
    table_name = str(args.get("table_name", "")).strip()
    try:
        items = await self._archive_service.list(table_name, limit=args.get("limit", 10), offset=args.get("offset", 0))
        return _json({"ok": True, "items": [{"table_name": i.table_name, "key": i.key, "value": i.value} for i in items]})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_delete_archive(self: ArchiveCRUDSkill, args: dict) -> str:
    if self._archive_service is None:
        return _json({"ok": False, "error": "archive_service 未配置"})
    try:
        await self._archive_service.delete(args["table_name"], args["key"])
        return _json({"ok": True})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

_HANDLERS = {
    "save_archive": _handle_save_archive,
    "read_archive": _handle_read_archive,
    "list_archive": _handle_list_archive,
    "delete_archive": _handle_delete_archive,
}
