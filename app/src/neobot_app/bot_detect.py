"""Official bot detection via get_robot_uin_range API."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter


class BotDetector:
    """Detects whether a QQ account is an official bot using get_robot_uin_range."""

    def __init__(self, adapter: OneBotAdapter | None = None) -> None:
        self._adapter = adapter
        self._ranges: list[tuple[int, int]] = []

    async def refresh(self) -> None:
        """Query the bot UIN ranges from the QQ backend and cache them."""
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
        """Check if a user ID falls within any known official bot UIN range."""
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
