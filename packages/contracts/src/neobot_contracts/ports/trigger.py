"""Trigger Ports — 触发器系统抽象"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class KeywordMatcher(Protocol):
    """关键词匹配器"""

    def match(self, message: str) -> list[str]: ...

    def calculate_weight(self, matched: list[str]) -> float: ...


@runtime_checkable
class RandomBoost(Protocol):
    """随机提权"""

    def boost(self, base_probability: float) -> float: ...


@runtime_checkable
class TriggerCalculator(Protocol):
    """触发计算器"""

    def calculate(self, message: str) -> tuple[bool, float, list[str]]: ...
