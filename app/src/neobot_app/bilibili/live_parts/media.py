"""直播画面截帧、录制、ASR 与画面描述。"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any

from neobot_app.bilibili._compat import call_client, get_field
from neobot_app.bilibili.live_parts.helpers import _to_int


class _MediaMixin:
    """按需截图/录制/转写；没有媒体服务时统一返回可读错误。"""

    async def frame_context(self, room_id: int) -> str:
        """抓当前直播画面并让视觉模型描述；失败返回空串，不阻断回复。"""
        # 没有视觉模型时截图无人消费，跳过；按需 snapshot 仍可单独调用。
        if self._vision_provider is None:
            return ""
        snapshot = await self.snapshot(room_id)
        if not snapshot.get("ok"):
            return ""
        return str(snapshot.get("description") or "").strip()

    async def snapshot(self, room_id: int) -> dict[str, Any]:
        """按需抓一帧直播画面（返回 path/描述；仅开播时）。"""
        rid = _to_int(room_id)
        if rid <= 0:
            return {"ok": False, "error": "房间号无效"}
        if self._media is None:
            return {"ok": False, "error": "直播媒体服务未配置"}
        if not await self.is_live(rid):
            return {"ok": False, "error": "未开播，不获取画面"}
        try:
            result = await call_client(self._media.capture_frame, rid)
        except Exception as exc:
            self._logger.warning(f"B站直播截帧失败：房间 {rid}，错误 {type(exc).__name__}: {exc}")
            return {"ok": False, "error": f"截帧失败：{exc}"}
        if not isinstance(result, dict) or not result.get("ok"):
            return result if isinstance(result, dict) else {"ok": False, "error": "截帧失败"}
        description = await self._describe_frame(result)
        if description:
            result["description"] = description
        return result

    async def record_clip(self, room_id: int, *, seconds: int = 30) -> dict[str, Any]:
        """按需录制一小段直播流（默认 30 秒，最长 300 秒）；仅开播时。"""
        rid = _to_int(room_id)
        if rid <= 0:
            return {"ok": False, "error": "房间号无效"}
        if self._media is None:
            return {"ok": False, "error": "直播媒体服务未配置"}
        if not await self.is_live(rid):
            return {"ok": False, "error": "未开播，不录制"}
        try:
            return await call_client(self._media.record_clip, rid, seconds=seconds)
        except Exception as exc:
            self._logger.warning(f"B站直播录制失败：房间 {rid}，错误 {type(exc).__name__}: {exc}")
            return {"ok": False, "error": f"直播录制失败：{exc}"}

    async def transcribe(self, room_id: int, *, seconds: int = 15) -> dict[str, Any]:
        """按需截取一段直播音频并转写（仅开播时）。"""
        rid = _to_int(room_id)
        if rid <= 0:
            return {"ok": False, "error": "房间号无效"}
        if self._media is None:
            return {"ok": False, "error": "直播媒体服务未配置"}
        if not await self.is_live(rid):
            return {"ok": False, "error": "未开播，不转写"}
        try:
            return await call_client(self._media.transcribe, rid, seconds=seconds)
        except Exception as exc:
            self._logger.warning(f"B站直播 ASR 失败：房间 {rid}，错误 {type(exc).__name__}: {exc}")
            return {"ok": False, "error": f"直播转写失败：{exc}"}

    async def _describe_frame(self, snapshot: dict[str, Any]) -> str:
        if self._vision_provider is None:
            return ""
        try:
            raw = snapshot.get("bytes")
            if not raw:
                path = snapshot.get("path")
                if not path:
                    return ""
                raw = await asyncio.to_thread(Path(path).read_bytes)
            from neobot_app.image.parser import _build_vision_image_part

            part = _build_vision_image_part(bytes(raw), logger=self._logger)
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "这是B站直播间的当前画面截图。用一两句话客观描述画面里发生了什么，供弹幕回复参考；不要编造看不清的细节。",
                        },
                        part,
                    ],
                }
            ]
            response = self._vision_provider.chat(messages)
            if inspect.isawaitable(response):
                response = await response
            content = response.get("content", "") if isinstance(response, dict) else get_field(response, "content", "")
            return str(content or "").strip()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._logger.debug(f"B站直播画面描述失败：{type(exc).__name__}: {exc}")
            return ""

    async def _save_reply_frame(self, room_id: int) -> None:
        if self._media is None:
            return
        try:
            result = await call_client(self._media.capture_frame, _to_int(room_id))
            if isinstance(result, dict) and result.get("ok"):
                self._logger.info(
                    f"B站直播回复截图已保留：房间 {room_id}，路径 {result.get('path')}"
                )
        except Exception as exc:
            self._logger.debug(
                f"B站直播回复截图失败：房间 {room_id}，错误 {type(exc).__name__}: {exc}"
            )
