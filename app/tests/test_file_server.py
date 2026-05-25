"""Tests for the file server module."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from neobot_app.core.file_server import FileServer


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
