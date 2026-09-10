"""文件服务器模块的测试。"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from pathlib import Path

import aiohttp
import pytest
from PIL import Image

import neobot_app.core.file_server as file_server_module
from neobot_app.core.file_server import FileServer
from neobot_app.image.parser import ImageParseService


def test_enabled_true_register_returns_url(tmp_path: Path) -> None:
    """enabled=True 时 register_file 返回 HTTP URL。"""
    file_path = tmp_path / "test.txt"
    file_path.write_text("hello world")

    fs = FileServer(data_dir=tmp_path, enabled=True)
    url = fs.register_file(file_path)

    assert "http://" in url
    assert "?token=" in url


@pytest.mark.asyncio
async def test_enabled_false_skip_server(tmp_path: Path) -> None:
    """enabled=False 时 start() 不启动服务器。"""
    fs = FileServer(data_dir=tmp_path, enabled=False)
    await fs.start()

    assert fs._running is False


@pytest.mark.asyncio
async def test_enabled_false_logs_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """enabled=False 时输出警告日志。"""
    caplog.set_level(logging.WARNING)

    fs = FileServer(data_dir=tmp_path, enabled=False)
    await fs.start()

    assert "已跳过 HTTP 文件服务器启动" in caplog.text


@pytest.mark.asyncio
async def test_stop_noop_when_not_running(tmp_path: Path) -> None:
    """服务器从未启动时 stop() 应安全无副作用。"""
    fs = FileServer(data_dir=tmp_path, enabled=True)
    await fs.stop()  # should not raise any exception


@pytest.mark.asyncio
async def test_upload_image_returns_registered_segment(tmp_path: Path) -> None:
    """POST /files 保存上传图片并返回 OneBot 图片消息段。"""
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
    """返回的消息段 URL 可直接被 ImageParseService 使用。"""
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
async def test_uploaded_image_download_bypasses_proxy_for_local_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """本机文件服务器 URL 的下载必须绕过代理。

    开启系统代理的机器上，httpx 默认 trust_env=True 会把 127.0.0.1 请求也
    转发给代理并失败（502），导致"自己上传的图片解析不了"。这里用一个不可用
    的代理环境变量复现该场景，要求本机地址仍然直连成功。
    """
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:9")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)

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
    """POST /files 仅接受真正的图片内容。"""
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


def _register_txt_file(fs: FileServer, tmp_path: Path, name: str, content: str) -> str:
    """Arrange 辅助：在 data_dir/tmp 下写文件并注册，返回带 token 的 URL。"""
    path = fs._tmp_dir / name
    path.write_text(content, encoding="utf-8")
    return fs.register_file(path)


@pytest.mark.asyncio
async def test_cors_headers_present_on_file_response(tmp_path: Path) -> None:
    """GET /files 响应必须携带 CORS 允许来源/方法/请求头与缓存时长。"""
    fs = FileServer(data_dir=tmp_path, port=0, enabled=True)
    await fs.start()
    try:
        url = _register_txt_file(fs, tmp_path, "cors.txt", "cors-body")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                assert resp.status == 200
                assert resp.headers["Access-Control-Allow-Origin"] == "*"
                assert resp.headers["Access-Control-Allow-Methods"] == "GET,POST,OPTIONS"
                assert resp.headers["Access-Control-Allow-Headers"] == "Content-Type,Authorization"
                assert resp.headers["Access-Control-Max-Age"] == "86400"
    finally:
        await fs.stop()


@pytest.mark.asyncio
async def test_options_preflight_returns_cors_headers(tmp_path: Path) -> None:
    """浏览器预检 OPTIONS 请求必须返回 204 且携带 CORS 头。"""
    fs = FileServer(data_dir=tmp_path, port=0, enabled=True)
    await fs.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.options(f"http://127.0.0.1:{fs._port}/files/x.png") as resp:
                assert resp.status == 204
                assert resp.headers["Access-Control-Allow-Origin"] == "*"
    finally:
        await fs.stop()


@pytest.mark.asyncio
async def test_wrong_or_missing_token_rejected(tmp_path: Path) -> None:
    """GET 时 token 缺失或错误必须返回 403，不泄露文件内容。"""
    fs = FileServer(data_dir=tmp_path, port=0, enabled=True)
    await fs.start()
    try:
        url = _register_txt_file(fs, tmp_path, "guarded.txt", "secret-content")
        filename = re.search(r"/files/([^?]+)", url).group(1)
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{fs._port}/files/{filename}") as resp:
                assert resp.status == 403
            async with session.get(
                f"http://127.0.0.1:{fs._port}/files/{filename}?token=wrong-token"
            ) as resp:
                assert resp.status == 403
                assert "secret-content" not in await resp.text()
    finally:
        await fs.stop()


@pytest.mark.asyncio
async def test_expired_token_returns_404_and_removes_metadata(tmp_path: Path, monkeypatch) -> None:
    """token 过期后请求必须返回 404 且元数据被清除（边界：过期瞬间）。"""
    fs = FileServer(data_dir=tmp_path, port=0, enabled=True)
    await fs.start()
    try:
        url = _register_txt_file(fs, tmp_path, "expire.txt", "will-expire")
        now = file_server_module.epoch_seconds()
        monkeypatch.setattr(file_server_module, "epoch_seconds", lambda: now + 1_000_000)

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                assert resp.status == 404
                assert "已过期" in await resp.text()
        assert "expire.txt" not in fs._files
    finally:
        await fs.stop()


@pytest.mark.asyncio
async def test_metadata_path_outside_data_dir_rejected(tmp_path: Path) -> None:
    """元数据 path 越界（指向数据目录外）时文件请求必须被拒绝且不泄露外部文件（修复 BUG-0002）。"""
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-CONTENT", encoding="utf-8")
    fs = FileServer(data_dir=tmp_path / "data", port=0, enabled=True)
    url = _register_txt_file(fs, tmp_path / "data", "legit.txt", "hello")
    token = re.search(r"token=(\S+)", url).group(1)
    fs._files["legit.txt"].path = str(secret)
    fs._save_metadata()
    await fs.start()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://127.0.0.1:{fs._port}/files/legit.txt?token={token}"
            ) as resp:
                body = await resp.text()
                assert resp.status != 200
                assert "TOP-SECRET-CONTENT" not in body
    finally:
        await fs.stop()
