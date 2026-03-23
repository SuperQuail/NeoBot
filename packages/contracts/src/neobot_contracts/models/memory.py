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
    user_id: str
    key: str
    value: str
    tags: list[str]
    created_at: datetime


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
