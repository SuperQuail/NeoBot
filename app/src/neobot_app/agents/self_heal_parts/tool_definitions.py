"""工具定义清单（schema）。"""

from __future__ import annotations


from neobot_chat.schema.types import (
    ToolDefinition,
)


from .models import (
    _tool_def,
)


class SelfHealToolDefinitionsMixin:
    """工具定义清单（schema）。"""

    REQUEST_SOURCE_DIRS = ["app", "packages"]
    SOURCE_FILE_SUFFIXES = {".py", ".ini", ".toml", ".cfg", ".md", ".rst", ".txt"}
    MAX_SOURCE_FILE_BYTES = 100 * 1024
    MAX_LOG_TAIL_LINES = 2000
    DEFAULT_LOG_TAIL_LINES = 200
    SEARCH_MAX_FILES = 200
    SEARCH_MAX_MATCHES_PER_FILE = 5
    SEARCH_MAX_MATCHES_TOTAL = 30
    SEARCH_CONTEXT_LINES = 3

    def definitions(self) -> list[ToolDefinition]:
        tools = [
            _tool_def(
                "read_errors",
                "读取触发本次自修复任务的异常快照。返回 JSON 数组，"
                "每条含 time/level/module/file/line/function/message/traceback。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "read_log_tail",
                "读取 neobot.log 文件尾部 N 行，用于了解异常前后的完整上下文。",
                {
                    "properties": {
                        "lines": {
                            "type": "integer",
                            "description": (
                                f"读取尾部行数，默认 {self.DEFAULT_LOG_TAIL_LINES}，"
                                f"上限 {self.MAX_LOG_TAIL_LINES}"
                            ),
                        }
                    },
                    "required": [],
                },
            ),
            _tool_def(
                "read_source_code",
                "读取 Bot 自身源码文件（项目 app/、packages/ 子树）。"
                "敏感文件（.env、config.toml、密钥等）禁止读取。",
                {
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "相对项目根的路径，如 "
                                "app/src/neobot_app/drawing/manager.py"
                            ),
                        }
                    },
                    "required": ["path"],
                },
            ),
            _tool_def(
                "search_source_code",
                "在 app/ 与 packages/ 源码树中按正则搜索。"
                "返回匹配行 + 上下文 + 文件路径。",
                {
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": "Python 正则表达式",
                        },
                        "path_glob": {
                            "type": "string",
                            "description": (
                                "可选路径 glob（项目内相对路径，如 app/src/**/*.py），"
                                "默认 app/**/*.py 与 packages/**/*.py；"
                                "禁止绝对路径与 ../ 越界"
                            ),
                        },
                    },
                    "required": ["pattern"],
                },
            ),
            _tool_def(
                "write_debug_report",
                "将诊断报告写入沙箱 debug 目录（Markdown）。"
                "返回沙箱相对路径，请将其传给 submit_resolution 的 debug_file。",
                {
                    "properties": {
                        "file_name": {
                            "type": "string",
                            "description": (
                                "文件名（不含目录），如 '2026-07-12_db_lock.md'。"
                                "若未提供则自动用时间戳生成。"
                            ),
                        },
                        "content_base64": {
                            "type": "string",
                            "description": ("Markdown 报告的 UTF-8 文本的 base64 编码"),
                        },
                    },
                    "required": ["content_base64"],
                },
            ),
            _tool_def(
                "list_debug_reports",
                "列出沙箱 debug 目录下已有的诊断报告。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "read_debug_report",
                "读取沙箱 debug 目录下已有的诊断报告，返回 base64。",
                {
                    "properties": {
                        "file_name": {"type": "string", "description": "文件名"},
                    },
                    "required": ["file_name"],
                },
            ),
            _tool_def(
                "search_web",
                "联网搜索（用于查询异常信息、依赖文档、已知 issue、相似报错）。"
                "支持 mode 进行多角度研究搜索：encyclopedia / community / news / "
                "official / video / academic。不填 mode 仅做普通关键词搜索。",
                {
                    "properties": {
                        "query": {"type": "string", "description": "搜索关键词"},
                        "num_results": {
                            "type": "integer",
                            "description": "返回结果数，默认 10",
                        },
                        "mode": {
                            "type": "string",
                            "description": (
                                "研究模式：encyclopedia/community/news/official/video/academic"
                            ),
                        },
                    },
                    "required": ["query"],
                },
            ),
            _tool_def(
                "read_search_result",
                "读取指定编号的网页搜索结果页面完整内容。",
                {
                    "properties": {
                        "indices": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "结果编号列表，如 [0, 1, 3]",
                        }
                    },
                    "required": ["indices"],
                },
            ),
            _tool_def(
                "search_status",
                "查看当前搜索会话状态。",
                {"properties": {}, "required": []},
            ),
            _tool_def(
                "submit_resolution",
                "提交诊断/修复结论，结束本次自修复任务。"
                "调用后任务标记为完成，系统自动向管理员私聊推送最终通知（包含 debug_file 路径）。",
                {
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "诊断摘要（必填）。一两句话说明发生了什么。",
                        },
                        "repaired": {
                            "type": "boolean",
                            "description": "是否已自行修复（必填，默认 false）",
                        },
                        "root_cause": {
                            "type": "string",
                            "description": "可选根因说明",
                        },
                        "debug_file": {
                            "type": "string",
                            "description": "write_debug_report 返回的沙箱相对路径",
                        },
                    },
                    "required": ["summary"],
                },
            ),
        ]
        if self._sandbox is not None:
            tools.extend(
                [
                    _tool_def(
                        "list_files",
                        "列出沙箱目录内容。",
                        {
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "目录相对路径，默认沙箱根",
                                }
                            },
                            "required": [],
                        },
                    ),
                    _tool_def(
                        "read_file",
                        "读取沙箱文件内容（支持文本/二进制检测），返回文本或 base64。",
                        {
                            "properties": {
                                "path": {
                                    "type": "string",
                                    "description": "沙箱相对路径",
                                },
                            },
                            "required": ["path"],
                        },
                    ),
                    _tool_def(
                        "run_python",
                        "在 Bot 的 Python 虚拟环境执行诊断代码。"
                        "代码 print() 输出会被捕获。仅用于诊断（如查询数据库、检查文件状态）。",
                        {
                            "properties": {
                                "code": {
                                    "type": "string",
                                    "description": "Python 代码",
                                },
                                "timeout": {
                                    "type": "integer",
                                    "description": "超时秒数（默认 30，最大 60）",
                                },
                            },
                            "required": ["code"],
                        },
                    ),
                    _tool_def(
                        "parse_image",
                        "解析沙箱中图片文件内容（如图表截图、报错截图）。",
                        {
                            "properties": {
                                "image_path": {"type": "string"},
                                "requirement": {
                                    "type": "string",
                                    "description": "分析要求",
                                },
                            },
                            "required": ["image_path"],
                        },
                    ),
                ]
            )
        # Repair hooks are optional; include only when wired in
        if "clear_drawing_cooldown" in self._repair_hooks:
            tools.append(
                _tool_def(
                    "clear_drawing_cooldown",
                    "清除指定聊天流的绘图冷却（用于诊断后修复卡死的绘图管线）。",
                    {
                        "properties": {
                            "pipeline_key": {
                                "type": "string",
                                "description": "形如 'group:123456' 或 'private:654321'",
                            }
                        },
                        "required": ["pipeline_key"],
                    },
                )
            )
        if "trigger_image_cleanup" in self._repair_hooks:
            tools.append(
                _tool_def(
                    "trigger_image_cleanup",
                    "触发图库失效记录与磁盘文件清理（用于诊断后修复磁盘/数据库记录不一致）。",
                    {"properties": {}, "required": []},
                )
            )
        return tools
