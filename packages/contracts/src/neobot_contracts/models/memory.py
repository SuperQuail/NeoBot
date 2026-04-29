"""记忆模型"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TopicNodeType(str, Enum):
    """话题节点类型"""

    RAW = "raw"
    SUMMARY = "summary"


@dataclass(frozen=True, slots=True)
class ArchiveMemory:
    """档案式记忆"""

    id: int
    table_name: str  # 表名，用于区分不同类别的记忆
    key: str  # 键名，在表内唯一标识一个条目
    value: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class TopicNode:
    """话题向量树节点"""

    id: int
    title: str
    content: str
    embedding: list[float]
    node_type: TopicNodeType
    tags: list[str]
    parent_id: int | None
    children_ids: list[int]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ImageAnalysis:
    """Cached image analysis metadata and text result."""

    id: int
    file_hash: str
    source: str | None
    mime_type: str | None
    original_width: int | None
    original_height: int | None
    processed_width: int | None
    processed_height: int | None
    analysis_text: str | None
    created_at: datetime
    updated_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class EmojiRecord:
    """表情包记录 — 解析后的表情包图片元数据与描述"""

    id: int
    file_hash: str
    file_name: str
    file_path: str
    mime_type: str | None
    original_width: int | None
    original_height: int | None
    analysis_text: str | None
    use_count: int
    created_at: datetime
    updated_at: datetime
    version: int
    image_source: str | None = None


@dataclass(frozen=True, slots=True)
class CreatorImageRecord:
    """Creator Agent image metadata."""

    id: int
    image_id: str
    source: str
    file_hash: str
    file_path: str
    prompt: str | None
    description: str | None
    mime_type: str | None
    original_width: int | None
    original_height: int | None
    created_at: datetime
    updated_at: datetime
    version: int
    image_source: str | None = None
