"""暴露给主回复代理的回复相关工具。"""

from __future__ import annotations

import asyncio
import inspect
import json
import math
import os
import re
import stat
from pathlib import Path
from typing import Any

from neobot_chat.schema.exceptions import ToolError
from neobot_chat.schema.protocol import ToolExecutor
from neobot_chat.schema.types import (
    ToolAccessPolicy,
    ToolAccessRule,
    ToolDefinition,
    ToolGuardContext,
)
from neobot_chat.tools.toolset import ToolSpec, Toolset
from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_app.reply.postprocess import ReplyPostProcessResult, process_reply_text
from neobot_app.skills.activation import SkillToolActivation
from neobot_app.time_context import monotonic_seconds


# 技能激活限制工具（allowed-tools）时始终可用的基础工具白名单。
# 除基础回复工具外，还包括技能读取基础设施（skills__read_manifest /
# skills__read_resource / agents__list / agents__delegate）：技能作者不会把这些
# 写进 allowed-tools，但模型必须依赖它们先读取技能正文并按需委托子代理，
# 因此不能被技能限制掉。
# skills__read_resource 本身有注册表 + 路径授权；agents__list 只读不执行；
# agents__delegate 的副作用受 AgentRegistry 注册表 + 超时/排空管理约束，
# 是插件能力的核心通道，同样不能被技能声明限制掉。
# check_background_tasks / cancel_task / check_last_drawing /
# mark_scheduled_task_complete 属于会话基础设施：技能受限轮次里模型必须仍能
# 查询/中止后台任务（如用户要求中止当前操作时响应 cancel_task），
# 同样不能被技能声明限制掉。
_SKILL_GUARD_BASE_TOOLS = frozenset(
    {
        "cancel",
        "split_reply",
        "send_reply",
        "wait",
        "send_emoji",
        "send_long_reply",
        "speak",
        "skills__read_manifest",
        "skills__read_resource",
        "skills__view_instructions",
        "skills__load_tools",
        "agents__list",
        "agents__delegate",
        "check_background_tasks",
        "cancel_task",
        "check_last_drawing",
        "mark_scheduled_task_complete",
    }
)
# 工具输出压缩:这些"基础回复类"工具的返回值只是控制流回执(是否发送成功、
# 是否切分、等待是否结束、表情是否发出等),压缩后只保留"调用成功",不再保留
# 具体内容;其余工具压缩后仍保留一段结果摘要。
BASIC_REPLY_TOOLS = frozenset(
    {
        "cancel",
        "split_reply",
        "send_reply",
        "send_long_reply",
        "send_emoji",
        "wait",
        "speak",
        "poke_user",
        "react_emoji",
        "search_qq_emoji",
        "search_custom_emoji",
        "list_emojis",
        "adjust_reply_willingness",
        "get_willingness_config",
        "manage_willing_config",
        "cancel_task",
        "check_last_drawing",
        "mark_scheduled_task_complete",
    }
)
_MAX_TOOL_TEXT_CHARS = 16 * 1024
_MAX_SKILL_RESOURCE_BYTES = 1024 * 1024
#: list_emojis 单次最多返回的条数(防止一次把整库灌进上下文)
_MAX_EMOJI_PAGE_SIZE = 200
_SKILL_INTERNAL_KEYS = frozenset(
    {"pipeline_key", "_numbering_mapping", "_delegate_context", "_requester_id",
     "_agent_tool_context", "_human_request", "_owner", "_source"}
)
_SESSION_ERROR_KEYS = frozenset({"error", "errors"})
_SESSION_FAILURE_PREFIXES = ("未知工具", "工具执行失败", "错误")


def _bounded_text(value: Any, limit: int = _MAX_TOOL_TEXT_CHARS) -> str:
    if isinstance(value, str):
        text = value[: limit + 1]
    elif isinstance(value, (dict, list, tuple)):
        try:
            text = json.dumps(value, ensure_ascii=False, default=lambda _: "<object>")[
                : limit + 1
            ]
        except (TypeError, ValueError, RecursionError):
            text = f"<{type(value).__name__}>"
    else:
        try:
            text = str(value)[: limit + 1]
        except Exception:
            text = f"<{type(value).__name__}>"
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"


def _path_is_within(path: Path, base: Path) -> bool:
    try:
        normalized_path = os.path.normcase(os.path.abspath(path))
        normalized_base = os.path.normcase(os.path.abspath(base))
        return os.path.commonpath((normalized_path, normalized_base)) == normalized_base
    except (OSError, ValueError):
        return False


def _opened_file_path(file_obj: Any) -> Path | None:
    """Return the OS-resolved path for an already-open file handle when available."""
    try:
        fd = file_obj.fileno()
    except (AttributeError, OSError, ValueError):
        return None

    if os.name == "nt":
        try:
            import ctypes
            import msvcrt
            from ctypes import wintypes

            get_final_path = ctypes.WinDLL(
                "kernel32", use_last_error=True
            ).GetFinalPathNameByHandleW
            get_final_path.argtypes = (
                wintypes.HANDLE,
                wintypes.LPWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
            )
            get_final_path.restype = wintypes.DWORD
            handle = msvcrt.get_osfhandle(fd)
            length = get_final_path(handle, None, 0, 0)
            if not length:
                return None
            buffer = ctypes.create_unicode_buffer(length + 1)
            written = get_final_path(handle, buffer, len(buffer), 0)
            if not written or written >= len(buffer):
                return None
            value = buffer.value
            if value.startswith("\\\\?\\UNC\\"):
                value = "\\\\" + value[8:]
            elif value.startswith("\\\\?\\"):
                value = value[4:]
            return Path(value)
        except (AttributeError, OSError, ValueError):
            return None

    for fd_root in ("/proc/self/fd", "/dev/fd"):
        fd_path = Path(fd_root) / str(fd)
        try:
            if fd_path.is_symlink():
                return Path(os.path.realpath(fd_path))
        except OSError:
            continue
    return None


def _same_open_file(first: os.stat_result, second: os.stat_result) -> bool:
    first_ino = getattr(first, "st_ino", 0)
    second_ino = getattr(second, "st_ino", 0)
    if not first_ino or not second_ino:
        return False
    return first_ino == second_ino and getattr(first, "st_dev", None) == getattr(
        second, "st_dev", None
    )


def _default_resolver(
    args: dict, context: ToolGuardContext, policy: ToolAccessPolicy
) -> ToolAccessRule:
    return ToolAccessRule(action="allow")


def _tool_def(name: str, description: str, parameters: dict) -> ToolDefinition:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", **parameters},
        },
    }


