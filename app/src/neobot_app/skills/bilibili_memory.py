"""BilibiliMemorySkill — B站长期记忆管理。

迁移自 dev-test/recovered_bilibili/.../skills/bilibili_memory.py，改用当前
ArchiveMemoryService（get/set/list/delete）：
- bv_video: 按 BV号 存视频相关记忆
- cv_column: 按 CV号 存专栏相关记忆
- bilibili_user: 按 B站UID 存用户相关记忆（账号关联合并时也读这张表）
"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.bilibili._compat import call_client, get_field
from neobot_app.skills.base import SkillModule
from neobot_app.utils.logger import get_module_logger

logger = get_module_logger("bilibili.memory_skill")


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _parse_tags(value: Any) -> list[str]:
    """标签归一化：模型常把数组写成 "搞笑,合集"，按逗号拆而不是逐字符
    （list("搞笑,合集") 会拆成 ['搞', '笑', ',', ...]）。"""
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple, set)):
        return []
    return [text for tag in value if tag is not None and (text := str(tag).strip())]


class BilibiliMemorySkill(SkillModule):
    """B站记忆 Skill — 管理视频/专栏/用户三类 B站专属档案。"""

    _ALLOWED_TABLES = ("bv_video", "cv_column", "bilibili_user")

    def __init__(
        self,
        archive_service: Any = None,
        allowed_tables: tuple[str, ...] = (),
    ) -> None:
        self._archive = archive_service
        self._allowed = allowed_tables or self._ALLOWED_TABLES

    @property
    def name(self) -> str:
        return "bilibili_memory"

    @property
    def description(self) -> str:
        return "B站长期记忆：管理视频(bv_video)、专栏(cv_column)、用户(bilibili_user)的档案"

    @property
    def instructions(self) -> str:
        return (
            "B站记忆 Skill 管理以 BV号 / CV号 / B站UID 为主键的长期档案：\n\n"
            "  save_memory — 保存/更新记忆；table_name 可选 bv_video(键=BV号)、"
            "cv_column(键=CV号)、bilibili_user(键=UID)。更新时写入完整合并内容。\n"
            "  read_memory — 读取一条记忆。\n"
            "  list_memory — 列出条目（分页 + 键名筛选）。\n"
            "  delete_memory — 删除一条记忆。\n\n"
            "使用场景：看到关于某个视频的有价值信息存 bv_video；与某位B站用户多次互动后，"
            "把对ta的印象存 bilibili_user（账号关联时会合并到对应QQ档案）。"
        )

    def reset(self) -> None:
        pass

    def get_tools(self) -> list[dict]:
        if self._archive is None:
            return []
        table_schema = {
            "type": "string",
            "description": "表名: bv_video / cv_column / bilibili_user",
            "enum": list(self._allowed),
        }
        return [
            self._tool_def(
                "save_memory",
                "保存或更新B站记忆档案。更新已有条目时请写入完整的合并内容（不要只写增量）。",
                {
                    "properties": {
                        "table_name": table_schema,
                        "key": {"type": "string", "description": "主键: BV号 / CV号 / B站UID"},
                        "value": {"type": "string", "description": "完整的档案内容文本"},
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
                    "properties": {"table_name": table_schema, "key": {"type": "string"}},
                    "required": ["table_name", "key"],
                },
            ),
            self._tool_def(
                "list_memory",
                "列出B站记忆条目，支持分页和键名模糊筛选。",
                {
                    "properties": {
                        "table_name": table_schema,
                        "key_query": {"type": "string", "description": "可选：键名模糊匹配"},
                        "limit": {"type": "integer", "description": "返回条数上限，默认10", "default": 10},
                        "offset": {"type": "integer", "description": "分页偏移，默认0", "default": 0},
                    },
                    "required": ["table_name"],
                },
            ),
            self._tool_def(
                "delete_memory",
                "删除一条B站记忆档案。",
                {
                    "properties": {"table_name": table_schema, "key": {"type": "string"}},
                    "required": ["table_name", "key"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown tool: {tool_name}"})
        table = str(args.get("table_name") or "").strip()
        if table not in self._allowed:
            return _json({"ok": False, "error": f"不允许的表名: {table}"})
        try:
            return await handler(self, table, args)
        except Exception as exc:
            logger.warning(f"B站记忆工具执行失败: {tool_name}: {type(exc).__name__}: {exc}")
            return _json({"ok": False, "error": str(exc)})


# ── Handlers ──


async def _handle_save(skill: BilibiliMemorySkill, table: str, args: dict) -> str:
    key = str(args.get("key") or "").strip()
    value = str(args.get("value") or "").strip()
    tags = _parse_tags(args.get("tags"))
    if not key or not value:
        return _json({"ok": False, "error": "缺少 key 或 value"})
    await call_client(skill._archive.set, table, key, value, tags)
    return _json({"ok": True, "table": table, "key": key})


async def _handle_read(skill: BilibiliMemorySkill, table: str, args: dict) -> str:
    key = str(args.get("key") or "").strip()
    if not key:
        return _json({"ok": False, "error": "缺少 key"})
    item = await call_client(skill._archive.get, table, key)
    if item is None:
        return _json({"ok": True, "found": False, "item": None})
    return _json(
        {
            "ok": True,
            "found": True,
            "item": {
                "key": str(get_field(item, "key", key)),
                "value": str(get_field(item, "value", "")),
                "tags": list(get_field(item, "tags", []) or []),
            },
        }
    )


async def _handle_list(skill: BilibiliMemorySkill, table: str, args: dict) -> str:
    key_query = str(args.get("key_query") or "").strip()
    limit = max(1, min(int(args.get("limit", 10) or 10), 50))
    offset = max(0, int(args.get("offset", 0) or 0))
    items = await call_client(
        skill._archive.list,
        table,
        key_query=key_query or None,
        limit=limit,
        offset=offset,
    )
    rows = [
        {
            "key": str(get_field(item, "key", "")),
            "value": str(get_field(item, "value", "")),
            "tags": list(get_field(item, "tags", []) or []),
        }
        for item in items or []
    ]
    return _json({"ok": True, "items": rows, "count": len(rows)})


async def _handle_delete(skill: BilibiliMemorySkill, table: str, args: dict) -> str:
    key = str(args.get("key") or "").strip()
    if not key:
        return _json({"ok": False, "error": "缺少 key"})
    deleted = await call_client(skill._archive.delete, table, key)
    return _json({"ok": True, "deleted": bool(deleted)})


_HANDLERS = {
    "save_memory": _handle_save,
    "read_memory": _handle_read,
    "list_memory": _handle_list,
    "delete_memory": _handle_delete,
}
