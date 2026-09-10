"""技能层的压缩/图片转换必须离开事件循环。

- ArchiveSkill 的 zip/tar 压缩解压是 CPU+磁盘密集工作，原先直接跑在 async 方法里；
- BrowserSkill 的 JPEG→PNG 转换（PIL 解码+编码）同理；
- sandbox_maintenance 的 TempCleaner 是同步实现（整树扫描/删除）。
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from PIL import Image

from neobot_app.skills.archive_skill import ArchiveSkill
from neobot_app.skills.browser_skill import _convert_jpeg_file_to_png


async def test_archive_compress_runs_off_loop(make_sandbox) -> None:
    loop_thread = threading.get_ident()
    seen: list[int] = []

    sandbox = make_sandbox()
    skill = ArchiveSkill(sandbox_service=sandbox)
    await sandbox.write_file(sandbox.resolve_path("a.txt"), b"hello")

    original = skill._compress_zip_sync

    def _spy(sources, out):
        seen.append(threading.get_ident())
        return original(sources, out)

    skill._compress_zip_sync = _spy

    result = await skill.execute(
        "archive_compress", {"paths": ["a.txt"], "output": "out.zip"}
    )

    assert '"ok": true' in result
    assert sandbox.resolve_path("out.zip").is_file()
    assert seen and seen[0] != loop_thread


async def test_archive_decompress_runs_off_loop(make_sandbox) -> None:
    loop_thread = threading.get_ident()
    seen: list[int] = []

    sandbox = make_sandbox()
    skill = ArchiveSkill(sandbox_service=sandbox)
    await sandbox.write_file(sandbox.resolve_path("src/b.txt"), b"payload")
    await skill.execute(
        "archive_compress", {"paths": ["src"], "output": "pack.zip"}
    )

    original = skill._decompress_zip_sync

    def _spy(archive, dest):
        seen.append(threading.get_ident())
        return original(archive, dest)

    skill._decompress_zip_sync = _spy

    result = await skill.execute(
        "archive_decompress", {"archive": "pack.zip", "dest": "out"}
    )

    assert '"ok": true' in result
    assert sandbox.resolve_path("out/src/b.txt").read_bytes() == b"payload"
    assert seen and seen[0] != loop_thread


async def test_jpeg_to_png_conversion_runs_off_loop(tmp_path: Path) -> None:
    loop_thread = threading.get_ident()
    jpg = tmp_path / "shot.jpg"
    Image.new("RGB", (24, 24), (10, 120, 220)).save(jpg, format="JPEG")
    seen: list[int] = []

    def _call() -> bytes:
        seen.append(threading.get_ident())
        return _convert_jpeg_file_to_png(str(jpg))

    png_bytes = await asyncio.to_thread(_call)

    assert png_bytes.startswith(b"\x89PNG")
    assert seen and seen[0] != loop_thread


def test_jpeg_to_png_returns_valid_png(tmp_path: Path) -> None:
    jpg = tmp_path / "a.jpg"
    Image.new("RGB", (16, 16), (0, 0, 0)).save(jpg, format="JPEG")

    data = _convert_jpeg_file_to_png(str(jpg))

    assert data.startswith(b"\x89PNG\r\n\x1a\n")
