"""ImageParseSkill — 图片内容解析（支持路径/URL/base64/消息ID/聊天流）。

实现按职责拆在 image_parse_parts（纯函数、Skill 元信息/工具声明、按消息/聊天流/编号的取图、segment 规整与工具处理函数）；本模块保留 ImageParseSkill 聚合类、不可用登记表相关的取图方法与 re-export。
"""

from __future__ import annotations

from neobot_app.image.source import IMAGE_FETCH_TIMEOUT_SECONDS
from neobot_app.image.unavailable import (
    DESCRIPTION_PREFIX,
    EXPIRED_NOTICE,
    REGISTRY,
    describe,
    image_ref_key,
    is_expiry_failure,
)
from neobot_app.skills.base import SkillModule
from neobot_app.utils.http import image_http_client
from neobot_app.utils.logger import get_module_logger

from .image_parse_parts.base import ImageParseSkillBase
from .image_parse_parts.chat_flow import ChatFlowResolveMixin
from .image_parse_parts.handlers import _HANDLERS, _handle_parse_image
from .image_parse_parts.helpers import (
    _json,
    _response_data_for_get_image,
    _read_image_ref,
    _find_in_replied,
)
from .image_parse_parts.message_resolve import MessageResolveMixin
from .image_parse_parts.msg_number import MsgNumberResolveMixin
from .image_parse_parts.segment import SegmentMixin


logger = get_module_logger("skills.image_parse")


class ImageParseSkill(
    MessageResolveMixin,
    ChatFlowResolveMixin,
    MsgNumberResolveMixin,
    SegmentMixin,
    ImageParseSkillBase,
    SkillModule,
):
    """图片内容解析 Skill — 解析聊天中的图片内容。"""

    async def _download_image_segment(self, seg_data: dict, *, timeout: float = IMAGE_FETCH_TIMEOUT_SECONDS) -> tuple[bytes | None, str | None]:
        """从 segment data 下载图片字节。

        先尝试 URL 直下，失败/缺失时 fallback 到 file 字段走 get_image API
        （旧消息的 URL 可能已过期，但 file 字段可用于 OneBot get_image 重新获取）。

        Returns:
            (image_bytes, None) 成功
            (None, error_reason) 失败 — error_reason 形如 "超时(30s)" / "URL过期且无file字段" / "下载失败"
        """
        # 命中「不可用登记表」直接失败返回：拉不到的图（设备侧历史被清理 / 过久被回收）
        # 以前就拉不到，再试一次也只是白等一个超时窗口。见 image/unavailable.py。
        key = image_ref_key(seg_data)
        known = REGISTRY.notice(key)
        if known is not None:
            return None, await self._expired_text(key, known)

        expired = False
        url = seg_data.get("url")
        if url:
            try:
                async with image_http_client(
                    timeout=timeout, follow_redirects=True, url=url
                ) as client:
                    resp = await client.get(str(url))
                    resp.raise_for_status()
                    return resp.content, None
            except Exception as exc:
                expired = is_expiry_failure(exc)
                # fall through to file fallback

        file_name = seg_data.get("file")
        if file_name and self._adapter is not None:
            try:
                from neobot_adapter.request.message import get_image

                result = await get_image(str(file_name), timeout=timeout)
                img_data = _response_data_for_get_image(result)
                img_ref = ""
                if isinstance(img_data, dict):
                    img_ref = str(img_data.get("file") or img_data.get("url") or "")
                if img_ref:
                    content = await _read_image_ref(img_ref, timeout=timeout)
                    if content is not None:
                        return content, None
                    error = f"get_image 返回的图片引用下载失败(file={file_name}, timeout={timeout}s)"
                else:
                    error = f"get_image 返回无效数据(file={file_name})"
                    expired = True
            except TimeoutError:
                error = f"get_image 超时(file={file_name}, timeout={timeout}s)"
                expired = True
            except Exception as exc:
                # 非超时异常不判过期：可能是适配器断线一类的瞬时故障，下次还该再试。
                error = f"get_image API 异常(file={file_name}): {exc}"
            if expired:
                REGISTRY.mark(key)
                return None, await self._expired_text(key, EXPIRED_NOTICE)
            return None, error

        if expired:
            REGISTRY.mark(key)
            return None, await self._expired_text(key, EXPIRED_NOTICE)
        if url and file_name:
            return None, f"URL下载和get_image均失败(url={str(url)[:60]}, file={file_name}, timeout={timeout}s)"
        if url:
            return None, f"URL下载失败且无file字段(url={str(url)[:60]}, timeout={timeout}s)"
        return None, "segment data 既无url也无file字段"

    async def _expired_text(self, key: str | None, notice: str) -> str:
        """过期说明 + 库里留过的描述。"""
        description = await describe(key)
        if description:
            return f"{notice}{DESCRIPTION_PREFIX}{description}"
        return notice


__all__ = [
    "logger",
    "_json",
    "_response_data_for_get_image",
    "_read_image_ref",
    "_find_in_replied",
    "ImageParseSkill",
    "_handle_parse_image",
    "_HANDLERS",
]
