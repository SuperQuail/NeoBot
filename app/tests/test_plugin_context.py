"""Tests for plugin context integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from neobot_contracts.models import ConversationRef
from neobot_modloader.context import PluginContext


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
def ctx(
    tmp_path: Path,
    mock_adapter: MagicMock,
    mock_file_server: MagicMock,
    mock_logger: MagicMock,
) -> PluginContext:
    return PluginContext(
        plugin_name="test_plugin",
        plugin_dir=tmp_path / "plugin",
        data_dir=tmp_path / "data",
        config={"key": "value"},
        logger=mock_logger,
        adapter=mock_adapter,
        file_server=mock_file_server,
    )


class TestSendImageByPath:
    """Tests for send_image with a local file path."""

    async def test_send_image_by_path(
        self,
        ctx: PluginContext,
        mock_adapter: MagicMock,
        conversation: ConversationRef,
        tmp_path: Path,
    ) -> None:
        """Mock adapter+FileServer, verify send_image(path=...) calls adapter.send."""
        img_path = tmp_path / "test_image.png"
        img_path.write_bytes(b"fake png content")

        await ctx.send_image(conversation, path=img_path)

        mock_adapter.send.assert_awaited_once()
        args = mock_adapter.send.await_args.args
        assert args[0] is conversation
        assert args[1][0]["type"] == "image"
        assert args[1][0]["data"]["file"] == f"file:///{img_path.as_posix()}"


class TestSendImageByBinary:
    """Tests for send_image with raw binary data."""

    async def test_send_image_by_binary(
        self,
        ctx: PluginContext,
        mock_adapter: MagicMock,
        conversation: ConversationRef,
    ) -> None:
        """Binary data writes a temp file, sends it, then cleans up."""
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
        ctx: PluginContext,
        conversation: ConversationRef,
    ) -> None:
        """>30MB binary data raises ValueError."""
        large_data = b"x" * 31_000_000
        with pytest.raises(ValueError, match="30MB"):
            await ctx.send_image(conversation, data=large_data, filename="large.png")

    async def test_send_image_binary_cleanup_on_error(
        self,
        ctx: PluginContext,
        mock_adapter: MagicMock,
        conversation: ConversationRef,
    ) -> None:
        """When adapter.send fails, the temp file is still cleaned up."""
        mock_adapter.send.side_effect = RuntimeError("send failed")
        data = b"\x89PNG\r\n\x1a\n"

        with pytest.raises(RuntimeError, match="send failed"):
            await ctx.send_image(conversation, data=data, filename="test.png")

        # Verify .media_cache directory is empty
        cache_dir = ctx._data_dir / ".media_cache"
        assert cache_dir.exists()
        assert list(cache_dir.iterdir()) == []


class TestSendImageMissingArgs:
    """Tests for send_image with missing/invalid arguments."""

    async def test_send_image_missing_args(
        self,
        ctx: PluginContext,
        conversation: ConversationRef,
    ) -> None:
        """Calling with neither path nor data raises ValueError."""
        with pytest.raises(ValueError, match="Must provide path or data"):
            await ctx.send_image(conversation)
