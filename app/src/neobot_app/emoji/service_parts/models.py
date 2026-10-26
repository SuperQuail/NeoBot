"""表情包条目模型与文件助手（由 service.py 拆分）。"""

from __future__ import annotations

import hashlib

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class EmojiEntry:
    """内存中的表情包条目"""
    file_name: str
    file_path: Path
    analysis_text: str
    file_hash: str = ""
    use_count: int = 0
    image_source: str | None = None
    created_at: Any = None
    updated_at: Any = None
    #: 候选曝光分：进入候选池但未被发送时累加，只影响排序
    exposure_score: float = 0.0
    #: 爱用：每轮表情包选择固定进入候选池
    is_favorite: bool = False

    @property
    def effective_use_count(self) -> float:
        """排序权重 = 实际发送次数 + 候选曝光分。"""
        return self.use_count + self.exposure_score


@dataclass(frozen=True, slots=True)
class EmojiImportResult:
    number: int
    entry: EmojiEntry


class EmojiDuplicateError(ValueError):
    """内容哈希已存在。

    重复加入不是错误：调用方应当把它当成幂等成功处理（返回已有编号），
    否则模型会在不同事件里反复重试同一个必然失败的调用。
    继承 ValueError 以保持既有 except ValueError 调用方的行为不变。
    """

    def __init__(
        self,
        message: str,
        *,
        number: int | None = None,
        file_name: str = "",
        analysis_text: str = "",
    ) -> None:
        super().__init__(message)
        self.number = number
        self.file_name = file_name
        self.analysis_text = analysis_text


def _file_hash_sync(path: Path) -> str:
    """同步算文件 sha256（读不到时返回空串）。"""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except Exception:
        return ""


def _detect_image_suffix(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "webp"
    if image_bytes.startswith(b"GIF87a") or image_bytes.startswith(b"GIF89a"):
        return "gif"
    return "png"


def _read_sidecar_text(file_path: Path) -> str | None:
    txt_path = file_path.with_suffix(".txt")
    if not txt_path.exists():
        return None
    try:
        text = txt_path.read_text(encoding="utf-8").strip()
        return text or None
    except Exception:
        return None


def _safe_emoji_file_name(file_name: str | None, suffix: str) -> str:
    suffix = suffix.lstrip(".").lower() or "png"
    raw_name = Path(str(file_name or "")).name.strip()
    if not raw_name:
        from uuid import uuid4
        return f"emoji_{uuid4().hex[:12]}.{suffix}"
    stem = Path(raw_name).stem.strip() or f"emoji_{uuid4().hex[:12]}"
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem)
    return f"{cleaned[:80] or 'emoji'}.{suffix}"
