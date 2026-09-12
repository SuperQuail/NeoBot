"""SandboxManagerSkill — 沙箱文件操作 Skill（读写/编辑/搜索/删除/列表/移动/复制/发送）。"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from neobot_app.skills.base import SkillModule

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)

MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
MAX_DOWNLOAD_REDIRECTS = 3

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
            "取 pipeline_key 的值（格式 group:12345 或 private:12345）。\n"
            "生产调用由宿主绑定当前聊天和 owner；参数不能切换聊天，发送也仅允许当前聊天。\n"
            "共享持久目录必须显式使用 shared:docs/... 等路径；共享修改需 agent_shared_write 凭据。\n"
            "覆盖已有 base64 文件需 agent_execute 凭据。已有文本文件修改请先 read_file。\n\n"
            "## 临时目录 vs 沙箱根（重要）\n"
            "路径选择规则：除非文件是长期复用的工具/文档/资源，否则一律写入临时目录。\n"
            "write_file / write_file_base64 写入的文件位于临时目录（sandbox/temp/{chat_flow_id}/）。\n"
            "生产工具的相对路径始终基于宿主绑定的当前聊天临时目录，不能使用 ../ 切换聊天。\n"
            "持久化资源必须显式使用 shared:tools/...、shared:docs/...、shared:assets/... 等白名单路径。\n"
            "无调用上下文的宿主直调保留历史 root/chat_flow_id 路径接口；模型不能选择该模式。\n\n"
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
        credential_manager: Any = None,
    ) -> None:
        self._sandbox = sandbox_service
        from neobot_app.runtime.agent_file_tools import AgentFileTools
        self._file_tools = AgentFileTools(sandbox_service) if sandbox_service is not None else None
        self._file_owner = f"legacy-sandbox-skill:{id(self)}"
        self._lock = sandbox_lock
        self._adapter = adapter
        self._file_server = file_server
        self._hold_max_minutes = hold_max_minutes
        from neobot_app.agent_tools.permissions import ToolPermissions
        self._permissions = ToolPermissions(credential_manager)

    def reset(self) -> None:
        pass

    def _resolve_send_path(self, path_str: str, chat_flow_id: str | None = None) -> Path:
        from neobot_app.agent_tools.invocation import CURRENT_INVOCATION
        invocation = CURRENT_INVOCATION.get()
        if invocation is not None:
            if self._file_tools is None:
                raise PermissionError("sandbox_service required for model file delivery")
            return self._file_tools.resolve_path(path_str, owner=invocation.context.owner,
                                                 chat_flow_id=invocation.context.chat_flow_id)
        p = Path(path_str)
        if p.is_absolute() and p.exists():
            return p
        if self._sandbox is not None:
            try:
                resolved = self._sandbox.resolve_read_path(path_str, chat_flow_id)
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
        definitions = [
            # ── 读取 ──
            self._tool_def(
                "read_file",
                "读取沙箱内文件的内容。文本文件返回文本，二进制文件返回 base64。"
                "操作临时文件时必须传入 chat_flow_id；支持 offset/limit 行分页及 column 长行续读。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（当前聊天临时目录相对路径，持久化资源使用 shared:docs/... 等显式共享路径）"},
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
                "这是修改文件的首选方式；建议先 read_file，随后会校验版本防止覆盖他人更新。"
                "编辑临时文件时必须传入 chat_flow_id。",
                {
                    "properties": {
                        "path": {"type": "string", "description": "文件路径（当前聊天临时目录相对路径，持久化资源使用 shared:docs/... 等显式共享路径）"},
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
                        "path": {"type": "string", "description": "文件路径（当前聊天临时目录相对路径，持久化资源使用 shared:docs/... 等显式共享路径）"},
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
                        "path": {"type": "string", "description": "目录路径（当前聊天相对路径或 shared:docs 等共享目录），默认为 ."},
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
                        "path": {"type": "string", "description": "文件路径（当前聊天临时目录相对路径，持久化资源使用 shared:docs/... 等显式共享路径）"},
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
                        "path": {"type": "string", "description": "文件路径（当前聊天临时目录相对路径，持久化资源使用 shared:docs/... 等显式共享路径）"},
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
        for definition in definitions:
            function = definition.get("function", definition)
            short_name = function["name"].rsplit("__", 1)[-1]
            properties = function["parameters"]["properties"]
            if short_name == "read_file":
                properties.update({"offset": {"type": "integer", "minimum": 1},
                                   "limit": {"type": "integer", "minimum": 1, "maximum": 2000},
                                   "column": {"type": "integer", "minimum": 0}})
            elif short_name in {"write_file", "edit_file"}:
                properties["expected_version"] = {"type": "string", "description": "read_file 返回的版本；已有文件写入需先完整读取"}
        return definitions

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        handler = _HANDLERS.get(tool_name)
        if handler is None:
            return _json({"ok": False, "error": f"unknown sandbox_manager tool: {tool_name}"})
        from neobot_app.agent_tools.invocation import CURRENT_INVOCATION
        invocation = CURRENT_INVOCATION.get()
        if invocation is not None:
            return await self._execute_trusted(tool_name, args, invocation.context)
        # Direct, context-free calls are a host-only compatibility API.
        return await handler(self, args)

    async def _execute_trusted(self, name: str, args: dict, context: Any) -> str:
        """Production model entry. Never mint authority from tool arguments.

        This is separate from the historical handlers so host-only integrations
        retain their old contract without weakening flow-bound model calls.
        """
        from neobot_app.agent_tools.contracts import AgentToolError, ToolContext
        from neobot_app.runtime.agent_file_tools import MAX_FILE_BYTES
        try:
            if not isinstance(context, ToolContext):
                raise AgentToolError("CONTEXT_REQUIRED", "Trusted ToolContext required")
            # Reply has already checked the qualified legacy skill capability.
            # allowed_tools contains NEW runtime names, not legacy skill names.
            if self._file_tools is None or self._sandbox is None:
                raise AgentToolError("SANDBOX_REQUIRED", "sandbox_service 未配置")
            if not isinstance(args, dict):
                raise AgentToolError("INVALID_ARGS", "Tool arguments must be an object")
            for key in ("chat_flow_id", "pipeline_key"):
                if args.get(key) not in (None, "", context.chat_flow_id):
                    raise AgentToolError("FLOW_MISMATCH", "Tool arguments cannot change the trusted chat flow")
            if any(key in args for key in ("owner", "context", "invocation")):
                raise AgentToolError("CONTEXT_REQUIRED", "Identity/context fields are host-only")
            clean = {key: value for key, value in args.items() if key not in {"chat_flow_id", "pipeline_key"}}
            bound = {**clean, "chat_flow_id": context.chat_flow_id}

            def resolve(value, *, write=False):
                if not isinstance(value, str) or not value:
                    raise AgentToolError("INVALID_ARGS", "A nonempty string path is required")
                return self._file_tools.resolve_path(value, owner=context.owner,
                                                     chat_flow_id=context.chat_flow_id, write=write)

            def shared(value):
                return isinstance(value, str) and value.startswith("shared:")

            async def execute_file(operation, values):
                return await self._file_tools.execute(operation, values, owner=context.owner,
                                                      chat_flow_id=context.chat_flow_id)

            mapping = {"read_file": "read", "write_file": "write", "edit_file": "edit",
                       "glob_files": "glob", "grep_files": "grep"}
            if name in mapping:
                operation = mapping[name]
                raw = clean.get("file_path", clean.get("path", "." if operation in {"glob", "grep"} else None))
                path = resolve(raw, write=operation in {"write", "edit"})
                if operation in {"write", "edit"} and shared(raw):
                    self._permissions.require(context, "agent_shared_write")
                values = dict(clean)
                if operation in {"glob", "grep"}:
                    values.pop("file_path", None)
                    values["path"] = raw
                else:
                    values.pop("path", None)
                    values["file_path"] = raw
                if operation == "grep":
                    values["include"] = values.pop("glob", None) or "*"
                    values["ignore_case"] = values.pop("-i", False)
                    values["limit"] = values.pop("head_limit", 50)
                    mode = values.pop("output_mode", "files_with_matches")
                    if mode not in {"content", "count", "files_with_matches"}:
                        raise AgentToolError("INVALID_ARGS", "Invalid output_mode")
                if operation == "read":
                    from neobot_app.runtime.sandbox_service import detect_file_type, MAX_BASE64_BYTES
                    info = detect_file_type(path)
                    if info["type"] in {"image", "binary"}:
                        return _json({"ok": True, **info,
                                      "note": "图片分析请使用 image_parse；发送请用 send_file/send_chat_file。"})
                result = await execute_file(operation, values)
                if operation == "read" and result.get("code") == "not_utf8":
                    with path.open("rb") as stream:
                        preview = stream.read(MAX_BASE64_BYTES)
                    return _json({"ok": True, "type": "unknown_binary", "size": path.stat().st_size,
                                  "content_base64": base64.b64encode(preview).decode(),
                                  "truncated": path.stat().st_size > len(preview),
                                  "note": "只读二进制预览；不可把预览作为完整文件覆盖。"})
                if result.get("ok") and operation in {"glob", "grep"}:
                    base = Path(result["root"])
                    def relative(value):
                        return str(Path(value).relative_to(base)) if Path(value) != base else Path(value).name
                    if operation == "glob":
                        result["matches"] = [{"path": relative(p), "is_dir": False} for p in result["paths"]]
                    elif mode == "content":
                        result["results"] = [{"file": relative(m["path"]), "line": m["lineNumber"], "text": m["line"]}
                                             for m in result["matches"]]
                    else:
                        counts = {}
                        for match in result["matches"]:
                            key = relative(match["path"])
                            counts[key] = counts.get(key, 0) + 1
                        result["results"] = [{"file": key, "count" if mode == "count" else "match_count": count}
                                             for key, count in counts.items()]
                    if operation == "grep":
                        result["total_matches"] = len(result["matches"])
                return _json(result)

            if name in {"move_file", "copy_file"}:
                source, destination = clean.get("source"), clean.get("destination")
                src = resolve(source, write=name == "move_file")
                dst = resolve(destination, write=True)
                # Service move/copy may append the basename for a directory target.
                if dst.is_dir():
                    resolve(destination.rstrip("/\\") + "/" + src.name, write=True)
                if shared(destination) or (name == "move_file" and shared(source)):
                    self._permissions.require(context, "agent_shared_write")
                operation = self._sandbox.move_file if name == "move_file" else self._sandbox.copy_file
                await operation(src, dst)
                return _json({"ok": True})

            if name == "list_files":
                raw = clean.get("path") or "."
                base = resolve(raw)
                if clean.get("pattern"):
                    result = await execute_file("glob", {"path": raw, "pattern": clean["pattern"]})
                    if result.get("ok"):
                        result["files"] = [{"name": Path(p).name, "path": p, "is_dir": False} for p in result["paths"]]
                    return _json(result)
                if not base.is_dir():
                    raise NotADirectoryError(base)
                import os
                files, truncated = [], False
                with os.scandir(base) as entries:
                    for count, entry in enumerate(entries):
                        if count >= 2000:
                            truncated = True
                            break
                        try:
                            path = resolve(raw.rstrip("/\\") + "/" + entry.name)
                        except PermissionError:
                            continue
                        stat = path.stat()
                        files.append({"name": path.name, "path": str(path), "is_dir": path.is_dir(),
                                      "size": stat.st_size if path.is_file() else 0, "mtime": stat.st_mtime})
                return _json({"ok": True, "files": files, "truncated": truncated})

            if name == "hold_temp":
                resolve(".", write=True)
                return await _HANDLERS[name](self, bound)

            raw = clean.get("save_name") if name == "download_file" else clean.get("path")
            writing = name in {"delete_file", "write_file_base64", "download_file"}
            path = resolve(raw, write=writing)
            if name == "delete_file":
                if shared(raw):
                    self._permissions.require(context, "agent_shared_write")
                await self._sandbox.delete_file(path)
                return _json({"ok": True})
            if name == "write_file_base64":
                value = clean.get("content_base64")
                if not isinstance(value, str) or len(value) > 4 * ((MAX_FILE_BYTES + 2) // 3):
                    raise AgentToolError("INVALID_ARGS", "Invalid or oversized base64 content")
                data = base64.b64decode(value, validate=True)
                if len(data) > MAX_FILE_BYTES:
                    raise AgentToolError("FILE_TOO_LARGE", "Binary write exceeds file limit")
                with self._sandbox.file_lock(path):
                    resolve(raw, write=True)
                    if shared(raw):
                        self._permissions.require(context, "agent_shared_write")
                    elif path.exists():
                        self._permissions.require(context, "agent_execute")
                    self._sandbox.atomic_write(path, data)
                return _json({"ok": True, "path": str(path), "size": len(data)})
            if name == "download_file":
                if shared(raw):
                    self._permissions.require(context, "agent_shared_write")
                bound["save_name"] = str(path)
                return await _HANDLERS[name](self, bound)
            if name in {"send_file", "send_chat_file"}:
                kind, recipient = context.chat_flow_id.split(":", 1)
                for key, expected in (("group_id", recipient if kind == "group" else ""),
                                      ("user_id", recipient if kind == "private" else "")):
                    if str(clean.get(key) or "") not in {"", expected}:
                        raise AgentToolError("FLOW_MISMATCH", "File delivery recipient must be the trusted flow")
                    bound[key] = expected
                # Preserve explicit shared syntax: strict _resolve_send_path checks again.
                bound["path"] = raw
                return await _HANDLERS[name](self, bound)
            raise AgentToolError("UNKNOWN_TOOL", name)
        except AgentToolError as exc:
            return _json({"ok": False, "code": exc.code, "error": str(exc), "details": exc.details})
        except PermissionError as exc:
            return _json({"ok": False, "code": "permission_denied", "error": str(exc)})
        except (OSError, ValueError, TypeError) as exc:
            # 只回传 str(exc) 时，像 FileNotFoundError 这类异常可能只剩一个路径；
            # 带上异常类型并给出下一步建议，模型才能自愈而不是反复换参数重试。
            return _json({
                "ok": False,
                "code": "file_error",
                "error": f"{type(exc).__name__}: {exc}",
                "hint": "确认路径存在且在允许目录内；目录不存在时先列上级目录，不要重复相同调用。",
            })

# ── Handlers ──

async def _handle_read_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._sandbox is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    rel_path = str(args.get("path", "")).strip().lstrip("/")
    if not rel_path:
        return _json({"ok": False, "error": "缺少 path"})
    try:
        from neobot_app.runtime.sandbox_service import (
            MAX_BASE64_BYTES,
            detect_file_type,
        )

        chat_flow_id = (args.get("chat_flow_id") or "").strip() or None
        path = self._sandbox.resolve_read_path(rel_path, chat_flow_id)

        info = detect_file_type(path)
        ftype = info["type"]
        fmt = info.get("format")
        size = info["size"]

        if ftype == "error":
            return _json({"ok": False, "error": f"无法读取文件: {rel_path}"})

        if ftype == "image":
            return _json({
                "ok": True,
                "type": "image",
                "format": fmt,
                "size": size,
                "note": (
                    f"这是 {fmt} 图片文件（{size} 字节），内容不会直接以文本/base64 返回。"
                    "请使用 image_parse 工具分析图片内容；发送图片请使用 send_file。"
                ),
            })

        if ftype == "binary":
            return _json({
                "ok": True,
                "type": "binary",
                "format": fmt,
                "size": size,
                "note": (
                    f"这是 {fmt} 二进制文件（{size} 字节），无法以文本读取。"
                    "发送此文件请使用 send_chat_file；分析内容请委托 background_trigger__submit_problem。"
                ),
            })

        # UTF-8 is decoded from the COMPLETE bounded file, then paginated.
        # This correctly handles a multibyte character straddling the old 64KiB cut.
        result = await self._file_tools.execute_legacy(
            "read", {**args, "file_path": rel_path}, owner=self._file_owner, chat_flow_id=chat_flow_id)
        if result.get("ok"):
            return _json(result)
        # Unknown binary is only a preview; never register it as a complete read.
        with path.open("rb") as stream:
            preview = stream.read(MAX_BASE64_BYTES)
        try:
            preview.decode("utf-8")
        except UnicodeDecodeError:
            return _json({"ok": True, "type": "unknown_binary",
                          "content_base64": base64.b64encode(preview).decode(),
                          "size": size, "truncated": size > len(preview),
                          "note": "二进制预览；发送文件请使用 send_chat_file。"})
        return _json(result)
    except Exception as e:
        return _json({"ok": False, "error": str(e)})

async def _handle_write_file(self: SandboxManagerSkill, args: dict) -> str:
    if self._file_tools is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    flow = self._get_chat_flow_id(args)
    if not args.get("path") or not flow or "content" not in args:
        return _json({"ok": False, "error": "缺少必要参数 path/content/chat_flow_id"})
    return _json(await self._file_tools.execute_legacy(
        "write", args, owner=self._file_owner, chat_flow_id=flow))

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
    if self._file_tools is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    return _json(await self._file_tools.execute_legacy(
        "edit", args, owner=self._file_owner, chat_flow_id=args.get("chat_flow_id") or None))


async def _handle_glob_files(self: SandboxManagerSkill, args: dict) -> str:
    if self._file_tools is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    result = await self._file_tools.execute_legacy(
        "glob", args, owner=self._file_owner, chat_flow_id=args.get("chat_flow_id") or None)
    if result.get("ok"):
        base = Path(result["root"])
        result["matches"] = [{"path": str(Path(p).relative_to(base)), "is_dir": False} for p in result["paths"]]
    return _json(result)


async def _handle_grep_files(self: SandboxManagerSkill, args: dict) -> str:
    if self._file_tools is None:
        return _json({"ok": False, "error": "sandbox_service 未配置"})
    mode = args.get("output_mode", "files_with_matches")
    if mode not in {"content", "files_with_matches", "count"}:
        return _json({"ok": False, "error": "invalid output_mode"})
    translated = {**args, "include": args.get("glob") or "*",
                  "ignore_case": args.get("-i", False), "limit": args.get("head_limit", 50)}
    result = await self._file_tools.execute_legacy(
        "grep", translated, owner=self._file_owner, chat_flow_id=args.get("chat_flow_id") or None)
    if result.get("ok"):
        base = Path(result["root"])
        def relative(p):
            return str(Path(p).relative_to(base)) if Path(p) != base else Path(p).name
        if mode == "content":
            result["results"] = [{"file": relative(m["path"]), "line": m["lineNumber"], "text": m["line"]}
                                 for m in result["matches"]]
        else:
            counts: dict[str, int] = {}
            for match in result["matches"]:
                p = relative(match["path"])
                counts[p] = counts.get(p, 0) + 1
            result["results"] = [{"file": p, "count" if mode == "count" else "match_count": count}
                                 for p, count in counts.items()]
        result["total_matches"] = len(result["matches"])
        # Counts explicitly describe the bounded matched prefix when truncated.
    return _json(result)

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
        path = self._sandbox.resolve_read_path(rel_path, chat_flow_id)
        files = await self._sandbox.list_files(path, pattern)
        return _json({"ok": True, "files": files})
    except (FileNotFoundError, NotADirectoryError):
        # 旧实现只回传 str(exc)，最坏情况下 error 里只有一个路径，模型无法据此
        # 判断该换参数还是换工具，只能反复猜（随后改去试别的工具）。
        return _json({
            "ok": False,
            "code": "not_found",
            "error": f"目录不存在或不是目录: {rel_path}",
            "hint": "先用 path=\".\" 列出当前目录确认可用路径；不要重复同样的参数。",
        })
    except PermissionError as e:
        return _json({
            "ok": False,
            "code": "permission_denied",
            "error": str(e),
            "hint": "该路径不在允许范围内：改用当前会话目录，或在允许时使用 shared: 前缀。",
        })
    except Exception as e:
        return _json({
            "ok": False,
            "code": "file_error",
            "error": f"{type(e).__name__}: {e}",
            "hint": "检查路径拼写与后缀；若仍失败请换一个路径或改用其它工具。",
        })

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
        src_path = self._sandbox.resolve_read_path(src, chat_flow_id or None)
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
        # 不等 echo：发送几乎不会失败，等待回执只会阻塞 agent 继续执行。
        resp = await self._adapter.send(conv_ref, [segment], wait_response=False)

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
        resp = await self._adapter.send(conv_ref, [segment], wait_response=False)

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

async def _read_download_limited(response: Any) -> bytes:
    """分块读取下载响应体，超过上限即中止。"""
    content_length = response.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError:
            declared = 0
        if declared > MAX_DOWNLOAD_BYTES:
            raise ValueError(f"文件过大（{declared} 字节），超过上限 {MAX_DOWNLOAD_BYTES} 字节")
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_DOWNLOAD_BYTES:
            raise ValueError(f"文件过大，超过上限 {MAX_DOWNLOAD_BYTES} 字节，下载已中止")
        chunks.append(chunk)
    return b"".join(chunks)


async def _download_with_redirects(client: Any, url: str) -> bytes:
    """流式下载并手动跟随重定向，每跳重新做 SSRF 校验。"""
    from neobot_app.utils.ssrf import validate_public_url_async

    current_url = url
    for _ in range(MAX_DOWNLOAD_REDIRECTS + 1):
        response = await client.get(current_url)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("location")
            if not location:
                raise ValueError(f"重定向响应缺少 Location（{response.status_code}）")
            import httpx
            current_url = str(httpx.URL(current_url).join(location))
            if not await validate_public_url_async(current_url):
                raise ValueError("重定向目标不允许下载（内网/非公网地址）")
            continue
        response.raise_for_status()
        return await _read_download_limited(response)
    raise ValueError(f"重定向次数超过限制（{MAX_DOWNLOAD_REDIRECTS} 次）")


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

    from neobot_app.utils.ssrf import validate_public_url_async

    if not await validate_public_url_async(url):
        return _json({"ok": False, "error": "禁止下载内网/非公网地址"})

    try:
        import httpx
        async with httpx.AsyncClient(timeout=float(timeout_seconds), follow_redirects=False) as client:
            data = await _download_with_redirects(client, url)

        # 检查沙箱总容量
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
    except ValueError as e:
        return _json({"ok": False, "error": str(e)})
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
