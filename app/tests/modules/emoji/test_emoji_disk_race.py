"""表情包目录扫描快照竞态：扫描期间新增的文件不能被误标为已处理。"""

from __future__ import annotations

from neobot_app.emoji.service import EmojiService


class _FakeEmojiRepo:
    async def list_all(self):
        return []


class _FakeUow:
    def __init__(self) -> None:
        self.emojis = _FakeEmojiRepo()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def commit(self) -> None:
        return None


def _uow_factory() -> _FakeUow:
    return _FakeUow()


async def test_scan_does_not_swallow_file_added_during_scan(tmp_path) -> None:
    """扫描先列文件、后盖章快照：列完后写入的文件必须留给下一次读取发现。"""
    service = EmojiService(data_dir=tmp_path, uow_factory=_uow_factory)
    await service.start()
    emoji_dir = tmp_path / "emoji"
    original = service._list_image_files

    def _racing_list():
        # 模拟「列文件之后、写快照之前」另一个群刚保存了一张表情包
        (emoji_dir / "new.png").write_bytes(b"\x89PNG\r\n\x1a\nfake-emoji")
        return []

    service._list_image_files = _racing_list  # type: ignore[method-assign]
    try:
        await service._scan_folder()
    finally:
        service._list_image_files = original  # type: ignore[method-assign]

    # 旧实现会在这里把目录快照更新为「已包含 new.png」，于是永远看不到它
    assert service.emoji_count == 1
    assert any(entry.file_name == "new.png" for _, entry in service.list_entries())
    await service.stop()