class ReplyToolExecutor(ToolExecutor):
    """回复模式工具的执行器。"""

    def __init__(
        self,
        *,
        send_reply_handler: Any = None,
        willing_service: Any = None,
        numbering: Any = None,
        send_emoji_handler: Any = None,
        emoji_service: Any = None,
        wait_handler: Any = None,
        react_emoji_handler: Any = None,
        search_emoji_handler: Any = None,
        cancel_handler: Any = None,
        tts_service: Any = None,
        speak_handler: Any = None,
        poke_user_handler: Any = None,
        drawing_manager: Any = None,
        scheduled_task_manager: Any = None,
        problem_solver_manager: Any = None,
        notification_hub: Any = None,
        markdown_image_converter: Any = None,
        send_long_reply_handler: Any = None,
        skill_manager: Any = None,
        skills_registry: Any = None,
        allowed_tools: set[str] | None = None,
        chat_context: str | None = None,
        conv_kind: str = "",
        conv_id: str = "",
        current_user_id: int | None = None,
        human_request: bool = False,
        agent_history: list[dict] | None = None,
        wait_cooldown_seconds: int = 60,
        ai_reply_check: bool = False,
        ai_reply_check_lightweight: bool = True,
        bot_name: str = "Bot",
        long_reply_fallback_template: str = "{bot_name}懒得和你说道理，你不配听",
        long_reply_max_length: int = 300,
        long_reply_max_sentence_count: int = 12,
        enable_ai_reply_regenerate: bool = True,
        logger: Logger | None = None,
        credential_manager: Any = None,
        config: Any = None,
        config_update_callback: Any = None,
        native_vision_provider: Any = None,
    ) -> None:
        self._native_vision_provider = native_vision_provider
        self._send_reply = send_reply_handler
        self._willing = willing_service
        self._numbering = numbering
        self._send_emoji = send_emoji_handler
        self._emoji = emoji_service
        self._wait = wait_handler
        self._react_emoji = react_emoji_handler
        self._search_emoji = search_emoji_handler
        self._cancel = cancel_handler
        self._tts_service = tts_service
        self._speak_handler = speak_handler
        self._poke_user = poke_user_handler
        self._drawing_manager = drawing_manager
        self._scheduled_task_manager = scheduled_task_manager
        self._problem_solver_manager = problem_solver_manager
        self._notification_hub = notification_hub
        self._markdown_image_converter = markdown_image_converter
        self._send_long_reply = send_long_reply_handler
        self._skill_manager = skill_manager
        self._skills_registry = skills_registry
        self._allowed_tools = allowed_tools
        self._chat_context = chat_context
        self._conv_kind = conv_kind
        self._conv_id = conv_id
        self._current_user_id = current_user_id
        self._human_request = human_request
        self._agent_history = agent_history if agent_history is not None else []
        self._ai_reply_check = ai_reply_check
        self._ai_reply_check_lightweight = ai_reply_check_lightweight
        self._bot_name = bot_name
        self._long_reply_fallback_template = long_reply_fallback_template
        self._long_reply_max_length = long_reply_max_length
        self._long_reply_max_sentence_count = long_reply_max_sentence_count
        self._enable_ai_reply_regenerate = enable_ai_reply_regenerate
        self._wait_cooldown_seconds = wait_cooldown_seconds
        self._credential_manager = credential_manager
        self._config = config
        self._config_update_callback = config_update_callback
        self._last_wait_time = 0.0
        self._session_tasks: set[asyncio.Task] = set()
        self._session_task_info: dict[int, dict] = {}
        self._session_task_queue: dict[str, dict] = {}
        self._session_completed: dict[str, list[dict]] = {}
        self._closed = False
        self._close_task: asyncio.Task[None] | None = None
        self._logger = logger or NullLogger()
        self._skill_tokens: dict[str, Any] = {}
        # 本管线已按需加载的技能工具；管线结束时随执行器一起销毁。
        # 惰性构建：允许测试/插件在构造之后替换 skill_manager。
        self._activation_cache: SkillToolActivation | None = None
        self._activation_manager: Any = None

    @property
    def closed(self) -> bool:
        """Whether close has begun and new session work is rejected."""
        return self._closed

    @property
    def _activation(self) -> SkillToolActivation | None:
        """当前 skill_manager 对应的按需加载状态；管理器被替换时自动重建。"""
        manager = self._skill_manager
        if manager is None:
            return None
        if self._activation_cache is None or self._activation_manager is not manager:
            self._activation_cache = SkillToolActivation(
                manager, authorize=self.is_tool_authorized
            )
            self._activation_manager = manager
        return self._activation_cache

    async def __aenter__(self) -> ReplyToolExecutor:
        if self._closed:
            raise RuntimeError("ReplyToolExecutor is closed")
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    def definitions(self) -> list[ToolDefinition]:
        tools: list[ToolDefinition] = []
        if self._skills_registry is not None and getattr(
            self._skills_registry, "skills", None
        ):
            tools.append(
                _tool_def(
                    "skills__read_manifest",
                    "读取一个技能的完整说明文档（SKILL.md 正文）。"
                    "技能 id 格式为 owner:name，由提示词中的 <可用技能> 列表提供。"
                    "执行技能任务前必须先调用本工具获取说明。",
                    {
                        "properties": {
                            "skill_id": {
                                "type": "string",
                                "description": "技能 id（格式 owner:name）。",
                            },
                        },
                        "required": ["skill_id"],
                    },
                )
            )
            tools.append(
                _tool_def(
                    "skills__read_resource",
                    "读取技能目录内的参考资料（相对路径）。"
                    "仅允许技能目录内的文件，禁止绝对路径或 .. 越界。",
                    {
                        "properties": {
                            "skill_id": {
                                "type": "string",
                                "description": "技能 id（格式 owner:name）。",
                            },
                            "path": {
                                "type": "string",
                                "description": "技能目录内的相对路径，如 references/cities.md。",
                            },
                        },
                        "required": ["skill_id", "path"],
                    },
                )
            )
        if self._skill_manager is not None:
            skill_names = getattr(self._skill_manager, "skill_names", None) or []
            if skill_names:
                tools.append(
                    _tool_def(
                        "skills__view_instructions",
                        "查看某个内置技能的完整操作说明（默认只显示一行摘要）。"
                        "需要深入了解某技能的使用规则、参数细节或注意事项时调用本工具；"
                        "技能名从提示词的 <Skill 操作说明> 摘要列表中选择。",
                        {
                            "properties": {
                                "skill": {
                                    "type": "string",
                                    "enum": skill_names,
                                    "description": "技能名（如 vision_detect、image_parse）。",
                                },
                            },
                            "required": ["skill"],
                        },
                    )
                )
            loader = (
                self._activation.loader_definition()
                if self._activation is not None
                else None
            )
            if loader:
                tools.append(loader)
        if self._cancel is not None:
            tools.append(
                _tool_def(
                    "cancel",
                    "主动结束本轮回复事件。当认为自己不适合参与当前话题、不需要回复、"
                    "或已通过其他方式完成互动时调用。调用后本轮回复立即结束，不再发送任何消息。",
                    {
                        "properties": {
                            "reason": {
                                "type": "string",
                                "description": "可选，取消回复的简要原因。",
                            },
                        },
                        "required": [],
                    },
                ),
            )
        tools.append(
            _tool_def(
                "split_reply",
                "只切分回复文本，不发送。用于在发送前查看分条结果；send_reply 实际发送时也会自动切分。",
                {
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "需要切分的回复内容。",
                        },
                    },
                    "required": ["text"],
                },
            ),
        )
        tools.append(
            _tool_def(
                "send_reply",
                "向当前会话发送回复，可附带表情包图片。发送图片时先逐一发送图片再发送切分后的文字；"
                "若设置 merge_text_with_image=true 则文字与第一张图片合并且不切分。"
                "调用后本轮回复视为完成。"
                "允许在同一轮内多次发送，用于长任务的开工与进度。",
                {
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "回复内容，尽量自然简洁。",
                        },
                        "reply_to": {
                            "type": "integer",
                            "description": "可选，要引用回复的消息编号。由 agent 根据上下文自行决定是否需要引用。",
                        },
                        "mention": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "可选，要 @ 的 QQ 号列表。仅在群聊生效，由 agent 自行决定是否 @ 以及 @ 谁。仅在需要提醒通知某人时使用。",
                        },
                        "segments": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选，已经确认过的分条回复内容；每个元素会作为一条消息发送。",
                        },
                        "images": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "可选，要发送的表情包编号列表。发送时先逐一发送图片（每条消息一张图片），再发送切分后的文字。若同时设置 merge_text_with_image=true，文字会与第一张图片合并为一条消息且文字不再切分。",
                        },
                        "merge_text_with_image": {
                            "type": "boolean",
                            "description": "可选，是否将文字与第一张图片合并发送，此时文字不切分。默认为 false。仅在提供了 images 参数时生效。",
                        },
                        "ai_check_approved": {
                            "type": "boolean",
                            "description": "AI回复检查开启时，确认切分结果没有严重问题或歧义后设为 true。",
                        },
                        "send_original": {
                            "type": "boolean",
                            "description": "AI回复检查开启且切分结果有问题但仍要发送时设为 true；会发送原文，不再切分。对于 @ 和引用消息也适用，设置为 true 后不会切分文字。",
                        },
                    },
                    "required": ["text"],
                },
            ),
        )
        if self._markdown_image_converter is not None:
            tools.append(
                _tool_def(
                    "send_long_reply",
                    "发送 Markdown 格式的长回复。这是唯一允许使用 Markdown 格式的发送方式。"
                    "提供 markdown 内容时，系统自动将其转为图片发送。"
                    "如果已有预渲染的图片文件，可提供 image_path 直接发送，"
                    "此时 markdown 仅用于日志记录（仍建议提供以便追溯）。"
                    "适用于包含代码块、表格、数学公式等复杂格式的长文本回复。"
                    "也用于发送解题结果、跨聊天通信结果等需要格式化的内容。"
                    "注意：普通聊天回复请使用 send_reply 发送纯文本（不使用 Markdown）。"
                    "调用后本轮回复视为完成。",
                    {
                        "properties": {
                            "markdown": {
                                "type": "string",
                                "description": "Markdown 格式的回复内容（image_path 为空时必填）。支持标题、列表、代码块、表格等标准 Markdown 语法。",
                            },
                            "image_path": {
                                "type": "string",
                                "description": "可选，预渲染的图片文件路径。提供后直接发送该图片，不再重新渲染。解题任务完成通知中会包含此路径。",
                            },
                            "reply_to": {
                                "type": "integer",
                                "description": "可选，要引用回复的消息编号。",
                            },
                            "mention": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "可选，要 @ 的 QQ 号列表。仅在群聊生效。",
                            },
                            "caption": {
                                "type": "string",
                                "description": "可选，随图片一起发送的简短说明文字。",
                            },
                        },
                        "required": [],
                    },
                ),
            )
        if self._wait is not None:
            tools.append(
                _tool_def(
                    "wait",
                    "等待一段时间让其他人发言。当认为当前话题未结束或聊天还可继续时调用。"
                    "等待期间的新消息会被收集并在返回结果中呈现。默认等待20秒。",
                    {
                        "properties": {
                            "seconds": {
                                "type": "integer",
                                "description": "等待秒数，默认20秒，最大值受配置限制。",
                            },
                        },
                        "required": [],
                    },
                ),
            )
        if self._willing is not None:
            tools.extend(
                [
                    _tool_def(
                        "adjust_reply_willingness",
                        "调整运行时回复意愿设置。\n"
                        "- set_conversation 等动作仅允许作用于当前会话\n"
                        "- set_global 设置全局回复意愿系数(影响所有群聊;私聊固定百分百"
                        "不受影响),需要管理员凭据:先调用凭据 skill 的 request 工具申请"
                        "凭据(action=willing_global,临时调整用 one_time,需要反复调整"
                        "可申请 timed),管理员在聊天中发送凭据文本后重试",
                        {
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": [
                                        "set_global",
                                        "set_conversation",
                                        "remove_conversation",
                                        "add_blacklist",
                                        "remove_blacklist",
                                    ],
                                    "description": "调整动作。set_global 为全局(需凭据);"
                                    "其余仅允许作用于当前会话。",
                                },
                                "conv_id": {
                                    "type": "string",
                                    "description": "可选，会话 ID；不填时使用当前会话。若提供，必须等于当前会话 ID。",
                                },
                                "value": {
                                    "type": "number",
                                    "description": "数值系数（set_global / set_conversation 必填）。",
                                },
                            },
                            "required": ["action"],
                        },
                    ),
                    _tool_def(
                        "get_willingness_config",
                        "查看当前运行时回复意愿设置。",
                        {"properties": {}, "required": []},
                    ),
                    _tool_def(
                        "manage_willing_config",
                        "查看/编辑 config.toml 中的全局回复意愿系数(agent 模式生效项为 "
                        "willing_agent_global_coefficient,common 模式为 "
                        "willing_global_coefficient)。编辑后写回配置文件并热重载,立即生效"
                        "并持久化(重启不丢失)。需要超级管理员凭据:先调用凭据 skill 的 "
                        "request 工具申请凭据(action=willing_config),管理员签发后重试。",
                        {
                            "properties": {
                                "action": {
                                    "type": "string",
                                    "enum": ["get", "set"],
                                    "description": "get=查看当前配置值;set=修改(需 value)",
                                },
                                "target": {
                                    "type": "string",
                                    "enum": ["agent", "common"],
                                    "description": "可选，编辑哪个模式下的系数；"
                                    "默认使用当前回复模式对应的系数。",
                                },
                                "value": {
                                    "type": "number",
                                    "description": "set 时必填，新的系数值（0.0-1.0）。",
                                },
                            },
                            "required": ["action"],
                        },
                    ),
                ]
            )
        if self._send_emoji is not None or self._emoji is not None:
            tools.append(
                _tool_def(
                    "send_emoji",
                    "向当前会话发送一个表情包图片（可附带可选文字）。"
                    "仅用于只发送表情包而不发送独立文字回复的场景。"
                    "若需要同时发送文字回复和表情包，请使用 send_reply 工具并通过 images 参数指定表情包编号。"
                    "编号用 list_emojis 或 search_custom_emoji 查看（按使用次数从少到多排列，优先用不常用的）。",
                    {
                        "properties": {
                            "number": {
                                "type": "integer",
                                "description": "表情包编号，用 list_emojis / search_custom_emoji 获取。",
                            },
                            "text": {
                                "type": "string",
                                "description": "可选，随表情包一起发送的文字。",
                            },
                        },
                        "required": ["number"],
                    },
                )
            )
        if self._emoji is not None:
            tools.append(
                _tool_def(
                    "list_emojis",
                    "分页查看自定义表情包库（非QQ表情）。返回的编号可直接用于 send_emoji 的 number "
                    "或 send_reply 的 images。列表按使用次数从少到多排列（使用次数均衡器），"
                    "因此优先选前面的编号。不确定用哪个表情包时先调用本工具；"
                    "已经有关键词时用 search_custom_emoji 更省 token。",
                    {
                        "properties": {
                            "offset": {
                                "type": "integer",
                                "description": "从第几个开始（0 起）。翻页时用上一次结果里的提示值。",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "本次返回条数，默认取配置的表情包每页数量。",
                            },
                        },
                        "required": [],
                    },
                ),
            )
            tools.append(
                _tool_def(
                    "search_custom_emoji",
                    "按关键词搜索自定义表情包（非QQ表情）。在表情包描述和文件名中匹配关键词，"
                    "结果按使用次数从少到多排列。已有关键词时优先用本工具；"
                    "没有明确关键词、想看有哪些表情包时用 list_emojis。",
                    {
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": '搜索关键词，如"狗"、"贴纸"、"猫"等。',
                            },
                        },
                        "required": ["keyword"],
                    },
                ),
            )
        if self._react_emoji is not None:
            tools.append(
                _tool_def(
                    "react_emoji",
                    "对指定消息做出QQ表情回应（emoji like）。调用前如果不确定表情ID，"
                    "可先用 search_qq_emoji 工具搜索表情关键词获取表情ID。",
                    {
                        "properties": {
                            "message_number": {
                                "type": "integer",
                                "description": "要回应的消息编号。",
                            },
                            "emoji_id": {
                                "type": "integer",
                                "description": "QQ表情的数字ID。常用表情如：76(赞)、66(爱心)、46(猪头)、182(笑哭)、128(猪)。",
                            },
                        },
                        "required": ["message_number", "emoji_id"],
                    },
                ),
            )
        if self._search_emoji is not None:
            tools.append(
                _tool_def(
                    "search_qq_emoji",
                    "搜索QQ内置表情。按关键词搜索表情名称，返回匹配的表情ID和名称列表。"
                    "找到合适的表情后，可使用 react_emoji 工具发送表情回应。",
                    {
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "搜索关键词，如「猪」、「赞」、「笑哭」等。",
                            },
                        },
                        "required": ["keyword"],
                    },
                ),
            )
        if self._tts_service is not None and getattr(
            self._tts_service, "enabled", False
        ):
            tools.append(
                _tool_def(
                    "speak",
                    "将文本转为语音消息并发送到当前会话。适合用于需要语音回复、朗读内容等场景。",
                    {
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "需要转为语音的文本内容。",
                            },
                        },
                        "required": ["text"],
                    },
                ),
            )
        if self._poke_user is not None:
            tools.append(
                _tool_def(
                    "poke_user",
                    "戳一戳指定的QQ用户。在群聊中自动使用群戳一戳，在私聊中自动使用好友戳一戳。"
                    "只需提供目标QQ号，Bot会自动判断会话类型。",
                    {
                        "properties": {
                            "user_id": {
                                "type": "integer",
                                "description": "要戳一戳的目标QQ号。",
                            },
                        },
                        "required": ["user_id"],
                    },
                ),
            )
        if (
            self._skill_manager is not None
            or self._drawing_manager is not None
            or self._scheduled_task_manager is not None
            or self._notification_hub is not None
        ):
            tools.append(
                _tool_def(
                    "check_background_tasks",
                    "查询当前聊天流的后台任务状态（可扩展，当前支持绘图任务）。"
                    "返回：后台任务列表及各任务的状态、进行中/冷却/最近完成/失败等信息；"
                    "活跃的会话工具（含已运行时长）；排队的会话工具；"
                    "最近完成的会话工具（含状态和结果摘要，防止重复执行已完成的相同操作）。"
                    "在决定是否调用 generate_image 之前，必须优先调用此工具检查是否有正在进行的后台任务，避免重复提交。",
                    {
                        "properties": {},
                        "required": [],
                    },
                )
            )
        # cancel_task：手动取消后台任务/会话工具
        tools.append(
            _tool_def(
                "cancel_task",
                "手动取消后台任务或会话工具。"
                "可取消正在执行的会话工具（如下载、图片解析）和其排队任务，"
                "也可取消绘图冷却限制。"
                "适用于用户想中止当前操作、或需要立即执行其他操作的场景。",
                {
                    "properties": {
                        "task_type": {
                            "type": "string",
                            "enum": ["session_tool", "drawing_cooldown"],
                            "description": "要取消的任务类型：session_tool（取消会话工具的当前任务和排队）、drawing_cooldown（取消绘图冷却）",
                        },
                    },
                    "required": ["task_type"],
                },
            )
        )
        if self._drawing_manager is not None:
            tools.append(
                _tool_def(
                    "check_last_drawing",
                    "查看当前聊天流上一次绘图任务的详细记录。"
                    "包括：任务ID、状态（完成/失败/超时）、图片ID、提示词、错误信息等。"
                    "用于确认上一次绘图是否成功、查看生成的图片ID或失败原因。",
                    {
                        "properties": {},
                        "required": [],
                    },
                )
            )
        if self._scheduled_task_manager is not None:
            tools.append(
                _tool_def(
                    "mark_scheduled_task_complete",
                    "标记指定 UUID 的定时任务已完成。定时任务提醒会提供任务 UUID；"
                    "当你已经完成该提醒对应的事项，或用户明确表示该事项已完成时调用。"
                    "如果提醒内容注明任务配置为一次性通知且系统已自动完成当前触发窗口，发送提醒后不要再调用本工具。"
                    "对于持续通知的提醒任务和生日祝福任务，只要已经发送提醒或祝福消息，就应调用本工具标记完成；"
                    "对于持续提醒类任务，如果已经提醒三到五次仍然没有用户反馈，发送最后一次自然提醒后也应调用本工具结束本次任务。",
                    {
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "定时任务提醒中提供的 UUID。",
                            },
                        },
                        "required": ["task_id"],
                    },
                )
            )
        # 合并 Skill 系统的工具定义：常驻技能 + 本管线已按需加载的技能。
        if self._skill_manager is not None:
            skill_tools = (
                self._activation.tools() if self._activation is not None else []
            )
            tools.extend(skill_tools)
            capture = getattr(self._skill_manager, "capture_execution_token", None)
            if callable(capture):
                tokens = dict(self._skill_tokens)
                for definition in skill_tools:
                    token = capture(definition["function"]["name"])
                    if token is not None:
                        tokens[definition["function"]["name"]] = token
                self._skill_tokens = tokens
        # allowed-tools 白名单：非空时过滤掉「不在白名单且不在 allowed_tools 中」的工具
        if self._allowed_tools:
            allowed = _SKILL_GUARD_BASE_TOOLS | self._allowed_tools
            tools = [t for t in tools if t["function"]["name"] in allowed]
        tools = [t for t in tools if self.is_tool_authorized(t["function"]["name"])]
        names: set[str] = set()
        for tool in tools:
            name = tool["function"]["name"]
            if name in names:
                raise ValueError(f"重复的最终工具定义: {name}")
            names.add(name)
        return tools

    def _shared_agent_tools(self) -> Any:
        from neobot_app.skills.agent_tools_skill import AgentToolsSkill
        lookup = getattr(self._skill_manager, "get", None)
        shared = lookup("agent_tools") if callable(lookup) else None
        return shared if isinstance(shared, AgentToolsSkill) else None

    def agent_tool_capabilities(self) -> frozenset[str]:
        """Authorize program bindings independently of their wire presentation."""
        shared = self._shared_agent_tools()
        if shared is None:
            return frozenset()
        names = set(shared.runtime.capability_names())
        if shared.runtime.config.ptc_enabled:
            names.add("run_code")
        return frozenset(name for name in names if self._policy_authorized(f"agent_tools__{name}"))

    def is_tool_authorized(self, name: str) -> bool:
        """主 Agent 的授权判定:能力存在 + 去重,与任务工具模式(native/PTC)无关。

        任务工具模式只决定「任务型 Agent(解题/子 Agent)如何编排」;
        主回复管线始终直接调用业务工具,不因切到 PTC 而把工具换成单个 run_code。
        """
        if not self._policy_authorized(name):
            return False
        shared = self._shared_agent_tools()
        if shared is not None:
            from neobot_app.agent_tools.modes import LEGACY_FILE_ALIASES
            if name.startswith("agent_tools__"):
                return name.removeprefix("agent_tools__") in shared.runtime.capability_names()
            if name in LEGACY_FILE_ALIASES and LEGACY_FILE_ALIASES[name] in shared.runtime.capability_names():
                return False
        return True

    def _policy_authorized(self, name: str) -> bool:
        """Apply the skill allowlist and live model capability policy, not mode filtering."""
        native_vision = getattr(self._native_vision_provider, "native_vision", False) is True
        if name.startswith("image_context__") and not native_vision:
            return False
        if native_vision and name in {
            "image_parse__parse_image",
            "drawing__inspect_image",
            "user_profile__analyze_user_avatar",
        }:
            return False
        return not self._allowed_tools or name in (
            _SKILL_GUARD_BASE_TOOLS | self._allowed_tools
        )

    def authorization_error(self, name: str) -> str:
        if self._allowed_tools and name not in (_SKILL_GUARD_BASE_TOOLS | self._allowed_tools):
            return f"Error: 工具 {name} 不在当前技能允许的工具列表内"
        shared = self._shared_agent_tools()
        if shared is not None:
            from neobot_app.agent_tools.modes import LEGACY_FILE_ALIASES
            if name in LEGACY_FILE_ALIASES:
                return f"Error: 工具 {name} 已去重，请使用 agent_tools__{LEGACY_FILE_ALIASES[name]}（PTC时在run_code内调用）"
            if name.startswith("agent_tools__") and name.removeprefix("agent_tools__") not in shared.runtime.capability_names():
                return f"Error: 工具 {name} 不存在或当前部署未启用"
        return f"Error: 工具 {name} 与当前模型视觉能力不匹配，请使用当前提供的图片工具"

    async def execute(self, name: str, args: dict) -> str:
        # allowed-tools 白名单拦截（须在 skills__read_* 等所有路由之前）
        if not self.is_tool_authorized(name):
            return self.authorization_error(name)
        if not name.startswith("agent_tools__") and self._skill_manager is not None:
            from neobot_app.skills.agent_tools_skill import AgentToolsSkill
            from neobot_app.agent_tools.contracts import ToolContext
            lookup = getattr(self._skill_manager, "get", None)
            shared = lookup("agent_tools") if callable(lookup) else None
            if isinstance(shared, AgentToolsSkill) and self._conv_kind in {"group", "private"} and str(self._conv_id).isdigit():
                flow = f"{self._conv_kind}:{self._conv_id}"
                context = ToolContext(owner=f"{flow}:main", chat_flow_id=flow)
                safe = {"cancel", "send_reply", "split_reply", "wait", "send_long_reply",
                        "credential__request", "credential__check", "skills__read_manifest",
                        "skills__read_resource", "skills__view_instructions", "check_background_tasks",
                        "cancel_task", "agents__list", "image_context__add_image", "image_parse__parse_image",
                        "sandbox_manager__read_file", "sandbox_manager__list_files",
                        "sandbox_manager__glob_files", "sandbox_manager__grep_files"}
                if shared.runtime.state.is_planning(context) and name not in safe:
                    return json.dumps({"ok": False, "code": "PLAN_MODE", "error": "计划待审批，不能通过旧工具绕过执行限制"}, ensure_ascii=False)
        if name == "cancel":
            return await self._execute_cancel(args)
        if name == "split_reply":
            return self._execute_split_reply(args)
        if name == "send_reply":
            return await self._execute_send_reply(args)
        if name == "wait":
            return await self._execute_wait(args)
        if name == "adjust_reply_willingness":
            return self._execute_adjust_willingness(args)
        if name == "get_willingness_config":
            return self._execute_get_willingness_config()
        if name == "manage_willing_config":
            return await self._execute_manage_willing_config(args)
        if name == "send_emoji":
            return await self._execute_send_emoji(args)
        if name == "list_emojis":
            return self._execute_list_emojis(args)
        if name == "search_custom_emoji":
            return self._execute_search_custom_emoji(args)
        if name == "react_emoji":
            return await self._execute_react_emoji(args)
        if name == "search_qq_emoji":
            return self._execute_search_qq_emoji(args)
        if name == "speak":
            return await self._execute_speak(args)
        if name == "poke_user":
            return await self._execute_poke_user(args)
        if name == "check_background_tasks":
            return await self._execute_check_background_tasks(args)
        if name == "cancel_task":
            return await self._execute_cancel_task(args)
        if name == "check_last_drawing":
            return await self._execute_check_last_drawing(args)
        if name == "mark_scheduled_task_complete":
            return await self._execute_mark_scheduled_task_complete(args)
        if name == "send_long_reply":
            return await self._execute_send_long_reply(args)
        # Markdown 技能读取（优先于 SkillManager 的 __ 路由）
        if name == "skills__read_manifest":
            return self._read_skill_manifest(args)
        if name == "skills__read_resource":
            return self._read_skill_resource(args)
        # 内置技能操作说明查看（按需读取,默认只注入一行摘要）
        if name == "skills__view_instructions":
            return self._view_skill_instructions(args)
        if name == "skills__load_tools":
            return self._load_skill_tools(args)
        # Skill 系统路由（优先于 ToolError）
        if self._skill_manager is not None and "__" in name:
            token = self._skill_tokens.get(name)
            capture = getattr(self._skill_manager, "capture_execution_token", None)
            if token is None and callable(capture):
                # Direct executor users may execute before asking for definitions.
                token = capture(name)
                if token is None:
                    return f"未知工具: {name}"
            # 自动注入当前对话上下文，skill 工具不需要也不应自行指定。
            # 模型伪造的内部键（pipeline_key/_numbering_mapping/_delegate_context）
            # 一律剥离，由会话状态覆盖。
            enriched = {
                key: value
                for key, value in dict(args).items()
                if key not in _SKILL_INTERNAL_KEYS
            }
            if self._conv_kind and self._conv_id:
                enriched["pipeline_key"] = f"{self._conv_kind}:{self._conv_id}"
            if self._current_user_id is not None:
                # 当前会话用户 QQ(凭据申请等需要记录请求者)
                enriched["_requester_id"] = self._current_user_id
            if self._numbering is not None:
                mapping = getattr(self._numbering, "mapping", None)
                if isinstance(mapping, dict):
                    enriched["_numbering_mapping"] = mapping
            if self._chat_context and name.startswith("agents__"):
                # 仅子 Agent 委派需要当前对话上下文，避免污染其他 skill 工具参数
                enriched["_delegate_context"] = self._chat_context
            if self._skill_manager.is_session_tool(name):
                return await self._execute_session_tool(name, enriched, token)
            return await self._execute_skill(name, enriched, token)
        raise ToolError(f"Unknown reply tool: {name}")

    async def _execute_skill(self, name: str, args: dict, token: Any) -> str:
        if not name.startswith(("agent_tools__", "agents__", "background_trigger__", "sandbox_manager__")):
            if token is None:
                return await self._skill_manager.execute(name, args)
            return await self._skill_manager.execute(name, args, token=token)
        from neobot_app.agent_tools.contracts import ToolContext
        from neobot_app.agent_tools.invocation import CURRENT_INVOCATION, ToolInvocation

        if self._conv_kind not in {"group", "private"} or not str(self._conv_id).isdigit():
            from neobot_app.skills.agent_tools_skill import AgentToolsSkill
            lookup = getattr(self._skill_manager, "get", None)
            shared = lookup("agent_tools") if callable(lookup) else None
            if name.startswith("agent_tools__") or isinstance(shared, AgentToolsSkill):
                return json.dumps({"ok": False, "code": "CONTEXT_REQUIRED", "error": "缺少可信聊天身份"})
            # Preserve host-only legacy callers when the shared runtime is absent.
            if token is None:
                return await self._skill_manager.execute(name, args)
            return await self._skill_manager.execute(name, args, token=token)
        flow = f"{self._conv_kind}:{self._conv_id}"
        definitions = self.definitions()
        allowed = self.agent_tool_capabilities()
        context = ToolContext(owner=f"{flow}:main", chat_flow_id=flow, user_id=self._current_user_id,
                              human_request=self._human_request, allowed_tools=allowed)
        external = [d for d in definitions if not d["function"]["name"].startswith("agent_tools__")]
        image_parts: list[dict] = []
        async def dispatch(external_name: str, external_args: dict) -> Any:
            result = await self.execute(external_name, external_args)
            image_parts.extend(getattr(result, "image_parts", []))
            return result
        invocation = ToolInvocation(context, dispatch, external, self._agent_history)
        marker = CURRENT_INVOCATION.set(invocation)
        try:
            if token is None:
                result = await self._skill_manager.execute(name, args)
            else:
                result = await self._skill_manager.execute(name, args, token=token)
            if image_parts:
                from neobot_app.skills.image_context_skill import ImageContextResult
                return ImageContextResult(str(result), image_parts)
            return result
        finally:
            CURRENT_INVOCATION.reset(marker)

    async def _execute_session_tool(
        self, name: str, args: dict, token: Any = None
    ) -> str:
        """将会话工具提交到后台执行（同一管线最多 1 运行 + 1 排队）。"""
        if self._closed:
            return json.dumps(
                {
                    "ok": False,
                    "status": "closed",
                    "tool": name,
                    "message": "回复执行器已关闭，拒绝提交新的会话工具。",
                },
                ensure_ascii=False,
            )
        pipeline_key = str(args.get("pipeline_key", "") or "")
        if not pipeline_key:
            return json.dumps(
                {
                    "ok": False,
                    "status": "missing_pipeline",
                    "tool": name,
                    "message": "无法确定当前会话，会话工具已拒绝执行。",
                },
                ensure_ascii=False,
            )
        conv_kind = self._conv_kind
        conv_id = self._conv_id

        has_running = any(
            info["pipeline_key"] == pipeline_key
            for info in self._session_task_info.values()
        )

        if has_running:
            if pipeline_key in self._session_task_queue:
                return json.dumps(
                    {
                        "ok": False,
                        "status": "queue_full",
                        "tool": name,
                        "message": (
                            "当前已有会话工具正在执行且已有排队任务（最多排队1个）。"
                            "请等待当前任务完成后重试，或调用 cancel_task 取消当前任务/排队。"
                        ),
                    },
                    ensure_ascii=False,
                )
            self._session_task_queue[pipeline_key] = {
                "name": name,
                "args": args,
                "token": token,
                "conv_kind": conv_kind,
                "conv_id": conv_id,
                "queued_at": monotonic_seconds(),
            }
            self._logger.info(
                "会话工具已加入排队",
                tool=name,
                pipeline_key=pipeline_key,
            )
            return json.dumps(
                {
                    "ok": True,
                    "status": "queued",
                    "tool": name,
                    "message": (
                        "已有会话工具正在执行，当前任务已加入排队。"
                        "系统会在当前任务完成后自动执行排队的任务。请立即结束本轮回复。"
                    ),
                },
                ensure_ascii=False,
            )

        return self._start_session_tool(
            name, args, pipeline_key, conv_kind, conv_id, token
        )

    def _start_session_tool(
        self,
        name: str,
        args: dict,
        pipeline_key: str,
        conv_kind: str,
        conv_id: str,
        token: Any = None,
    ) -> str:
        """创建并启动会话工具任务，完成后自动处理排队。"""
        if self._closed:
            return json.dumps(
                {
                    "ok": False,
                    "status": "closed",
                    "tool": name,
                    "message": "回复执行器已关闭，拒绝提交新的会话工具。",
                },
                ensure_ascii=False,
            )
        task = asyncio.create_task(
            self._run_session_tool(
                name=name,
                args=args,
                pipeline_key=pipeline_key,
                conv_kind=conv_kind,
                conv_id=conv_id,
                token=token,
            )
        )
        tid = id(task)
        self._session_tasks.add(task)
        self._session_task_info[tid] = {
            "name": name,
            "pipeline_key": pipeline_key,
            "started_at": monotonic_seconds(),
        }

        def _cleanup(t: asyncio.Task) -> None:
            self._session_tasks.discard(t)
            info = self._session_task_info.pop(tid, None)
            # 关闭后不得消费排队项、不得再启动新任务
            if self._closed:
                return
            if not t.cancelled():
                exc = t.exception()
                if exc is not None:
                    self._logger.warning(
                        "会话工具任务异常",
                        tool=name,
                        pipeline_key=info["pipeline_key"] if info else "",
                        error_type=type(exc).__name__,
                    )
                    if info is not None:
                        started = info.get("started_at", 0.0) or 0.0
                        self._record_session_completion(
                            info["name"],
                            info["pipeline_key"],
                            "error",
                            "工具执行异常",
                            max(0.0, monotonic_seconds() - started),
                        )
            if info:
                pk = info["pipeline_key"]
                if pk and pk in self._session_task_queue:
                    queued = self._session_task_queue.pop(pk)
                    self._logger.info(
                        "会话工具排队任务开始执行",
                        tool=queued["name"],
                        pipeline_key=pk,
                    )
                    self._start_session_tool(
                        name=queued["name"],
                        args=queued["args"],
                        pipeline_key=pk,
                        conv_kind=queued["conv_kind"],
                        conv_id=queued["conv_id"],
                        token=queued.get("token"),
                    )

        task.add_done_callback(_cleanup)

        self._logger.info(
            "会话工具已提交（后台执行）",
            tool=name,
            pipeline_key=pipeline_key,
        )

        return json.dumps(
            {
                "ok": True,
                "status": "session_submitted",
                "tool": name,
                "message": (
                    "任务已提交到后台执行，完成后会自动通知你。"
                    "请立即结束本轮回复，不要等待、不要轮询、不要调用 wait 工具。"
                ),
            },
            ensure_ascii=False,
        )

    async def _execute_cancel_task(self, args: dict) -> str:
        """手动取消后台任务或会话工具。"""
        task_type = str(args.get("task_type", ""))
        if not self._conv_kind or not self._conv_id:
            return json.dumps(
                {"ok": False, "error": "无法获取当前会话信息"}, ensure_ascii=False
            )
        pipeline_key = f"{self._conv_kind}:{self._conv_id}"

        if task_type == "session_tool":
            cancelled: list[str] = []
            # 取消排队中的会话工具
            if pipeline_key in self._session_task_queue:
                queued = self._session_task_queue.pop(pipeline_key)
                cancelled.append(f"排队任务 {queued['name']}")
            # 取消运行中的会话工具
            cancelled_running = 0
            for tid, info in list(self._session_task_info.items()):
                if info["pipeline_key"] == pipeline_key:
                    for task in list(self._session_tasks):
                        if id(task) == tid:
                            task.cancel()
                            cancelled_running += 1
                            break
            if cancelled_running > 0:
                cancelled.append(f"运行中任务({cancelled_running}个)")

            if not cancelled:
                return json.dumps(
                    {
                        "ok": True,
                        "message": "当前管线没有正在执行或排队的会话工具",
                    },
                    ensure_ascii=False,
                )
            self._logger.info(
                "主Agent取消会话工具",
                pipeline_key=pipeline_key,
                cancelled=cancelled,
            )
            return json.dumps(
                {
                    "ok": True,
                    "cancelled": cancelled,
                    "message": f"已取消：{', '.join(cancelled)}。排队的任务（如有）将不会执行。",
                },
                ensure_ascii=False,
            )

        if task_type == "drawing_cooldown":
            if self._drawing_manager is None:
                return json.dumps(
                    {"ok": False, "error": "绘图系统未配置"}, ensure_ascii=False
                )
            self._drawing_manager.cancel_cooldown(pipeline_key)
            self._logger.info("主Agent取消绘图冷却", pipeline_key=pipeline_key)
            return json.dumps(
                {"ok": True, "message": "已取消当前管线的绘图冷却限制"},
                ensure_ascii=False,
            )

        return json.dumps(
            {"ok": False, "error": f"未知任务类型: {task_type}"}, ensure_ascii=False
        )

    @staticmethod
    def _parse_session_timeout(raw: Any) -> int:
        """防御性解析模型传入的 timeout_seconds 并钳制到 [1, 1800]。

        数值零、空值、布尔值、Infinity/NaN 与畸形输入回退默认 300；
        负数钳制为 1，正小数向零取整。
        """
        if raw is None or isinstance(raw, bool):
            return 300
        try:
            if isinstance(raw, int):
                parsed = raw
                if parsed == 0:
                    return 300
            else:
                numeric = float(raw)
                if not math.isfinite(numeric) or numeric == 0:
                    return 300
                parsed = int(numeric)
        except (TypeError, ValueError, OverflowError):
            return 300
        return max(1, min(parsed, 1800))

    @staticmethod
    def _classify_session_result(result_text: str) -> tuple[bool, str]:
        """Return success and a safe failure summary for a session result."""
        parsed: Any = None
        parsed_json = False
        try:
            parsed = json.loads(result_text)
            parsed_json = True
        except (json.JSONDecodeError, TypeError):
            pass

        bare_text = parsed if isinstance(parsed, str) else result_text
        stripped = bare_text.strip()
        if stripped.startswith(
            _SESSION_FAILURE_PREFIXES
        ) or stripped.lower().startswith("error:"):
            return False, stripped

        if not parsed_json or not isinstance(parsed, dict):
            # Empty JSON containers are valid successful results.
            return True, ""

        for key, value in parsed.items():
            if str(key).casefold() in _SESSION_ERROR_KEYS:
                return False, _bounded_text(value, 200)

        status = parsed.get("status")
        if isinstance(status, str) and status.strip().casefold() in {
            "cancelled",
            "error",
            "failed",
            "failure",
            "timeout",
        }:
            return False, status.strip()

        if "ok" not in parsed:
            return True, ""
        ok = parsed["ok"]
        if isinstance(ok, bool):
            success = ok
        elif ok is None:
            success = False
        elif isinstance(ok, (int, float)):
            success = bool(ok) and (not isinstance(ok, float) or math.isfinite(ok))
        elif isinstance(ok, str):
            success = ok.strip().casefold() not in {
                "false",
                "no",
                "0",
                "0.0",
                "none",
                "",
            }
        else:
            success = True
        return success, "" if success else result_text

    async def _run_session_tool(
        self,
        name: str,
        args: dict,
        pipeline_key: str,
        conv_kind: str,
        conv_id: str,
        token: Any = None,
    ) -> None:
        """在后台执行会话工具并将结果发布到 NotificationHub。

        timeout_seconds 从 args 读取（默认 300，最大 1800），用于 asyncio.wait_for。
        额外 +10 秒留给 NotificationHub publish 等收尾操作。
        """
        started_at = monotonic_seconds()
        timeout_seconds = self._parse_session_timeout(args.get("timeout_seconds", 300))
        status = "completed"
        result_summary = ""
        notification: str | None = None

        try:
            result = await asyncio.wait_for(
                self._execute_skill(name, args, token),
                timeout=timeout_seconds + 10,
            )
            result_text = _bounded_text(result)
            success, error_msg = self._classify_session_result(result_text)
            if result_text.startswith("工具不可用或已更新 ["):
                success = False
                error_msg = result_text

            if success:
                result_summary = result_text[:200]
                notification = (
                    f"<会话工具结果>\n"
                    f"工具 {name} 已完成：\n"
                    f"{result_text}\n"
                    f"请根据此结果继续处理用户的请求。\n"
                    f"</会话工具结果>"
                )
            else:
                status = "failed"
                result_summary = (error_msg or result_text)[:200]
                notification = (
                    f"<会话工具结果>\n"
                    f"工具 {name} 执行失败：{error_msg or result_text}\n"
                    f"请告知用户操作失败，并根据情况尝试替代方案。\n"
                    f"</会话工具结果>"
                )

            self._logger.info(
                "会话工具任务完成",
                tool=name,
                pipeline_key=pipeline_key,
                success=success,
            )
        except asyncio.TimeoutError:
            status = "timeout"
            result_summary = f"超时（{timeout_seconds}秒）"
            notification = (
                f"<会话工具结果>\n"
                f"工具 {name} 执行超时（{timeout_seconds}秒）。\n"
                f"请告知用户下载超时，建议减小文件或稍后重试。\n"
                f"如需更长时间，可通过 timeout_seconds 参数设置（最长 1800 秒）。\n"
                f"</会话工具结果>"
            )
            self._logger.warning(
                "会话工具任务超时",
                tool=name,
                pipeline_key=pipeline_key,
                timeout_seconds=timeout_seconds,
            )
        except asyncio.CancelledError:
            status = "cancelled"
            result_summary = "任务被取消"
            raise
        except Exception as exc:
            status = "error"
            result_summary = "工具执行异常"
            notification = (
                f"<会话工具结果>\n"
                f"工具 {name} 执行异常。\n"
                f"请告知用户操作失败。\n"
                f"</会话工具结果>"
            )
            self._logger.error(
                "会话工具任务异常",
                tool=name,
                pipeline_key=pipeline_key,
                error_type=type(exc).__name__,
            )
        finally:
            elapsed = monotonic_seconds() - started_at
            self._record_session_completion(
                name, pipeline_key, status, result_summary, elapsed
            )

        if (
            notification is not None
            and self._notification_hub is not None
            and conv_kind
            and conv_id
        ):
            try:
                await self._notification_hub.publish(
                    source="session_tool",
                    kind=conv_kind,
                    conversation_id=conv_id,
                    content=notification,
                    manager_name="session_tool",
                    metadata={"tool_name": name, "pipeline_key": pipeline_key},
                )
            except Exception:
                self._logger.warning(
                    "会话工具通知发布失败",
                    tool=name,
                    pipeline_key=pipeline_key,
                )

    _MAX_COMPLETED_HISTORY = 5

    def _record_session_completion(
        self,
        name: str,
        pipeline_key: str,
        status: str,
        summary: str,
        elapsed: float,
    ) -> None:
        """记录已完成的会话工具，供 check_background_tasks 展示。"""
        if pipeline_key not in self._session_completed:
            self._session_completed[pipeline_key] = []
        history = self._session_completed[pipeline_key]
        history.append(
            {
                "tool": name,
                "status": status,
                "summary": summary,
                "elapsed_seconds": round(elapsed),
                "completed_at": monotonic_seconds(),
            }
        )
        if len(history) > self._MAX_COMPLETED_HISTORY:
            self._session_completed[pipeline_key] = history[
                -self._MAX_COMPLETED_HISTORY :
            ]

    async def _execute_cancel(self, args: dict) -> str:
        if self._cancel is None:
            return "错误：cancel 处理器未配置"
        reason = str(args.get("reason") or "").strip()
        await self._cancel(reason=reason if reason else None)
        return "回复已取消" if not reason else f"回复已取消：{reason}"

    def _execute_split_reply(self, args: dict) -> str:
        text = str(args.get("text") or "")
        if not text.strip():
            return "错误：回复内容不能为空"
        result = self._preview_split(text)
        payload = {
            "ok": True,
            "original_text": result.original_text,
            "messages": result.messages,
            "fallback_used": result.fallback_used,
            "reason": result.reason,
        }
        return json.dumps(payload, ensure_ascii=False)

    async def _execute_send_reply(self, args: dict) -> str:
        if self._send_reply is None:
            return "错误：send_reply 处理器未配置"
        text = str(args.get("text") or "")
        if not text.strip():
            return "错误：回复内容不能为空"
        segments = self._normalize_segments(args.get("segments"))
        send_original = bool(args.get("send_original") is True)
        ai_check_approved = bool(args.get("ai_check_approved") is True)
        merge_text_with_image = bool(args.get("merge_text_with_image") is True)
        raw_images = args.get("images")
        images: list[int] | None = None
        if raw_images is not None:
            if not isinstance(raw_images, list):
                return f"错误：images 必须为列表，收到 {type(raw_images).__name__}"
            try:
                images = [int(n) for n in raw_images]
            except (ValueError, TypeError):
                return f"错误：images 必须为整数列表，收到 {raw_images}"
        reply_to = args.get("reply_to")
        if reply_to is not None:
            try:
                reply_to = int(reply_to)
            except (ValueError, TypeError):
                return f"错误：reply_to 必须为整数，收到 {reply_to}"
        raw_mention = args.get("mention")
        mention: list[int] | None = None
        if raw_mention:
            try:
                mention = [int(qq) for qq in raw_mention]
            except (ValueError, TypeError):
                return f"错误：mention 必须为整数列表，收到 {raw_mention}"

        if self._ai_reply_check and not (
            send_original or ai_check_approved or segments
        ):
            result = self._preview_split(text)
            return self._build_ai_check_prompt(result)

        if (
            self._ai_reply_check_lightweight
            and not self._ai_reply_check
            and not (send_original or ai_check_approved or segments)
        ):
            result = self._preview_split(text)
            if result.fallback_used:
                return self._build_ai_check_prompt(result)

        if (
            self._enable_ai_reply_regenerate
            and not (send_original or merge_text_with_image)
            and not segments
        ):
            pre_check = self._preview_split(text)
            if pre_check.fallback_used:
                return (
                    f"回复被拦截：{pre_check.reason}"
                    f"（字符上限 {self._long_reply_max_length}，"
                    f"分句上限 {self._long_reply_max_sentence_count}）。"
                    f"请精简为更短的版本后重新调用 send_reply。"
                )

        if (
            self._enable_ai_reply_regenerate
            and not (send_original or merge_text_with_image)
            and ai_check_approved
        ):
            pre_check = self._preview_split(text)
            if pre_check.fallback_used:
                return (
                    f"回复被拦截：{pre_check.reason}"
                    f"（字符上限 {self._long_reply_max_length}，"
                    f"分句上限 {self._long_reply_max_sentence_count}）。"
                    f"当前切分结果为默认回复，并非你的原意，请精简为更短的版本后重新调用 send_reply。"
                )

        await self._send_reply(
            text=text,
            reply_to=reply_to,
            mention=mention,
            segments=segments,
            send_original=send_original,
            images=images,
            merge_text_with_image=merge_text_with_image,
        )
        if segments:
            seg_text = "\n---\n".join(segments)
            return f"已发送 {len(segments)} 条消息：\n{seg_text}"
        if send_original:
            display = text.strip()
            return f"已发送原文：{display[:300]}{'...' if len(display) > 300 else ''}"
        preview = self._preview_split(text)
        preview_text = "\n---\n".join(preview.messages)
        if images:
            return f"已发送（{len(images)} 张图片 + {len(preview.messages)} 条文字）：\n{preview_text}"
        return f"已发送 {len(preview.messages)} 条消息：\n{preview_text}"

    async def _execute_wait(self, args: dict) -> str:
        if self._wait is None:
            return "错误：wait 处理器未配置"
        raw_seconds = args.get("seconds", 20)
        if raw_seconds is None:
            seconds = 20
        elif isinstance(raw_seconds, bool):
            return f"错误：seconds 必须为整数，收到 {raw_seconds}"
        else:
            try:
                if isinstance(raw_seconds, float) and not raw_seconds.is_integer():
                    raise ValueError
                seconds = int(raw_seconds)
            except (ValueError, TypeError, OverflowError):
                return f"错误：seconds 必须为整数，收到 {raw_seconds}"
        if seconds < 0:
            return f"错误：seconds 不能为负数，收到 {raw_seconds}"

        now = monotonic_seconds()
        elapsed = now - self._last_wait_time
        if self._last_wait_time > 0 and elapsed < self._wait_cooldown_seconds:
            remaining = int(self._wait_cooldown_seconds - elapsed)
            return (
                f"wait 处于冷却中，还需等待 {remaining} 秒后才可再次调用。"
                "【提示】如果是在等待后台任务完成，请结束本轮回复，系统会在完成后通知你。"
            )
        self._last_wait_time = now
        return await self._wait(seconds=seconds)

    def _execute_adjust_willingness(self, args: dict) -> str:
        if self._willing is None:
            return "错误：回复意愿服务未配置"
        action = str(args.get("action") or "")
        if action == "set_global":
            return self._execute_set_global_willing(args)
        current_conv_id = str(self._conv_id or "").strip()
        requested_conv_id = str(args.get("conv_id") or current_conv_id).strip()
        if action in {
            "set_conversation",
            "remove_conversation",
            "add_blacklist",
            "remove_blacklist",
        }:
            if not current_conv_id:
                return "错误：无法确定当前会话 ID"
            if requested_conv_id != current_conv_id:
                return "错误：只能调整当前会话的回复意愿"
        if action == "set_conversation":
            value = args.get("value")
            if value is None:
                return "错误：set_conversation 需要提供 value 参数"
            return self._willing.set_runtime_conversation_coefficient(
                current_conv_id, float(value)
            )
        if action == "remove_conversation":
            return self._willing.remove_runtime_conversation_coefficient(
                current_conv_id
            )
        if action == "add_blacklist":
            return self._willing.add_runtime_blacklist(current_conv_id)
        if action == "remove_blacklist":
            return self._willing.remove_runtime_blacklist(current_conv_id)
        return f"错误：未知操作 {action}"

    def _execute_set_global_willing(self, args: dict) -> str:
        """设置全局回复意愿系数(运行时):需 willing_global 凭据。

        凭据类型由 agent 在凭据 skill 申请时决定:临时调整用 one_time,
        需要反复调整可申请 timed(签发后持续有效)。
        """
        if self._willing is None:
            return "错误：回复意愿服务未配置"
        value = args.get("value")
        if value is None:
            return "错误：set_global 需要提供 value 参数"
        try:
            coefficient = float(value)
        except (TypeError, ValueError):
            return "错误：value 必须是数字"
        if not 0.0 <= coefficient <= 1.0:
            return "错误：value 必须在 0.0 到 1.0 之间"
        chat_flow = self._credential_chat_flow()
        if chat_flow is None:
            return "错误：无法确定当前会话"
        missing = self._credential_missing_message(
            chat_flow, "willing_global", "全局回复意愿"
        )
        if missing is not None:
            return missing
        return self._willing.set_runtime_global_coefficient(coefficient)

    async def _execute_manage_willing_config(self, args: dict) -> str:
        """查看/编辑 config 中的全局回复意愿系数(持久化+热重载):需超级管理员凭据。"""
        action = str(args.get("action") or "")
        chat_flow = self._credential_chat_flow()
        if chat_flow is None:
            return "错误：无法确定当前会话"
        missing = self._credential_missing_message(
            chat_flow, "willing_config", "修改全局回复意愿配置"
        )
        if missing is not None:
            return missing

        if self._config is None:
            return "错误：配置未注入,无法读取全局回复意愿系数"
        chat = getattr(self._config, "chat", None)
        if chat is None:
            return "错误：配置缺少 chat 段"
        reply_mode = str(getattr(chat, "reply_mode", "agent") or "agent")
        agent_coeff = getattr(chat, "willing_agent_global_coefficient", 1.0)
        common_coeff = getattr(chat, "willing_global_coefficient", 1.0)

        if action == "get":
            effective = "agent" if reply_mode == "agent" else "common"
            return (
                "当前全局回复意愿系数配置:\n"
                f"- 回复模式: {reply_mode}(生效项: {effective})\n"
                f"- agent 模式系数(willing_agent_global_coefficient): {agent_coeff}\n"
                f"- common 模式系数(willing_global_coefficient): {common_coeff}"
            )
        if action != "set":
            return f"错误：未知操作 {action}(可选值: get / set)"

        target = str(args.get("target") or reply_mode or "agent").strip().casefold()
        if target not in ("agent", "common"):
            return "错误：target 必须是 agent 或 common"
        value = args.get("value")
        if value is None:
            return "错误：set 需要提供 value 参数"
        try:
            coefficient = float(value)
        except (TypeError, ValueError):
            return "错误：value 必须是数字"
        if not 0.0 <= coefficient <= 1.0:
            return "错误：value 必须在 0.0 到 1.0 之间"
        key = (
            "willing_agent_global_coefficient"
            if target == "agent"
            else "willing_global_coefficient"
        )
        callback = self._config_update_callback
        if callback is None:
            return "错误：配置更新能力未注入"
        try:
            result = callback(key, coefficient)
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            return f"错误：配置更新失败: {exc}"
        if isinstance(result, str) and result.startswith("错误"):
            return result
        return (
            f"已更新全局回复意愿系数: chat.{key} = {coefficient:.3f}"
            "(已写回 config.toml 并热重载,立即生效;重启不丢失)"
        )

    def _credential_chat_flow(self) -> str | None:
        conv_kind = str(self._conv_kind or "").strip()
        conv_id = str(self._conv_id or "").strip()
        if not conv_kind or not conv_id:
            return None
        return f"{conv_kind}:{conv_id}"

    def _credential_missing_message(
        self, chat_flow: str, action: str, purpose: str
    ) -> str | None:
        """检查并消费凭据;无可用凭据时返回引导文案,否则返回 None。"""
        if self._credential_manager is None:
            return (
                f"错误：凭据服务未配置,无法执行{purpose}。"
                "请联系管理员检查配置"
            )
        credential = self._credential_manager.consume(
            chat_flow=chat_flow, action=action, commit=True
        )
        if credential is not None:
            return None
        return (
            f"需要管理员凭据才能执行{purpose}。\n"
            f"请调用凭据 skill 的 request 工具申请凭据: action={action}\n"
            "- 临时调整一次: credential_type=one_time(默认)\n"
            "- 需要反复调整: credential_type=timed(签发后持续有效,可多次使用)\n"
            "管理员在聊天中发送凭据文本后,凭据即生效,届时再执行原操作。"
        )

    def _execute_get_willingness_config(self) -> str:
        if self._willing is None:
            return "错误：回复意愿服务未配置"
        return self._willing.get_runtime_config_summary()

    async def _execute_send_emoji(self, args: dict) -> str:
        handler = self._send_emoji
        if handler is None:
            return "错误：send_emoji 处理器未配置"
        try:
            number = int(args.get("number", -1))
        except (ValueError, TypeError):
            return "错误：number 必须为整数"
        emoji_entry = None
        if self._emoji is not None:
            emoji_entry = self._emoji.get_entry(number)
            if emoji_entry is None:
                total = self._emoji.emoji_count
                return f"错误：表情包编号 {number} 不存在，当前共 {total} 个表情包"
        text = str(args.get("text") or "")
        await handler(number=number, text=text)
        entry_name = emoji_entry.file_name if emoji_entry else f"#{number}"
        return f"已发送表情包 {entry_name}"

    def _execute_list_emojis(self, args: dict) -> str:
        """分页列出自定义表情包（文本形式，编号可直接用于发送工具）。"""
        if self._emoji is None:
            return "错误：表情包服务未配置"
        try:
            offset = max(0, int(args.get("offset") or 0))
        except (ValueError, TypeError):
            return "错误：offset 必须为整数"
        raw_limit = args.get("limit")
        limit: int | None = None
        if raw_limit is not None:
            try:
                limit = int(raw_limit)
            except (ValueError, TypeError):
                return "错误：limit 必须为整数"
            if limit <= 0:
                return "错误：limit 必须为正整数"
            limit = min(limit, _MAX_EMOJI_PAGE_SIZE)
        text = self._emoji.build_list_text(offset=offset, limit=limit)
        if not text:
            return "当前没有可用的自定义表情包"
        return text

    def _execute_search_custom_emoji(self, args: dict) -> str:
        if self._emoji is None:
            return "错误：表情包服务未配置"
        keyword = str(args.get("keyword") or "").strip()
        if not keyword:
            return "错误：keyword 不能为空"
        results = self._emoji.search_entries(keyword)
        if not results:
            return f'未找到与"{keyword}"相关的自定义表情包'
        lines = [f'搜索"{keyword}"的结果（按使用次数从少到多排列）：']
        for number, entry in results:
            usage_info = f" [已用{entry.use_count}次]" if entry.use_count > 0 else ""
            lines.append(
                f"  #{number}: {entry.analysis_text}{usage_info} ({entry.file_name})"
            )
        return "\n".join(lines)

    async def _execute_react_emoji(self, args: dict) -> str:
        if self._react_emoji is None:
            return "错误：react_emoji 处理器未配置"
        try:
            message_number = int(args.get("message_number", -1))
        except (ValueError, TypeError):
            return "错误：message_number 必须为整数"
        try:
            emoji_id = int(args.get("emoji_id", -1))
        except (ValueError, TypeError):
            return "错误：emoji_id 必须为整数"
        if message_number <= 0:
            return f"错误：message_number 无效，收到 {message_number}"
        if emoji_id < 0:
            return f"错误：emoji_id 无效，收到 {emoji_id}"
        return await self._react_emoji(message_number=message_number, emoji_id=emoji_id)

    def _execute_search_qq_emoji(self, args: dict) -> str:
        if self._search_emoji is None:
            return "错误：search_qq_emoji 处理器未配置"
        keyword = str(args.get("keyword") or "").strip()
        if not keyword:
            return "错误：keyword 不能为空"
        return self._search_emoji(keyword=keyword)

    async def _execute_speak(self, args: dict) -> str:
        if self._tts_service is None:
            return "错误：TTS 服务未配置"
        if not getattr(self._tts_service, "enabled", False):
            return "错误：TTS 服务当前不可用"
        if self._speak_handler is None:
            return "错误：speak 处理器未配置"
        text = str(args.get("text") or "").strip()
        if not text:
            return "错误：text 不能为空"
        try:
            return await self._speak_handler(text=text)
        except Exception as exc:
            self._logger.warning("语音生成失败", error_type=type(exc).__name__)
            return "语音生成失败"

    async def _execute_poke_user(self, args: dict) -> str:
        if self._poke_user is None:
            return "错误：poke_user 处理器未配置"
        try:
            user_id = int(args.get("user_id", -1))
        except (ValueError, TypeError):
            return "错误：user_id 必须为整数"
        if user_id <= 0:
            return f"错误：user_id 无效，收到 {args.get('user_id')}"
        return await self._poke_user(user_id=user_id)

    async def _execute_check_background_tasks(self, args: dict) -> str:
        """查询当前聊天流的后台任务状态（绘图、定时任务、解题、会话工具）。"""
        pipeline_key = f"{self._conv_kind}:{self._conv_id}"
        if not self._conv_kind or not self._conv_id:
            return json.dumps(
                {"ok": False, "error": "无法获取当前会话信息"}, ensure_ascii=False
            )

        has_any_manager = (
            self._drawing_manager is not None
            or self._scheduled_task_manager is not None
            or self._problem_solver_manager is not None
            or self._notification_hub is not None
        )
        has_session_activity = (
            bool(self._session_task_info)
            or bool(self._session_task_queue)
            or bool(self._session_completed.get(pipeline_key, []))
        )

        if not has_any_manager and not has_session_activity:
            return json.dumps(
                {"ok": False, "error": "后台任务未配置"}, ensure_ascii=False
            )

        status: dict[str, Any] = {}
        if self._drawing_manager is not None:
            status.update(self._drawing_manager.get_pipeline_status(pipeline_key))
        if self._scheduled_task_manager is not None:
            status.update(
                self._scheduled_task_manager.get_pipeline_status(pipeline_key)
            )
        if self._problem_solver_manager is not None:
            status.update(
                self._problem_solver_manager.get_pipeline_status(pipeline_key)
            )
        if self._notification_hub is not None:
            status.update(self._notification_hub.get_pipeline_status(pipeline_key))

        # 当前管线的会话工具 — 运行中 + 排队中
        now = monotonic_seconds()
        active_session_tools: list[dict] = []
        for info in self._session_task_info.values():
            # "or not info["pipeline_key"]" 为防御性处理，当前逻辑下 pipeline_key 始终非空
            if info["pipeline_key"] == pipeline_key or not info["pipeline_key"]:
                active_session_tools.append(
                    {
                        "tool": info["name"],
                        "pipeline_key": info["pipeline_key"] or pipeline_key,
                        "elapsed_seconds": round(now - info["started_at"]),
                    }
                )
        if active_session_tools:
            status["active_session_tools"] = active_session_tools

        queued_tools: list[dict] = []
        for pk, queued in self._session_task_queue.items():
            if pk == pipeline_key:
                queued_tools.append(
                    {
                        "tool": queued["name"],
                        "queued_seconds": round(now - queued["queued_at"]),
                    }
                )
        if queued_tools:
            status["queued_session_tools"] = queued_tools

        # 最近完成的会话工具（防止 agent 重复执行已完成的相同任务）
        completed = self._session_completed.get(pipeline_key, [])
        if completed:
            status["completed_session_tools"] = [
                {
                    "tool": c["tool"],
                    "status": c["status"],
                    "summary": c["summary"],
                    "elapsed_seconds": c["elapsed_seconds"],
                    "completed_ago_seconds": round(now - c["completed_at"]),
                }
                for c in completed
            ]

        # 补充绘图任务的已运行时长
        active_draw = status.get("active_task")
        if isinstance(active_draw, dict) and active_draw.get("created_at"):
            try:
                created = float(active_draw["created_at"])
                active_draw["elapsed_seconds"] = round(now - created)
            except (ValueError, TypeError):
                pass

        self._logger.info(
            "主Agent查询后台任务状态",
            pipeline_key=pipeline_key,
            has_active=status.get("has_active_task"),
            cooldown=status.get("cooldown_remaining_seconds"),
            session_tools=len(active_session_tools),
            queued=len(queued_tools),
            completed=len(completed),
        )
        return json.dumps(
            {"ok": True, "pipeline_key": pipeline_key, **status}, ensure_ascii=False
        )

    async def _execute_mark_scheduled_task_complete(self, args: dict) -> str:
        if self._scheduled_task_manager is None:
            return json.dumps(
                {"ok": False, "error": "定时任务系统未配置"}, ensure_ascii=False
            )
        task_id = str(args.get("task_id") or "").strip()
        if not task_id:
            return json.dumps(
                {"ok": False, "error": "task_id 不能为空"}, ensure_ascii=False
            )
        result = await self._scheduled_task_manager.mark_completed(task_id)
        self._logger.info(
            "主Agent标记定时任务完成",
            task_id=task_id,
            ok=result.get("ok"),
        )
        return json.dumps(result, ensure_ascii=False)

    async def _execute_send_long_reply(self, args: dict) -> str:
        if self._markdown_image_converter is None:
            return json.dumps(
                {"ok": False, "error": "Markdown 转图片功能未配置"}, ensure_ascii=False
            )

        markdown = str(args.get("markdown") or "").strip()
        pre_rendered = str(args.get("image_path") or "").strip()

        if not markdown and not pre_rendered:
            return json.dumps(
                {"ok": False, "error": "markdown 和 image_path 至少需要提供一个"},
                ensure_ascii=False,
            )

        reply_to = args.get("reply_to")
        if reply_to is not None:
            try:
                reply_to = int(reply_to)
            except (ValueError, TypeError):
                return json.dumps(
                    {"ok": False, "error": f"reply_to 必须为整数，收到 {reply_to}"},
                    ensure_ascii=False,
                )
        raw_mention = args.get("mention")
        mention: list[int] | None = None
        if raw_mention:
            try:
                mention = [int(qq) for qq in raw_mention]
            except (ValueError, TypeError):
                return json.dumps(
                    {"ok": False, "error": "mention 必须为整数列表"}, ensure_ascii=False
                )
        caption = str(args.get("caption") or "").strip()

        if pre_rendered:
            image_path = pre_rendered
        else:
            try:
                image_path = str(await self._markdown_image_converter.convert(markdown))
            except Exception as exc:
                self._logger.error("Markdown 转图片失败", error_type=type(exc).__name__)
                return json.dumps(
                    {"ok": False, "error": "Markdown 转图片失败"}, ensure_ascii=False
                )

        # 调用 orchestrator 提供的 handler 实际发送图片
        if self._send_long_reply is not None:
            await self._send_long_reply(
                image_path=image_path,
                caption=caption,
                reply_to=reply_to,
                mention=mention,
                markdown=markdown,
            )
        return json.dumps(
            {
                "ok": True,
                "status": "sent",
                "image_path": image_path,
                "caption": caption or None,
                "message": f"已发送Markdown图片{'(预渲染)' if pre_rendered else ''}，路径：{image_path}",
            },
            ensure_ascii=False,
        )

    # ── Markdown 技能读取 ──

    def _resolve_skill(self, skill_id: str) -> Any:
        if self._skills_registry is None:
            raise ToolError("Markdown 技能注册表不可用")
        skill = self._skills_registry.skills.get(str(skill_id))
        if skill is None:
            raise ToolError(f"技能不存在或已卸载: {skill_id}")
        return skill

    def _read_skill_manifest(self, args: dict) -> str:
        skill_id = str(args.get("skill_id") or "").strip()
        if not skill_id:
            return "Error: 缺少 skill_id 参数"
        try:
            skill = self._resolve_skill(skill_id)
        except ToolError as exc:
            return f"Error: {exc}"
        return skill.content

    def _view_skill_instructions(self, args: dict) -> str:
        """返回指定内置技能的完整操作说明(按需查看)。"""
        if self._skill_manager is None:
            return "Error: SkillManager 不可用"
        skill_name = str(args.get("skill") or "").strip()
        if not skill_name:
            return "Error: 缺少 skill 参数"
        return self._skill_manager.get_skill_instructions(skill_name)

    # ── 技能工具按需加载 ──

    def _deferred_skill_names(self) -> list[str]:
        """仍处于「未加载」状态的技能名；已加载的技能不再出现在下拉里。"""
        if self._activation is None:
            return []
        return self._activation.candidates()

    def _load_skill_tools(self, args: dict) -> str:
        """把一个或多个技能的工具定义加入本管线后续的模型调用。

        工具 schema 会随每次模型调用一起发送，全部常驻时开销极大；
        因此在模型明确需要某个技能时再加载，加载后本轮即可直接调用。
        """
        if self._activation is None:
            return "Error: SkillManager 不可用"
        return self._activation.load(args)

    def activated_skill_names(self) -> list[str]:
        """本管线已按需加载的技能名（用于日志/调试）。"""
        return self._activation.activated_names() if self._activation else []

    def consume_tools_dirty(self) -> bool:
        """取出并清除「工具列表已变化」标记，供调用方重建 tools。"""
        return self._activation.consume_dirty() if self._activation else False

    @staticmethod
    def _inspect_skill_resource_path(
        base: Path, target: Path
    ) -> tuple[os.stat_result | None, str | None]:
        try:
            relative = target.relative_to(base)
        except ValueError:
            return None, "outside"

        current = base
        target_stat: os.stat_result | None = None
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        try:
            for component in relative.parts:
                current /= component
                target_stat = current.lstat()
                file_attributes = getattr(target_stat, "st_file_attributes", 0)
                if stat.S_ISLNK(target_stat.st_mode) or file_attributes & reparse_flag:
                    return None, "reparse"
        except FileNotFoundError:
            return None, "missing"
        except OSError:
            return None, "read_failed"

        if target_stat is None or not stat.S_ISREG(target_stat.st_mode):
            return None, "missing"
        return target_stat, None

    @classmethod
    def _validate_open_skill_resource(
        cls, file_obj: Any, base: Path, target: Path
    ) -> tuple[os.stat_result | None, str | None]:
        try:
            opened_stat = os.fstat(file_obj.fileno())
        except (AttributeError, OSError, ValueError):
            return None, "unverifiable"
        if not stat.S_ISREG(opened_stat.st_mode):
            return None, "missing"
        link_count = getattr(opened_stat, "st_nlink", None)
        if isinstance(link_count, int) and link_count > 1:
            return None, "hard_link"

        path_stat, error = cls._inspect_skill_resource_path(base, target)
        if error is not None or path_stat is None:
            return None, error or "unverifiable"
        try:
            resolved_target = target.resolve(strict=True)
        except (OSError, RuntimeError):
            return None, "changed"
        if not _path_is_within(resolved_target, base):
            return None, "outside"

        opened_path = _opened_file_path(file_obj)
        if os.name == "nt" and opened_path is None:
            return None, "unverifiable"
        if opened_path is not None and not _path_is_within(opened_path, base):
            return None, "outside"

        if not _same_open_file(opened_stat, path_stat):
            same_resolved_path = opened_path is not None and os.path.normcase(
                os.path.abspath(opened_path)
            ) == os.path.normcase(os.path.abspath(resolved_target))
            if not same_resolved_path:
                return None, "changed"
        return opened_stat, None

    @staticmethod
    def _skill_resource_error(error: str, rel: str) -> str:
        if error == "outside":
            return f"Error: 路径越界，拒绝读取: {rel}"
        if error == "reparse":
            return f"Error: 拒绝读取 symlink/junction 路径: {rel}"
        if error == "hard_link":
            return f"Error: 拒绝读取硬链接文件: {rel}"
        if error == "missing":
            return f"Error: 文件不存在: {rel}"
        if error == "changed":
            return f"Error: 路径在读取期间发生变化，拒绝读取: {rel}"
        if error == "unverifiable":
            return f"Error: 无法安全验证文件路径，拒绝读取: {rel}"
        return f"Error: 读取失败: {rel}"

    def _read_skill_resource(self, args: dict) -> str:
        skill_id = str(args.get("skill_id") or "").strip()
        rel = str(args.get("path") or "").strip()
        if not skill_id or not rel:
            return "Error: 缺少 skill_id 或 path 参数"
        if (
            rel.startswith("/")
            or rel.startswith("\\")
            or re.match(r"^[A-Za-z]:", rel)
            or ".." in rel.replace("\\", "/").split("/")
        ):
            return "Error: 非法路径（仅允许技能目录内的相对路径）"
        try:
            skill = self._resolve_skill(skill_id)
        except ToolError as exc:
            return f"Error: {exc}"
        try:
            base = Path(skill.path.parent).resolve(strict=True)
        except (OSError, RuntimeError):
            return "Error: 技能目录不可用"
        relative_parts = [
            part for part in rel.replace("\\", "/").split("/") if part not in {"", "."}
        ]
        target = base.joinpath(*relative_parts)

        _, error = self._inspect_skill_resource_path(base, target)
        if error is not None:
            return self._skill_resource_error(error, rel)
        try:
            if not _path_is_within(target.resolve(strict=True), base):
                return self._skill_resource_error("outside", rel)
        except (OSError, RuntimeError):
            return self._skill_resource_error("read_failed", rel)

        try:
            with target.open("rb", buffering=0) as file_obj:
                opened_stat, error = self._validate_open_skill_resource(
                    file_obj, base, target
                )
                if error is not None or opened_stat is None:
                    return self._skill_resource_error(error or "unverifiable", rel)
                if opened_stat.st_size > _MAX_SKILL_RESOURCE_BYTES:
                    return f"Error: 文件超过 1MB 限制: {rel}"

                content = file_obj.read(_MAX_SKILL_RESOURCE_BYTES + 1)
                final_stat, error = self._validate_open_skill_resource(
                    file_obj, base, target
                )
                if error is not None or final_stat is None:
                    return self._skill_resource_error(error or "unverifiable", rel)
                if (
                    len(content) > _MAX_SKILL_RESOURCE_BYTES
                    or final_stat.st_size > _MAX_SKILL_RESOURCE_BYTES
                ):
                    return f"Error: 文件超过 1MB 限制: {rel}"
        except FileNotFoundError:
            return self._skill_resource_error("missing", rel)
        except (OSError, ValueError):
            return self._skill_resource_error("read_failed", rel)
        return content.decode("utf-8", errors="replace")

    async def _execute_check_last_drawing(self, args: dict) -> str:
        """查询当前聊天流上一次绘图任务的详细记录。"""
        if self._drawing_manager is None:
            return json.dumps(
                {"ok": False, "error": "后台任务未配置"}, ensure_ascii=False
            )
        pipeline_key = f"{self._conv_kind}:{self._conv_id}"
        if not self._conv_kind or not self._conv_id:
            return json.dumps(
                {"ok": False, "error": "无法获取当前会话信息"}, ensure_ascii=False
            )
        info = self._drawing_manager.get_last_draw_info(pipeline_key)
        if info.get("found"):
            self._logger.info(
                "主Agent查询上一次绘图记录",
                pipeline_key=pipeline_key,
                task_id=info.get("task_id"),
                status=info.get("status"),
            )
        return json.dumps(
            {"ok": True, "pipeline_key": pipeline_key, **info}, ensure_ascii=False
        )

    def _preview_split(self, text: str) -> ReplyPostProcessResult:
        return process_reply_text(
            text,
            bot_name=self._bot_name,
            fallback_template=self._long_reply_fallback_template,
            max_length=self._long_reply_max_length,
            max_sentence_count=self._long_reply_max_sentence_count,
        )

    @staticmethod
    def _normalize_segments(value: Any) -> list[str] | None:
        if value is None:
            return None
        if not isinstance(value, list):
            return None
        segments = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, (dict, list)) and not item:
                continue
            text = str(item).strip()
            if text:
                segments.append(text)
        return segments or None

    def _build_ai_check_prompt(self, result: ReplyPostProcessResult) -> str:
        lines = [
            "AI回复检查已开启，暂未发送。",
            "请检查切分后的分条回复是否存在严重问题或明显歧义。",
            f"原文：{result.original_text}",
            "切分结果：",
        ]
        for index, message in enumerate(result.messages, start=1):
            lines.append(f"{index}. {message}")
        if result.fallback_used:
            lines.append(
                f"注意：因 {result.reason or '未知原因'}，已触发默认回复替换，当前切分结果为默认回复文本。"
            )
            if self._enable_ai_reply_regenerate:
                lines.append(
                    "默认回复不是你的原意，请重新生成一个更简短的版本（不超过"
                    f"{self._long_reply_max_length}字符、不超过"
                    f"{self._long_reply_max_sentence_count}条），"
                    "然后直接调用 send_reply 发送新文本，无需设置 ai_check_approved。"
                )
            else:
                lines.append(
                    "如确认使用当前默认回复，请再次调用 send_reply，传入原 text、"
                    "segments 为上述切分结果、ai_check_approved=true。"
                    "如不应发送任何回复，请调用 cancel。"
                )
        else:
            lines.append(
                "如果没有严重问题或歧义，请再次调用 send_reply，传入原 text、segments 为上述切分结果、ai_check_approved=true。"
            )
            lines.append(
                "如果切分有问题但仍要发送原文，请调用 send_reply 并设置 send_original=true；如果不应发送，请调用 cancel。"
            )
        return "\n".join(lines)

    async def drain_sessions(self) -> None:
        """等待在途会话工具任务自然结束，不取消它们。

        回复管线结束时调用。会话工具的契约是活过本轮回复（工具返回值明确要求模型
        「立即结束本轮回复」，完成后由通知中心唤醒下一次回复），所以这里只等它们
        跑完，好让执行器连同完整对话历史一起释放；只有进程关停才用 close() 取消。
        """
        while self._session_tasks:
            tasks = tuple(self._session_tasks)
            await asyncio.gather(*tasks, return_exceptions=True)
            self._session_tasks.difference_update(tasks)

    async def close(self) -> None:
        """Idempotently reject new session work, cancel active work, and wait for it."""
        if self._close_task is None:
            self._closed = True
            self._session_task_queue.clear()
            self._close_task = asyncio.create_task(self._finish_close())
        await asyncio.shield(self._close_task)

    async def _finish_close(self) -> None:
        while self._session_tasks:
            tasks = tuple(self._session_tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._session_tasks.difference_update(tasks)
        self._session_task_queue.clear()
        self._session_task_info.clear()
        self._session_completed.clear()


def build_reply_toolset(
    *,
    send_reply_handler: Any = None,
    willing_service: Any = None,
    numbering: Any = None,
    send_emoji_handler: Any = None,
    emoji_service: Any = None,
    wait_handler: Any = None,
    react_emoji_handler: Any = None,
    search_emoji_handler: Any = None,
    cancel_handler: Any = None,
    tts_service: Any = None,
    speak_handler: Any = None,
    poke_user_handler: Any = None,
    drawing_manager: Any = None,
    scheduled_task_manager: Any = None,
    problem_solver_manager: Any = None,
    notification_hub: Any = None,
    markdown_image_converter: Any = None,
    send_long_reply_handler: Any = None,
    skill_manager: Any = None,
    skills_registry: Any = None,
    allowed_tools: set[str] | None = None,
    chat_context: str | None = None,
    conv_kind: str = "",
    conv_id: str = "",
    current_user_id: int | None = None,
    human_request: bool = False,
    agent_history: list[dict] | None = None,
    wait_cooldown_seconds: int = 60,
    ai_reply_check: bool = False,
    ai_reply_check_lightweight: bool = True,
    bot_name: str = "Bot",
    long_reply_fallback_template: str = "{bot_name}懒得和你说道理，你不配听",
    long_reply_max_length: int = 300,
    long_reply_max_sentence_count: int = 12,
    enable_ai_reply_regenerate: bool = True,
    logger: Logger | None = None,
    policy: ToolAccessPolicy | None = None,
    credential_manager: Any = None,
    config: Any = None,
    config_update_callback: Any = None,
    native_vision_provider: Any = None,
) -> Toolset:
    executor = ReplyToolExecutor(
        send_reply_handler=send_reply_handler,
        willing_service=willing_service,
        numbering=numbering,
        send_emoji_handler=send_emoji_handler,
        emoji_service=emoji_service,
        wait_handler=wait_handler,
        react_emoji_handler=react_emoji_handler,
        search_emoji_handler=search_emoji_handler,
        cancel_handler=cancel_handler,
        tts_service=tts_service,
        speak_handler=speak_handler,
        poke_user_handler=poke_user_handler,
        drawing_manager=drawing_manager,
        scheduled_task_manager=scheduled_task_manager,
        problem_solver_manager=problem_solver_manager,
        notification_hub=notification_hub,
        markdown_image_converter=markdown_image_converter,
        send_long_reply_handler=send_long_reply_handler,
        skill_manager=skill_manager,
        skills_registry=skills_registry,
        allowed_tools=allowed_tools,
        chat_context=chat_context,
        conv_kind=conv_kind,
        conv_id=conv_id,
        current_user_id=current_user_id,
        human_request=human_request,
        agent_history=agent_history,
        wait_cooldown_seconds=wait_cooldown_seconds,
        ai_reply_check=ai_reply_check,
        ai_reply_check_lightweight=ai_reply_check_lightweight,
        bot_name=bot_name,
        long_reply_fallback_template=long_reply_fallback_template,
        long_reply_max_length=long_reply_max_length,
        long_reply_max_sentence_count=long_reply_max_sentence_count,
        enable_ai_reply_regenerate=enable_ai_reply_regenerate,
        logger=logger,
        credential_manager=credential_manager,
        config=config,
        config_update_callback=config_update_callback,
        native_vision_provider=native_vision_provider,
    )
    definitions = executor.definitions()
    specs = [
        ToolSpec(definition=definition, access_resolver=_default_resolver)
        for definition in definitions
    ]
    return Toolset(executor=executor, specs=specs, policy=policy or ToolAccessPolicy())
