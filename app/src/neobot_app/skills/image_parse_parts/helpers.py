"""图片解析的纯函数：JSON 包装、响应取值、图片引用读取、队列查找。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neobot_app.image.source import IMAGE_FETCH_TIMEOUT_SECONDS
from neobot_app.utils.http import image_http_client

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _response_data_for_get_image(response: Any) -> dict | None:
    """从 get_image API 响应中提取 data 字典。"""
    if response is None:
        return None
    if isinstance(response, dict):
        data = response.get("data", {})
        return data if isinstance(data, dict) else None
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return data
    if hasattr(data, "model_dump"):
        return data.model_dump(exclude_none=True)
    return None


async def _read_image_ref(ref: str, *, timeout: float = IMAGE_FETCH_TIMEOUT_SECONDS) -> bytes | None:
    """读取图片引用（base64 / data URL / file / URL / 路径）。"""
    import base64 as _base64

    if ref.startswith("base64://"):
        try:
            return _base64.b64decode(ref[9:])
        except Exception:
            return None
    if ref.startswith("data:") and ";base64," in ref:
        try:
            return _base64.b64decode(ref.split(";base64,", 1)[1])
        except Exception:
            return None
    if ref.startswith("file://"):
        try:
            return Path(ref[7:]).expanduser().read_bytes()
        except OSError:
            return None
    path = Path(ref).expanduser()
    if path.exists() and path.is_file():
        try:
            return path.read_bytes()
        except OSError:
            return None
    if not ref.startswith(("http://", "https://")):
        return None  # 非 URL 引用无需创建 HTTP 客户端
    try:
        async with image_http_client(
            timeout=timeout, follow_redirects=True, url=ref
        ) as client:
            resp = await client.get(ref)
            resp.raise_for_status()
            return resp.content
    except Exception:
        return None


def _find_in_replied(queue: Any, conv_id: str, message_id: int) -> Any:
    """在队列所有条目的 replied_messages 中查找指定消息。"""
    from neobot_app.message.queue import QueueEntryType

    try:
        entries = queue.entries(conv_id)
    except KeyError:
        return None
    for entry in entries:
        if entry.kind != QueueEntryType.MESSAGE:
            continue
        for replied in getattr(entry, "replied_messages", []) or []:
            if getattr(replied, "message_id", None) == message_id:
                return replied
    return None
