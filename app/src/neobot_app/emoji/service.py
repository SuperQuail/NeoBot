"""EmojiService — 表情包扫描、解析、编号与清单生成（清单按需由 list_emojis 返回）"""

from __future__ import annotations

from neobot_app.emoji.service_parts.models import (
    EmojiDuplicateError,
    EmojiEntry,
    EmojiImportResult,
)
from neobot_app.emoji.service_parts.core import _CoreMixin
from neobot_app.emoji.service_parts.queries import _QueryMixin
from neobot_app.emoji.service_parts.sending import _SendingMixin
from neobot_app.emoji.service_parts.mutations import _MutationMixin
from neobot_app.emoji.service_parts.scanning import _ScanningMixin
from neobot_app.emoji.service_parts.indexing import _IndexMixin
from neobot_app.emoji.service_parts.disk_watch import _DiskWatchMixin

__all__ = ["EmojiDuplicateError", "EmojiEntry", "EmojiImportResult", "EmojiService"]


class EmojiService(
    _CoreMixin,
    _QueryMixin,
    _SendingMixin,
    _MutationMixin,
    _ScanningMixin,
    _IndexMixin,
    _DiskWatchMixin,
):
    """管理表情包的扫描、解析、编号与提示词生成"""
