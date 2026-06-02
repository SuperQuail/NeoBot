"""Tests for the file server module."""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path

import aiohttp
import pytest
from PIL import Image

from neobot_app.core.file_server import FileServer
from neobot_app.image.parser import ImageParseService


def test_enabled_true_register_returns_url(tmp_path: Path) -> None:
    """register_file returns HTTP URL when enabled=True."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")

    fs = FileServer(data_dir=tmp_path, enabled=True)
    url = fs.register_file(file_path)

    assert "http://" in url
    assert "?token=" in url


@pytest.mark.asyncio
async def test_enabled_false_skip_server(tmp_path: Path) -> None:
    """start() does not start server when enabled=False."""
    fs = FileServer(data_dir=tmp_path, enabled=False)
    await fs.start()

    assert fs._running is False


@pytest.mark.asyncio
async def test_enabled_false_logs_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """warning log emitted when enabled=False."""
    caplog.set_level(logging.WARNING)

    fs = FileServer(data_dir=tmp_path, enabled=False)
    await fs.start()

    assert "已跳过 HTTP 文件服务器启动" in caplog.text


@pytest.mark.asyncio
async def test_stop_noop_when_not_running(tmp_path: Path) -> None:
    """stop() is safe when server never started."""
    fs = FileServer(data_dir=tmp_path, enabled=True)
    await fs.stop()  # should not raise any exception


@pytest.mark.asyncio
async def test_upload_image_returns_registered_segment(tmp_path: Path) -> None:
    """POST /files stores an uploaded image and returns a OneBot image segment."""
    fs = FileServer(data_dir=tmp_path, port=0, enabled=True)
    await fs.start()
    try:
        image_bytes = _png_bytes()
        form = aiohttp.FormData()
        form.add_field(
            "file",
            image_bytes,
            filename="photo.png",
            content_type="image/png",
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(f"http://127.0.0.1:{fs._port}/files", data=form) as resp:
                assert resp.status == 200
                payload = await resp.json()

            assert payload["ok"] is True
            data = payload["data"]
            assert data["original_filename"] == "photo.png"
            assert data["content_type"] == "image/png"
            assert data["width"] == 2
            assert data["height"] == 2
            assert data["url"].startswith(f"http://127.0.0.1:{fs._port}/files/")
            assert "?token=" in data["url"]
            assert data["segment"] == {
                "type": "image",
                "data": {
                    "file": data["url"],
                    "url": data["url"],
                },
            }

            async with session.get(data["url"]) as file_resp:
                assert file_resp.status == 200
                assert await file_resp.read() == image_bytes
    finally:
        await fs.stop()


@pytest.mark.asyncio
async def test_uploaded_image_segment_can_be_read_by_image_parser(tmp_path: Path) -> None:
    """The returned segment URL is directly usable by ImageParseService."""
    fs = FileServer(data_dir=tmp_path, port=0, enabled=True)
    await fs.start()
    try:
        form = aiohttp.FormData()
        form.add_field(
            "file",
            _png_bytes(),
            filename="photo.png",
            content_type="image/png",
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(f"http://127.0.0.1:{fs._port}/files", data=form) as resp:
                payload = await resp.json()

        parser = ImageParseService()
        content = await parser._download_image(payload["data"]["segment"])

        assert content == _png_bytes()
    finally:
        await fs.stop()


@pytest.mark.asyncio
async def test_upload_image_rejects_non_image(tmp_path: Path) -> None:
    """POST /files only accepts real image payloads."""
    fs = FileServer(data_dir=tmp_path, port=0, enabled=True)
    await fs.start()
    try:
        form = aiohttp.FormData()
        form.add_field(
            "file",
            b"not an image",
            filename="note.txt",
            content_type="text/plain",
        )

        async with aiohttp.ClientSession() as session:
            async with session.post(f"http://127.0.0.1:{fs._port}/files", data=form) as resp:
                assert resp.status == 400
                payload = await resp.json()

        assert payload["ok"] is False
        assert payload["error"]["code"] == "invalid_image"
    finally:
        await fs.stop()


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color=(255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()
