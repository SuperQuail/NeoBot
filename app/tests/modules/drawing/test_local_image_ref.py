"""本地图片引用的读取边界测试。

修复前的 ``_download_image_ref`` 对 ``file://`` 与裸路径都直接 ``read_bytes()``：
上游只要能给到 ``url``/``file`` 字段（被注入的事件、模型构造的引用），
就能让 Bot 读任意本地文件。现在只接受「确实是图片且不超上限」的文件。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from neobot_app.drawing import service as drawing_service_module
from neobot_app.drawing.service import CreatorImageService

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
_JPEG_BYTES = b"\xff\xd8\xff" + b"\x00" * 64


def _stub_service() -> CreatorImageService:
    """本地读取分支不需要实例状态，构造一个 bare 实例即可。"""
    return CreatorImageService.__new__(CreatorImageService)


async def test_local_ref_rejects_non_image_file(tmp_path: Path) -> None:
    secret = tmp_path / ".env"
    secret.write_text("DeepSeek_APIKey=sk-super-secret-value\n", encoding="utf-8")

    with pytest.raises(LookupError) as excinfo:
        await _stub_service()._download_image_ref(f"file:///{secret.as_posix()}")

    assert "不是图片" in str(excinfo.value)


async def test_local_ref_accepts_real_image(tmp_path: Path) -> None:
    image = tmp_path / "picture.png"
    image.write_bytes(_PNG_BYTES)

    data = await _stub_service()._download_image_ref(f"file:///{image.as_posix()}")

    assert data == _PNG_BYTES


async def test_bare_path_is_validated_too(tmp_path: Path) -> None:
    """裸路径分支（无 file:// 前缀）走同一套校验。"""
    secret = tmp_path / "neobot.db"
    secret.write_bytes(b"SQLite format 3\x00" + b"\x00" * 32)

    with pytest.raises(LookupError) as excinfo:
        await _stub_service()._download_image_ref(str(secret))

    assert "不是图片" in str(excinfo.value)


async def test_bare_path_accepts_real_image(tmp_path: Path) -> None:
    image = tmp_path / "photo.jpg"
    image.write_bytes(_JPEG_BYTES)

    assert await _stub_service()._download_image_ref(str(image)) == _JPEG_BYTES


async def test_local_ref_rejects_oversized_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(drawing_service_module, "_MAX_REMOTE_FETCH_BYTES", 32)
    image = tmp_path / "big.png"
    image.write_bytes(_PNG_BYTES)

    with pytest.raises(LookupError) as excinfo:
        await _stub_service()._download_image_ref(f"file:///{image.as_posix()}")

    assert "过大" in str(excinfo.value)


async def test_riff_without_webp_marker_is_rejected(tmp_path: Path) -> None:
    """RIFF 容器还要看 WEBP 标识，避免把普通 RIFF 文件当图片。"""
    riff = tmp_path / "sound.wav"
    riff.write_bytes(b"RIFF" + b"\x00" * 8 + b"WAVE" + b"\x00" * 32)

    with pytest.raises(LookupError):
        await _stub_service()._download_image_ref(f"file:///{riff.as_posix()}")


async def test_missing_file_reports_clear_error(tmp_path: Path) -> None:
    with pytest.raises(LookupError) as excinfo:
        await _stub_service()._download_image_ref(
            f"file:///{(tmp_path / 'nope.png').as_posix()}"
        )

    assert "不存在" in str(excinfo.value)
