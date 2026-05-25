"""Tests for the media sender module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from neobot_app.utils.media_sender import (
    prepare_audio_segment,
    prepare_image_segment,
    send_audio,
    send_image,
)


def _make_file_server(enabled: bool = True) -> MagicMock:
    """Create a mock FileServer with a controllable _enabled flag."""
    fs = MagicMock()
    fs._enabled = enabled

    def _register_file(path: Path) -> str:
        return f"http://127.0.0.1:8765/files/{path.name}?token=faketoken"

    fs.register_file.side_effect = _register_file
    return fs


def _make_adapter() -> AsyncMock:
    """Create a mock async adapter."""
    adapter = AsyncMock()
    adapter.send.return_value = MagicMock()
    return adapter


# ── send_image ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_image_enabled_true(tmp_path: Path) -> None:
    """send_image with enabled FileServer calls register_file and adapter.send."""
    fs = _make_file_server(enabled=True)
    adapter = _make_adapter()
    conv = MagicMock()
    path = tmp_path / "test.png"
    path.write_bytes(b"fake image data")

    result = await send_image(fs, adapter, conv, path)

    fs.register_file.assert_called_once_with(path)
    adapter.send.assert_called_once()
    args, _ = adapter.send.call_args
    assert args[0] is conv
    segment = args[1][0]
    assert segment["type"] == "image"
    assert segment["data"]["file"] == "http://127.0.0.1:8765/files/test.png?token=faketoken"


@pytest.mark.asyncio
async def test_send_image_enabled_false(tmp_path: Path) -> None:
    """send_image with disabled FileServer uses file:/// path."""
    fs = _make_file_server(enabled=False)
    adapter = _make_adapter()
    conv = MagicMock()
    path = tmp_path / "test.png"
    path.write_bytes(b"fake image data")

    result = await send_image(fs, adapter, conv, path)

    fs.register_file.assert_not_called()
    adapter.send.assert_called_once()
    args, _ = adapter.send.call_args
    segment = args[1][0]
    assert segment["type"] == "image"
    assert segment["data"]["file"].startswith("file:///")


@pytest.mark.asyncio
async def test_send_image_file_not_found(tmp_path: Path) -> None:
    """send_image with non-existent path raises FileNotFoundError."""
    fs = _make_file_server(enabled=True)
    adapter = _make_adapter()
    conv = MagicMock()
    missing = tmp_path / "nonexistent.png"

    with pytest.raises(FileNotFoundError, match="文件不存在"):
        await send_image(fs, adapter, conv, missing)


# ── send_audio ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_audio(tmp_path: Path) -> None:
    """send_audio produces a segment with type='record'."""
    fs = _make_file_server(enabled=True)
    adapter = _make_adapter()
    conv = MagicMock()
    path = tmp_path / "voice.amr"
    path.write_bytes(b"fake audio data")

    result = await send_audio(fs, adapter, conv, path)

    fs.register_file.assert_called_once_with(path)
    adapter.send.assert_called_once()
    args, _ = adapter.send.call_args
    segment = args[1][0]
    assert segment["type"] == "record"
    assert "file" in segment["data"]


# ── prepare_image_segment ───────────────────────────────────────────────


def test_prepare_image_segment_enabled(tmp_path: Path) -> None:
    """prepare_image_segment with enabled FileServer returns HTTP URL."""
    fs = _make_file_server(enabled=True)
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"fake photo data")

    segment = prepare_image_segment(fs, path)

    assert segment["type"] == "image"
    assert segment["data"]["file"] == "http://127.0.0.1:8765/files/photo.jpg?token=faketoken"
    fs.register_file.assert_called_once_with(path)


def test_prepare_image_segment_disabled(tmp_path: Path) -> None:
    """prepare_image_segment with disabled FileServer returns file:/// path."""
    fs = _make_file_server(enabled=False)
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"fake photo data")

    segment = prepare_image_segment(fs, path)

    assert segment["type"] == "image"
    assert segment["data"]["file"].startswith("file:///")
    fs.register_file.assert_not_called()
