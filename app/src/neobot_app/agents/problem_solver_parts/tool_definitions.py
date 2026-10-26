"""工具定义清单（含 PTC/普通模式）。"""

from __future__ import annotations


from neobot_chat.schema.types import (
    ToolDefinition,
)


from .models import (
    _tool_def,
)


class ProblemSolverToolDefinitionsMixin:
    """工具定义清单（含 PTC/普通模式）。"""

    def definitions(self) -> list[ToolDefinition]:
        if self._runtime is None:
            return self._legacy_definitions()
        business = self._business_definitions()
        tools = self._runtime.definitions(external=business)
        return tools if self._runtime.mode == "ptc" else business + tools

    def _business_definitions(self) -> list[ToolDefinition]:
        return [d for d in self._legacy_definitions()
                if d["function"]["name"] in {"get_chat_context", "submit_solution"}]

    def _legacy_definitions(self) -> list[ToolDefinition]:
        tools = [
            _tool_def(
                "get_chat_context",
                "读取主Agent本轮看到的聊天上下文和消息编号映射，"
                "用于理解问题背景和对话环境。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "search",
                "联网搜索。强烈建议使用 mode 参数进行多角度研究搜索，"
                "一次 mode 搜索会从多个变体查询并合并去重，比多次普通关键词搜索高效得多。"
                "可用 mode：encyclopedia（百科/百度百科/wiki）、community（知乎/贴吧/论坛/NGA）、"
                "news（新闻/资讯）、official（官网）、video（bilibili/评测）、academic（论文/研究）。"
                "不填 mode 仅做普通关键词搜索。查百科资料用 mode='encyclopedia' 远优于搜索 'xxx 百度百科'。",
                {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词或研究主题",
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "单次搜索返回的结果数量，默认 10",
                        },
                        "mode": {
                            "type": "string",
                            "description": (
                                "研究模式（强烈推荐）：encyclopedia（百科类）、community（社区类）、"
                                "news（新闻类）、official（官方类）、video（视频类）、academic（学术类）"
                            ),
                        },
                    },
                    "required": ["query"],
                },
            ),
            _tool_def(
                "read_page",
                "读取指定编号的搜索结果页面完整内容，返回页面正文。"
                "已读取的页面会自动在后续搜索中去重。",
                {
                    "properties": {
                        "indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "要读取的结果编号列表，如 [0, 1, 3]",
                        },
                    },
                    "required": ["indices"],
                },
            ),
            _tool_def(
                "search_status",
                "查看当前搜索会话状态，包括已完成轮次、已读/未读结果统计。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "submit_solution",
                "提交解题结果。将完整的解题过程以 Markdown 格式提交。"
                "支持代码块、表格、公式等标准 Markdown 语法。"
                "提交后解题任务视为完成。",
                {
                    "properties": {
                        "solution": {
                            "type": "string",
                            "description": "完整的解题过程，使用 Markdown 格式。",
                        },
                    },
                    "required": ["solution"],
                },
            ),
            _tool_def(
                "run_python",
                "在 Bot 的 Python 虚拟环境中执行 Python 代码，返回标准输出和错误。"
                "可用于生成文件（PDF/图片等）、数据分析、计算等。"
                "代码中的 `print()` 输出会被捕获返回。"
                "生成的临时文件保存在当前工作目录，可通过 write_file/read_file 持久化到沙箱。"
                "运行耗时操作时注意控制执行时间，避免超时。",
                {
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "要执行的 Python 代码",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "可选，超时秒数（默认 30，最大 120）",
                        },
                    },
                    "required": ["code"],
                },
            ),
            _tool_def(
                "parse_image",
                "解析沙箱中的图片文件内容。传入图片路径和分析要求，返回图片的文字描述。"
                "适用于：读取图片中的数据/文字、分析图表、理解图片内容等。",
                {
                    "properties": {
                        "image_path": {
                            "type": "string",
                            "description": "图片文件路径（相对于沙箱临时目录或沙箱根）",
                        },
                        "requirement": {
                            "type": "string",
                            "description": "分析要求，如「请描述这张图片的内容」「请提取图片中的文字」",
                            "default": "请简洁描述这张图片的主要内容。",
                        },
                        "chat_flow_id": {
                            "type": "string",
                            "description": "聊天流 ID，便于定位临时目录中的文件",
                        },
                    },
                    "required": ["image_path"],
                },
            ),
        ]
        if self._sandbox is not None:
            tools.extend(
                [
                    _tool_def(
                        "write_file",
                        "将内容写入沙箱文件。文件路径相对于沙箱临时目录。"
                        "可用于保存生成的 PDF、图片、代码等文件。"
                        "写入后主Agent可通过 sandbox_manager 工具查看和发送这些文件。",
                        {
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "文件名（如 test.pdf），将保存到沙箱临时目录",
                                },
                                "content_base64": {
                                    "type": "string",
                                    "description": "文件内容的 base64 编码",
                                },
                            },
                            "required": ["path", "content_base64"],
                        },
                    ),
                    _tool_def(
                        "read_file",
                        "读取沙箱文件的内容，返回 base64 编码数据。",
                        {
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "文件路径（相对于沙箱根）",
                                },
                            },
                            "required": ["path"],
                        },
                    ),
                    _tool_def(
                        "list_files",
                        "列出沙箱目录下的内容。",
                        {
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "目录路径（相对于沙箱根），默认为 /",
                                },
                            },
                            "required": [],
                        },
                    ),
                ]
            )
        return tools
