"""SandboxManagerSkill — 沙箱文件操作 Skill（读写/编辑/搜索/删除/列表/移动/复制/发送）。"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from neobot_app.skills.base import SkillModule

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

class SandboxManagerSkill(SkillModule):
    """沙箱文件操作 Skill — 沙箱内文件读写/编辑/搜索/删列移拷贝及发送到聊天。"""

    @property
    def name(self) -> str:
        return "sandbox_manager"

    @property
    def description(self) -> str:
        return "沙箱文件管理：读取/写入/编辑/搜索/删除/列表/移动/复制文件，发送文件到聊天"

    @property
    def instructions(self) -> str:
        return (
            "沙箱文件管理 Skill。你可以直接操作沙箱内的文件。\n\n"
            "=== 能力边界 ===\n"
            "你可以自己做（简单、无需代码执行）：\n"
            "  - 写入/编辑纯文本文件（.txt .md .json .yaml .py .html .css .js .csv 等）\n"
            "  - 读取/搜索/列出/移动/复制/删除沙箱中的文件\n"
            "  - 从 URL 下载文件到沙箱\n"
            "  - 将沙箱文件发送到聊天\n\n"
            "你必须委托子 agent 的场景（需要运行代码）：\n"
            "  - 生成 PDF / 图片 / Word / Excel / PPT / 图表\n"
            "  - 数据处理、格式转换\n"
            "  - 任何需要运行 Python/Shell 的操作\n"
            "  委托方式：background_trigger__submit_problem\n\n"
            "=== 委托流程 ===\n"
            "用户要生成文件 → submit_problem(question=\"生成xxx...\")\n"
            "              → 告知用户稍候，结束本轮回复\n"
            "              → 收到后台通知（含文件路径）\n"
            "              → send_chat_file(path) 发送给用户\n\n"
            "=== 工具列表 ===\n"
            "  read_file(path, chat_flow_id)  — 读取文件（返回文本或 base64）\n"
            "  write_file(path, content, chat_flow_id) — 写入文本内容到文件\n"
            "  write_file_base64(path, content_base64, chat_flow_id) — 写入 base64 数据\n"
            "  edit_file(path, old_string, new_string, chat_flow_id) — 原地替换文本片段\n"
            "  glob_files(pattern, path, chat_flow_id) — 按 glob 模式搜索文件名\n"
            "  grep_files(pattern, path, glob, chat_flow_id) — 按正则搜索文件内容\n"
            "  list_files(path, pattern, chat_flow_id) — 列出目录\n"
            "  delete_file(path, chat_flow_id) / move_file / copy_file\n"
            "  download_file(url, save_name, chat_flow_id) — 从 URL 下载\n"
            "  send_file(path, chat_flow_id) / send_chat_file(path, chat_flow_id) — 发送到聊天\n"
            "  hold_temp(chat_flow_id, minutes) — 保活临时目录\n\n"
            "## 下载任务（重要）\n"
            "download_file 为会话工具(session模式)：\n"
            "  - 调用后立即返回 session_submitted，实际下载在后台进行\n"
            "  - timeout_seconds 默认为 300 秒（5分钟），agent 可按需设置，最长 1800 秒（30分钟）\n"
            "  - 收到返回后请立即结束本轮回复，不要继续调用其他工具或使用 wait\n"
            "  - 系统会在下载完成后通过通知自动唤醒你，届时携带文件路径\n\n"
            "## chat_flow_id\n"
            "取 pipeline_key 的值（格式 group:12345 或 private:12345）。\n\n"
            "## 临时目录 vs 沙箱根（重要）\n"
            "路径选择规则：除非文件是长期复用的工具/文档/资源，否则一律写入临时目录。\n"
            "write_file / write_file_base64 写入的文件位于临时目录（sandbox/temp/{chat_flow_id}/）。\n"
            "read_file / edit_file / glob_files / grep_files / list_files 操作临时文件时，\n"
            "必须显式传入 chat_flow_id（取 pipeline_key 的值），否则默认在沙箱根目录查找。\n"
            "注意：读工具不会自动使用 pipeline_key 作为 chat_flow_id，你必须显式传递。\n"
            "沙箱根目录仅用于访问持久化文件（tools/、docs/、assets/、gift/、emoji/ 等长期复用的资源）。\n\n"
            "## 持久化文件操作（tools/docs/assets 目录）\n"
            "  操作前先调用 file_storage__read_storage_doc 查看索引\n"
            "  修改后调用 file_storage__update_storage_doc 更新索引"
        )

    @property
    def session_tools(self) -> set[str]:
        return {"download_file"}

    def __init__(
        self,
        sandbox_service: Any = None,
        sandbox_lock: Any = None,
        adapter: Any = None,
        file_server: Any = None,
        hold_max_minutes: int = 120,
    ) -> None:
        self._sandbox = sandbox_service
        self._lock = sandbox_lock
        self._adapter = adapter
        self._file_server = file_server
        self._hold_max_minutes = hold_max_minutes

    def reset(self) -> None:
        pass

    def _resolve_send_path(self, path_str: str, chat_flow_id: str | None = None) -> Path:
        p = Path(path_str)
        if p.is_absolute() and p.exists():
            return p
        if self._sandbox is not None:
            try:
                resolved = self._sandbox.resolve_path(path_str, chat_flow_id)
                if resolved.exists():
                    return resolved
            except Exception:
                pass
        return p

    def _resolve_write_path(self, rel_path: str, chat_flow_id: str) -> Path:
        if self._sandbox is not None:
            return self._sandbox.resolve_path(rel_path, chat_flow_id)
        return Path(rel_path)

    def _get_chat_flow_id(self, args: dict) -> str:
        cid = str(args.get("chat_flow_id", "")).strip()
        if not cid:
            cid = str(args.get("pipeline_key", "")).strip()
        return cid

    def get_tools(self) -> list[dict]:
        return [
            # ── 读取 ──
            self._tool_def(
                "read_file",
                "读取沙箱内文件的内容。文本文件返回文本，二进制文件返回 base64。"
                "操作临时文件时必须传入 chat_flow_id。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（临时文件相对于临时目录，持久化文件相对于沙箱根）"},
                        "chat_flow_id": {"type": "string", "description": "读取临时文件时必传，取 pipeline_key 的值"},
                    },
                    "required": ["path"],
                },
            ),
            # ── 写入（文本直写，CC 风格） ──
            self._tool_def(
                "write_file",
                "写入文本内容到沙箱文件。直接传入字符串内容即可，不需要自己编码。"
                "适用于：保存 .txt .md .json .yaml .py .html .css .js .csv 等纯文本文件。"
                "注意：不能用于生成 PDF/图片/二进制文件——生成这些必须用 background_trigger__submit_problem。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（相对于临时目录）"},
                        "content": {"type": "string", "description": "要写入的文本内容，直接传入字符串即可"},
                        "chat_flow_id": {"type": "string", "description": "聊天流 ID，取 pipeline_key 的值"},
                    },
                    "required": ["path", "content", "chat_flow_id"],
                },
            ),
            # ── 写入（base64，二进制） ──
            self._tool_def(
                "write_file_base64",
                "写入 base64 编码的数据到沙箱文件。仅当你已有 base64 数据时使用"
                "（如从 read_file 读取的二进制文件、download_file 下载后想另存）。"
                "不能用于创建新内容——你没有生成 base64 的能力。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（相对于临时目录）"},
                        "content_base64": {"type": "string", "description": "文件内容的 base64 编码"},
                        "chat_flow_id": {"type": "string", "description": "聊天流 ID，取 pipeline_key 的值"},
                    },
                    "required": ["path", "content_base64", "chat_flow_id"],
                },
            ),
            # ── 编辑（CC 风格 Edit） ──
            self._tool_def(
                "edit_file",
                "原地编辑沙箱内文本文件：查找 old_string 替换为 new_string。"
                "old_string 必须在文件中唯一（除非设置 replace_all=true）。"
                "这是修改文件的首选方式——不需要先读取再写入。"
                "编辑临时文件时必须传入 chat_flow_id。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（临时文件相对于临时目录，持久化文件相对于沙箱根）"},
                        "old_string": {"type": "string", "description": "要被替换的文本片段"},
                        "new_string": {"type": "string", "description": "替换后的文本片段"},
                        "replace_all": {
                            "type": "boolean",
                            "description": "是否替换所有匹配项。默认 false（要求 old_string 唯一）",
                        },
                        "chat_flow_id": {"type": "string", "description": "编辑临时文件时必传，取 pipeline_key 的值"},
                    },
                    "required": ["path", "old_string", "new_string"],
                },
            ),
            # ── 搜索（CC 风格 Glob） ──
            self._tool_def(
                "glob_files",
                "按 glob 模式搜索沙箱中的文件路径。支持 ** 递归匹配。"
                "示例：glob_files(pattern='**/*.py') 查找所有 Python 文件。"
                "搜索临时文件时必须传入 chat_flow_id。",
                {
                    "properties": {
                        "pattern": {"type": "string", "description": "glob 模式，如 **/*.py、*.txt、tools/**"},
                        "path": {"type": "string", "description": "搜索起始目录（临时文件相对于临时目录，持久化文件相对于沙箱根），默认根目录"},
                        "chat_flow_id": {"type": "string", "description": "搜索临时文件时必传，取 pipeline_key 的值"},
                    },
                    "required": ["pattern"],
                },
            ),
            # ── 搜索（CC 风格 Grep） ──
            self._tool_def(
                "grep_files",
                "在沙箱文件中按正则表达式搜索内容。可指定文件过滤和输出模式。"
                "output_mode: content（显示匹配行）、files_with_matches（仅文件路径）、count（匹配计数）。"
                "搜索临时文件时必须传入 chat_flow_id。",
                {
                    "properties": {
                        "pattern": {"type": "string", "description": "正则表达式，如 'def write_file'"},
                        "path": {"type": "string", "description": "搜索目录（临时文件相对于临时目录，持久化文件相对于沙箱根），默认根目录"},
                        "glob": {"type": "string", "description": "文件过滤，如 *.py、**/*.md"},
                        "output_mode": {
                            "type": "string",
                            "enum": ["content", "files_with_matches", "count"],
                            "description": "输出模式，默认 files_with_matches",
                        },
                        "-i": {"type": "boolean", "description": "大小写不敏感搜索"},
                        "head_limit": {"type": "integer", "description": "最多返回条数，默认 50"},
                        "chat_flow_id": {"type": "string", "description": "搜索临时文件时必传，取 pipeline_key 的值"},
                    },
                    "required": ["pattern"],
                },
            ),
            # ── 其他 ──
            self._tool_def(
                "delete_file",
                "删除沙箱内的文件或空目录。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（临时文件相对于临时目录，持久化文件相对于沙箱根）"},
                        "chat_flow_id": {"type": "string", "description": "删除临时文件时必传，取 pipeline_key 的值"},
                    },
                    "required": ["path"],
                },
            ),
            self._tool_def(
                "list_files",
                "列出沙箱目录下的内容。列出临时文件时必须传入 chat_flow_id。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "目录路径（临时文件相对于临时目录，持久化文件相对于沙箱根），默认为 /"},
                        "pattern": {"type": "string", "description": "可选，glob 模式过滤如 *.txt"},
                        "chat_flow_id": {"type": "string", "description": "列出临时文件时必传，取 pipeline_key 的值"},
                    },
                    "required": [],
                },
            ),
            self._tool_def(
                "move_file",
                "移动或重命名沙箱内的文件/目录。",
                {
                    "properties": {
                        "source": {"type": "string", "description": "源路径（临时文件相对于临时目录，持久化文件相对于沙箱根）"},
                        "destination": {"type": "string", "description": "目标路径（临时文件相对于临时目录，持久化文件相对于沙箱根）"},
                        "chat_flow_id": {"type": "string", "description": "操作临时文件时必传，取 pipeline_key 的值"},
                    },
                    "required": ["source", "destination"],
                },
            ),
            self._tool_def(
                "copy_file",
                "复制沙箱内的文件。",
                {
                    "properties": {
                        "source": {"type": "string", "description": "源路径（临时文件相对于临时目录，持久化文件相对于沙箱根）"},
                        "destination": {"type": "string", "description": "目标路径（临时文件相对于临时目录，持久化文件相对于沙箱根）"},
                        "chat_flow_id": {"type": "string", "description": "操作临时文件时必传，取 pipeline_key 的值"},
                    },
                    "required": ["source", "destination"],
                },
            ),
            self._tool_def(
                "send_file",
                "将沙箱内的图片发送到聊天（以图片消息）。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（临时文件相对于临时目录，持久化文件相对于沙箱根）"},
                        "group_id": {"type": "string", "description": "可选，目标群号"},
                        "user_id": {"type": "string", "description": "可选，目标QQ号"},
                        "chat_flow_id": {"type": "string", "description": "发送临时文件时必传，取 pipeline_key 的值"},
                    },
                    "required": ["path"],
                },
            ),
            self._tool_def(
                "send_chat_file",
                "将沙箱内的任意文件（PDF/文档/代码等）发送到聊天（以文件附件形式）。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（临时文件相对于临时目录，持久化文件相对于沙箱根）"},
                        "group_id": {"type": "string", "description": "目标群号"},
                        "user_id": {"type": "string", "description": "目标QQ号"},
                        "chat_flow_id": {"type": "string", "description": "发送临时文件时必传，取 pipeline_key 的值"},
                    },
                    "required": ["path"],
                },
            ),
            self._tool_def(
                "hold_temp",
                "保活当前聊天流的临时文件目录，防止被自动清理。最长保活2小时。",
                {
                    "properties": {
                        "chat_flow_id": {"type": "string", "description": "聊天流 ID"},
                        "minutes": {"type": "integer", "description": "保活分钟数，默认120", "default": 120},
                    },
                    "required": ["chat_flow_id"],
                },
            ),
            self._tool_def(
                "download_file",
                "【会话工具】从 URL 下载文件到沙箱。支持下载聊天中的文件、网络图片等。"
                "下载后文件保存到沙箱临时目录，供后续读取或发送。"
                "调用后立即返回 session_submitted，不要等待——系统会在下载完成后通知你。",
                {
                    "properties": {
                        "url": {"type": "string", "description": "文件的下载 URL"},
                        "save_name": {"type": "string", "description": "保存的文件名，如 image.png、document.pdf"},
                        "chat_flow_id": {"type": "string", "description": "聊天流 ID，取 pipeline_key 的值"},
                        "timeout_seconds": {
                            "type": "integer",
                            "description": "可选，下载超时秒数，默认 300（5分钟），最大 1800（30分钟）",
                            "default": 300,
                        },
                    },
                    "required": ["url", "save_name", "chat_flow_id"],
                },
            ),
        ]

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown sandbox_manager tool: {tool_name}"})
        return await handler(self, args)

# ── Handlers ──

async def _handle_read_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip().lstrip("/")
    if not rel_path:
        return _json({"ok": False, "error": "缺少 path"})
    try:
        chat_flow_id = (args.get("chat_flow_id") or "").strip() or None
        path = self._sandbox.resolve_path(rel_path, chat_flow_id)
        data = await self._sandbox.read_file(path)
        try:
            text = data.decode("utf-8")
            return _json({"ok": True, "content": text, "size": len(data)})
        except UnicodeDecodeError:
            return _json({"ok": True, "content_base64": base64.b64encode(data).decode(), "size": len(data)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_write_file(self: SandboxManagerSkill, args: dict) -> str:
    """CC 风格：直接写文本内容。"""
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip()
    content = str(args.get("content", ""))
    chat_flow_id = self._get_chat_flow_id(args)
    if not rel_path or not chat_flow_id:
        return _json({"ok": False, "error": "缺少必要参数 path/chat_flow_id"})
    if not content:
        return _json({"ok": False, "error": "content 不能为空"})
    try:
        data = content.encode("utf-8")
        path = self._sandbox.resolve_path(rel_path, chat_flow_id)
        await self._sandbox.write_file(path, data)
        return _json({"ok": True, "path": str(path), "size": len(data)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_write_file_base64(self: SandboxManagerSkill, args: dict) -> str:
    """二进制内容通过 base64 写入。"""
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip()
    content_b64 = str(args.get("content_base64", "")).strip()
    chat_flow_id = self._get_chat_flow_id(args)
    if not rel_path or not content_b64 or not chat_flow_id:
        return _json({"ok": False, "error": "缺少必要参数 path/content_base64/chat_flow_id"})
    try:
        data = base64.b64decode(content_b64)
        path = self._sandbox.resolve_path(rel_path, chat_flow_id)
        await self._sandbox.write_file(path, data)
        return _json({"ok": True, "path": str(path), "size": len(data)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_edit_file(self: SandboxManagerSkill, args: dict) -> str:
    """CC 风格 Edit：读取→替换→写回。"""
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip().lstrip("/")
    old_string = str(args.get("old_string", ""))
    new_string = str(args.get("new_string", ""))
    replace_all = bool(args.get("replace_all", False))
    if not rel_path:
        return _json({"ok": False, "error": "缺少 path"})
    if not old_string:
        return _json({"ok": False, "error": "old_string 不能为空"})
    try:
        chat_flow_id = (args.get("chat_flow_id") or "").strip() or None
        path = self._sandbox.resolve_path(rel_path, chat_flow_id)
        data = await self._sandbox.read_file(path)
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _json({"ok": False, "error": "文件不是文本格式，无法编辑"})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

    count = text.count(old_string)
    if count == 0:
        return _json({"ok": False, "error": f"未找到匹配的 old_string: {old_string[:80]}..."})
    if count > 1 and not replace_all:
        return _json({"ok": False, "error": f"old_string 出现了 {count} 次，不唯一。设置 replace_all=true 替换全部或用更精确的字符串"})
    new_text = text.replace(old_string, new_string) if replace_all else text.replace(old_string, new_string, 1)
    try:
        await self._sandbox.write_file(path, new_text.encode("utf-8"))
        return _json({"ok": True, "path": str(path), "replacements": count})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_glob_files(self: SandboxManagerSkill, args: dict) -> str:
    """CC 风格 Glob：按模式匹配文件路径。"""
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    pattern = str(args.get("pattern", "")).strip()
    base_path = str(args.get("path", "")).strip().lstrip("/") or "."
    if not pattern:
        return _json({"ok": False, "error": "缺少 pattern"})
    try:
        chat_flow_id = (args.get("chat_flow_id") or "").strip() or None
        base = self._sandbox.resolve_path(base_path, chat_flow_id)
        full_pattern = str(base / pattern)
        import glob as glob_module
        matches = []
        for p in glob_module.iglob(full_pattern, recursive=True):
            fp = Path(p)
            if not self._sandbox.is_path_allowed(fp):
                continue
            stat = fp.stat()
            matches.append({
                "path": str(fp.relative_to(base)),
                "size": stat.st_size,
                "is_dir": fp.is_dir(),
            })
        # 排序，限制数量
        matches.sort(key=lambda m: m["path"])
        result = matches[:200]
        return _json({"ok": True, "matches": result, "count": len(matches)})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_grep_files(self: SandboxManagerSkill, args: dict) -> str:
    """CC 风格 Grep：正则搜索文件内容。"""
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    pattern = str(args.get("pattern", ""))
    base_path = str(args.get("path", "")).strip().lstrip("/") or "."
    glob_filter = args.get("glob")
    output_mode = str(args.get("output_mode", "files_with_matches")).strip()
    case_insensitive = bool(args.get("-i", False))
    head_limit = int(args.get("head_limit", 50))
    if not pattern:
        return _json({"ok": False, "error": "缺少 pattern"})

    flags = re.IGNORECASE if case_insensitive else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return _json({"ok": False, "error": f"正则表达式无效: {e}"})

    try:
        chat_flow_id = (args.get("chat_flow_id") or "").strip() or None
        base = self._sandbox.resolve_path(base_path, chat_flow_id)
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

    import glob as glob_module
    if glob_filter:
        search = str(base / glob_filter)
        candidates = [Path(p) for p in glob_module.iglob(search, recursive=True)]
    else:
        candidates = list(base.rglob("*"))

    results: list[dict] = []
    files_searched = 0

    for fp in candidates:
        if not fp.is_file():
            continue
        if not self._sandbox.is_path_allowed(fp):
            continue
        # 跳过二进制文件
        try:
            text = fp.read_text("utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        files_searched += 1
        lines = text.split("\n")
        file_matches = []
        for li, line in enumerate(lines, 1):
            if regex.search(line):
                file_matches.append({"line": li, "text": line[:500]})
                if output_mode == "content" and len(file_matches) >= 20:
                    break

        if file_matches:
            rel = str(fp.relative_to(base))
            if output_mode == "content":
                for m in file_matches:
                    results.append({"file": rel, "line": m["line"], "text": m["text"]})
            elif output_mode == "files_with_matches":
                results.append({"file": rel, "match_count": len(file_matches)})
            elif output_mode == "count":
                results.append({"file": rel, "count": len(file_matches)})

        if len(results) >= head_limit:
            break

    return _json({
        "ok": True,
        "results": results[:head_limit],
        "total_matches": len(results),
        "files_searched": files_searched,
    })

async def _handle_delete_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    if not rel_path:
        return _json({"ok": False, "error": "缺少 path"})
    try:
        path = self._sandbox.resolve_path(rel_path, chat_flow_id or None)
        await self._sandbox.delete_file(path)
        return _json({"ok": True})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_list_files(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip().lstrip("/") or "."
    pattern = args.get("pattern")
    try:
        chat_flow_id = (args.get("chat_flow_id") or "").strip() or None
        path = self._sandbox.resolve_path(rel_path, chat_flow_id)
        files = await self._sandbox.list_files(path, pattern)
        return _json({"ok": True, "files": files})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_move_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    src = str(args.get("source", "")).strip()
    dst = str(args.get("destination", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    if not src or not dst:
        return _json({"ok": False, "error": "缺少 source 或 destination"})
    try:
        src_path = self._sandbox.resolve_path(src, chat_flow_id or None)
        dst_path = self._sandbox.resolve_path(dst, chat_flow_id or None)
        await self._sandbox.move_file(src_path, dst_path)
        return _json({"ok": True})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_copy_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    src = str(args.get("source", "")).strip()
    dst = str(args.get("destination", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    if not src or not dst:
        return _json({"ok": False, "error": "缺少 source 或 destination"})
    try:
        src_path = self._sandbox.resolve_path(src, chat_flow_id or None)
        dst_path = self._sandbox.resolve_path(dst, chat_flow_id or None)
        await self._sandbox.copy_file(src_path, dst_path)
        return _json({"ok": True})
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_send_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    if self._file_server is None:
        return _json({"ok": False, "error": "file_server 未配置"})
    file_path = str(args.get("path", "")).strip()
    group_id = str(args.get("group_id", "")).strip()
    user_id = str(args.get("user_id", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip() or None
    if not file_path:
        return _json({"ok": False, "error": "缺少 path"})
    path = self._resolve_send_path(file_path, chat_flow_id)
    if not path.exists():
        return _json({"ok": False, "error": f"文件不存在: {file_path}"})
    if not group_id and not user_id:
        return _json({"ok": False, "error": "缺少 group_id 或 user_id"})
    try:
        from neobot_app.utils.media_sender import prepare_image_segment
        from neobot_contracts.models import ConversationRef

        if group_id:
            conv_ref = ConversationRef(kind="group", id=group_id)
        else:
            conv_ref = ConversationRef(kind="private", id=user_id)

        segment = prepare_image_segment(self._file_server, path)
        resp = await self._adapter.send(conv_ref, [segment])

        if resp is None:
            return _json({"ok": False, "error": "发送超时，无响应"})
        if hasattr(resp, "status") and hasattr(resp, "retcode"):
            if resp.status == "failed" or (resp.retcode is not None and resp.retcode != 0):
                msg = resp.message or resp.wording or str(resp.retcode)
                return _json({"ok": False, "error": f"发送失败(retcode={resp.retcode}): {msg}"})
        elif isinstance(resp, dict):
            r_status = resp.get("status")
            r_retcode = resp.get("retcode")
            if r_status == "failed" or (r_retcode is not None and r_retcode != 0):
                msg = resp.get("message") or resp.get("wording") or str(r_retcode)
                return _json({"ok": False, "error": f"发送失败(retcode={r_retcode}): {msg}"})
        return _json({"ok": True, "path": str(path)})
    except Exception as e:
        return _json({"ok": False, "error": f"发送失败: {e}"})

async def _handle_send_chat_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._adapter is None:
        return _json({"ok": False, "error": "adapter 未配置"})
    if self._file_server is None:
        return _json({"ok": False, "error": "file_server 未配置"})
    file_path = str(args.get("path", "")).strip()
    group_id = str(args.get("group_id", "")).strip()
    user_id = str(args.get("user_id", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip() or None
    if not file_path:
        return _json({"ok": False, "error": "缺少 path"})
    path = self._resolve_send_path(file_path, chat_flow_id)
    if not path.exists():
        return _json({"ok": False, "error": f"文件不存在: {file_path}"})
    if not group_id and not user_id:
        return _json({"ok": False, "error": "缺少 group_id 或 user_id"})
    try:
        from neobot_app.utils.media_sender import prepare_file_segment
        from neobot_contracts.models import ConversationRef

        if group_id:
            conv_ref = ConversationRef(kind="group", id=group_id)
        else:
            conv_ref = ConversationRef(kind="private", id=user_id)

        segment = prepare_file_segment(self._file_server, path)
        resp = await self._adapter.send(conv_ref, [segment])

        if resp is None:
            return _json({"ok": False, "error": "发送超时，无响应"})
        if hasattr(resp, "status") and hasattr(resp, "retcode"):
            if resp.status == "failed" or (resp.retcode is not None and resp.retcode != 0):
                msg = resp.message or resp.wording or str(resp.retcode)
                return _json({"ok": False, "error": f"发送失败(retcode={resp.retcode}): {msg}"})
        elif isinstance(resp, dict):
            r_status = resp.get("status")
            r_retcode = resp.get("retcode")
            if r_status == "failed" or (r_retcode is not None and r_retcode != 0):
                msg = resp.get("message") or resp.get("wording") or str(r_retcode)
                return _json({"ok": False, "error": f"发送失败(retcode={r_retcode}): {msg}"})
        return _json({"ok": True, "path": str(path)})
    except Exception as e:
        return _json({"ok": False, "error": f"发送失败: {e}"})

async def _handle_hold_temp(self: SandboxManagerSkill, args: dict) -> str:
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    minutes = int(args.get("minutes", 120))
    if not chat_flow_id:
        return _json({"ok": False, "error": "缺少 chat_flow_id"})
    if self._sandbox is None:
        return _json({"ok": True, "note": f"模拟：临时目录 {chat_flow_id} 已保活 {minutes} 分钟"})
    self._sandbox.ensure_temp_dir(chat_flow_id)
    return _json({"ok": True, "note": f"临时目录 {chat_flow_id} 已保活 {minutes} 分钟"})

async def _handle_download_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    url = str(args.get("url", "")).strip()
    save_name = str(args.get("save_name", "")).strip()
    chat_flow_id = str(args.get("chat_flow_id", "")).strip()
    if not url or not save_name or not chat_flow_id:
        return _json({"ok": False, "error": "缺少必要参数 url/save_name/chat_flow_id"})

    timeout_seconds = int(args.get("timeout_seconds", 300) or 300)
    timeout_seconds = max(1, min(timeout_seconds, 1800))

    # 安全检查：禁止非 HTTP(S) 协议
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return _json({"ok": False, "error": f"不支持的协议: {parsed.scheme}，仅允许 http/https"})

    # 安全检查：禁止回环地址
    hostname = (parsed.hostname or "").lower()
    if hostname in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
        return _json({"ok": False, "error": "禁止下载回环地址"})

    # 安全检查：禁止内网地址
    if hostname.startswith(("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                            "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                            "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                            "172.30.", "172.31.", "192.168.")):
        return _json({"ok": False, "error": "禁止下载内网地址"})

    try:
        import httpx
        async with httpx.AsyncClient(timeout=float(timeout_seconds), follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.content

        # 检查沙箱总容量（不限制单文件大小）
        remaining = self._sandbox.check_capacity(len(data))
        if remaining is not None and remaining < 0:
            current = self._sandbox.get_total_size()
            max_mb = self._sandbox.max_total_size / (1024 * 1024)
            current_mb = current / (1024 * 1024)
            return _json({
                "ok": False,
                "error": (
                    f"沙箱空间不足：当前 {current_mb:.0f}MB / 上限 {max_mb:.0f}MB，"
                    f"下载需要 {len(data) / (1024*1024):.1f}MB"
                ),
            })

        path = self._sandbox.resolve_path(save_name, chat_flow_id)
        await self._sandbox.write_file(path, data)
        return _json({"ok": True, "path": str(path), "size": len(data)})
    except Exception as e:
        return _json({"ok": False, "error": f"下载失败: {e}"})

_HANDLERS = {
    "read_file": _handle_read_file,
    "write_file": _handle_write_file,
    "write_file_base64": _handle_write_file_base64,
    "edit_file": _handle_edit_file,
    "glob_files": _handle_glob_files,
    "grep_files": _handle_grep_files,
    "delete_file": _handle_delete_file,
    "list_files": _handle_list_files,
    "move_file": _handle_move_file,
    "copy_file": _handle_copy_file,
    "send_file": _handle_send_file,
    "send_chat_file": _handle_send_chat_file,
    "hold_temp": _handle_hold_temp,
    "download_file": _handle_download_file,
}
