"""B 站视频画面：DASH 地址解析、抽帧拼图、视觉描述与失败降级（不联网）。"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from neobot_app.audio.ffmpeg_install import FFmpegTools
from neobot_app.bilibili import video_frames as video_frames_module
from neobot_app.bilibili.client import DEFAULT_USER_AGENT
from neobot_app.bilibili.video_frames import VideoFrameService
from neobot_app.skills.bilibili_video_frames import BilibiliVideoFramesSkill

_FFMPEG = Path(__file__).resolve().with_name("ffmpeg.exe")
_BVID = "BV1xx411c7mD"
_VIEW = {"bvid": _BVID, "aid": 170001, "pages": [{"cid": 111}]}
_AVC_720 = {
    "base_url": "https://cdn/avc-720.m4s",
    "codecid": 7,
    "codecs": "avc1.64001F",
    "width": 1280,
    "height": 720,
    "bandwidth": 2_000_000,
}
_AVC_1080 = {
    "base_url": "https://cdn/avc-1080.m4s",
    "codecid": 7,
    "codecs": "avc1.640028",
    "width": 1920,
    "height": 1080,
    "bandwidth": 5_000_000,
}
_HEVC_1080 = {
    "base_url": "https://cdn/hevc-1080.m4s",
    "codecid": 12,
    "codecs": "hev1.1.6.L120",
    "width": 1920,
    "height": 1080,
    "bandwidth": 9_000_000,
}


class _FakeClient:
    """只提供视频链路用到的最小 client。"""

    def __init__(
        self,
        *,
        info: Any = None,
        player: Any = None,
        playurl: Any = None,
    ) -> None:
        self.info = _VIEW if info is None else info
        self.player = {} if player is None else player
        self.playurl = {"code": 0, "data": {"dash": {"video": []}}} if playurl is None else playurl
        self.calls: list[tuple[Any, ...]] = []
        self.fetch_calls: list[dict[str, Any]] = []

    def get_video_info(self, identifier: str) -> Any:
        self.calls.append(("info", identifier))
        if isinstance(self.info, Exception):
            raise self.info
        return self.info

    def get_player_info(self, bvid: str, cid: int) -> Any:
        self.calls.append(("player", bvid, cid))
        return self.player

    def _fetch(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        self.fetch_calls.append({"method": method, "url": url, "params": params, "headers": headers})
        if isinstance(self.playurl, Exception):
            raise self.playurl
        return self.playurl


class _FakeRun:
    """subprocess.run 替身：按 ffmpeg 输出模板写几张真 JPEG，记录命令。"""

    def __init__(
        self,
        *,
        frames: int = 3,
        returncode: int = 0,
        stderr: bytes = b"",
        error: Exception | None = None,
        partial: int = 0,
    ) -> None:
        self.commands: list[list[str]] = []
        self.frames = frames
        self.returncode = returncode
        self.stderr = stderr
        self.error = error
        self.partial = partial

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.commands.append(list(command))
        if self.error is not None:
            raise self.error
        count = self.frames if self.returncode == 0 else self.partial
        if count:
            target = Path(command[-1])
            target.parent.mkdir(parents=True, exist_ok=True)
            for index in range(1, count + 1):
                Image.new("RGB", (640, 360), (index * 40 % 255, 80, 120)).save(target.parent / f"f_{index:05d}.jpg")
        return subprocess.CompletedProcess(command, self.returncode, b"", self.stderr)


class _FakeVision:
    def __init__(self, content: str = "画面里是游戏实况", *, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.messages: list[list[dict[str, Any]]] = []

    async def chat(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        self.messages.append(messages)
        if self.error is not None:
            raise self.error
        return {"content": self.content}


@pytest.fixture()
def fake_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> Path:
    async def _ensure(**_kwargs: Any) -> FFmpegTools:
        return FFmpegTools(_FFMPEG, None)

    monkeypatch.setattr(video_frames_module, "ensure_ffmpeg", _ensure)
    return _FFMPEG.resolve()


def _player(*videos: dict[str, Any]) -> dict[str, Any]:
    return {"dash": {"video": list(videos)}}


# ── 视频流地址 ──


async def test_frames_picks_avc_720p_and_builds_sheet(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_run = _FakeRun(frames=5)
    monkeypatch.setattr(video_frames_module.subprocess, "run", fake_run)
    client = _FakeClient(player=_player(_HEVC_1080, _AVC_1080, _AVC_720))
    data_dir = tmp_path / "data"

    result = await VideoFrameService(client, data_dir=data_dir).frames(f"https://www.bilibili.com/video/{_BVID}")

    assert result["ok"] is True
    assert result["bvid"] == _BVID
    assert result["error"] == ""
    assert result["description"] == ""
    frames = [Path(item) for item in result["frames"]]
    assert len(frames) == 5
    assert all(path.is_file() and path.suffix == ".jpg" for path in frames)
    assert frames[0].parent.name == "frames"
    assert frames[0].parent.parent.parent == data_dir / "bilibili_frames"
    assert frames[0].parent.parent.name.startswith(f"run-{_BVID}-")
    assert (frames[0].parent.parent / video_frames_module._COMPLETE_MARKER).is_file()
    sheets = [Path(item) for item in result["sheets"]]
    assert len(sheets) == 1
    assert sheets[0].name == "sheet_1.jpg"
    assert sheets[0].is_file()
    with Image.open(sheets[0]) as sheet_image:
        assert sheet_image.size == (4 * 320, 4 * 180)

    command = fake_run.commands[0]
    assert command[0] == str(fake_ffmpeg)
    assert command[command.index("-i") + 1] == _AVC_720["base_url"]
    assert command[command.index("-user_agent") + 1] == DEFAULT_USER_AGENT
    assert "Referer: https://www.bilibili.com/" in command[command.index("-headers") + 1]
    assert command[command.index("-vf") + 1] == "fps=1/60,scale=640:-2"
    assert command[command.index("-frames:v") + 1] == "32"
    assert command[-1].endswith("f_%05d.jpg")
    assert client.calls == [
        ("info", f"https://www.bilibili.com/video/{_BVID}"),
        ("player", _BVID, 111),
    ]


async def test_frames_splits_into_multiple_sheets(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=17))
    service = VideoFrameService(_FakeClient(player=_player(_AVC_720)), data_dir=tmp_path)

    result = await service.frames(_BVID)

    assert result["ok"] is True
    sheets = [Path(item) for item in result["sheets"]]
    assert [path.name for path in sheets] == ["sheet_1.jpg", "sheet_2.jpg"]
    for sheet in sheets:
        with Image.open(sheet) as sheet_image:
            assert sheet_image.size == (4 * 320, 4 * 180)


async def test_concurrent_frames_for_same_bvid_keep_full_output(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=2))
    service = VideoFrameService(_FakeClient(player=_player(_AVC_720)), data_dir=tmp_path)

    first, second = await asyncio.gather(service.frames(_BVID), service.frames(_BVID))

    for result in (first, second):
        assert result["ok"] is True
        assert all(Path(item).is_file() for item in result["frames"])
    base = tmp_path / "bilibili_frames"
    output_dirs = [Path(result["frames"][0]).parent.parent for result in (first, second)]
    assert output_dirs[0] != output_dirs[1]
    assert set(base.iterdir()) == set(output_dirs)
    for output in output_dirs:
        assert len(list((output / "frames").glob("f_*.jpg"))) == 2
    # 没有残留的临时目录
    assert [item.name for item in base.iterdir() if item.name.startswith(".")] == []


async def test_concurrent_frames_keep_each_requests_sheets_during_description(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """第二次抽帧完成时，第一次仍必须能读取自己的第二张拼图。"""
    started = asyncio.Event()
    release = asyncio.Event()

    class PausedVision(_FakeVision):
        async def chat(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
            self.messages.append(messages)
            if len(self.messages) == 1:
                started.set()
                await release.wait()
            return {"content": f"拼图{len(self.messages)}"}

    vision = PausedVision()
    service = VideoFrameService(_FakeClient(player=_player(_AVC_720)), vision_provider=vision, data_dir=tmp_path)
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=17))
    first_task = asyncio.create_task(service.frames(_BVID))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=1))
        second = await service.frames(_BVID, describe=False)
    finally:
        release.set()
    first = await asyncio.wait_for(first_task, timeout=5)

    assert first["ok"] is True and second["ok"] is True
    assert first["description"] == "拼图1\n\n拼图2"
    assert len(first["frames"]) == 17 and len(second["frames"]) == 1
    assert all(Path(item).is_file() for result in (first, second) for item in result["frames"] + result["sheets"])
    assert Path(first["frames"][0]).parent != Path(second["frames"][0]).parent


async def test_frames_failure_keeps_previous_output(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=2))
    service = VideoFrameService(_FakeClient(player=_player(_AVC_720)), data_dir=tmp_path)
    previous = await service.frames(_BVID)
    assert previous["ok"] is True
    previous_bytes = {path: Path(path).read_bytes() for path in previous["frames"] + previous["sheets"]}

    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(returncode=1, stderr=b"boom"))
    failed = await service.frames(_BVID)

    assert failed["ok"] is False
    assert all(Path(path).read_bytes() == content for path, content in previous_bytes.items())
    assert list((tmp_path / "bilibili_frames").iterdir()) == [Path(previous["frames"][0]).parent.parent]


async def test_frames_prunes_old_output_dirs(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=1))
    base = tmp_path / "bilibili_frames"
    expired = time.time() - video_frames_module._OUTPUT_TTL_SECONDS - 60
    expired_dir = base / "BVexpired" / "frames"
    expired_dir.mkdir(parents=True)
    (expired_dir / "f_00001.jpg").write_bytes(b"old")
    os.utime(expired_dir.parent, (expired, expired))
    for index in range(25):
        extra = base / f"BVstale{index:02d}" / "frames"
        extra.mkdir(parents=True)
        (extra / "f_00001.jpg").write_bytes(b"old")
    service = VideoFrameService(_FakeClient(player=_player(_AVC_720)), data_dir=tmp_path)

    result = await service.frames(_BVID)
    assert result["ok"] is True

    # 只保留最近 20 份；超时的旧目录即使份数没超也会被清掉
    kept = sorted(item.name for item in base.iterdir() if item.is_dir())
    assert len(kept) == video_frames_module._MAX_OUTPUT_DIRS
    assert Path(result["frames"][0]).parent.parent.name in kept
    assert "BVexpired" not in kept


async def test_frames_falls_back_to_wbi_playurl_and_clamps_limits(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_run = _FakeRun(frames=2)
    monkeypatch.setattr(video_frames_module.subprocess, "run", fake_run)
    client = _FakeClient(
        player={},
        playurl={"code": 0, "data": {"dash": {"video": [_AVC_720]}}},
    )

    result = await VideoFrameService(client, data_dir=tmp_path).frames(_BVID, every=10, max_frames=99)

    assert result["ok"] is True
    assert len(result["frames"]) == 2
    assert len(client.fetch_calls) == 1
    call = client.fetch_calls[0]
    assert call["url"].endswith("/x/player/wbi/playurl")
    assert call["params"] == {"bvid": _BVID, "cid": 111, "fnval": 16, "fourk": 1}
    assert call["headers"] == {"Referer": f"https://www.bilibili.com/video/{_BVID}"}
    command = fake_run.commands[0]
    assert command[command.index("-vf") + 1] == "fps=1/10,scale=640:-2"
    assert command[command.index("-frames:v") + 1] == "32"


async def test_frames_uses_client_wbi_signing_when_available(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=1))

    class _SigningClient(_FakeClient):
        def _sign_wbi(self, params: dict[str, Any]) -> dict[str, Any]:
            return {**params, "w_rid": "signed"}

    client = _SigningClient(player={}, playurl={"code": 0, "data": {"dash": {"video": [_AVC_720]}}})
    result = await VideoFrameService(client, data_dir=tmp_path).frames(_BVID)

    assert result["ok"] is True
    assert client.fetch_calls[0]["params"]["w_rid"] == "signed"


# ── 视觉描述 ──


async def test_frames_describes_sheet_with_vision(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=4))
    vision = _FakeVision()
    service = VideoFrameService(
        _FakeClient(player=_player(_AVC_720)),
        vision_provider=vision,
        data_dir=tmp_path,
    )

    result = await service.frames(_BVID)

    assert result["ok"] is True
    assert result["description"] == "画面里是游戏实况"
    assert len(vision.messages) == 1
    content = vision.messages[0][0]["content"]
    assert content[0]["type"] == "text"
    assert "关键帧" in content[0]["text"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


async def test_frames_keeps_frames_when_vision_fails(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=3))
    vision = _FakeVision(error=RuntimeError("视觉模型炸了"))
    service = VideoFrameService(
        _FakeClient(player=_player(_AVC_720)),
        vision_provider=vision,
        data_dir=tmp_path,
    )

    result = await service.frames(_BVID)

    assert result["ok"] is True
    assert result["description"] == ""
    assert len(result["frames"]) == 3
    assert len(result["sheets"]) == 1


async def test_frames_skips_vision_when_describe_false(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_frames_module.subprocess, "run", _FakeRun(frames=2))
    vision = _FakeVision()
    service = VideoFrameService(
        _FakeClient(player=_player(_AVC_720)),
        vision_provider=vision,
        data_dir=tmp_path,
    )

    result = await service.frames(_BVID, describe=False)

    assert result["ok"] is True
    assert result["description"] == ""
    assert vision.messages == []


# ── 失败降级 ──


async def test_frames_degrades_without_client_or_video(tmp_path: Path) -> None:
    dormant = await VideoFrameService(None, data_dir=tmp_path).frames(_BVID)
    assert dormant["ok"] is False
    assert "未登录" in dormant["error"]

    broken = await VideoFrameService(_FakeClient(info=RuntimeError("接口炸了")), data_dir=tmp_path).frames(_BVID)
    assert broken["ok"] is False
    assert "获取视频信息失败" in broken["error"]

    missing = await VideoFrameService(_FakeClient(info={}), data_dir=tmp_path).frames(_BVID)
    assert missing["ok"] is False
    assert "未找到视频" in missing["error"]


async def test_frames_degrades_without_stream(tmp_path: Path, fake_ffmpeg: Path) -> None:
    client = _FakeClient(player={}, playurl={"code": 0, "data": {}})

    result = await VideoFrameService(client, data_dir=tmp_path).frames(_BVID)

    assert result["ok"] is False
    assert "视频流" in result["error"]
    assert result["frames"] == [] and result["sheets"] == []


async def test_frames_degrades_without_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _none(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(video_frames_module, "ensure_ffmpeg", _none)
    client = _FakeClient(player=_player(_AVC_720))

    result = await VideoFrameService(client, data_dir=tmp_path).frames(_BVID)

    assert result["ok"] is False
    assert "ffmpeg" in result["error"]
    assert client.fetch_calls == []


async def test_frames_cleans_partial_output_on_ffmpeg_failure(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_run = _FakeRun(returncode=1, partial=1, stderr=b"HTTP error 403")
    monkeypatch.setattr(video_frames_module.subprocess, "run", fake_run)

    result = await VideoFrameService(_FakeClient(player=_player(_AVC_720)), data_dir=tmp_path).frames(_BVID)

    assert result["ok"] is False
    assert "403" in result["error"]
    assert result["frames"] == [] and result["sheets"] == []
    assert list((tmp_path / "bilibili_frames").iterdir()) == []


async def test_frames_reports_ffmpeg_timeout_and_cleans_up(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_run = _FakeRun(error=subprocess.TimeoutExpired(["ffmpeg"], 300))
    monkeypatch.setattr(video_frames_module.subprocess, "run", fake_run)

    result = await VideoFrameService(_FakeClient(player=_player(_AVC_720)), data_dir=tmp_path).frames(_BVID)

    assert result["ok"] is False
    assert "超时" in result["error"]
    assert list((tmp_path / "bilibili_frames").iterdir()) == []


# ── Skill ──


class _FakeFramesService:
    def __init__(
        self,
        result: Any = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def frames(self, identifier: str, **kwargs: Any) -> Any:
        self.calls.append((identifier, kwargs))
        if self.error is not None:
            raise self.error
        return self.result


def _frames_result(**overrides: Any) -> dict[str, Any]:
    result = {
        "ok": True,
        "bvid": _BVID,
        "frames": ["/tmp/f_00001.jpg", "/tmp/f_00002.jpg"],
        "sheets": ["/tmp/sheet_1.jpg"],
        "description": "画面里是测试场景",
        "error": "",
    }
    result.update(overrides)
    return result


async def test_skill_returns_paths_and_no_auto_send_note() -> None:
    service = _FakeFramesService(_frames_result())
    skill = BilibiliVideoFramesSkill(service)

    raw = await skill.execute(
        "video_frames",
        {"identifier": _BVID, "every": 10, "max_frames": 4, "describe": False},
    )
    payload = json.loads(raw)

    assert payload["ok"] is True
    assert payload["bvid"] == _BVID
    assert payload["frames"] == ["/tmp/f_00001.jpg", "/tmp/f_00002.jpg"]
    assert payload["sheets"] == ["/tmp/sheet_1.jpg"]
    assert payload["description"] == "画面里是测试场景"
    assert payload["count"] == 2
    assert "read_image" in payload["note"]
    assert "画面里是测试场景" in raw and "\\u" not in raw
    assert service.calls == [(_BVID, {"every": 10, "max_frames": 4, "describe": False})]


async def test_skill_defaults_and_clamps_arguments() -> None:
    service = _FakeFramesService(_frames_result())
    skill = BilibiliVideoFramesSkill(service)

    await skill.execute("video_frames", {"identifier": _BVID})
    await skill.execute(
        "video_frames",
        {"identifier": _BVID, "every": 0, "max_frames": 100, "describe": "false"},
    )

    assert service.calls[0] == (_BVID, {"every": 60, "max_frames": 32, "describe": True})
    assert service.calls[1] == (_BVID, {"every": 60, "max_frames": 32, "describe": False})


async def test_skill_reports_missing_service_and_bad_arguments() -> None:
    assert BilibiliVideoFramesSkill(None).get_tools() == []
    unavailable = json.loads(await BilibiliVideoFramesSkill(None).execute("video_frames", {"identifier": _BVID}))
    assert unavailable["ok"] is False
    assert "未配置" in unavailable["error"]

    skill = BilibiliVideoFramesSkill(_FakeFramesService(_frames_result()))
    missing = json.loads(await skill.execute("video_frames", {}))
    assert missing["ok"] is False
    assert "identifier" in missing["error"]

    unknown = json.loads(await skill.execute("unknown", {}))
    assert unknown["ok"] is False
    assert "未知工具" in unknown["error"]


async def test_skill_degrades_when_service_fails_or_rejects() -> None:
    broken = BilibiliVideoFramesSkill(_FakeFramesService(error=RuntimeError("抽帧炸了")))
    result = json.loads(await broken.execute("video_frames", {"identifier": _BVID}))
    assert result["ok"] is False
    assert "获取视频画面失败" in result["error"]

    rejected = BilibiliVideoFramesSkill(_FakeFramesService(_frames_result(ok=False, error="没有取到视频流")))
    result = json.loads(await rejected.execute("video_frames", {"identifier": _BVID}))
    assert result["ok"] is False
    assert "没有取到视频流" in result["error"]

    weird = BilibiliVideoFramesSkill(_FakeFramesService("not-a-dict"))
    result = json.loads(await weird.execute("video_frames", {"identifier": _BVID}))
    assert result["ok"] is False
    assert "无法识别" in result["error"]
