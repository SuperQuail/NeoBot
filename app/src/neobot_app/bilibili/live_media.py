"""B 站直播媒体：按需解析拉流地址、截一帧画面、截一段音频转写。

不常驻拉流：每次现解析地址（缓存到失效前 5 分钟）-> 起一个短命 ffmpeg -> 退出。
所有失败都降级成 `ok=False` + 中文 `error`，不向调用方抛异常 —— 直播媒体只是
弹幕交互的增强项，失败不应该打断回复链路。
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.audio.ffmpeg_install import ensure_ffmpeg
from neobot_app.bilibili._compat import call_client, resolve_client
from neobot_app.bilibili.client import DEFAULT_USER_AGENT
from neobot_app.core import DATA_DIR

#: FLV CDN 不带 Referer/Origin 会 403；ffmpeg 的 -headers 要求每行以 \r\n 结尾。
_LIVE_HEADERS = "Referer: https://live.bilibili.com/\r\nOrigin: https://live.bilibili.com\r\n"
#: 拉流地址提前 5 分钟视为过期（地址本身约 1 小时有效）。
_CACHE_SAFETY_SECONDS = 300
_CAPTURE_TIMEOUT_SECONDS = 20
#: 截音频的兜底超时 = 目标时长 + 这段余量（连接/转码开销）。
_TRANSCODE_GRACE_SECONDS = 20
#: ASRService.transcribe 失败时返回的中文说明前缀（成功时是转写正文）。
_ASR_FAILURE_PREFIXES = ("语音识别失败", "语音识别未启用")
#: 截帧/录像产物保留策略：每个目录最多保留的文件数与最长保留时间。
_KEEP_FILES = 200
_KEEP_SECONDS = 7 * 24 * 3600.0


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _file_ready(path: Path) -> bool:
    """输出文件存在且非空；stat 竞态/权限失败按未就绪处理。"""
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _discard(path: Path) -> None:
    """清理半成品；删不掉也不向上抛。"""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _stderr_tail(completed: subprocess.CompletedProcess[bytes]) -> str:
    stderr = completed.stderr or b""
    detail = stderr.decode("utf-8", errors="replace").strip() if isinstance(stderr, bytes) else str(stderr).strip()
    return detail.splitlines()[-1][:200] if detail else "无输出"


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _prune_files(directory: Path, *, keep_files: int, keep_seconds: float) -> int:
    """按数量/时间清理一个产物目录（新的留下、超期或超量删除）；返回删除个数。

    截帧/录像会长期累积，这里每写成功一次就顺手清一次；任何 IO 失败都跳过。
    """
    try:
        entries = [item for item in directory.iterdir() if item.is_file()]
    except OSError:
        return 0
    entries.sort(key=_mtime, reverse=True)
    now = time.time()
    removed = 0
    for index, item in enumerate(entries):
        if index < keep_files and now - _mtime(item) <= keep_seconds:
            continue
        try:
            item.unlink(missing_ok=True)
        except OSError:
            continue
        removed += 1
    return removed


class LiveMediaService:
    """直播媒体门面：解析拉流地址（带缓存）+ 截帧 + 截音频转写。"""

    def __init__(
        self,
        service: Any = None,
        *,
        asr_service: Any = None,
        logger: Logger | None = None,
        data_dir: Path | None = None,
    ) -> None:
        # service 可以是 BilibiliService 或 BilibiliClient；每轮用 resolve_client 取当前 client。
        self._service = service
        self._asr = asr_service
        self._logger = logger or NullLogger()
        self._data_dir = Path(data_dir) if data_dir is not None else None
        # room_id -> (url, format, expires, 过期 monotonic 时刻)
        self._cache: dict[int, tuple[str, str, int, float]] = {}

    # ── 拉流地址 ──

    async def get_play_url(self, room_id: int, *, force: bool = False) -> dict[str, Any]:
        """取直播拉流地址：缓存到 expires-300s，过期或 force 时重取。"""
        rid = _to_int(room_id)
        result: dict[str, Any] = {
            "ok": False,
            "room_id": rid,
            "url": "",
            "format": "",
            "expires": 0,
            "error": "",
        }
        if rid <= 0:
            result["error"] = "房间号无效"
            return result
        now = time.monotonic()
        cached = self._cache.get(rid)
        if cached is not None and not force and cached[3] > now:
            url, fmt, expires, _deadline = cached
            return {
                "ok": True,
                "room_id": rid,
                "url": url,
                "format": fmt,
                "expires": expires,
                "error": "",
            }
        client = self._resolve_client()
        if client is None:
            result["error"] = "B站未登录或功能已关闭"
            return result
        try:
            info = await call_client(client.get_live_playurl, rid)
        except Exception as exc:
            self._logger.warning(f"B站直播拉流地址解析失败: {exc}")
            result["error"] = f"获取直播拉流地址失败：{type(exc).__name__}"
            return result
        if not isinstance(info, dict) or not info.get("ok") or not info.get("url"):
            result["error"] = (
                str(info.get("error") or "获取直播拉流地址失败") if isinstance(info, dict) else "获取直播拉流地址失败"
            )
            return result
        url = str(info.get("url") or "")
        fmt = str(info.get("format") or "")
        expires = _to_int(info.get("expires"))
        ttl = expires - _CACHE_SAFETY_SECONDS
        if ttl > 0:
            self._cache[rid] = (url, fmt, expires, now + ttl)
        return {
            "ok": True,
            "room_id": _to_int(info.get("room_id")) or rid,
            "url": url,
            "format": fmt,
            "expires": expires,
            "error": "",
        }

    # ── 截帧 ──

    async def capture_frame(self, room_id: int, *, scale_width: int = 640) -> dict[str, Any]:
        """抓当前直播画面的一帧 JPEG；失败返回中文 error 并清理半成品。"""
        rid = _to_int(room_id)
        result: dict[str, Any] = {
            "ok": False,
            "path": "",
            "room_id": rid,
            "url": "",
            "bytes": b"",
            "error": "",
        }
        if rid <= 0:
            result["error"] = "房间号无效"
            return result
        ffmpeg = await self._resolve_ffmpeg()
        if ffmpeg is None:
            result["error"] = "未找到 ffmpeg（自动安装也失败，请安装后加入 PATH）"
            return result
        stream = await self.get_play_url(rid)
        if not stream.get("ok"):
            result["error"] = str(stream.get("error") or "获取直播拉流地址失败")
            return result
        url = str(stream.get("url") or "")
        result["url"] = url
        width = max(_to_int(scale_width) or 640, 2)
        frame_dir = self._frames_dir()
        target = frame_dir / f"{rid}_{datetime.now():%Y%m%d_%H%M%S_%f}.jpg"
        try:
            frame_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            result["error"] = f"创建截帧目录失败（{type(exc).__name__}）"
            return result
        command = [
            str(ffmpeg),
            "-y",
            "-loglevel",
            "error",
            "-rw_timeout",
            "15000000",
            "-user_agent",
            DEFAULT_USER_AGENT,
            "-headers",
            _LIVE_HEADERS,
            "-i",
            url,
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:-2",
            "-q:v",
            "5",
            str(target),
        ]
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                command,
                capture_output=True,
                timeout=_CAPTURE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            _discard(target)
            result["error"] = f"直播截帧超时（{_CAPTURE_TIMEOUT_SECONDS} 秒）"
            return result
        except OSError as exc:
            _discard(target)
            result["error"] = f"无法启动 ffmpeg（{type(exc).__name__}）"
            return result
        if completed.returncode != 0 or not _file_ready(target):
            _discard(target)
            result["error"] = f"直播截帧失败（{_stderr_tail(completed)}）"
            return result
        try:
            raw = target.read_bytes()
        except OSError as exc:
            _discard(target)
            result["error"] = f"读取截帧失败（{type(exc).__name__}）"
            return result
        result.update({"ok": True, "path": str(target), "bytes": raw})
        self._logger.debug(f"B站直播截帧成功：房间 {rid}，路径 {target}")
        await self._prune(frame_dir)
        return result

    # ── 截音频 + 转写 ──

    async def transcribe(self, room_id: int, *, seconds: int = 15, max_chars: int = 4000) -> dict[str, Any]:
        """截取直播流 seconds 秒音频并转写；ASR 不可用/失败返回中文 error。"""
        rid = _to_int(room_id)
        duration = max(_to_int(seconds) or 15, 1)
        result: dict[str, Any] = {
            "ok": False,
            "text": "",
            "seconds": 0,
            "error": "",
        }
        if rid <= 0:
            result["error"] = "房间号无效"
            return result
        if self._asr is None:
            result["error"] = "语音识别不可用：未配置语音识别服务"
            return result
        ffmpeg = await self._resolve_ffmpeg()
        if ffmpeg is None:
            result["error"] = "未找到 ffmpeg（自动安装也失败，请安装后加入 PATH）"
            return result
        stream = await self.get_play_url(rid)
        if not stream.get("ok"):
            result["error"] = str(stream.get("error") or "获取直播拉流地址失败")
            return result
        url = str(stream.get("url") or "")
        try:
            with tempfile.TemporaryDirectory(prefix="neobot_live_", dir=self._temp_parent()) as tmp:
                audio = Path(tmp) / "audio.mp3"
                command = [
                    str(ffmpeg),
                    "-y",
                    "-loglevel",
                    "error",
                    "-rw_timeout",
                    "15000000",
                    "-user_agent",
                    DEFAULT_USER_AGENT,
                    "-headers",
                    _LIVE_HEADERS,
                    "-i",
                    url,
                    "-t",
                    str(duration),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-c:a",
                    "libmp3lame",
                    str(audio),
                ]
                try:
                    completed = await asyncio.to_thread(
                        subprocess.run,
                        command,
                        capture_output=True,
                        timeout=duration + _TRANSCODE_GRACE_SECONDS,
                    )
                except subprocess.TimeoutExpired:
                    result["error"] = f"直播音频截取超时（{duration + _TRANSCODE_GRACE_SECONDS} 秒）"
                    return result
                except OSError as exc:
                    result["error"] = f"无法启动 ffmpeg（{type(exc).__name__}）"
                    return result
                if completed.returncode != 0 or not _file_ready(audio):
                    result["error"] = f"直播音频截取失败（{_stderr_tail(completed)}）"
                    return result
                result["seconds"] = duration
                try:
                    text = str(await call_client(self._asr.transcribe, audio) or "").strip()
                except Exception as exc:
                    self._logger.warning(f"B站直播语音识别失败: {exc}")
                    result["error"] = f"语音识别失败：{type(exc).__name__}"
                    return result
        except Exception as exc:
            self._logger.warning(f"B站直播转写失败: {exc}")
            result["error"] = f"直播转写失败：{type(exc).__name__}"
            return result
        if not text:
            result["error"] = "语音识别没有返回内容"
            return result
        if text.startswith(_ASR_FAILURE_PREFIXES):
            result["error"] = text
            return result
        result["text"] = text[: max(_to_int(max_chars) or 4000, 1)]
        result["ok"] = True
        return result

    # ── 录制一小段 ──

    async def record_clip(self, room_id: int, *, seconds: int = 30) -> dict[str, Any]:
        """把直播流原样录一小段（默认 30 秒）到本地 FLV；仅用于回看/留证。"""
        rid = _to_int(room_id)
        duration = max(5, min(_to_int(seconds) or 30, 300))
        result: dict[str, Any] = {
            "ok": False,
            "path": "",
            "room_id": rid,
            "seconds": duration,
            "bytes": 0,
            "error": "",
        }
        if rid <= 0:
            result["error"] = "房间号无效"
            return result
        ffmpeg = await self._resolve_ffmpeg()
        if ffmpeg is None:
            result["error"] = "未找到 ffmpeg（自动安装也失败，请安装后加入 PATH）"
            return result
        stream = await self.get_play_url(rid)
        if not stream.get("ok"):
            result["error"] = str(stream.get("error") or "获取直播拉流地址失败")
            return result
        url = str(stream.get("url") or "")
        base = self._data_dir if self._data_dir is not None else DATA_DIR
        clip_dir = base / "live_clips"
        target = clip_dir / f"{rid}_{datetime.now():%Y%m%d_%H%M%S}.flv"
        try:
            clip_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            result["error"] = f"创建录制目录失败（{type(exc).__name__}）"
            return result
        command = [
            str(ffmpeg), "-y", "-loglevel", "error",
            "-rw_timeout", "15000000",
            "-user_agent", DEFAULT_USER_AGENT,
            "-headers", _LIVE_HEADERS,
            "-i", url,
            "-t", str(duration),
            "-c", "copy",
            str(target),
        ]
        try:
            completed = await asyncio.to_thread(
                subprocess.run, command, capture_output=True,
                timeout=duration + _TRANSCODE_GRACE_SECONDS,
            )
        except subprocess.TimeoutExpired:
            _discard(target)
            result["error"] = f"直播录制超时（{duration + _TRANSCODE_GRACE_SECONDS} 秒）"
            return result
        except OSError as exc:
            _discard(target)
            result["error"] = f"无法启动 ffmpeg（{type(exc).__name__}）"
            return result
        if completed.returncode != 0 or not _file_ready(target):
            _discard(target)
            result["error"] = f"直播录制失败（{_stderr_tail(completed)}）"
            return result
        try:
            result["bytes"] = target.stat().st_size
        except OSError:
            result["bytes"] = 0
        result.update({"ok": True, "path": str(target)})
        self._logger.debug(f"B站直播录制完成：房间 {rid}，路径 {target}")
        await self._prune(clip_dir)
        return result

    # ── 内部 ──

    def _resolve_client(self) -> Any | None:
        try:
            target = self._service() if callable(self._service) else self._service
            return resolve_client(target)
        except Exception as exc:
            self._logger.warning(f"B站客户端解析失败: {exc}")
            return None

    async def _resolve_ffmpeg(self) -> Path | None:
        try:
            tools = await ensure_ffmpeg(logger=self._logger)
        except Exception as exc:
            self._logger.warning(f"ffmpeg 准备失败: {exc}")
            return None
        # ffmpeg 一律用绝对路径，避免子进程工作目录不同导致解析不到。
        return Path(tools.ffmpeg).resolve() if tools is not None else None

    async def _prune(self, directory: Path) -> None:
        """清理超量/超期的截帧与录像；失败只记日志，不影响本次结果。"""
        try:
            removed = await asyncio.to_thread(
                _prune_files, directory, keep_files=_KEEP_FILES, keep_seconds=_KEEP_SECONDS
            )
        except OSError as exc:
            self._logger.debug(f"B站直播产物清理失败（{directory.name}）：{type(exc).__name__}: {exc}")
            return
        if removed:
            self._logger.debug(f"B站直播产物已清理 {removed} 个：目录 {directory}")

    def _frames_dir(self) -> Path:
        base = self._data_dir if self._data_dir is not None else DATA_DIR
        return base / "live_frames"

    def _temp_parent(self) -> Path | None:
        if self._data_dir is None:
            return None
        self._data_dir.mkdir(parents=True, exist_ok=True)
        return self._data_dir
