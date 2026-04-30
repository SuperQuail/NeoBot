from __future__ import annotations

from collections import deque
from typing import Any


class ReplyBlockRegistry:
    def __init__(self, *, max_size: int = 2048) -> None:
        self._max_size = max(1, max_size)
        self._keys: set[tuple[str, str, int]] = set()
        self._message_ids: set[int] = set()
        self._order: deque[tuple[str, str, int]] = deque()

    def block_event(self, event: Any) -> None:
        key = self._message_key(event)
        if key is None or key in self._keys:
            return
        self._keys.add(key)
        self._message_ids.add(key[2])
        self._order.append(key)
        while len(self._order) > self._max_size:
            old_key = self._order.popleft()
            self._keys.discard(old_key)
            if not any(existing[2] == old_key[2] for existing in self._keys):
                self._message_ids.discard(old_key[2])

    def consume_message(self, message: Any) -> bool:
        key = self._message_key(message)
        message_id = self._message_id(message)
        if key is None:
            if message_id is None or message_id not in self._message_ids:
                return False
            self._remove_message_id(message_id)
            return True
        if key in self._keys:
            self._keys.remove(key)
            if not any(existing[2] == key[2] for existing in self._keys):
                self._message_ids.discard(key[2])
            return True
        if message_id is not None and message_id in self._message_ids:
            self._remove_message_id(message_id)
            return True
        return False

    def _remove_message_id(self, message_id: int) -> None:
        removed_keys = {key for key in self._keys if key[2] == message_id}
        self._keys.difference_update(removed_keys)
        self._message_ids.discard(message_id)

    @staticmethod
    def _message_id(event: Any) -> int | None:
        data = _event_to_mapping(event)
        return _safe_int(_get_value(data, event, "message_id"))

    @staticmethod
    def _message_key(event: Any) -> tuple[str, str, int] | None:
        data = _event_to_mapping(event)
        message_id = _safe_int(_get_value(data, event, "message_id"))
        if message_id is None:
            return None

        message_type = str(_get_value(data, event, "message_type") or "")
        group_id = _safe_int(_get_value(data, event, "group_id"))
        if group_id is not None:
            return (message_type or "group", str(group_id), message_id)

        user_id = _safe_int(_get_value(data, event, "user_id"))
        if user_id is not None:
            return (message_type or "private", str(user_id), message_id)

        return (message_type or "unknown", "", message_id)


def _event_to_mapping(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        return event
    if hasattr(event, "model_dump"):
        dumped = event.model_dump(mode="python")
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _get_value(data: dict[str, Any], event: Any, key: str) -> Any:
    if key in data:
        return data[key]
    return getattr(event, key, None)


def _safe_int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
