"""FileStorageSkill — 沙箱持久化文件存储管理 Skill。

管理 sandbox/ 下的 文件存储.md（文件索引）和 TODO.md（待实现工具清单），
以及持久化子目录（tools/、docs/、assets/、gift/）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neobot_app.skills.base import SkillModule

_STORAGE_DOC = "文件存储.md"
_TODO_DOC = "TODO.md"
_PERSISTENT_DIRS = ["tools", "docs", "assets", "gift"]


def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


class FileStorageSkill(SkillModule):
    """文件存储管理 Skill — 读写 文件存储.md 和 TODO.md，管理持久化目录。"""

    @property
    def name(self) -> str:
        return "file_storage"

    @property
    def description(self) -> str:
        return "文件存储管理：读写文件索引文档和 TODO 清单，浏览持久化目录"

    @property
    def instructions(self) -> str:
        return (
            "文件存储管理 Skill 用于管理沙箱持久化文件系统（非 temp 临时目录）。\n\n"
            "## 持久化目录结构\n"
            "  tools/   — 可复用工具脚本（Python/shell 等）\n"
            "  docs/    — 参考文档、使用说明、备忘\n"
            "  assets/  — 静态资源（模板、字体、图片等）\n"
            "  gift/    — 礼物准备目录（由 gift skill 管理）\n\n"
            "## 核心规则\n"
            "1. 在非 temp 目录进行任何文件操作前，**必须先调用 read_storage_doc** 了解当前文件布局\n"
            "2. 每次修改非 temp 目录文件后，**必须调用 update_storage_doc** 更新文件索引\n"
            "3. 文件存储.md 应保持精简：每个文件只写一行，工具类写明用法和用途，"
            "文档类写明大概内容\n"
            "4. 需要但暂未实现的复杂脚本/工具，写入 TODO.md（通过 update_todo）\n\n"
            "## 工具列表\n"
            "  read_storage_doc — 读取 文件存储.md 全文\n"
            "  update_storage_doc — 更新 文件存储.md 中的文件条目\n"
            "  read_todo — 读取 TODO.md 全文\n"
            "  update_todo — 添加/更新/完成 TODO 条目\n"
            "  list_storage_dirs — 列出持久化目录结构概览"
        )

    def __init__(self, sandbox_service: Any = None) -> None:
        self._sandbox = sandbox_service

    def reset(self) -> None:
        pass

    def _root_path(self, relative: str = "") -> Path:
        if self._sandbox is not None:
            return self._sandbox.resolve_path(relative)
        return Path(relative)

    def _ensure_dirs_and_docs(self) -> None:
        """确保持久化子目录和索引文档存在。"""
        if self._sandbox is None:
            return
        import asyncio

        async def _init():
            for d in _PERSISTENT_DIRS:
                dir_path = self._root_path(d)
                if not dir_path.exists():
                    dir_path.mkdir(parents=True, exist_ok=True)
            for doc_name in [_STORAGE_DOC, _TODO_DOC]:
                doc_path = self._root_path(doc_name)
                if not doc_path.exists():
                    await self._sandbox.write_file(doc_path, self._default_content(doc_name).encode("utf-8"))

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import asyncio
                asyncio.ensure_future(_init())
            else:
                loop.run_until_complete(_init())
        except Exception:
            pass

    @staticmethod
    def _default_content(doc_name: str) -> str:
        if doc_name == _STORAGE_DOC:
            return (
                "# 沙箱文件存储\n\n"
                "## tools/\n"
                "（暂无工具脚本）\n\n"
                "## docs/\n"
                "（暂无文档）\n\n"
                "## assets/\n"
                "（暂无资源）\n\n"
                "## gift/\n"
                "（由 gift skill 管理，勿手动编辑）\n"
            )
        else:
            return (
                "# 待实现工具\n\n"
                "## Pending\n"
                "（暂无待实现项）\n\n"
                "## Done\n"
                "（暂无已完成项）\n"
            )

    def get_tools(self) -> list[dict]:
        return [
            self._tool_def(
                "read_storage_doc",
                "读取 文件存储.md（沙箱持久化文件索引文档）全文。在进行非 temp 目录文件操作前必须先调用。",
                {"properties": {}, "required": []},
            ),
            self._tool_def(
                "update_storage_doc",
                "更新 文件存储.md 中的文件条目。每次在 tools/docs/assets 目录下新增/修改/删除文件后必须调用。"
                "传入 section（目录名如 tools/docs/assets）和 entry（单行描述：文件名 + 用途/内容）。"
                "action 可选 add（新增）、remove（删除）、update（修改）；默认 add。",
                {
                    "properties": {
                        "section": {"type": "string", "description": "目录名：tools、docs、assets"},
                        "entry": {"type": "string", "description": "单行条目，如 '- `script.py` — 用途说明'"},
                        "action": {
                            "type": "string",
                            "enum": ["add", "remove", "update"],
                            "description": "操作类型：add（新增）、remove（删除）、update（替换匹配行）；默认 add",
                        },
                    },
                    "required": ["section", "entry"],
                },
            ),
            self._tool_def(
                "read_todo",
                "读取 TODO.md 全文，查看待实现和已完成的工具清单。",
                {"properties": {}, "required": []},
            ),
            self._tool_def(
                "update_todo",
                "更新 TODO.md。添加新的待实现项或将已有项标记为完成。"
                "entry 格式：'- [ ] tool_name.py — 用途说明'（pending）或 '- [x] tool_name.py — 用途说明'（done）。"
                "action: add（新增到 Pending）、complete（将 Pending 中的项移到 Done）。",
                {
                    "properties": {
                        "entry": {"type": "string", "description": "TODO 条目，如 '- [ ] batch_resize.py — 批量图片缩放'"},
                        "action": {
                            "type": "string",
                            "enum": ["add", "complete"],
                            "description": "add=新增到 Pending；complete=标记为完成移到 Done",
                        },
                    },
                    "required": ["entry", "action"],
                },
            ),
            self._tool_def(
                "list_storage_dirs",
                "列出持久化目录结构概览，展示 tools/docs/assets/gift 下的文件树。",
                {"properties": {}, "required": []},
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown file_storage tool: {tool_name}"})
        return await handler(self, args)

    @staticmethod
    def _tool_def(name: str, desc: str, params: dict | None = None) -> dict:
        p = {"type": "object", "properties": {}, "required": []}
        if params:
            p["properties"] = params.get("properties", {})
            p["required"] = params.get("required", [])
        return {"type": "function", "function": {"name": name, "description": desc, "parameters": p}}


# ── Handlers ──

async def _handle_read_storage_doc(self: FileStorageSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    try:
        path = self._root_path(_STORAGE_DOC)
        if not path.exists():
            return _json({"ok": True, "content": FileStorageSkill._default_content(_STORAGE_DOC)})
        data = await self._sandbox.read_file(path)
        return _json({"ok": True, "content": data.decode("utf-8")})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_update_storage_doc(self: FileStorageSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    section = str(args.get("section", "")).strip()
    entry = str(args.get("entry", "")).strip()
    action = str(args.get("action", "add")).strip()
    if section not in ("tools", "docs", "assets"):
        return _json({"ok": False, "error": f"section 必须是 tools/docs/assets，收到: {section}"})
    if not entry:
        return _json({"ok": False, "error": "entry 不能为空"})
    try:
        path = self._root_path(_STORAGE_DOC)
        if not path.exists():
            content = FileStorageSkill._default_content(_STORAGE_DOC)
        else:
            data = await self._sandbox.read_file(path)
            content = data.decode("utf-8")
        content = _apply_storage_update(content, section, entry, action)
        await self._sandbox.write_file(path, content.encode("utf-8"))
        return _json({"ok": True, "section": section, "action": action})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_read_todo(self: FileStorageSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    try:
        path = self._root_path(_TODO_DOC)
        if not path.exists():
            return _json({"ok": True, "content": FileStorageSkill._default_content(_TODO_DOC)})
        data = await self._sandbox.read_file(path)
        return _json({"ok": True, "content": data.decode("utf-8")})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_update_todo(self: FileStorageSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    entry = str(args.get("entry", "")).strip()
    action = str(args.get("action", "add")).strip()
    if not entry:
        return _json({"ok": False, "error": "entry 不能为空"})
    try:
        path = self._root_path(_TODO_DOC)
        if not path.exists():
            content = FileStorageSkill._default_content(_TODO_DOC)
        else:
            data = await self._sandbox.read_file(path)
            content = data.decode("utf-8")
        content = _apply_todo_update(content, entry, action)
        await self._sandbox.write_file(path, content.encode("utf-8"))
        return _json({"ok": True, "action": action})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


async def _handle_list_storage_dirs(self: FileStorageSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    try:
        result: dict[str, Any] = {}
        for d in _PERSISTENT_DIRS:
            dir_path = self._root_path(d)
            if dir_path.is_dir():
                items = []
                for child in sorted(dir_path.iterdir()):
                    items.append({
                        "name": child.name,
                        "is_dir": child.is_dir(),
                        "size": child.stat().st_size if child.is_file() else 0,
                    })
                result[d] = items
            else:
                result[d] = []
        return _json({"ok": True, "dirs": result})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})


def _apply_storage_update(content: str, section: str, entry: str, action: str) -> str:
    """更新 文件存储.md 中指定 section 的条目。"""
    section_header = f"## {section}/"
    lines = content.split("\n")
    new_lines = []
    in_section = False
    applied = False

    for line in lines:
        if line.strip().startswith(section_header):
            in_section = True
            new_lines.append(line)
            continue
        if in_section and line.strip().startswith("## "):
            # 离开当前 section 前，如果是 add 操作，在 section 末尾追加
            if not applied and action == "add":
                new_lines.append(entry)
                applied = True
            in_section = False
            new_lines.append(line)
            continue
        if in_section:
            if action == "add" and not applied:
                if line.strip() == "（暂无" or line.strip().startswith("（暂无"):
                    new_lines.append(entry)
                    applied = True
                    continue
            elif action == "remove" and entry in line:
                continue  # 跳过要删除的行
            elif action == "update":
                # 尝试匹配现有文件名的行进行替换
                entry_name = _extract_filename(entry)
                if entry_name and entry_name in line:
                    new_lines.append(entry)
                    applied = True
                    continue
        new_lines.append(line)

    if not applied and action == "add":
        # 如果 section 是最后一个，直接在末尾追加
        new_lines.append(entry)

    return "\n".join(new_lines)


def _apply_todo_update(content: str, entry: str, action: str) -> str:
    """更新 TODO.md。"""
    lines = content.split("\n")
    new_lines = []
    in_pending = False
    in_done = False
    applied = False

    for line in lines:
        if line.strip().startswith("## Pending"):
            in_pending = True
            in_done = False
            new_lines.append(line)
            if action == "add":
                new_lines.append(entry)
                applied = True
            continue
        if line.strip().startswith("## Done"):
            if action == "complete" and not applied:
                new_lines.append(entry.replace("[ ]", "[x]"))
                applied = True
            in_pending = False
            in_done = True
            new_lines.append(line)
            continue
        if in_pending and action == "complete":
            entry_name = _extract_filename(entry)
            if entry_name and entry_name in line:
                continue  # 从 Pending 移除
        new_lines.append(line)

    if not applied and action == "add":
        new_lines.append(entry)

    return "\n".join(new_lines)


def _extract_filename(entry: str) -> str:
    """从条目中提取文件名，如 '- `script.py` — ...' -> 'script.py'。"""
    import re
    m = re.search(r"`([^`]+)`", entry)
    return m.group(1) if m else ""


_HANDLERS = {
    "read_storage_doc": _handle_read_storage_doc,
    "update_storage_doc": _handle_update_storage_doc,
    "read_todo": _handle_read_todo,
    "update_todo": _handle_update_todo,
    "list_storage_dirs": _handle_list_storage_dirs,
}
