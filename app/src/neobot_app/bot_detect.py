"""通过 get_robot_uin_range API 检测官方机器人账号。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter


class BotDetector:
    """使用 get_robot_uin_range 检测 QQ 账号是否为官方机器人。"""

    def __init__(self, adapter: OneBotAdapter | None = None) -> None:
        self._adapter = adapter
        self._ranges: list[tuple[int, int]] = []

    async def refresh(self) -> None:
        """从 QQ 后端查询机器人 UIN 段并缓存。"""
        if self._adapter is None:
            return

        from neobot_adapter.request.private import get_robot_uin_range

        try:
            response = await get_robot_uin_range()
        except Exception:
            return

        data = getattr(response, "data", None)
        if not data:
            return

        ranges: list[tuple[int, int]] = []
        for item in data:
            min_uin = getattr(item, "minUin", None)
            max_uin = getattr(item, "maxUin", None)
            if min_uin is not None and max_uin is not None:
                ranges.append((int(min_uin), int(max_uin)))
        self._ranges = ranges

    def is_official_bot(self, user_id: int | str) -> bool:
        """检查用户 ID 是否落在已知的官方机器人 UIN 段内。"""
        if not self._ranges:
            return False
        try:
            uid = int(user_id)
        except (ValueError, TypeError):
            return False
        return any(min_uin <= uid <= max_uin for min_uin, max_uin in self._ranges)

    @property
    def ranges(self) -> list[tuple[int, int]]:
        return list(self._ranges)
