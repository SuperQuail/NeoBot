"""插件上下文集成的测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from neobot_contracts.models import ConversationRef
from neobot_modloader.context import RuntimePluginContext


@pytest.fixture
def conversation() -> ConversationRef:
    return ConversationRef(kind="group", id="123456")


@pytest.fixture
def mock_adapter() -> MagicMock:
    adapter = MagicMock()
    adapter.send = AsyncMock()
    return adapter


@pytest.fixture
def mock_file_server() -> MagicMock:
    fs = MagicMock()
    fs._enabled = False
    return fs


@pytest.fixture
def mock_logger() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_media_sender(mock_adapter: MagicMock, mock_file_server: MagicMock) -> MagicMock:
    """模拟 FileServer 禁用状态（file:/// URL）的 MediaSender 假对象。"""
    ms = MagicMock()

    async def _send_image(
        adapter: MagicMock,
        conversation: ConversationRef,
        *,
        path: Path | None = None,
        data: bytes | None = None,
        filename: str | None = None,
    ) -> None:
        segment = {"type": "image", "data": {"file": f"file:///{path.as_posix()}"}}
        return await adapter.send(conversation, [segment])

    ms.send_image = AsyncMock(side_effect=_send_image)
    ms.send_audio = AsyncMock()
    return ms


@pytest.fixture
def ctx(
    tmp_path: Path,
    mock_adapter: MagicMock,
    mock_file_server: MagicMock,
    mock_logger: MagicMock,
    mock_media_sender: MagicMock,
) -> RuntimePluginContext:
    return RuntimePluginContext(
        plugin_name="test_plugin",
        plugin_dir=tmp_path / "plugin",
        data_dir=tmp_path / "data",
        config={"key": "value"},
        logger=mock_logger,
        adapter=mock_adapter,
        file_server=mock_file_server,
        media_sender=mock_media_sender,
    )


class TestSendImageByPath:
    """send_image 使用本地文件路径发送图片的测试。"""

    async def test_send_image_by_path(
        self,
        ctx: RuntimePluginContext,
        mock_adapter: MagicMock,
        conversation: ConversationRef,
        tmp_path: Path,
    ) -> None:
        """使用假 adapter+FileServer，验证 send_image(path=...) 会调用 adapter.send。"""
        img_path = tmp_path / "test_image.png"
        img_path.write_bytes(b"fake png content")

        await ctx.send_image(conversation, path=img_path)

        mock_adapter.send.assert_awaited_once()
        args = mock_adapter.send.await_args.args
        assert args[0] is conversation
        assert args[1][0]["type"] == "image"
        assert args[1][0]["data"]["file"] == f"file:///{img_path.as_posix()}"


class TestSendImageByBinary:
    """send_image 使用原始二进制数据发送图片的测试。"""

    async def test_send_image_by_binary(
        self,
        ctx: RuntimePluginContext,
        mock_adapter: MagicMock,
        conversation: ConversationRef,
    ) -> None:
        """二进制数据先写临时文件、发送后清理。"""
        png_header = b"\x89PNG\r\n\x1a\n"

        await ctx.send_image(conversation, data=png_header, filename="test.png")

        # Verify adapter.send was called
        mock_adapter.send.assert_awaited_once()
        args = mock_adapter.send.await_args.args
        assert args[0] is conversation
        assert args[1][0]["type"] == "image"
        # URL should reference the .media_cache temp file
        file_url = args[1][0]["data"]["file"]
        assert ".media_cache" in file_url
        assert file_url.endswith(".png")

        # Verify temp file was cleaned up
        temp_path = Path(file_url.removeprefix("file:///"))
        assert not temp_path.exists()

    async def test_send_image_binary_size_limit(
        self,
        ctx: RuntimePluginContext,
        conversation: ConversationRef,
    ) -> None:
        """超过 30MB 的二进制数据应抛出 ValueError。"""
        large_data = b"x" * 31_000_000
        with pytest.raises(ValueError, match="30MB"):
            await ctx.send_image(conversation, data=large_data, filename="large.png")

    async def test_send_image_binary_cleanup_on_error(
        self,
        ctx: RuntimePluginContext,
        mock_media_sender: MagicMock,
        conversation: ConversationRef,
    ) -> None:
        """media_sender.send_image 失败时临时文件仍应被清理。"""
        mock_media_sender.send_image.side_effect = RuntimeError("send failed")
        data = b"\x89PNG\r\n\x1a\n"

        with pytest.raises(RuntimeError, match="send failed"):
            await ctx.send_image(conversation, data=data, filename="test.png")

        # Verify .media_cache directory is empty
        cache_dir = ctx._data_dir / ".media_cache"
        assert cache_dir.exists()
        assert list(cache_dir.iterdir()) == []


class TestSendImageMissingArgs:
    """send_image 缺少/非法参数的测试。"""

    async def test_send_image_missing_args(
        self,
        ctx: RuntimePluginContext,
        conversation: ConversationRef,
    ) -> None:
        """path 与 data 均未提供时抛出 ValueError。"""
        with pytest.raises(ValueError, match="Must provide path or data"):
            await ctx.send_image(conversation)
