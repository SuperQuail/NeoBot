"""SandboxManagerSkill — 沙箱文件操作 Skill（读写/编辑/搜索/删除/列表/移动/复制/发送）。

实现按职责拆在 sandbox_manager_parts（公共常量与 JSON 包装、元信息/构造、工具声明与分发、可信调用、按族的处理函数、工具注册表）；本模块保留 SandboxManagerSkill 聚合类与原有模块级名称的 re-export。
"""

from __future__ import annotations

from neobot_app.skills.base import SkillModule

from .sandbox_manager_parts.base import SandboxManagerSkillBase
from .sandbox_manager_parts.common import (
    MAX_DOWNLOAD_BYTES,
    MAX_DOWNLOAD_REDIRECTS,
    _json,
)
from .sandbox_manager_parts.dispatch import _HANDLERS
from .sandbox_manager_parts.handlers_download import (
    _download_with_redirects,
    _handle_download_file,
    _read_download_limited,
)
from .sandbox_manager_parts.handlers_files import (
    _handle_read_file,
    _handle_write_file,
    _handle_write_file_base64,
    _handle_edit_file,
    _handle_glob_files,
    _handle_grep_files,
    _handle_delete_file,
    _handle_list_files,
    _handle_move_file,
    _handle_copy_file,
)
from .sandbox_manager_parts.handlers_send import (
    _handle_send_file,
    _handle_send_chat_file,
    _handle_hold_temp,
)
from .sandbox_manager_parts.tools import ToolsMixin
from .sandbox_manager_parts.trusted import TrustedMixin


class SandboxManagerSkill(ToolsMixin, TrustedMixin, SandboxManagerSkillBase, SkillModule):
    """沙箱文件操作 Skill — 沙箱内文件读写/编辑/搜索/删列移拷贝及发送到聊天。"""


__all__ = [
    "_json",
    "MAX_DOWNLOAD_BYTES",
    "MAX_DOWNLOAD_REDIRECTS",
    "SandboxManagerSkill",
    "_handle_read_file",
    "_handle_write_file",
    "_handle_write_file_base64",
    "_handle_edit_file",
    "_handle_glob_files",
    "_handle_grep_files",
    "_handle_delete_file",
    "_handle_list_files",
    "_handle_move_file",
    "_handle_copy_file",
    "_handle_send_file",
    "_handle_send_chat_file",
    "_handle_hold_temp",
    "_read_download_limited",
    "_download_with_redirects",
    "_handle_download_file",
    "_HANDLERS",
]
