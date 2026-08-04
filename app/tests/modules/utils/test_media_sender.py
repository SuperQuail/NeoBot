"""媒体发送器模块的测试。"""

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
    """创建带可控 _enabled 标志的假 FileServer。"""
    fs = MagicMock()
    fs._enabled = enabled

    def _register_file(path: Path) -> str:
        return f"http://127.0.0.1:8765/files/{path.name}?token=faketoken"

    fs.register_file.side_effect = _register_file
    return fs


def _make_adapter() -> AsyncMock:
    """创建假异步 adapter。"""
    adapter = AsyncMock()
    adapter.send.return_value = MagicMock()
    return adapter


# ── send_image ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_image_enabled_true(tmp_path: Path) -> None:
    """FileServer 启用时 send_image 会调用 register_file 与 adapter.send。"""
    fs = _make_file_server(enabled=True)
    adapter = _make_adapter()
    conv = MagicMock()
    path = tmp_path / "test.png"
    path.write_bytes(b"fake image data")

    result = await send_image(fs, adapter, conv, path)

    assert result is adapter.send.return_value
    fs.register_file.assert_called_once_with(path)
    adapter.send.assert_called_once()
    args, _ = adapter.send.call_args
    assert args[0] is conv
    segment = args[1][0]
    assert segment["type"] == "image"
    assert segment["data"]["file"] == "http://127.0.0.1:8765/files/test.png?token=faketoken"


@pytest.mark.asyncio
async def test_send_image_enabled_false(tmp_path: Path) -> None:
    """FileServer 禁用时 send_image 使用 file:/// 路径。"""
    fs = _make_file_server(enabled=False)
    adapter = _make_adapter()
    conv = MagicMock()
    path = tmp_path / "test.png"
    path.write_bytes(b"fake image data")

    result = await send_image(fs, adapter, conv, path)

    assert result is adapter.send.return_value
    fs.register_file.assert_not_called()
    adapter.send.assert_called_once()
    args, _ = adapter.send.call_args
    segment = args[1][0]
    assert segment["type"] == "image"
    assert segment["data"]["file"].startswith("file:///")


@pytest.mark.asyncio
async def test_send_image_file_not_found(tmp_path: Path) -> None:
    """send_image 传入不存在的路径应抛出 FileNotFoundError。"""
    fs = _make_file_server(enabled=True)
    adapter = _make_adapter()
    conv = MagicMock()
    missing = tmp_path / "nonexistent.png"

    with pytest.raises(FileNotFoundError, match="文件不存在"):
        await send_image(fs, adapter, conv, missing)


# ── send_audio ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_audio(tmp_path: Path) -> None:
    """send_audio 生成 type='record' 的消息段。"""
    fs = _make_file_server(enabled=True)
    adapter = _make_adapter()
    conv = MagicMock()
    path = tmp_path / "voice.amr"
    path.write_bytes(b"fake audio data")

    result = await send_audio(fs, adapter, conv, path)

    assert result is adapter.send.return_value
    fs.register_file.assert_called_once_with(path)
    adapter.send.assert_called_once()
    args, _ = adapter.send.call_args
    segment = args[1][0]
    assert segment["type"] == "record"
    assert "file" in segment["data"]


# ── prepare_image_segment ───────────────────────────────────────────────


def test_prepare_image_segment_enabled(tmp_path: Path) -> None:
    """FileServer 启用时 prepare_image_segment 返回 HTTP URL。"""
    fs = _make_file_server(enabled=True)
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"fake photo data")

    segment = prepare_image_segment(fs, path)

    assert segment["type"] == "image"
    assert segment["data"]["file"] == "http://127.0.0.1:8765/files/photo.jpg?token=faketoken"
    fs.register_file.assert_called_once_with(path)


def test_prepare_image_segment_disabled(tmp_path: Path) -> None:
    """FileServer 禁用时 prepare_image_segment 返回 file:/// 路径。"""
    fs = _make_file_server(enabled=False)
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"fake photo data")

    segment = prepare_image_segment(fs, path)

    assert segment["type"] == "image"
    assert segment["data"]["file"].startswith("file:///")
    fs.register_file.assert_not_called()


def test_prepare_audio_segment_enabled(tmp_path: Path) -> None:
    fs = _make_file_server(enabled=True)
    path = tmp_path / "voice.amr"
    path.write_bytes(b"fake audio data")

    segment = prepare_audio_segment(fs, path)

    assert segment["type"] == "record"
    assert segment["data"]["file"].endswith("/voice.amr?token=faketoken")
