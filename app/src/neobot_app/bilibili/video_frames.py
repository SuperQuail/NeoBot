"""B 站视频画面：解析 DASH 视频流、按间隔抽关键帧、拼 4x4 接触印相纸。

不依赖字幕：即使视频没有字幕也能看到画面。所有失败都降级成 `ok=False` +
中文 `error`，不向调用方抛异常 —— 画面只是视频理解的增强项。
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from PIL import Image

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.audio.ffmpeg_install import ensure_ffmpeg
from neobot_app.bilibili._compat import call_client, resolve_client
from neobot_app.bilibili.client import API_BASE, DEFAULT_USER_AGENT
from neobot_app.core import DATA_DIR
from neobot_app.image.parser import _build_vision_image_part

_PLAYURL_URL = f"{API_BASE}/x/player/wbi/playurl"
#: B 站 CDN 不带 Referer 会 403；ffmpeg 的 -headers 要求每行以 \r\n 结尾。
_VIDEO_HEADERS = "Referer: https://www.bilibili.com/\r\nOrigin: https://www.bilibili.com\r\n"
_DEFAULT_EVERY = 60
_MAX_FRAMES = 32
_SCALE_WIDTH = 640
_COLUMNS = 4
_ROWS = 4
_CELL_WIDTH = 320
_FRAME_TIMEOUT_SECONDS = 300
_VISION_TIMEOUT_SECONDS = 60.0
#: 抽帧结果保留策略：只留最近这么多份、且不超过这个时长（磁盘占用有界）。
_MAX_OUTPUT_DIRS = 20
_OUTPUT_TTL_SECONDS = 7 * 24 * 3600
_DESCRIBE_PROMPT = (
    "这是B站视频按每 {every} 秒抽取、从左到右从上到下排列的4x4关键帧拼图。"
    "请用中文概括画面里发生的事、场景变化和屏幕上的文字；"
    "只描述看得到的内容，不要编造听不到的对白或视频以外的信息。"
)


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _dir_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _first_page_cid(info: dict[str, Any]) -> int:
    pages = info.get("pages")
    if isinstance(pages, list) and pages and isinstance(pages[0], dict):
        return _to_int(pages[0].get("cid"))
    return 0


def _safe_name(value: str) -> str:
    name = re.sub(r"[^0-9A-Za-z_-]", "", value or "")[:64]
    return name or "video"


def _stderr_tail(completed: subprocess.CompletedProcess[bytes]) -> str:
    stderr = completed.stderr or b""
    detail = stderr.decode("utf-8", errors="replace").strip() if isinstance(stderr, bytes) else str(stderr).strip()
    return detail.splitlines()[-1][:200] if detail else "无输出"


def _dash_videos(info: Any) -> list[dict[str, Any]]:
    """取出 player/playurl 返回里的 dash.video；兼容 data 包装。"""
    if not isinstance(info, dict):
        return []
    dash = info.get("dash")
    if not isinstance(dash, dict):
        data = info.get("data")
        dash = data.get("dash") if isinstance(data, dict) else None
    videos = dash.get("video") if isinstance(dash, dict) else None
    return [item for item in videos or [] if isinstance(item, dict)]


def _video_rank(item: dict[str, Any]) -> tuple[bool, int, int]:
    """avc 优先，其次接近 720p，最后带宽大的优先。"""
    codecs = str(item.get("codecs") or "").lower()
    avc = _to_int(item.get("codecid")) == 7 or codecs.startswith("avc")
    height = _to_int(item.get("height"))
    return (not avc, abs(height - 720) if height else 999, -_to_int(item.get("bandwidth")))


def _pick_video_url(videos: list[dict[str, Any]]) -> str:
    candidates = [item for item in videos if item.get("base_url") or item.get("baseUrl")]
    if not candidates:
        return ""
    best = min(candidates, key=_video_rank)
    return str(best.get("base_url") or best.get("baseUrl") or "")


class VideoFrameService:
    """视频画面门面：解析视频流 + 抽帧 + 拼图 + 可选视觉描述。"""

    def __init__(
        self,
        service: Any = None,
        *,
        vision_provider: Any = None,
        logger: Logger | None = None,
        data_dir: Path | None = None,
    ) -> None:
        # service 可以是 BilibiliService 或 BilibiliClient；每轮用 resolve_client 取当前 client。
        self._service = service
        self._vision_provider = vision_provider
        self._logger = logger or NullLogger()
        self._data_dir = Path(data_dir) if data_dir is not None else None

    async def frames(
        self,
        identifier: str,
        *,
        every: int = _DEFAULT_EVERY,
        max_frames: int = _MAX_FRAMES,
        describe: bool = True,
    ) -> dict[str, Any]:
        """抽关键帧并生成接触印相纸；失败返回中文 error，不抛异常。"""
        result: dict[str, Any] = {
            "ok": False,
            "bvid": "",
            "frames": [],
            "sheets": [],
            "description": "",
            "error": "",
        }
        text = str(identifier or "").strip()
        if not text:
            result["error"] = "缺少视频标识（BV号、av号或视频链接）"
            return result
        client = self._resolve_client()
        if client is None:
            result["error"] = "B站未登录或功能已关闭"
            return result
        try:
            info = await call_client(client.get_video_info, text)
        except Exception as exc:
            result["error"] = f"获取视频信息失败：{type(exc).__name__}: {exc}"
            self._logger.warning(result["error"])
            return result
        if not isinstance(info, dict) or not info.get("bvid"):
            result["error"] = f"未找到视频：{text}"
            return result

        bvid = str(info.get("bvid") or "")
        cid = _to_int(info.get("cid")) or _first_page_cid(info)
        result["bvid"] = bvid
        if cid <= 0:
            result["error"] = "视频缺少 cid，无法解析视频流"
            return result
        ffmpeg = await self._resolve_ffmpeg()
        if ffmpeg is None:
            result["error"] = "未找到 ffmpeg（自动安装也失败，请安装后加入 PATH）"
            return result
        url, reason = await self._video_url(client, bvid, cid)
        if not url:
            result["error"] = reason
            return result

        every = min(max(_to_int(every) or _DEFAULT_EVERY, 1), 3600)
        max_frames = min(max(_to_int(max_frames) or _MAX_FRAMES, 1), _MAX_FRAMES)
        out_dir = self._output_dir(bvid)
        # 每次请求用独立临时目录，成功后再整体替换：并发抽同一个 bvid 不会互删对方的帧。
        try:
            out_dir.parent.mkdir(parents=True, exist_ok=True)
            work_dir = Path(
                tempfile.mkdtemp(prefix=f".{_safe_name(bvid)}-", dir=out_dir.parent)
            )
        except OSError as exc:
            result["error"] = f"创建画面目录失败（{type(exc).__name__}: {exc}）"
            return result
        frames_dir = work_dir / "frames"
        sheets_dir = work_dir / "sheets"
        try:
            frames_dir.mkdir()
            sheets_dir.mkdir()
        except OSError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            result["error"] = f"创建画面目录失败（{type(exc).__name__}: {exc}）"
            return result

        command = [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-rw_timeout",
            "15000000",
            "-user_agent",
            DEFAULT_USER_AGENT,
            "-headers",
            _VIDEO_HEADERS,
            "-i",
            url,
            "-vf",
            f"fps=1/{every},scale={_SCALE_WIDTH}:-2",
            "-frames:v",
            str(max_frames),
            "-q:v",
            "4",
            str(frames_dir / "f_%05d.jpg"),
        ]
        try:
            completed = await self._run_ffmpeg(command, _FRAME_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            shutil.rmtree(work_dir, ignore_errors=True)
            result["error"] = f"抽帧超时（{_FRAME_TIMEOUT_SECONDS} 秒）"
            return result
        except OSError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            result["error"] = f"无法启动 ffmpeg（{type(exc).__name__}: {exc}）"
            return result
        frames = sorted(frames_dir.glob("f_*.jpg"))
        if completed.returncode != 0 or not frames:
            detail = _stderr_tail(completed)
            shutil.rmtree(work_dir, ignore_errors=True)
            result["error"] = f"抽帧失败（{detail}）"
            return result

        # 拼图是纯 CPU 操作，放线程池里跑，别阻塞事件循环。
        sheets = await asyncio.to_thread(self._make_sheets, frames, sheets_dir)
        try:
            self._publish(work_dir, out_dir)
        except OSError as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            result["error"] = f"保存抽帧结果失败（{type(exc).__name__}: {exc}）"
            return result
        result["frames"] = [str(out_dir / "frames" / path.name) for path in frames]
        result["sheets"] = [str(out_dir / "sheets" / path.name) for path in sheets]
        if describe and sheets and self._vision_provider is not None:
            result["description"] = await self._describe(
                [out_dir / "sheets" / path.name for path in sheets], every
            )
        result["ok"] = True
        self._prune_outputs(out_dir.parent)
        self._logger.debug(f"B站视频抽帧完成: bvid={bvid} frames={len(frames)} sheets={len(sheets)}")
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
        return Path(tools.ffmpeg).resolve() if tools is not None else None

    async def _video_url(self, client: Any, bvid: str, cid: int) -> tuple[str, str]:
        try:
            info = await call_client(client.get_player_info, bvid, cid)
        except Exception as exc:
            self._logger.debug(f"B站播放器信息读取失败: {exc}")
            info = {}
        url = _pick_video_url(_dash_videos(info))
        if url:
            return url, ""
        fetch = getattr(client, "_fetch", None)
        if not callable(fetch):
            return "", "播放器信息里没有 dash 视频流"
        params = await self._playurl_params(client, bvid, cid)
        try:
            payload = await call_client(
                fetch,
                "GET",
                _PLAYURL_URL,
                params=params,
                headers={"Referer": f"https://www.bilibili.com/video/{bvid}"},
            )
        except Exception as exc:
            self._logger.warning(f"B站视频流地址读取失败: {exc}")
            return "", f"获取视频流失败：{type(exc).__name__}"
        url = _pick_video_url(_dash_videos(payload.get("data") if isinstance(payload, dict) else {}))
        if not url:
            return "", "没有取到视频流（可能需要登录或该视频不允许播放）"
        return url, ""

    async def _playurl_params(self, client: Any, bvid: str, cid: int) -> dict[str, Any]:
        params: dict[str, Any] = {"bvid": bvid, "cid": cid, "fnval": 16, "fourk": 1}
        sign = getattr(client, "_sign_wbi", None)
        if callable(sign):
            try:
                signed = await call_client(sign, params)
                if isinstance(signed, dict):
                    params = signed
            except Exception as exc:
                self._logger.debug(f"B站视频流参数签名失败: {exc}")
        return params

    async def _run_ffmpeg(self, command: list[str], timeout: int) -> subprocess.CompletedProcess[bytes]:
        return await asyncio.to_thread(subprocess.run, command, capture_output=True, timeout=timeout)

    @staticmethod
    def _publish(work_dir: Path, out_dir: Path) -> None:
        """用临时目录整体替换结果目录；替换失败时把旧结果放回去，不丢已完成的帧。"""
        stale = out_dir.with_name(f".{out_dir.name}.old")
        shutil.rmtree(stale, ignore_errors=True)
        if out_dir.exists():
            out_dir.rename(stale)
        try:
            work_dir.rename(out_dir)
        except OSError:
            if stale.exists():
                stale.rename(out_dir)
            raise
        shutil.rmtree(stale, ignore_errors=True)

    def _prune_outputs(self, base: Path) -> None:
        """按数量和时长清理旧的抽帧目录（磁盘占用有界，失败只记 debug）。"""
        try:
            entries = [
                item
                for item in base.iterdir()
                if item.is_dir() and not item.name.startswith(".")
            ]
        except OSError as exc:
            self._logger.debug(f"B站抽帧目录清理跳过: {exc}")
            return
        cutoff = time.time() - _OUTPUT_TTL_SECONDS
        entries.sort(key=_dir_mtime, reverse=True)
        for index, item in enumerate(entries):
            if index < _MAX_OUTPUT_DIRS and _dir_mtime(item) >= cutoff:
                continue
            self._logger.debug(f"B站抽帧目录清理: {item.name}")
            shutil.rmtree(item, ignore_errors=True)

    def _make_sheets(self, frames: list[Path], sheet_dir: Path) -> list[Path]:
        """把关键帧拼成 4x4 接触印相纸；单张失败不影响已拼好的。"""
        sheets: list[Path] = []
        per_sheet = _COLUMNS * _ROWS
        try:
            cell_height = 0
            for start in range(0, len(frames), per_sheet):
                batch = frames[start : start + per_sheet]
                if cell_height <= 0:
                    with Image.open(batch[0]) as first:
                        width, height = first.size
                    cell_height = max(2, int(height * _CELL_WIDTH / max(width, 1)) // 2 * 2)
                canvas = Image.new("RGB", (_COLUMNS * _CELL_WIDTH, _ROWS * cell_height), (0, 0, 0))
                for index, path in enumerate(batch):
                    with Image.open(path) as image:
                        tile = image.convert("RGB").resize((_CELL_WIDTH, cell_height), Image.Resampling.LANCZOS)
                    canvas.paste(
                        tile,
                        (
                            (index % _COLUMNS) * _CELL_WIDTH,
                            (index // _COLUMNS) * cell_height,
                        ),
                    )
                target = sheet_dir / f"sheet_{len(sheets) + 1}.jpg"
                canvas.save(target, format="JPEG", quality=85)
                sheets.append(target)
        except Exception as exc:
            self._logger.warning(f"B站视频关键帧拼图失败: {exc}")
        return sheets

    async def _describe(self, sheets: list[Path], every: int) -> str:
        """逐张描述拼图；视觉模型失败时返回已拿到的部分（通常为空）。"""
        prompt = _DESCRIBE_PROMPT.format(every=every)
        texts: list[str] = []
        for sheet in sheets:
            try:
                part = _build_vision_image_part(sheet.read_bytes(), logger=self._logger)
                response = await asyncio.wait_for(
                    call_client(
                        self._vision_provider.chat,
                        [{"role": "user", "content": [{"type": "text", "text": prompt}, part]}],
                    ),
                    timeout=_VISION_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                self._logger.warning(f"B站视频画面描述失败: {exc}")
                break
            content = response.get("content", "") if isinstance(response, dict) else getattr(response, "content", "")
            text = content.strip() if isinstance(content, str) else str(content).strip()
            if text:
                texts.append(text)
        return "\n\n".join(texts)

    def _output_dir(self, bvid: str) -> Path:
        base = self._data_dir if self._data_dir is not None else DATA_DIR
        return base / "bilibili_frames" / _safe_name(bvid)
