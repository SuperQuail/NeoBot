"""媒体发送工具 - 统一图片/语音发送，根据 FileServer.enabled 决定输出格式"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from neobot_adapter.model.response import SendMsgResponse
from neobot_contracts.models import ConversationRef

if TYPE_CHECKING:
    from neobot_app.core.file_server import FileServer


def prepare_image_segment(file_server: FileServer, file_path: Path) -> Dict[str, Any]:
    """准备图片消息段

    根据 FileServer 是否启用，返回不同格式的消息段：
    - 启用：调用 register_file 获取 HTTP URL
    - 禁用：使用 file:/// 本地路径
    """
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    if file_server._enabled:
        url = file_server.register_file(file_path)
    else:
        url = f"file:///{file_path.as_posix()}"

    return {"type": "image", "data": {"file": url}}


def prepare_audio_segment(file_server: FileServer, file_path: Path) -> Dict[str, Any]:
    """准备语音消息段

    根据 FileServer 是否启用，返回不同格式的消息段：
    - 启用：调用 register_file 获取 HTTP URL
    - 禁用：使用 file:/// 本地路径
    """
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    if file_server._enabled:
        url = file_server.register_file(file_path)
    else:
        url = f"file:///{file_path.as_posix()}"

    return {"type": "record", "data": {"file": url}}


async def send_image(
    file_server: FileServer,
    adapter: Any,
    conversation: ConversationRef,
    file_path: Path,
) -> SendMsgResponse:
    """发送图片消息"""
    segment = prepare_image_segment(file_server, file_path)
    return await adapter.send(conversation, [segment])


async def send_audio(
    file_server: FileServer,
    adapter: Any,
    conversation: ConversationRef,
    file_path: Path,
) -> SendMsgResponse:
    """发送语音消息"""
    segment = prepare_audio_segment(file_server, file_path)
    return await adapter.send(conversation, [segment])
