"""ArchiveCRUDSkill — 长期记忆档案 CRUD（存档增查改删）。"""

from __future__ import annotations

import json
from typing import Any

from neobot_app.skills.base import SkillModule

# 待总结消息暂存表，与 runtime.archive_memory_summary.COUNTER_TABLE 保持一致。
PENDING_MESSAGES_TABLE = "memory_counter"


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

class ArchiveCRUDSkill(SkillModule):
    """长期记忆档案管理 — 档案增查改删。"""

    @property
    def name(self) -> str:
        return "archive_crud"

    @property
    def description(self) -> str:
        # 与工具表保持一致：allow_delete=false 时 delete_archive 不注入给模型，
        # 摘要里再宣称「删除」会让模型调用一个不存在的工具。
        suffix = "增量编辑/读取/列出/删除档案条目" if self._allow_delete else "增量编辑/读取/列出档案条目"
        return f"长期记忆档案管理：{suffix}"

    @property
    def instructions(self) -> str:
        limits = ", ".join(
            f"{table}({limit}字)"
            for table, limit in sorted((self._max_chars or {}).items())
        )
        limit_note = (
            f"；prompt 中展示的档案摘要长度上限：{limits}"
            if limits
            else ""
        )
        # 工具表会按开关裁剪，提示词必须同步：否则模型按 instructions 去调用
        # 一个被隐藏的工具（错误回灌、白费轮次），或向用户声称已删除记忆。
        delete_line = (
            "  delete_archive — 删除档案记忆\n" if self._allow_delete else ""
        )
        delete_note = (
            ""
            if self._allow_delete
            else "删除档案未启用（agent.memory.archive.allow_delete=false），不要尝试删除。\n"
        )
        allowed = self._allowed_tables
        allowed_note = (
            f"可访问的档案表：{', '.join(allowed)}（其余表一律拒绝）。\n"
            if allowed
            else ""
        )
        return (
            "档案管理 Skill 提供以下能力：\n\n"
            "  patch_archive — 增量编辑档案（推荐）：append/prepend 追加片段，replace/delete 定点改删，"
            "只写改动内容，不需要先读全文，也绝不重写整条档案\n"
            "  save_archive — 整条覆盖写入档案（只在必须整体压缩/重写时使用，如定长摘要表）\n"
            "  read_archive — 读取档案记忆；mode='outline' 只看目录/大纲，offset 分页读正文\n"
            "  read_pending_messages — 读取待总结的实时消息全文（总结提示词里被截断时用）\n"
            "  list_archive — 列出档案条目，支持按内容/标签筛选\n"
            f"{delete_line}\n"
            f"{allowed_note}"
            f"{delete_note}"
            "写入原则：新增内容用 patch_archive(append) 只写增量；修改已有内容先 outline 定位、"
            "再分页读该片段、然后 patch_archive(replace) 定点修改；不要为了写入而先读全文。"
            "原始档案不会截断，可长期积累。\n"
            "分页阅读：read_archive 的 offset 参数以页为单位，每页 500 字。\n"
            "  - offset=0（默认）从头部读第一页\n"
            "  - offset 为正数：从头部向后翻页（1=第二页）\n"
            "  - offset 为负数：从尾部向前翻页（-1=最后一页/最新内容，-2=倒数第二页）\n"
            "档案越靠后的内容越新。需要了解最新动态时，优先用负数 offset 从尾部阅读。"
            f"{limit_note}"
        )

    def __init__(
        self,
        archive_service: Any = None,
        allow_delete: bool = False,
        allowed_tables: tuple[str, ...] = (),
        max_chars: dict[str, int] | None = None,
        pending_table: str = PENDING_MESSAGES_TABLE,
    ) -> None:
        self._archive_service = archive_service
        self._allow_delete = allow_delete
        self._allowed_tables = allowed_tables
        self._max_chars = dict(max_chars or {})
        self._pending_table = str(pending_table or PENDING_MESSAGES_TABLE)

    def reset(self) -> None:
        pass

    @staticmethod
    def build_summary(text: str, limit: int) -> tuple[str, bool]:
        """从超长档案生成摘要(保留最新内容尾部,从完整行开始)。

        返回 (摘要文本, 是否截断)。原始档案由调用方完整保留。
        """
        if limit <= 0 or len(text) <= limit:
            return text, False
        tail = text[-limit:]
        newline = tail.find("\n")
        if 0 < newline < len(tail) - 1:
            tail = tail[newline + 1 :]
        return tail, True

    def get_tools(self) -> list[dict]:
        read_item_schema = {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "档案表名"},
                "key": {"type": "string", "description": "条目键"},
            },
            "required": ["table_name", "key"],
        }
        tools = [
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
                "patch_archive",
                "增量编辑档案（新增/修改内容的首选方式）：只提交改动片段，不需要先读全文，也不重写整条档案。"
                "operations 按顺序执行：append 追加到末尾、prepend 插入到开头、replace 把唯一出现的 old 换成 new、"
                "delete 删除唯一出现的 old。全部操作要么一起生效，要么一起失败。",
                {
                    "properties": {
                        "table_name": {"type": "string", "description": "档案表名，例如 user_profile 或 group_profile"},
                        "key": {"type": "string", "description": "条目键，例如 QQ 号或群号"},
                        "operations": {
                            "type": "array",
                            "description": "按顺序执行的编辑操作列表",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "op": {
                                        "type": "string",
                                        "enum": ["append", "prepend", "replace", "delete"],
                                        "description": "操作类型",
                                    },
                                    "text": {"type": "string", "description": "append/prepend 要写入的内容"},
                                    "old": {"type": "string", "description": "replace/delete 要定位的原文片段，必须唯一"},
                                    "new": {"type": "string", "description": "replace 替换后的内容"},
                                },
                                "required": ["op"],
                            },
                        },
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "可选标签，省略则保留原有标签"},
                    },
                    "required": ["table_name", "key", "operations"],
                },
            ),
            self._tool_def(
                "read_archive",
                "读取档案记忆。可传单条 table_name 加 key，也可传 items 批量读取多条。"
                "mode='outline' 只返回大纲（每行开头），用于定位后再分页读正文；"
                "超长档案用 offset 分页阅读（每页 500 字）：offset=0 从头部，正数向后翻页，"
                "负数从尾部向前翻页（-1=最新一页），档案越靠后内容越新。",
                {
                    "properties": {
                        "table_name": {"type": "string", "description": "单条读取时的档案表名"},
                        "key": {"type": "string", "description": "单条读取时的条目键"},
                        "mode": {
                            "type": "string",
                            "enum": ["full", "outline"],
                            "description": "full=读正文（默认），outline=只读大纲/目录（每行开头，用于先定位再读）",
                        },
                        "offset": {"type": "integer", "description": "可选，分页页号：0=头部第一页，正数向后翻页，负数从尾部向前翻页（-1=最新一页）；省略该参数则返回完整内容"},
                        "items": {"type": "array", "items": read_item_schema, "description": "批量读取时的条目列表"},
                    },
                },
            ),
            self._tool_def(
                "read_pending_messages",
                "读取待总结的实时消息全文（总结提示词中的消息文本可能被截断）。"
                "conversation_key 形如 'group:888' 或 'private:10001'；"
                "可传 indices（消息序号列表，从 1 开始）只取需要的几条，省略则返回全部。",
                {
                    "properties": {
                        "conversation_key": {"type": "string", "description": "会话键，形如 group:888 或 private:10001"},
                        "indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "可选，要读取的消息序号列表（从 1 开始）",
                        },
                    },
                    "required": ["conversation_key"],
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
        if not self._allow_delete:
            # 未启用删除时干脆不把工具暴露给模型（与 allow_delete=false 语义一致），
            # 避免模型反复调用一个必然被拒的工具。
            tools = [
                tool
                for tool in tools
                if tool.get("function", {}).get("name") != "delete_archive"
            ]
        return tools

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown archive_crud tool: {tool_name}"})
        return await handler(self, args)

# ── Handlers ──

_ARCHIVE_PAGE_SIZE = 500
_OUTLINE_MAX_LINES = 80
_OUTLINE_LINE_CHARS = 80
_MAX_PATCH_OPERATIONS = 20


def _table_guard(self: ArchiveCRUDSkill, table_name: str) -> str | None:
    """校验表名是否在 ``agent.memory.archive.allowed_tables`` 白名单内。

    返回 None 表示放行，否则返回给模型的错误文案。留空表示不限制。
    """
    allowed = tuple(self._allowed_tables or ())
    if not allowed or table_name in allowed:
        return None
    return _json(
        {
            "ok": False,
            "error": f"该档案表不允许访问: {table_name}",
            "allowed_tables": list(allowed),
        }
    )


def _delete_guard(self: ArchiveCRUDSkill) -> str | None:
    """``agent.memory.archive.allow_delete`` 开关（默认 false）。"""
    if self._allow_delete:
        return None
    return _json(
        {
            "ok": False,
            "error": "档案删除未启用（agent.memory.archive.allow_delete=false）",
        }
    )


def _overflow_payload_fields(outcome: Any) -> dict[str, Any]:
    """把服务的容量治理结果翻译成工具返回字段（供模型判断「已超限、正在压缩」）。"""
    return {
        "over_limit": True,
        "total_chars": int(getattr(outcome, "chars", 0) or 0),
        "max_total_chars": int(getattr(outcome, "max_total_chars", 0) or 0),
        "compressing": bool(getattr(outcome, "scheduled", False)),
        "hint": str(getattr(outcome, "hint", "") or ""),
    }


async def _write_archive_entry(
    self: ArchiveCRUDSkill,
    table_name: str,
    key: str,
    value: str,
    tags: Any,
) -> dict[str, Any]:
    """写入一条档案，并把「是否超过存储上限」如实回给模型。

    优先走 ArchiveMemoryService.set_with_outcome（可拿到 over_limit / hint /
    是否已调度压缩）；档案服务只实现 set 时（旧实现、测试替身）退化为老路径。
    overflow_action='reject' 时服务不落库，这里返回明确错误与压缩指引。
    """
    service = self._archive_service
    writer = getattr(service, "set_with_outcome", None)
    if not callable(writer):
        item = await service.set(table_name, key, value, tags)
        return {
            "ok": True,
            "table_name": item.table_name,
            "key": item.key,
            "version": item.version,
            "total_chars": len(value or ""),
        }
    outcome = await writer(table_name, key, value, tags)
    item = getattr(outcome, "item", None)
    if item is None:
        return {
            "ok": False,
            "error": str(getattr(outcome, "error", "") or "档案超过存储上限，已拒绝写入"),
            **_overflow_payload_fields(outcome),
        }
    payload: dict[str, Any] = {
        "ok": True,
        "table_name": item.table_name,
        "key": item.key,
        "version": item.version,
        "total_chars": len(value or ""),
    }
    if getattr(outcome, "over_limit", False):
        payload.update(_overflow_payload_fields(outcome))
    return payload


def _apply_patch_operations(value: str, operations: list[Any]) -> tuple[str, list[str]]:
    """按顺序应用增量编辑操作，返回 (新内容, 错误列表)。

    操作类型：
    - append：追加到末尾（空档案直接写入）
    - prepend：插入到开头
    - replace：把唯一出现的 old 片段替换为 new
    - delete：删除唯一出现的 old 片段
    """
    current = value
    errors: list[str] = []
    for index, raw_op in enumerate(operations, start=1):
        if not isinstance(raw_op, dict):
            errors.append(f"#{index} 操作必须是对象")
            continue
        op = str(raw_op.get("op") or "").strip().lower()
        if op in ("append", "prepend"):
            text = str(raw_op.get("text") or "").strip()
            if not text:
                errors.append(f"#{index} {op} 缺少 text")
                continue
            if not current.strip():
                current = text
            elif op == "append":
                current = f"{current.rstrip()}\n{text}"
            else:
                current = f"{text}\n{current.lstrip()}"
            continue
        if op in ("replace", "delete"):
            old = str(raw_op.get("old") or "")
            if not old:
                errors.append(f"#{index} {op} 缺少 old")
                continue
            occurrences = current.count(old)
            if occurrences == 0:
                errors.append(f"#{index} 未找到 old 片段")
                continue
            if occurrences > 1:
                errors.append(f"#{index} old 片段出现 {occurrences} 次，不唯一")
                continue
            replacement = "" if op == "delete" else str(raw_op.get("new") or "")
            current = current.replace(old, replacement, 1)
            continue
        errors.append(f"#{index} 未知操作 {op!r}")
    return current, errors


def _outline_payload(item: Any, value: str) -> dict[str, Any]:
    """构造大纲（目录）读取结果：只返回每行开头，供模型决定读哪一页。"""
    lines = value.splitlines()
    outline = [
        f"{number}: {line.strip()[:_OUTLINE_LINE_CHARS]}"
        for number, line in enumerate(lines[:_OUTLINE_MAX_LINES], start=1)
        if line.strip()
    ]
    return {
        "table_name": item.table_name,
        "key": item.key,
        "mode": "outline",
        "total_chars": len(value),
        "line_count": len(lines),
        "version": getattr(item, "version", None),
        "outline": outline,
        "truncated": len(lines) > _OUTLINE_MAX_LINES,
    }


def _read_item_payload(item: Any, *, offset: int | None = None) -> dict[str, Any]:
    """构造读取结果。offset 为 None 返回完整内容;否则按页返回(每页 500 字)。

    分页语义:
    - offset=0: 头部第一页
    - offset>0: 从头部向后翻页(1=第二页)
    - offset<0: 从尾部向前翻页(-1=最后一页/最新内容, -2=倒数第二页)
    行边界对齐,避免截断半行;越靠后的内容越新。
    """
    value = item.value or ""
    total_chars = len(value)
    payload: dict[str, Any] = {
        "table_name": item.table_name,
        "key": item.key,
        "total_chars": total_chars,
    }
    if offset is None:
        payload["value"] = value
        return payload

    if not value:
        payload.update(
            {
                "value": "",
                "offset": offset,
                "page_size": _ARCHIVE_PAGE_SIZE,
                "has_more_forward": False,
                "has_more_backward": False,
            }
        )
        return payload

    if offset >= 0:
        start = offset * _ARCHIVE_PAGE_SIZE
        if start >= total_chars:
            return {
                **payload,
                "value": "",
                "offset": offset,
                "page_size": _ARCHIVE_PAGE_SIZE,
                "has_more_forward": False,
                "has_more_backward": True,
            }
    else:
        start = max(0, total_chars + offset * _ARCHIVE_PAGE_SIZE)
    end = min(total_chars, start + _ARCHIVE_PAGE_SIZE)

    # 行边界对齐:start 对齐到行首,end 对齐到行尾(含换行符,仅当截断点在行中间时)
    if start > 0:
        newline = value.find("\n", start)
        if newline != -1 and newline < end:
            start = newline + 1
    if end < total_chars:
        newline = value.rfind("\n", start, end)
        if newline != -1 and newline >= start:
            end = newline + 1

    page = value[start:end]
    payload.update(
        {
            "value": page,
            "offset": offset,
            "page_size": _ARCHIVE_PAGE_SIZE,
            "has_more_forward": end < total_chars,
            "has_more_backward": start > 0,
        }
    )
    return payload

async def _handle_save_archive(self: ArchiveCRUDSkill, args: dict) -> str:
    if self._archive_service is None:
        return _json({"ok": False, "error": "archive_service 未配置"})
    table_name = str(args.get("table_name", "")).strip()
    key = str(args.get("key", "")).strip()
    value = str(args.get("value", "")).strip()
    if not table_name or not key or not value:
        return _json({"ok": False, "error": "缺少必要参数"})
    blocked = _table_guard(self, table_name)
    if blocked is not None:
        return blocked
    try:
        # 原始档案完整保存(不截断)。存储上限由 ArchiveMemoryService 统一收口：
        # 超过 agent.memory.archive.max_total_chars 时先落库、再异步触发压缩，
        # 返回体里带 over_limit/hint 让模型知道「已超限、正在压缩」；
        # overflow_action='reject' 时服务直接拒绝，这里回明确错误。
        # 渲染侧仍按 max_chars/group_profile_max_chars 截断展示，完整内容用 offset 分页读。
        return _json(await _write_archive_entry(self, table_name, key, value, args.get("tags")))
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_patch_archive(self: ArchiveCRUDSkill, args: dict) -> str:
    if self._archive_service is None:
        return _json({"ok": False, "error": "archive_service 未配置"})
    table_name = str(args.get("table_name", "")).strip()
    key = str(args.get("key", "")).strip()
    operations = args.get("operations")
    if not table_name or not key:
        return _json({"ok": False, "error": "缺少必要参数"})
    if not isinstance(operations, list) or not operations:
        return _json({"ok": False, "error": "operations 不能为空"})
    blocked = _table_guard(self, table_name)
    if blocked is not None:
        return blocked
    if len(operations) > _MAX_PATCH_OPERATIONS:
        return _json(
            {"ok": False, "error": f"单次最多 {_MAX_PATCH_OPERATIONS} 个操作"}
        )
    try:
        item = await self._archive_service.get(table_name, key)
        old_value = (item.value or "") if item is not None else ""
        new_value, errors = _apply_patch_operations(old_value, operations)
        if errors:
            return _json(
                {
                    "ok": False,
                    "error": "；".join(errors),
                    "hint": "所有操作要么一起生效要么一起失败；请修正后重试，或先用 read_archive 查看原文",
                }
            )
        if not new_value.strip():
            return _json({"ok": False, "error": "编辑后内容为空，已拒绝写入"})
        tags = args.get("tags")
        if tags is None:
            tags = list(getattr(item, "tags", None) or [])
        if item is not None and new_value == (item.value or ""):
            return _json(
                {
                    "ok": True,
                    "table_name": table_name,
                    "key": key,
                    "version": getattr(item, "version", None),
                    "total_chars": len(new_value),
                    "applied": len(operations),
                    "unchanged": True,
                }
            )
        payload = await _write_archive_entry(self, table_name, key, new_value, tags)
        if not payload.get("ok"):
            # 超过存储上限且配置为拒绝：不落库，把压缩指引回给模型。
            return _json(payload)
        payload["total_chars"] = len(new_value)
        payload["applied"] = len(operations)
        return _json(payload)
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_read_archive(self: ArchiveCRUDSkill, args: dict) -> str:
    if self._archive_service is None:
        return _json({"ok": False, "error": "archive_service 未配置"})
    try:
        mode = str(args.get("mode") or "full").strip().lower()
        if mode not in ("full", "outline"):
            return _json({"ok": False, "error": "mode 只支持 full 或 outline"})
        offset = args.get("offset")
        if offset is not None:
            try:
                offset = int(offset)
            except (TypeError, ValueError):
                return _json({"ok": False, "error": "offset 必须为整数"})
        if mode == "outline":
            offset = None

        def _payload(item: Any) -> dict[str, Any]:
            if mode == "outline":
                return _outline_payload(item, item.value or "")
            return _read_item_payload(item, offset=offset)

        items_raw = args.get("items")
        if items_raw:
            results = []
            for it in items_raw:
                if not isinstance(it, dict):
                    return _json({"ok": False, "error": "items 元素必须是对象"})
                # 逐项校验：items 批量模式与单条读取走同一套 allowed_tables 限制，
                # 否则只要顶层 table_name 合法（或干脆不填），就能借 items 里的任意
                # 表名读到任何档案。
                blocked = _table_guard(self, str(it.get("table_name", "")).strip())
                if blocked is not None:
                    return blocked
                if it.get("key") is None:
                    return _json({"ok": False, "error": "items 元素缺少 key"})
                item = await self._archive_service.get(it["table_name"], it["key"])
                if item:
                    results.append(_payload(item))
            return _json({"ok": True, "items": results})
        table_name = args.get("table_name")
        key = args.get("key")
        if table_name and key:
            blocked = _table_guard(self, str(table_name).strip())
            if blocked is not None:
                return blocked
            item = await self._archive_service.get(table_name, key)
            if item:
                return _json({"ok": True, "item": _payload(item)})
            return _json({"ok": False, "error": "条目不存在"})
        return _json({"ok": False, "error": "传入 table_name+key 或 items"})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_read_pending_messages(self: ArchiveCRUDSkill, args: dict) -> str:
    # 有意不套 allowed_tables 白名单：这里读的是自动总结用的内部计数表
    # （memory_counter），不是用户档案；限制它会让档案自动总结功能整体失效。
    if self._archive_service is None:
        return _json({"ok": False, "error": "archive_service 未配置"})
    conversation_key = str(args.get("conversation_key", "")).strip()
    if not conversation_key:
        return _json({"ok": False, "error": "缺少 conversation_key"})
    try:
        item = await self._archive_service.get(self._pending_table, conversation_key)
        if item is None or not item.value:
            return _json(
                {
                    "ok": True,
                    "conversation_key": conversation_key,
                    "count": 0,
                    "total": 0,
                    "messages": [],
                }
            )
        try:
            state = json.loads(item.value)
        except json.JSONDecodeError:
            return _json({"ok": False, "error": "待总结消息状态损坏"})
        raw_messages = state.get("messages") if isinstance(state, dict) else None
        if not isinstance(raw_messages, list):
            raw_messages = []

        indices_raw = args.get("indices")
        selected: list[tuple[int, Any]] = []
        if indices_raw is not None:
            if not isinstance(indices_raw, list):
                return _json({"ok": False, "error": "indices 必须为整数列表"})
            for raw_index in indices_raw:
                try:
                    index = int(raw_index)
                except (TypeError, ValueError):
                    return _json({"ok": False, "error": "indices 必须为整数列表"})
                if 1 <= index <= len(raw_messages):
                    selected.append((index, raw_messages[index - 1]))
        else:
            selected = list(enumerate(raw_messages, start=1))

        messages = []
        for index, raw in selected:
            entry = raw if isinstance(raw, dict) else {"text": str(raw)}
            messages.append(
                {
                    "index": index,
                    "sender_name": str(entry.get("sender_name") or ""),
                    "sender_id": str(entry.get("sender_id") or ""),
                    "text": str(entry.get("text") or ""),
                }
            )
        return _json(
            {
                "ok": True,
                "conversation_key": conversation_key,
                "count": len(messages),
                "total": len(raw_messages),
                "messages": messages,
            }
        )
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_list_archive(self: ArchiveCRUDSkill, args: dict) -> str:
    if self._archive_service is None:
        return _json({"ok": False, "error": "archive_service 未配置"})
    table_name = str(args.get("table_name", "")).strip()
    blocked = _table_guard(self, table_name)
    if blocked is not None:
        return blocked
    try:
        items = await self._archive_service.list(table_name, limit=args.get("limit", 10), offset=args.get("offset", 0))
        return _json({"ok": True, "items": [{"table_name": i.table_name, "key": i.key, "value": i.value} for i in items]})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_delete_archive(self: ArchiveCRUDSkill, args: dict) -> str:
    if self._archive_service is None:
        return _json({"ok": False, "error": "archive_service 未配置"})
    table_name = str(args.get("table_name", "")).strip()
    blocked = _delete_guard(self)
    if blocked is not None:
        return blocked
    blocked = _table_guard(self, table_name)
    if blocked is not None:
        return blocked
    try:
        await self._archive_service.delete(args["table_name"], args["key"])
        return _json({"ok": True})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

_HANDLERS = {
    "save_archive": _handle_save_archive,
    "patch_archive": _handle_patch_archive,
    "read_archive": _handle_read_archive,
    "read_pending_messages": _handle_read_pending_messages,
    "list_archive": _handle_list_archive,
    "delete_archive": _handle_delete_archive,
}
