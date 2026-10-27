"""动态：配图上传与发布。"""

from __future__ import annotations

import mimetypes
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..errors import BilibiliApiError
from .common import _DYNAMIC_CREATE_URL, _DYNAMIC_IMAGE_UPLOAD_URL, _to_int


class _DynamicMixin:
    """动态配图上传与发布。"""

    # ── 动态 ──

    def upload_dynamic_image(self, image_path: str | Path) -> dict[str, Any]:
        """上传一张动态配图，返回 upload_bfs 的 data（含 image_url/image_width/image_height）。"""
        path = Path(image_path)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise BilibiliApiError(-1, f"读取图片失败: {path}（{exc}）") from exc
        if not content:
            raise BilibiliApiError(-1, f"图片为空: {path}")
        mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
        self._rate_limit_wait()
        payload = self._fetch(
            "POST",
            _DYNAMIC_IMAGE_UPLOAD_URL,
            data={"category": "daily", "biz": "new_dyn", "csrf": self._bili_jct},
            files={"file_up": (path.name, content, mime_type)},
            headers={"Referer": "https://t.bilibili.com/"},
            # 上传图片重发最多多一份附件，不会产生重复评论/私信，5xx 可以重试。
            retry=True,
        )
        data = payload.get("data")
        if not isinstance(data, dict) or not data.get("image_url"):
            raise BilibiliApiError(-1, "图片上传成功但未返回 image_url")
        return data

    def publish_dynamic(
        self, text: str, images: Sequence[str | Path] | None = None
    ) -> int:
        """发布一条文本/图文动态，返回 dynamic_id；失败抛 BilibiliApiError。"""
        content = (text or "").strip()
        image_paths = [Path(item) for item in images or ()]
        if not content and not image_paths:
            raise ValueError("动态内容不能为空")
        pics: list[dict[str, Any]] = []
        for path in image_paths:
            info = self.upload_dynamic_image(path)
            pics.append(
                {
                    "img_src": str(info["image_url"]),
                    "img_width": _to_int(info.get("image_width")),
                    "img_height": _to_int(info.get("image_height")),
                    "img_size": info.get("img_size") or 0,
                }
            )
        dyn_req: dict[str, Any] = {
            "content": {
                "contents": (
                    [{"biz_id": "", "type": 1, "raw_text": content}] if content else []
                )
            },
            "scene": 2 if pics else 1,
            "meta": {"app_meta": {"from": "create.dynamic.web", "mobi_app": "web"}},
            "attach_card": None,
        }
        if pics:
            dyn_req["pics"] = pics
        self._rate_limit_wait()
        payload = self._fetch(
            "POST",
            _DYNAMIC_CREATE_URL,
            params={"csrf": self._bili_jct},
            json_body={"dyn_req": dyn_req},
            headers={"Referer": "https://t.bilibili.com/"},
        )
        data = payload.get("data")
        dynamic_id = 0
        if isinstance(data, dict):
            for key in ("dyn_id", "dyn_id_str", "dynamic_id"):
                value = data.get(key)
                if value in (None, ""):
                    continue
                try:
                    dynamic_id = int(value)
                except (TypeError, ValueError):
                    continue
                if dynamic_id:
                    break
        if not dynamic_id:
            raise BilibiliApiError(-1, "发布动态成功但未返回 dynamic_id")
        self._logger.info(f"B站动态已发布: dynamic_id={dynamic_id}")
        return dynamic_id
