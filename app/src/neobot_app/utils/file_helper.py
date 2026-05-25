"""文件辅助工具 - 创建消息段"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, TYPE_CHECKING

from neobot_app.utils.media_sender import prepare_audio_segment, prepare_image_segment

if TYPE_CHECKING:
    from neobot_app.core.file_server import FileServer


def create_text_segment(text: str) -> Dict[str, Any]:
    """创建文本消息段"""
    return {"type": "text", "data": {"text": text}}


def create_image_segment(file_server: FileServer, file_path: Path) -> Dict[str, Any]:
    """创建图片消息段"""
    return prepare_image_segment(file_server, file_path)


def create_video_segment(
    file_server: FileServer, file_path: Path, cover_path: Path | None = None
) -> Dict[str, Any]:
    """创建视频消息段"""
    data = {"file": file_server.register_file(file_path)}
    if cover_path:
        data["cover"] = file_server.register_file(cover_path)
    return {"type": "video", "data": data}


def create_audio_segment(file_server: FileServer, file_path: Path) -> Dict[str, Any]:
    """创建语音消息段"""
    return prepare_audio_segment(file_server, file_path)
