"""SandboxManagerSkill 的工具声明与分发入口。"""

from __future__ import annotations

from typing import Any

from .common import _json
from .dispatch import _HANDLERS

class ToolsMixin:

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
