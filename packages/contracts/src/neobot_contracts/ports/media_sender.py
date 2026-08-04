"""MediaSender 端口 — 发送媒体（图片/音频）消息的协议。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from neobot_contracts.models import ConversationRef


@runtime_checkable
class MediaSender(Protocol):
    """通过文件服务器发送图片与音频媒体的协议。

    实现方负责绑定基础设施细节（如 FileServer），并向插件代码暴露统一接口，
    使插件无需导入应用层模块即可调用。
    """

    async def send_image(
        self,
        adapter: Any,
        conversation: ConversationRef,
        *,
        path: Path | None = None,
        data: bytes | None = None,
        filename: str | None = None,
    ) -> Any:
        """向会话发送一张图片。

        需要提供文件 *path* 或原始 *data*（附带 *filename*）。
        """
        ...

    async def send_audio(
        self,
        adapter: Any,
        conversation: ConversationRef,
        *,
        path: Path,
    ) -> Any:
        """向会话发送一段音频。"""
        ...

    def prepare_image_segment(self, file_server: Any, file_path: Path) -> dict:
        """使用给定的文件服务器构造图片消息段字典。"""
        ...

    def prepare_audio_segment(self, file_server: Any, file_path: Path) -> dict:
        """使用给定的文件服务器构造音频消息段字典。"""
        ...
