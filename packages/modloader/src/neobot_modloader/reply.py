from __future__ import annotations

from pathlib import Path
from typing import Any

from neobot_modloader.message import normalize_message_payload


class Reply:
    def __init__(self, context: Any, event: dict[str, Any]) -> None:
        self._context = context
        self._event = event

    @property
    def event(self) -> dict[str, Any]:
        return self._event

    async def send(self, message: Any) -> Any:
        return await self._context.reply(self._event, normalize_message_payload(message))

    async def text(self, value: str) -> Any:
        return await self.send(value)

    async def private(self, user_id: int, message: Any) -> Any:
        return await self._context.send_private(user_id, normalize_message_payload(message))

    async def group(self, group_id: int, message: Any) -> Any:
        return await self._context.send_group(group_id, normalize_message_payload(message))

    async def image(
        self,
        *,
        url: str | None = None,
        file: str | None = None,
        path: Path | str | None = None,
        data: bytes | None = None,
        filename: str | None = None,
    ) -> Any:
        if path is not None or data is not None:
            conversation = self._context.conversation_from_event(self._event)
            return await self._context.send_image(
                conversation,
                path=Path(path) if path is not None else None,
                data=data,
                filename=filename,
            )
        payload: dict[str, Any] = {}
        if url is not None:
            payload["url"] = url
        if file is not None:
            payload["file"] = file
        return await self.send({"type": "image", "data": payload})
