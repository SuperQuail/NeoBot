"""B 站直播媒体服务：拉流地址缓存、截帧、截音频转写（全部失败降级）。"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from neobot_app.audio.ffmpeg_install import FFmpegTools
from neobot_app.bilibili import live_media
from neobot_app.bilibili.client import DEFAULT_USER_AGENT
from neobot_app.bilibili.live_media import LiveMediaService

_FFMPEG = Path(__file__).resolve().with_name("ffmpeg.exe")
_STREAM_URL = "https://flv.bilivideo.com/live-bvc/5050/live.flv?expires=1"
_HEADERS = "Referer: https://live.bilibili.com/\r\nOrigin: https://live.bilibili.com\r\n"


class _FakeClient:
    """只提供 get_live_playurl 的最小 client。"""

    def __init__(self, *, expires: int = 3598, url: str = _STREAM_URL) -> None:
        self.calls = 0
        self.expires = expires
        self.url = url

    def get_live_playurl(self, room_id: int) -> dict[str, Any]:
        self.calls += 1
        if not self.url:
            return {}
        return {
            "ok": True,
            "room_id": room_id,
            "url": self.url,
            "format": "flv",
            "expires": self.expires,
            "error": "",
        }


class _FakeAsr:
    def __init__(self, text: str = "直播里说的话", *, error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.sources: list[Path] = []

    async def transcribe(self, source: Any) -> str:
        self.sources.append(Path(source))
        if self.error is not None:
            raise self.error
        return self.text


class _FakeRun:
    """subprocess.run 替身：记录命令，成功时把 payload 写到最后一个参数（输出路径）。"""

    def __init__(
        self,
        *,
        returncode: int = 0,
        payload: bytes = b"fake-media",
        stderr: bytes = b"",
        error: Exception | None = None,
    ) -> None:
        self.commands: list[list[str]] = []
        self.returncode = returncode
        self.payload = payload
        self.stderr = stderr
        self.error = error

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.commands.append(list(command))
        if self.error is not None:
            raise self.error
        if self.returncode == 0:
            Path(command[-1]).write_bytes(self.payload)
        return subprocess.CompletedProcess(command, self.returncode, b"", self.stderr)


class _Clock:
    def __init__(self, now: float = 1000.0) -> None:
        self.now = now

    def monotonic(self) -> float:
        return self.now


@pytest.fixture()
def fake_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> Path:
    async def _ensure(**_kwargs: Any) -> FFmpegTools:
        return FFmpegTools(_FFMPEG, None)

    monkeypatch.setattr(live_media, "ensure_ffmpeg", _ensure)
    return _FFMPEG.resolve()


# ── 拉流地址缓存 ──


async def test_get_play_url_caches_and_refetches_on_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    monkeypatch.setattr(live_media, "time", SimpleNamespace(monotonic=clock.monotonic))
    client = _FakeClient(expires=3598)
    service = LiveMediaService(client)

    first = await service.get_play_url(5050)
    assert first["ok"] is True
    assert first["url"] == _STREAM_URL
    assert first["expires"] == 3598

    clock.now += 3000
    assert (await service.get_play_url(5050))["url"] == _STREAM_URL
    assert client.calls == 1

    clock.now += 400  # 超过 expires-300s（3298s）
    await service.get_play_url(5050)
    assert client.calls == 2

    await service.get_play_url(5050, force=True)
    assert client.calls == 3


async def test_get_play_url_resolves_client_getter_and_degrades() -> None:
    assert (await LiveMediaService(_FakeClient()).get_play_url(0))["error"] == "房间号无效"

    dormant = await LiveMediaService(lambda: None).get_play_url(5050)
    assert dormant["ok"] is False
    assert "未登录" in dormant["error"]

    class _Broken:
        def get_live_playurl(self, room_id: int) -> dict[str, Any]:
            raise RuntimeError("接口炸了")

    broken = await LiveMediaService(_Broken()).get_play_url(5050)
    assert broken["ok"] is False
    assert "获取直播拉流地址失败" in broken["error"]

    empty = await LiveMediaService(_FakeClient(url="")).get_play_url(5050)
    assert empty["ok"] is False
    assert "获取直播拉流地址失败" in empty["error"]

    getter = LiveMediaService(lambda: _FakeClient())
    assert (await getter.get_play_url(5050))["ok"] is True


# ── 截帧 ──


async def test_capture_frame_saves_jpeg(tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_run = _FakeRun(payload=b"fake-jpeg")
    monkeypatch.setattr(live_media.subprocess, "run", fake_run)
    client = _FakeClient()
    service = LiveMediaService(client, data_dir=tmp_path / "data")

    result = await service.capture_frame(5050)

    assert result["ok"] is True
    assert result["room_id"] == 5050
    assert result["url"] == _STREAM_URL
    assert result["bytes"] == b"fake-jpeg"
    frame = Path(result["path"])
    assert frame.is_file()
    assert frame.read_bytes() == b"fake-jpeg"
    assert frame.parent == tmp_path / "data" / "live_frames"
    assert frame.name.startswith("5050_") and frame.suffix == ".jpg"
    assert client.calls == 1
    command = fake_run.commands[0]
    assert command[0] == str(fake_ffmpeg)
    assert command[command.index("-i") + 1] == _STREAM_URL
    assert command[command.index("-rw_timeout") + 1] == "15000000"
    assert command[command.index("-user_agent") + 1] == DEFAULT_USER_AGENT
    assert command[command.index("-headers") + 1] == _HEADERS
    assert command[command.index("-frames:v") + 1] == "1"
    assert command[command.index("-vf") + 1] == "scale=640:-2"
    assert command[command.index("-q:v") + 1] == "5"
    assert command[-1] == result["path"]


async def test_capture_frame_honours_custom_scale_width(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_run = _FakeRun()
    monkeypatch.setattr(live_media.subprocess, "run", fake_run)
    service = LiveMediaService(_FakeClient(), data_dir=tmp_path)

    result = await service.capture_frame(5050, scale_width=320)

    assert result["ok"] is True
    command = fake_run.commands[0]
    assert command[command.index("-vf") + 1] == "scale=320:-2"


async def test_capture_frame_failure_cleans_partial_file(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_run = _FakeRun(returncode=1, payload=b"partial", stderr=b"Connection refused")
    monkeypatch.setattr(live_media.subprocess, "run", fake_run)
    service = LiveMediaService(_FakeClient(), data_dir=tmp_path)

    result = await service.capture_frame(5050)
    assert result["ok"] is False
    assert "Connection refused" in result["error"]
    assert result["path"] == "" and result["bytes"] == b""
    assert list((tmp_path / "live_frames").iterdir()) == []

    monkeypatch.setattr(
        live_media.subprocess,
        "run",
        _FakeRun(error=subprocess.TimeoutExpired(["ffmpeg"], 20)),
    )
    result = await service.capture_frame(5050)
    assert result["ok"] is False
    assert "超时" in result["error"]
    assert list((tmp_path / "live_frames").iterdir()) == []

    monkeypatch.setattr(live_media.subprocess, "run", _FakeRun(error=OSError("no such executable")))
    result = await service.capture_frame(5050)
    assert result["ok"] is False
    assert "无法启动 ffmpeg" in result["error"]
    assert list((tmp_path / "live_frames").iterdir()) == []


async def test_capture_frame_degrades_without_ffmpeg_or_stream(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _none(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(live_media, "ensure_ffmpeg", _none)
    missing = await LiveMediaService(_FakeClient(), data_dir=tmp_path).capture_frame(5050)
    assert missing["ok"] is False
    assert "ffmpeg" in missing["error"]

    fake_run = _FakeRun()
    monkeypatch.setattr(live_media, "ensure_ffmpeg", _fake_ensure_ffmpeg)
    monkeypatch.setattr(live_media.subprocess, "run", fake_run)
    no_stream = await LiveMediaService(_FakeClient(url=""), data_dir=tmp_path).capture_frame(5050)
    assert no_stream["ok"] is False
    assert "拉流地址" in no_stream["error"]
    assert fake_run.commands == []


async def test_capture_frame_prunes_old_frames(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """截帧长期累积：超过保留时间/数量的旧图要被清掉，新图保留。"""
    monkeypatch.setattr(live_media.subprocess, "run", _FakeRun())
    service = LiveMediaService(_FakeClient(), data_dir=tmp_path)
    frames = tmp_path / "live_frames"
    frames.mkdir(parents=True)
    stale = frames / "5050_old.jpg"
    stale.write_bytes(b"old")
    os.utime(stale, (1000.0, 1000.0))  # 远早于保留窗口

    result = await service.capture_frame(5050)

    assert result["ok"] is True
    assert Path(result["path"]).is_file()
    assert not stale.exists()


async def test_record_clip_prunes_old_clips(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live_media.subprocess, "run", _FakeRun())
    service = LiveMediaService(_FakeClient(), data_dir=tmp_path)
    clips = tmp_path / "live_clips"
    clips.mkdir(parents=True)
    stale = clips / "5050_old.flv"
    stale.write_bytes(b"old")
    os.utime(stale, (1000.0, 1000.0))

    result = await service.record_clip(5050, seconds=5)

    assert result["ok"] is True
    assert Path(result["path"]).is_file()
    assert not stale.exists()


# ── 截音频 + 转写 ──


async def test_transcribe_extracts_audio_and_returns_text(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_run = _FakeRun(payload=b"fake-mp3")
    monkeypatch.setattr(live_media.subprocess, "run", fake_run)
    asr = _FakeAsr("主播在聊天")
    data_dir = tmp_path / "data"
    service = LiveMediaService(_FakeClient(), asr_service=asr, data_dir=data_dir)

    result = await service.transcribe(5050, seconds=15)

    assert result == {"ok": True, "text": "主播在聊天", "seconds": 15, "error": ""}
    command = fake_run.commands[0]
    assert command[0] == str(fake_ffmpeg)
    assert command[command.index("-i") + 1] == _STREAM_URL
    assert command[command.index("-rw_timeout") + 1] == "15000000"
    assert command[command.index("-user_agent") + 1] == DEFAULT_USER_AGENT
    assert command[command.index("-headers") + 1] == _HEADERS
    assert command[command.index("-t") + 1] == "15"
    assert "-vn" in command
    assert command[command.index("-ac") + 1] == "1"
    assert command[command.index("-ar") + 1] == "16000"
    assert command[command.index("-c:a") + 1] == "libmp3lame"
    assert command[-1].endswith("audio.mp3")
    assert len(asr.sources) == 1
    assert not asr.sources[0].parent.exists()  # 临时目录已清理
    assert list(data_dir.iterdir()) == []


async def test_transcribe_truncates_text(tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(live_media.subprocess, "run", _FakeRun())
    service = LiveMediaService(_FakeClient(), asr_service=_FakeAsr("0123456789"), data_dir=tmp_path)

    result = await service.transcribe(5050, seconds=5, max_chars=4)

    assert result["ok"] is True
    assert result["text"] == "0123"
    assert result["seconds"] == 5


async def test_transcribe_reports_asr_failure_and_timeout(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live_media.subprocess, "run", _FakeRun())
    failed = _FakeAsr("语音识别失败：请求超时")
    service = LiveMediaService(_FakeClient(), asr_service=failed, data_dir=tmp_path)
    result = await service.transcribe(5050)
    assert result["ok"] is False
    assert result["error"] == "语音识别失败：请求超时"
    assert result["seconds"] == 15

    raising = LiveMediaService(_FakeClient(), asr_service=_FakeAsr(error=RuntimeError("boom")), data_dir=tmp_path)
    result = await raising.transcribe(5050)
    assert result["ok"] is False
    assert "语音识别失败" in result["error"]

    timeout_run = _FakeRun(error=subprocess.TimeoutExpired(["ffmpeg"], 35))
    monkeypatch.setattr(live_media.subprocess, "run", timeout_run)
    asr = _FakeAsr("不该用到")
    timed_out = LiveMediaService(_FakeClient(), asr_service=asr, data_dir=tmp_path)
    result = await timed_out.transcribe(5050, seconds=15)
    assert result["ok"] is False
    assert "超时" in result["error"]
    assert result["seconds"] == 0
    assert asr.sources == []
    assert list(tmp_path.iterdir()) == []


async def test_transcribe_degrades_without_asr_ffmpeg_or_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    no_asr = await LiveMediaService(_FakeClient(), data_dir=tmp_path).transcribe(5050)
    assert no_asr["ok"] is False
    assert "未配置语音识别" in no_asr["error"]

    async def _none(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(live_media, "ensure_ffmpeg", _none)
    no_ffmpeg = await LiveMediaService(_FakeClient(), asr_service=_FakeAsr()).transcribe(5050)
    assert no_ffmpeg["ok"] is False
    assert "ffmpeg" in no_ffmpeg["error"]

    fake_run = _FakeRun()
    monkeypatch.setattr(live_media, "ensure_ffmpeg", _fake_ensure_ffmpeg)
    monkeypatch.setattr(live_media.subprocess, "run", fake_run)
    asr = _FakeAsr()
    no_stream = await LiveMediaService(_FakeClient(url=""), asr_service=asr, data_dir=tmp_path).transcribe(5050)
    assert no_stream["ok"] is False
    assert "拉流地址" in no_stream["error"]
    assert fake_run.commands == []
    assert asr.sources == []


async def _fake_ensure_ffmpeg(**_kwargs: Any) -> FFmpegTools:
    return FFmpegTools(_FFMPEG, None)


# ── 录制片段 ──


async def test_record_clip_saves_flv(tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_run = _FakeRun(payload=b"fake-flv")
    monkeypatch.setattr(live_media.subprocess, "run", fake_run)
    service = LiveMediaService(_FakeClient(), data_dir=tmp_path / "data")

    result = await service.record_clip(5050, seconds=12)

    assert result["ok"] is True
    assert result["seconds"] == 12
    clip = Path(result["path"])
    assert clip.is_file() and clip.read_bytes() == b"fake-flv"
    assert clip.parent == tmp_path / "data" / "live_clips"
    command = fake_run.commands[0]
    assert command[command.index("-t") + 1] == "12"
    assert command[command.index("-c") + 1] == "copy"
    assert command[-1] == result["path"]


async def test_record_clip_failure_cleans_partial(
    tmp_path: Path, fake_ffmpeg: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        live_media.subprocess,
        "run",
        _FakeRun(returncode=1, stderr=b"CDN 403"),
    )
    service = LiveMediaService(_FakeClient(), data_dir=tmp_path)
    result = await service.record_clip(5050)
    assert result["ok"] is False
    assert "CDN 403" in result["error"]
    assert list((tmp_path / "live_clips").iterdir()) == []
