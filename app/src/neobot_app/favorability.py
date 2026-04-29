"""Favorability (好感度) text mapping and range utilities."""

from __future__ import annotations

# Each tuple: (min_value, max_value, label)
# Evaluated top-to-bottom; first matching range wins.
_FAVORABILITY_LEVELS: list[tuple[int, int, str]] = [
    (-1000, -901, "不共戴天的仇敌"),
    (-900, -801, "深恶痛绝"),
    (-800, -701, "非常讨厌"),
    (-700, -601, "讨厌"),
    (-600, -501, "很不喜欢"),
    (-500, -401, "不喜欢"),
    (-400, -301, "有点不满"),
    (-300, -201, "略感不悦"),
    (-200, -101, "略有微词"),
    (-100, 100, "普通网友"),
    (101, 200, "有点好感"),
    (201, 300, "印象不错"),
    (301, 400, "朋友"),
    (401, 500, "好朋友"),
    (501, 600, "关系很好的亲密网友"),
    (601, 700, "闺蜜/兄弟"),
    (701, 800, "知心好友"),
    (801, 900, "无可替代的重要之人"),
    (901, 1000, "生命中不可或缺的存在"),
]

FAVORABILITY_MIN = -1000
FAVORABILITY_MAX = 1000


def favorability_to_text(value: int) -> str:
    """Map a favorability score to a human-readable level label."""
    for lo, hi, label in _FAVORABILITY_LEVELS:
        if lo <= value <= hi:
            return label
    if value < FAVORABILITY_MIN:
        return _FAVORABILITY_LEVELS[0][2]
    return _FAVORABILITY_LEVELS[-1][2]


def clamp_favorability(
    value: int,
    *,
    min_val: int = FAVORABILITY_MIN,
    max_val: int = FAVORABILITY_MAX,
) -> int:
    """Clamp a favorability value to the valid range."""
    lo = min(min_val, max_val)
    hi = max(min_val, max_val)
    return max(lo, min(hi, value))
