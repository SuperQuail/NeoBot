"""工具名到处理函数的注册表。"""

from __future__ import annotations

from .handlers_files import (
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
from .handlers_send import _handle_send_file, _handle_send_chat_file, _handle_hold_temp
from .handlers_download import _handle_download_file

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
