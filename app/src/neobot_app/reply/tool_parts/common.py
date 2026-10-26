"""模块级常量与通用助手函数（由 reply/tools.py 拆分）。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from neobot_chat.schema.types import ToolAccessPolicy, ToolAccessRule, ToolDefinition, ToolGuardContext


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
