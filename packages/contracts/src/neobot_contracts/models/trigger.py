"""触发器模型"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KeywordConfig:
    """关键词配置"""

    keyword: str
    weight: float


@dataclass(frozen=True, slots=True)
class TriggerResult:
    """触发结果"""

    should_reply: bool
    probability: float
    matched_keywords: list[str]
