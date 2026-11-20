"""表情包定时扫描：目录指纹跳过与 8 小时强制全扫。"""

from __future__ import annotations

import time
from io import BytesIO

import pytest
from PIL import Image

from neobot_app.emoji.service import EmojiService
from neobot_storage import create_engine, make_uow_factory
from neobot_storage.models import Base


def _png_bytes(color: str = "red", size: tuple[int, int] = (2, 2)) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, color=color).save(output, format="PNG")
    return output.getvalue()


async def _make_service(tmp_path):
    engine = create_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'emoji.sqlite3').as_posix()}"
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    service = EmojiService(
        data_dir=tmp_path,
        uow_factory=make_uow_factory(engine),
    )
    return engine, service


def test_scan_intervals_are_15_minutes_and_8_hours() -> None:
    assert EmojiService._REFRESH_INTERVAL_SECONDS == 15 * 60
    assert EmojiService._FULL_SCAN_INTERVAL_SECONDS == 8 * 60 * 60


def test_dir_fingerprint_tracks_file_and_sidecar_changes(tmp_path) -> None:
    service = EmojiService(data_dir=tmp_path, uow_factory=lambda: None)  # type: ignore[arg-type]
    emoji_dir = tmp_path / "emoji"
    emoji_dir.mkdir()

    empty = service._dir_fingerprint()
    assert empty == ()

    image = emoji_dir / "a.png"
    image.write_bytes(_png_bytes())
    first = service._dir_fingerprint()
    assert first and first != empty

    # 同名原地覆盖：大小与 mtime_ns 变化都要能感知。
    image.write_bytes(_png_bytes(color="blue", size=(4, 4)))
    second = service._dir_fingerprint()
    assert second and second != first

    # 只改 .txt 侧文件也要能感知（目录 mtime 不会变）。
    (emoji_dir / "a.txt").write_text("描述", encoding="utf-8")
    third = service._dir_fingerprint()
    assert third and third != second


def test_dir_fingerprint_missing_directory_is_none(tmp_path) -> None:
    service = EmojiService(data_dir=tmp_path, uow_factory=lambda: None)  # type: ignore[arg-type]

    # 缺失与空目录必须区分：空目录是「稳定状态」，缺失要持续重试。
    assert service._dir_fingerprint() is None


@pytest.mark.asyncio
async def test_successful_scan_stamps_fingerprint(tmp_path) -> None:
    engine, service = await _make_service(tmp_path)
    try:
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        (emoji_dir / "a.png").write_bytes(_png_bytes())
        (emoji_dir / "a.txt").write_text("红色方块", encoding="utf-8")

        await service._scan_safe()

        assert service._last_dir_fingerprint == service._dir_fingerprint()
        assert service._last_full_scan_at > 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_refresh_skips_unchanged_and_scans_on_change(tmp_path, monkeypatch) -> None:
    engine, service = await _make_service(tmp_path)
    try:
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        image = emoji_dir / "a.png"
        image.write_bytes(_png_bytes())
        (emoji_dir / "a.txt").write_text("红色方块", encoding="utf-8")
        await service._scan_safe()

        calls = 0

        async def fake_scan_safe() -> None:
            nonlocal calls
            calls += 1

        monkeypatch.setattr(service, "_scan_safe", fake_scan_safe)

        # 目录没变：既没有新文件也没有新 txt，直接跳过。
        assert await service._refresh_once() is False
        assert calls == 0

        # 只改 txt 也要触发扫描（目录 mtime 不变，靠指纹里的文件 mtime）。
        (emoji_dir / "a.txt").write_text("新描述", encoding="utf-8")
        assert await service._refresh_once() is True
        assert calls == 1

        # 加文件同样触发。
        (emoji_dir / "b.png").write_bytes(_png_bytes(color="green"))
        assert await service._refresh_once() is True
        assert calls == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_full_scan_is_forced_after_eight_hours(tmp_path, monkeypatch) -> None:
    engine, service = await _make_service(tmp_path)
    try:
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        (emoji_dir / "a.png").write_bytes(_png_bytes())
        (emoji_dir / "a.txt").write_text("红色方块", encoding="utf-8")
        await service._scan_safe()

        calls = 0

        async def fake_scan_safe() -> None:
            nonlocal calls
            calls += 1

        monkeypatch.setattr(service, "_scan_safe", fake_scan_safe)
        service._last_full_scan_at = time.monotonic() - service._FULL_SCAN_INTERVAL_SECONDS - 1

        assert await service._refresh_once() is True
        assert calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_failed_scan_does_not_stamp_and_is_retried(tmp_path, monkeypatch) -> None:
    """扫描失败不能盖章，否则目录不变就永远不会重试。"""
    engine, service = await _make_service(tmp_path)
    try:
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        (emoji_dir / "a.png").write_bytes(_png_bytes())  # 没有 txt，会走视觉解析

        async def boom(items):
            raise RuntimeError("parse failed")

        monkeypatch.setattr(service, "_parse_batch", boom)

        with pytest.raises(RuntimeError):
            await service._scan_folder()

        assert service._last_dir_fingerprint is None
        assert service._last_full_scan_at == 0.0

        calls = 0

        async def fake_scan_safe() -> None:
            nonlocal calls
            calls += 1

        monkeypatch.setattr(service, "_scan_safe", fake_scan_safe)
        assert await service._refresh_once() is True
        assert calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cleanup_failure_does_not_stamp(tmp_path, monkeypatch) -> None:
    """DB 清理失败不能盖章，否则陈旧记录要等到下次目录变化或 8 小时后才重试。"""
    engine, service = await _make_service(tmp_path)
    try:
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        (emoji_dir / "a.png").write_bytes(_png_bytes())
        (emoji_dir / "a.txt").write_text("红色方块", encoding="utf-8")

        async def failing_cleanup(disk_files):
            return False

        monkeypatch.setattr(service, "_cleanup_stale_emoji_records", failing_cleanup)

        await service._scan_folder()

        # 已经成功扫过一次；清理失败必须把旧指纹清掉，否则下一轮会误判“没变化”。
        assert service._last_dir_fingerprint is None

        calls = 0

        async def fake_scan_safe() -> None:
            nonlocal calls
            calls += 1

        monkeypatch.setattr(service, "_scan_safe", fake_scan_safe)
        assert await service._refresh_once() is True
        assert calls == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_lookup_failure_does_not_stamp(tmp_path, monkeypatch) -> None:
    """DB 查询失败同样不盖章：下一轮重试而不是封印到 8 小时后。"""

    class _BrokenRepo:
        async def get_by_hash(self, file_hash):
            raise RuntimeError("db down")

        async def set(self, *args, **kwargs):
            return None

        async def list_all(self):
            return []

    class _BrokenUow:
        def __init__(self) -> None:
            self.emojis = _BrokenRepo()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def commit(self) -> None:
            return None

    service = EmojiService(data_dir=tmp_path, uow_factory=lambda: _BrokenUow())
    emoji_dir = tmp_path / "emoji"
    emoji_dir.mkdir()
    (emoji_dir / "a.png").write_bytes(_png_bytes())
    (emoji_dir / "a.txt").write_text("红色方块", encoding="utf-8")

    await service._scan_folder()

    assert service._last_dir_fingerprint is None


