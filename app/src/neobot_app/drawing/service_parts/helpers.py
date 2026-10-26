"""服务内共用的纯函数：JSON、文件名、data URL、MIME、图片缩放/去底。"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image

from neobot_contracts.models.memory import CreatorImageRecord


if TYPE_CHECKING:
    pass

def _json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


_MAX_REMOTE_FETCH_BYTES = 100 * 1024 * 1024


def _read_sidecar_description(file_path: str | Path) -> str | None:
    """读取图片同名的 .txt 伴生文件获取描述，不存在时返回 None。"""
    path = Path(file_path)
    txt_path = path.with_suffix(".txt")
    if not txt_path.exists():
        return None
    try:
        content = txt_path.read_text(encoding="utf-8").strip()
        return content or None
    except Exception:
        return None


def _sanitize_filename(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return ""
    stem = Path(raw).stem.strip()
    if not stem:
        return ""
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem)
    cleaned = cleaned.strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")
    return cleaned[:100] or "unnamed"


#: data URL -> 文件扩展名
_MIME_EXTENSIONS: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}


def _extension_for_mime(mime: str) -> str:
    return _MIME_EXTENSIONS.get(str(mime or "").lower(), ".png")


def _decode_data_url(value: str) -> tuple[bytes | None, str]:
    """解析 data URL，返回 (原始字节, mime)；非 base64 data URL 返回 (None, "")。"""
    text = str(value or "")
    if not text.startswith("data:") or "," not in text:
        return None, ""
    header, _, encoded = text.partition(",")
    if "base64" not in header.lower():
        return None, ""
    mime = header[len("data:") :].split(";")[0].strip() or "image/png"
    try:
        return base64.b64decode(encoded), mime
    except Exception:
        return None, ""


def _record_payload(record: CreatorImageRecord) -> dict[str, Any]:
    description = record.description or _read_sidecar_description(record.file_path)
    return {
        "image_id": record.image_id,
        "source": record.source,
        "file_path": record.file_path,
        "prompt": record.prompt,
        "description": description,
        "mime_type": record.mime_type,
        "width": record.original_width,
        "height": record.original_height,
    }


def _resize_keep_ratio(img: Any, target: tuple[int | None, int | None]) -> Any:
    """等比缩放:只给一边时按单边等比,两边都给时取 fit(不拉伸)。"""
    width, height = target
    original_w, original_h = img.size
    if width and height:
        ratio = min(width / original_w, height / original_h)
        new_size = (
            max(1, int(original_w * ratio)),
            max(1, int(original_h * ratio)),
        )
    elif width:
        ratio = width / original_w
        new_size = (int(width), max(1, int(original_h * ratio)))
    elif height:
        ratio = height / original_h
        new_size = (max(1, int(original_w * ratio)), int(height))
    else:
        return img
    return img.resize(new_size, Image.Resampling.LANCZOS)


def _remove_background(img: Any, background_color: str | None = None) -> Any:
    """纯色背景去底为透明(参考 codex remove_chroma_key 思路)。

    - 键色:background_color 指定(如 "#00ff00");未指定时从边框四角采样平均
    - alpha:色差距离做 soft matte(transparent 阈值 12 / opaque 阈值 220)
    - despill:低透明度边缘向键色方向清理,避免色边
    """
    import numpy as np

    rgba = img.convert("RGBA")
    arr = np.asarray(rgba).astype(np.float32)
    rgb = arr[:, :, :3]

    if background_color:
        key = _parse_hex_color(background_color)
        key_arr = np.array(key, dtype=np.float32)
    else:
        # 边框采样:四角小方块平均
        h, w = rgb.shape[:2]
        patch = max(1, min(h, w, 12))
        patches = [
            rgb[0:patch, 0:patch],
            rgb[0:patch, w - patch : w],
            rgb[h - patch : h, 0:patch],
            rgb[h - patch : h, w - patch : w],
        ]
        key_arr = np.mean(np.concatenate([p.reshape(-1, 3) for p in patches]), axis=0)

    # 归一化颜色距离(0-1)
    distance = np.linalg.norm(rgb - key_arr, axis=2) / np.sqrt(3.0)

    transparent_threshold = 12.0 / 255.0
    opaque_threshold = 220.0 / 255.0
    alpha = np.clip(
        (distance - transparent_threshold)
        / max(opaque_threshold - transparent_threshold, 1e-6),
        0.0,
        1.0,
    )

    # despill:键色成分主导的低透明度区域,把颜色向键色方向收敛
    key_dominance = (rgb * key_arr).sum(axis=2) / (
        np.linalg.norm(rgb, axis=2) * np.linalg.norm(key_arr) + 1e-6
    )
    spill = (alpha < 0.5) & (key_dominance > 0.9)
    if spill.any():
        rgb[spill] = rgb[spill] * (1.0 - alpha[spill, None] * 0.8)

    out = np.dstack([rgb, alpha * 255.0]).astype(np.uint8)
    return Image.fromarray(out, mode="RGBA")


def _parse_hex_color(raw: str) -> tuple[int, int, int]:
    """解析 "#rrggbb" 或 "rrggbb" 颜色。"""
    value = str(raw or "").strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"颜色格式无效: {raw}(应为 #rrggbb)")
    try:
        return (
            int(value[0:2], 16),
            int(value[2:4], 16),
            int(value[4:6], 16),
        )
    except ValueError as exc:
        raise ValueError(f"颜色格式无效: {raw}") from exc
