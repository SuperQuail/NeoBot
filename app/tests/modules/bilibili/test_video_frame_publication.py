"""抽帧结果的完成边界、保留策略与后台线程取消。"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from neobot_app.bilibili import video_frames as video_frames_module
from neobot_app.bilibili.video_frames import VideoFrameService

from .test_video_frames import _AVC_720, _BVID, _FakeClient, _FakeRun, _FakeVision, _player
from .test_video_frames import fake_ffmpeg as fake_ffmpeg


def test_pruning_keeps_active_requests_and_removes_abandoned_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module, "_MAX_OUTPUT_DIRS", 1)
    service = VideoFrameService(data_dir=tmp_path)
    active = service._create_output_dir(_BVID)
    abandoned = service._create_output_dir(_BVID)
    older = service._create_output_dir(_BVID)
    newer = service._create_output_dir(_BVID)
    for path in (older, newer):
        (path / video_frames_module._COMPLETE_MARKER).touch()
    now = time.time()
    for path, stamp in (
        (active, now - 20),
        (abandoned, now - video_frames_module._OUTPUT_TTL_SECONDS - 1),
        (older, now),
        (newer, now),
    ):
        os.utime(path, (stamp, stamp))

    # 模拟粗粒度文件系统时间戳；本次完成的目录不能因并列而被清掉。
    service._prune_outputs(active.parent, keep=newer)

    assert set(active.parent.iterdir()) == {active, newer}
    assert not (active / video_frames_module._COMPLETE_MARKER).exists()


def test_pruning_reclaims_only_expired_legacy_frame_scratch_directories(tmp_path: Path) -> None:
    service = VideoFrameService(data_dir=tmp_path)
    base = tmp_path / "bilibili_frames"
    expired = time.time() - video_frames_module._OUTPUT_TTL_SECONDS - 60
    removed_names = {f".{_BVID}-abc12345", f".{_BVID}.old"}
    kept_names = {f".{_BVID}-abc12346", ".unrelated-abc12345", f".{_BVID}-short", f".{_BVID}-abc12347"}
    for name in removed_names | kept_names:
        directory = base / name
        directory.mkdir(parents=True)
        if name != f".{_BVID}-abc12347":
            (directory / "frames").mkdir()
            (directory / "sheets").mkdir()
        if name != f".{_BVID}-abc12346":
            os.utime(directory, (expired, expired))

    service._prune_outputs(base)

    assert {path.name for path in base.iterdir()} == kept_names


async def test_active_description_is_excluded_from_completed_output_limit(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module, "_MAX_OUTPUT_DIRS", 1)
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=1))
    started = asyncio.Event()
    release = asyncio.Event()

    class PausedVision(_FakeVision):
        async def chat(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
            started.set()
            await release.wait()
            return {"content": "完整画面"}

    service = VideoFrameService(
        _FakeClient(player=_player(_AVC_720)), vision_provider=PausedVision(), data_dir=tmp_path
    )
    first_task = asyncio.create_task(service.frames(_BVID))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        base = tmp_path / "bilibili_frames"
        active = next(base.iterdir())
        assert not (active / video_frames_module._COMPLETE_MARKER).exists()
        second = await service.frames(_BVID, describe=False)
        assert second["ok"] is True
        assert active.is_dir()
        assert (active / "sheets" / "sheet_1.jpg").is_file()
    finally:
        release.set()
    first = await asyncio.wait_for(first_task, timeout=5)
    assert first["ok"] is True and first["description"] == "完整画面"
    assert (active / video_frames_module._COMPLETE_MARKER).is_file()
    assert list(base.iterdir()) == [active]


async def test_completion_marker_failure_removes_only_its_request(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=1))
    service = VideoFrameService(_FakeClient(player=_player(_AVC_720)), data_dir=tmp_path)
    previous = await service.frames(_BVID)
    previous_bytes = {path: Path(path).read_bytes() for path in previous["frames"] + previous["sheets"]}
    original_touch = Path.touch

    def deny_marker(path: Path, *args: Any, **kwargs: Any) -> None:
        if path.name == video_frames_module._COMPLETE_MARKER:
            raise PermissionError("marker denied")
        original_touch(path, *args, **kwargs)

    monkeypatch.setattr(Path, "touch", deny_marker)
    failed = await service.frames(_BVID)

    assert failed["ok"] is False and "保存抽帧结果失败" in failed["error"]
    assert failed["frames"] == [] and failed["sheets"] == []
    assert all(Path(path).read_bytes() == content for path, content in previous_bytes.items())
    assert list((tmp_path / "bilibili_frames").iterdir()) == [Path(previous["frames"][0]).parent.parent]


async def test_output_subdirectory_failure_cleans_new_run(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_mkdir = Path.mkdir

    def deny_sheets(path: Path, *args: Any, **kwargs: Any) -> None:
        if path.name == "sheets":
            raise PermissionError("sheets denied")
        original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", deny_sheets)
    service = VideoFrameService(_FakeClient(player=_player(_AVC_720)), data_dir=tmp_path)

    failed = await service.frames(_BVID)

    assert failed["ok"] is False and "创建画面目录失败" in failed["error"]
    assert list((tmp_path / "bilibili_frames").iterdir()) == []


@pytest.mark.parametrize("stage", ["ffmpeg", "sheets"])
@pytest.mark.parametrize("writer_fails", [False, True])
async def test_cancel_waits_for_running_writer_before_discarding_its_directory(
    stage: str, writer_fails: bool, tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    release = threading.Event()
    removed = asyncio.Event()
    loop = asyncio.get_running_loop()
    writer_saw_directory: list[bool] = []
    service = VideoFrameService(_FakeClient(player=_player(_AVC_720)), data_dir=tmp_path)
    fake_run = _FakeRun(frames=1)
    monkeypatch.setattr(video_frames_module.subprocess, "run", fake_run)
    previous = await service.frames(_BVID)
    assert previous["ok"] is True
    previous_output = Path(previous["frames"][0]).parent.parent
    previous_bytes = {path: Path(path).read_bytes() for path in previous["frames"] + previous["sheets"]}
    original_sheets = service._make_sheets
    original_rmtree = video_frames_module.shutil.rmtree

    def pause_writer(directory: Path) -> None:
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test writer was not released")
        writer_saw_directory.append(directory.is_dir())
        if writer_fails:
            raise RuntimeError("canceled writer failed")

    def run(command: list[str], **kwargs: Any) -> Any:
        if stage == "ffmpeg":
            pause_writer(Path(command[-1]).parent.parent)
        return fake_run(command, **kwargs)

    def sheets(frames: list[Path], sheet_dir: Path) -> list[Path]:
        if stage == "sheets":
            pause_writer(sheet_dir.parent)
        return original_sheets(frames, sheet_dir)

    def rmtree(path: Any, **kwargs: Any) -> None:
        original_rmtree(path, **kwargs)
        if Path(path).name.startswith(video_frames_module._RUN_PREFIX):
            loop.call_soon_threadsafe(removed.set)

    monkeypatch.setattr(video_frames_module.subprocess, "run", run)
    monkeypatch.setattr(service, "_make_sheets", sheets)
    monkeypatch.setattr(video_frames_module.shutil, "rmtree", rmtree)
    task = asyncio.create_task(service.frames(_BVID))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        output = next(path for path in (tmp_path / "bilibili_frames").iterdir() if path != previous_output)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=1)
        assert output.is_dir()
        assert not removed.is_set()
        assert not (output / video_frames_module._COMPLETE_MARKER).exists()
    finally:
        release.set()

    await asyncio.wait_for(removed.wait(), timeout=5)
    assert writer_saw_directory == [True]
    assert not output.exists()
    assert all(Path(path).read_bytes() == content for path, content in previous_bytes.items())
    assert list((tmp_path / "bilibili_frames").iterdir()) == [previous_output]


async def test_cancel_during_description_discards_unfinished_run(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=1))
    started = asyncio.Event()

    class PausedVision(_FakeVision):
        async def chat(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
            started.set()
            await asyncio.Event().wait()
            return {"content": "unreachable"}

    service = VideoFrameService(
        _FakeClient(player=_player(_AVC_720)), vision_provider=PausedVision(), data_dir=tmp_path
    )
    previous = await service.frames(_BVID, describe=False)
    previous_bytes = {path: Path(path).read_bytes() for path in previous["frames"] + previous["sheets"]}
    task = asyncio.create_task(service.frames(_BVID))
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1)

    assert all(Path(path).read_bytes() == content for path, content in previous_bytes.items())
    assert list((tmp_path / "bilibili_frames").iterdir()) == [Path(previous["frames"][0]).parent.parent]


@pytest.mark.parametrize("stage", ["ffmpeg", "sheets"])
@pytest.mark.parametrize("writer_fails", [False, True])
def test_asyncio_run_shutdown_preserves_writer_directory_until_thread_finishes(
    stage: str, writer_fails: bool, tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    release = threading.Event()
    shutdown = threading.Event()
    failures: list[BaseException] = []
    outputs: list[Path] = []
    writer_saw_directory: list[bool] = []
    service = VideoFrameService(_FakeClient(player=_player(_AVC_720)), data_dir=tmp_path)
    fake_run = _FakeRun(frames=1)
    original_sheets = service._make_sheets
    original_shutdown = asyncio.BaseEventLoop.shutdown_default_executor
    previous = service._create_output_dir(_BVID)
    (previous / video_frames_module._COMPLETE_MARKER).touch()
    previous_frame = previous / "frames" / "keep.jpg"
    previous_frame.write_bytes(b"previous request")

    def pause_writer(directory: Path) -> None:
        outputs.append(directory)
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test writer was not released")
        writer_saw_directory.append(directory.is_dir())
        if writer_fails:
            raise RuntimeError("shutdown writer failed")

    def run(command: list[str], **kwargs: Any) -> Any:
        if stage == "ffmpeg":
            pause_writer(Path(command[-1]).parent.parent)
        return fake_run(command, **kwargs)

    def sheets(frames: list[Path], sheet_dir: Path) -> list[Path]:
        if stage == "sheets":
            pause_writer(sheet_dir.parent)
        return original_sheets(frames, sheet_dir)

    async def observe_shutdown(loop: asyncio.BaseEventLoop, *args: Any, **kwargs: Any) -> None:
        # asyncio.run 已取消并等待所有 Task，真实 executor 线程仍被 release 阻塞。
        shutdown.set()
        await original_shutdown(loop, *args, **kwargs)

    async def main() -> None:
        asyncio.create_task(service.frames(_BVID))
        assert await asyncio.to_thread(started.wait, 5)
        # 直接结束 main，让 asyncio.run 执行真正的全 Task 取消及 executor shutdown。

    def runner() -> None:
        try:
            asyncio.run(main())
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(video_frames_module.subprocess, "run", run)
    monkeypatch.setattr(service, "_make_sheets", sheets)
    monkeypatch.setattr(asyncio.BaseEventLoop, "shutdown_default_executor", observe_shutdown)
    thread = threading.Thread(target=runner)
    thread.start()
    try:
        assert shutdown.wait(timeout=5)
        assert len(outputs) == 1
        assert outputs[0].is_dir()
        assert not (outputs[0] / video_frames_module._COMPLETE_MARKER).exists()
    finally:
        release.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert failures == []
    assert writer_saw_directory == [True]
    assert not outputs[0].exists()
    assert list(previous.parent.iterdir()) == [previous]
    assert previous_frame.read_bytes() == b"previous request"


async def test_unexpected_writer_failure_cleans_unfinished_run(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_run(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("writer failed")

    monkeypatch.setattr(video_frames_module.subprocess, "run", broken_run)
    service = VideoFrameService(_FakeClient(player=_player(_AVC_720)), data_dir=tmp_path)

    with pytest.raises(RuntimeError, match="writer failed"):
        await service.frames(_BVID)

    assert list((tmp_path / "bilibili_frames").iterdir()) == []


@pytest.mark.timeout(180)
async def test_100_rounds_of_concurrent_frames_keep_complete_independent_outputs(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=2))
    service = VideoFrameService(_FakeClient(player=_player(_AVC_720)), data_dir=tmp_path)

    for round_number in range(100):
        results = await asyncio.gather(service.frames(_BVID), service.frames(_BVID))
        directories = []
        for result in results:
            assert result["ok"] is True, (round_number, result["error"])
            assert len(result["frames"]) == 2 and len(result["sheets"]) == 1
            assert all(Path(path).is_file() for path in result["frames"] + result["sheets"])
            directory = Path(result["frames"][0]).parent.parent
            assert (directory / video_frames_module._COMPLETE_MARKER).is_file()
            directories.append(directory)
        assert directories[0] != directories[1]

    assert len(list((tmp_path / "bilibili_frames").iterdir())) == video_frames_module._MAX_OUTPUT_DIRS