@pytest.mark.asyncio
async def test_missing_directory_retries_then_empty_recreation_clears_entries(
    tmp_path,
) -> None:
    engine, service = await _make_service(tmp_path)
    try:
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        (emoji_dir / "a.png").write_bytes(_png_bytes())
        (emoji_dir / "a.txt").write_text("红色方块", encoding="utf-8")
        await service._scan_safe()
        assert service.emoji_count == 1

        # 目录被移走：指纹为 None，定时循环每轮重试，且不清理数据库。
        emoji_dir.rename(tmp_path / "emoji-moved")
        assert await service._refresh_once() is True
        assert service._last_dir_fingerprint is None
        assert service.emoji_count == 1

        # 重建为空目录：这一轮必须真正扫描并清空旧索引，之后才允许跳过。
        (tmp_path / "emoji").mkdir()
        assert await service._refresh_once() is True
        assert service._entries == {}
        assert await service._refresh_once() is False
    finally:
        await service.stop()
        await engine.dispose()


@pytest.mark.asyncio
async def test_unreadable_file_does_not_stamp(tmp_path) -> None:
    """有文件读不出来时保留重试：瞬时 IO 错误不该被 8 小时强制周期封印。"""
    engine, service = await _make_service(tmp_path)
    try:
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        (emoji_dir / "good.png").write_bytes(_png_bytes())
        (emoji_dir / "good.txt").write_text("好的", encoding="utf-8")
        (emoji_dir / "bad.png").write_bytes(b"not-an-image")

        await service._scan_folder()

        assert service._last_dir_fingerprint is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_directory_failure_keeps_entries_and_does_not_stamp(tmp_path, monkeypatch) -> None:
    engine, service = await _make_service(tmp_path)
    try:
        emoji_dir = tmp_path / "emoji"
        emoji_dir.mkdir()
        (emoji_dir / "a.png").write_bytes(_png_bytes())
        (emoji_dir / "a.txt").write_text("红色方块", encoding="utf-8")
        await service._scan_safe()

        monkeypatch.setattr(service, "_list_image_files", lambda: None)
        await service._scan_folder()

        # 读目录失败：保留索引，但把指纹清掉，让下一轮继续重试。
        assert service._last_dir_fingerprint is None
        assert service.emoji_count == 1
    finally:
        await engine.dispose()
