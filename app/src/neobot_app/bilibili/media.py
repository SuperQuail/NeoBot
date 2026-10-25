"""B 站视频理解：视频信息 + 字幕/语音识别转写 + 热门评论。

站点字幕优先（准确、免费），拿不到再下载 DASH 音频走 ASR。所有失败都降级成
`ok=False` + 中文 `error`，不向调用方抛异常 —— 视频链路只是 LLM 的输入增强项。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger

from ._compat import call_client, resolve_client

#: ASRService.transcribe 失败时返回的中文说明前缀（成功时是转写正文）。
_ASR_FAILURE_PREFIXES = ("语音识别失败", "语音识别未启用")


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _subtitle_rank(item: dict[str, Any]) -> int:
    """中文（含自动生成）优先，其次其它语言。"""
    lang = str(item.get("lan") or "").lower()
    doc = str(item.get("lan_doc") or "")
    return 0 if lang.startswith("zh") or "中文" in doc else 1


def _parse_subtitle_body(raw: str | None) -> str:
    """解析字幕 JSON 的 body（[{from,to,content}]）并按行拼接。"""
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except ValueError:
        return ""
    body = payload.get("body") if isinstance(payload, dict) else None
    lines = [
        str(item.get("content") or "").strip()
        for item in body or []
        if isinstance(item, dict)
    ]
    return "\n".join(line for line in lines if line)


class BilibiliVideoService:
    """视频理解服务门面（同步 client + 可选 ASR 服务）。"""

    def __init__(
        self,
        service: Any = None,
        asr_service: Any = None,
        archive_service: Any = None,
        logger: Logger | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self._service = service
        self._asr = asr_service
        self._archive = archive_service
        self._logger = logger or NullLogger()
        self._data_dir = Path(data_dir) if data_dir else None

    async def watch(
        self,
        identifier: str,
        *,
        max_chars: int = 6000,
        include_comments: int = 0,
    ) -> dict[str, Any]:
        """读取一个视频：返回视频信息 + 字幕/ASR 转写（+ 可选热门评论）。"""
        result: dict[str, Any] = {
            "ok": False,
            "bvid": "",
            "aid": 0,
            "cid": 0,
            "title": "",
            "owner": "",
            "duration": 0,
            "desc": "",
            "url": "",
            "source": "none",
            "transcript": "",
            "error": "",
        }
        client = self._resolve_client()
        if client is None:
            result["error"] = "B站未登录或功能已关闭"
            return result
        try:
            info = await call_client(client.get_video_info, identifier)
        except Exception as exc:
            result["error"] = f"获取视频信息失败：{exc}"
            self._logger.warning(result["error"])
            return result
        if not isinstance(info, dict) or not info.get("bvid"):
            result["error"] = f"未找到视频：{identifier}"
            return result

        bvid = str(info.get("bvid") or "")
        cid = _to_int(info.get("cid")) or _first_page_cid(info)
        result.update(
            {
                "bvid": bvid,
                "aid": _to_int(info.get("aid")),
                "cid": cid,
                "title": str(info.get("title") or ""),
                "owner": str((info.get("owner") or {}).get("name") or ""),
                "duration": _to_int(info.get("duration")),
                "desc": str(info.get("desc") or ""),
                "url": f"https://www.bilibili.com/video/{bvid}",
            }
        )

        transcript, source, reason = "", "none", ""
        try:
            # 先拿完整转写：超过本次限制的部分按需存进档案，而不是永久丢掉。
            full_text, source, reason = await self._transcript(
                client, bvid, cid, 200_000
            )
        except Exception as exc:
            full_text, source = "", "none"
            reason = f"获取视频内容失败：{exc}"
            self._logger.warning(reason)
        transcript = full_text[: max(_to_int(max_chars), 1)]
        if transcript and len(full_text) > len(transcript):
            stored = await self._store_transcript(bvid, full_text, source)
            result["archived"] = stored
            if stored:
                result["archive_key"] = bvid
        result["transcript"] = transcript
        result["source"] = source
        if transcript:
            result["ok"] = True
        else:
            result["error"] = reason or "未获取到字幕，且没有可用的语音识别"

        if include_comments > 0:
            result["comments"] = await self._comments(
                client, result["aid"], _to_int(include_comments)
            )
        return result

    async def _store_transcript(self, bvid: str, text: str, source: str) -> bool:
        """把超长转写存进 bilibili_video 档案，供 read_video_transcript 按需读取。"""
        if self._archive is None or not bvid or not text:
            return False
        try:
            await call_client(
                self._archive.set,
                "bilibili_video",
                bvid,
                text,
                ["bilibili-video", "auto", f"source:{source or 'unknown'}"],
            )
            return True
        except Exception as exc:
            self._logger.debug(f"B站视频转写档案写入失败: {exc}")
            return False

    # ── 内部 ──

    def _resolve_client(self) -> Any | None:
        target = self._service
        if callable(target):
            target = target()
        return resolve_client(target)

    async def _transcript(
        self, client: Any, bvid: str, cid: int, max_chars: int
    ) -> tuple[str, str, str]:
        text = await self._site_subtitle(client, bvid, cid)
        if text:
            return text[:max_chars], "site", ""
        if self._asr is None:
            return "", "none", "站点无字幕，且未配置语音识别"
        if cid <= 0:
            return "", "none", "站点无字幕，且缺少 cid 无法识别音频"
        url = await call_client(client.get_playurl_audio, bvid, cid)
        if not url:
            return "", "none", "站点无字幕，且未取到音频流"
        parent = None
        if self._data_dir is not None:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            parent = self._data_dir
        try:
            with tempfile.TemporaryDirectory(prefix="neobot_bili_", dir=parent) as tmp:
                audio = Path(tmp) / "audio.m4s"
                if not await call_client(client.download_file, url, audio):
                    return "", "none", "站点无字幕，且音频下载失败"
                text = str(await call_client(self._asr.transcribe, audio) or "").strip()
        except Exception as exc:
            self._logger.warning(f"B站视频语音识别失败: {exc}")
            return "", "none", f"语音识别失败：{exc}"
        if not text:
            return "", "none", "语音识别没有返回内容"
        if text.startswith(_ASR_FAILURE_PREFIXES):
            return "", "none", text
        return text[:max_chars], "asr", ""

    async def _site_subtitle(self, client: Any, bvid: str, cid: int) -> str:
        if cid <= 0:
            return ""
        try:
            info = await call_client(client.get_player_info, bvid, cid)
            subtitle = (info or {}).get("subtitle") if isinstance(info, dict) else None
            subtitles = subtitle.get("subtitles") if isinstance(subtitle, dict) else None
            candidates = sorted(
                (item for item in subtitles or [] if isinstance(item, dict)),
                key=_subtitle_rank,
            )
            for item in candidates:
                url = str(item.get("subtitle_url") or "")
                if url.startswith("//"):
                    url = f"https:{url}"
                text = _parse_subtitle_body(await call_client(client.fetch_text, url))
                if text:
                    return text
        except Exception as exc:
            self._logger.warning(f"B站站点字幕读取失败: {exc}")
        return ""

    async def _comments(self, client: Any, aid: int, limit: int) -> list[dict[str, Any]]:
        if aid <= 0:
            return []
        try:
            raw = await call_client(client.get_video_comments, aid, order="hot")
        except Exception as exc:
            self._logger.warning(f"B站视频评论读取失败: {exc}")
            return []
        comments = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            content = item.get("content") if isinstance(item.get("content"), dict) else {}
            member = item.get("member") if isinstance(item.get("member"), dict) else {}
            message = str(content.get("message") or "").strip()
            if not message:
                continue
            comments.append(
                {
                    "uname": str(member.get("uname") or ""),
                    "content": message,
                    "like": _to_int(item.get("like")),
                }
            )
            if len(comments) >= limit:
                break
        return comments


def _first_page_cid(info: dict[str, Any]) -> int:
    pages = info.get("pages")
    if isinstance(pages, list) and pages and isinstance(pages[0], dict):
        return _to_int(pages[0].get("cid"))
    return 0
