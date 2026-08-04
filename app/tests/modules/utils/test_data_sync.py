"""neobot_app.utils.data_sync sync_data_files 数据同步测试。"""

from __future__ import annotations

from pathlib import Path

from neobot_app.utils.data_sync import sync_data_files


class _RecorderLogger:
    """记录 info/warning 消息的假 Logger，用于断言同步行为。"""

    def __init__(self) -> None:
        self.info_messages: list[str] = []
        self.warning_messages: list[str] = []

    def info(self, message: str, **kw) -> None:
        self.info_messages.append(str(message))

    def warning(self, message: str, **kw) -> None:
        self.warning_messages.append(str(message))


def test_sync_copies_new_file_when_dest_missing(tmp_path: Path) -> None:
    """Arrange: 源目录有文件而目标目录为空；Act: sync_data_files；Assert: 文件被复制。"""
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    (src / "a.txt").write_text("hello", encoding="utf-8")

    sync_data_files(src, dest)

    assert (dest / "a.txt").read_text(encoding="utf-8") == "hello"


def test_sync_overwrites_when_hash_differs(tmp_path: Path) -> None:
    """Arrange: 目标文件存在但内容与源不同；Act: sync_data_files；Assert: 目标被覆盖为源内容。"""
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    dest.mkdir()
    (src / "a.txt").write_text("new-content", encoding="utf-8")
    (dest / "a.txt").write_text("old-content", encoding="utf-8")

    sync_data_files(src, dest)

    assert (dest / "a.txt").read_text(encoding="utf-8") == "new-content"


def test_sync_skips_identical_file_and_logs_copy(tmp_path: Path) -> None:
    """Arrange: 目标文件不存在；Act: 连续同步两次；Assert: 首次复制记录日志、二次跳过不覆盖。"""
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    src.mkdir()
    (src / "a.txt").write_text("same", encoding="utf-8")
    logger = _RecorderLogger()

    sync_data_files(src, dest, logger=logger)
    sync_data_files(src, dest, logger=logger)

    assert len(logger.info_messages) == 1
    assert "已复制" in logger.info_messages[0]
    assert (dest / "a.txt").read_text(encoding="utf-8") == "same"


def test_sync_missing_source_dir_is_tolerant(tmp_path: Path) -> None:
    """Arrange: 源目录不存在；Act: sync_data_files；Assert: 不抛错、不打日志级异常、目标不创建。"""
    src = tmp_path / "not_exist"
    dest = tmp_path / "dest"
    logger = _RecorderLogger()

    sync_data_files(src, dest, logger=logger)

    assert not dest.exists()
    assert len(logger.warning_messages) == 1
    assert "源数据目录不存在" in logger.warning_messages[0]


def test_sync_recurses_into_nested_directories(tmp_path: Path) -> None:
    """Arrange: 源目录含嵌套子目录文件；Act: sync_data_files；Assert: 层级结构被完整复制。"""
    src = tmp_path / "src"
    nested = src / "sub" / "deep"
    nested.mkdir(parents=True)
    (src / "root.txt").write_text("r", encoding="utf-8")
    (nested / "leaf.txt").write_text("l", encoding="utf-8")
    dest = tmp_path / "dest"

    sync_data_files(src, dest)

    assert (dest / "root.txt").read_text(encoding="utf-8") == "r"
    assert (dest / "sub" / "deep" / "leaf.txt").read_text(encoding="utf-8") == "l"


def test_sync_empty_source_creates_dest_only(tmp_path: Path) -> None:
    """Arrange: 源目录为空；Act: sync_data_files；Assert: 目标目录被创建且无文件。"""
    src = tmp_path / "src"
    src.mkdir()
    dest = tmp_path / "dest"

    sync_data_files(src, dest)

    assert dest.is_dir()
    assert list(dest.iterdir()) == []


def test_sync_skips_directories_and_is_idempotent(tmp_path: Path) -> None:
    """Arrange: 源含空子目录与文件；Act: 连续同步两次；Assert: 第二次不产生额外覆盖（幂等）。"""
    src = tmp_path / "src"
    (src / "empty_dir").mkdir(parents=True)
    (src / "f.bin").write_bytes(b"\x00\x01\x02")
    dest = tmp_path / "dest"

    sync_data_files(src, dest)
    first_mtime = (dest / "f.bin").stat().st_mtime_ns
    sync_data_files(src, dest)

    assert not (dest / "empty_dir").exists()
    assert (dest / "f.bin").stat().st_mtime_ns == first_mtime
