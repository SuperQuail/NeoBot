"""Windows 原生共享句柄：发布不依赖对已生成的目录改名。"""

from __future__ import annotations

import ctypes
import sys
from contextlib import ExitStack, contextmanager
from ctypes import wintypes
from pathlib import Path
from typing import Iterator

import pytest

from neobot_app.bilibili import video_frames as video_frames_module
from neobot_app.bilibili.video_frames import VideoFrameService

from .test_video_frames import _AVC_720, _BVID, _FakeClient, _FakeRun, _player
from .test_video_frames import fake_ffmpeg as fake_ffmpeg


@contextmanager
def _read_handle_without_delete_sharing(path: Path) -> Iterator[None]:
    """与普通读者相容，但不允许对这个路径进行删除或改名。"""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create_file.restype = wintypes.HANDLE
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    # GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, OPEN_EXISTING。
    # 打开目录还需要 FILE_FLAG_BACKUP_SEMANTICS；故意不授予 FILE_SHARE_DELETE。
    flags = 0x02000000 if path.is_dir() else 0x00000080
    handle = create_file(str(path), 0x80000000, 0x00000003, None, 3, flags, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        yield
    finally:
        if not close_handle(handle):
            raise ctypes.WinError(ctypes.get_last_error())


@pytest.mark.skipif(sys.platform != "win32", reason="需要 Windows 的 CreateFileW 共享语义")
@pytest.mark.parametrize("held_path", ["directory", "frame"])
async def test_frames_complete_while_native_reader_blocks_directory_rename(
    held_path: str, tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=2))
    service = VideoFrameService(_FakeClient(player=_player(_AVC_720)), data_dir=tmp_path)
    original_sheets = service._make_sheets
    denied_codes: list[int] = []

    with ExitStack() as readers:

        def make_sheets_and_hold_reader(frames: list[Path], sheet_dir: Path) -> list[Path]:
            sheets = original_sheets(frames, sheet_dir)
            output = sheet_dir.parent
            readers.enter_context(
                _read_handle_without_delete_sharing(output if held_path == "directory" else frames[0])
            )
            # 系统真实拒绝改名，确认拒绝条件；并非 monkeypatch 出来的 PermissionError。
            target = output.with_name(f"{output.name}-renamed")
            assert output.is_dir() and not target.exists()
            with pytest.raises(PermissionError) as denied:
                output.rename(target)
            assert denied.value.winerror in (5, 32)
            denied_codes.append(denied.value.winerror)
            assert output.is_dir() and not target.exists()
            return sheets

        monkeypatch.setattr(service, "_make_sheets", make_sheets_and_hold_reader)
        result = await service.frames(_BVID, describe=False)

        assert denied_codes
        assert result["ok"] is True, result["error"]
        assert len(result["frames"]) == 2 and len(result["sheets"]) == 1
        assert all(Path(path).is_file() for path in result["frames"] + result["sheets"])
        output = Path(result["frames"][0]).parent.parent
        assert (output / video_frames_module._COMPLETE_MARKER).is_file()
