from __future__ import annotations

from typing import Any

from neobot_contracts.models import ConversationRef


class Bot:
    """Wrapper around an adapter providing a stable messaging API.

    Exposes ``send``, ``send_private``, and ``send_group`` while hiding
    adapter internals from plugins and DI-resolved handlers.
    """

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter

    @property
    def self_id(self) -> Any:
        """Get the bot's own ID from adapter."""
        return getattr(self._adapter, "self_id", None)

    async def send(self, conversation: ConversationRef, message: Any) -> Any:
        """Send *message* to *conversation*.

        Delegates to ``adapter.send(conversation, message)``.
        """
        return await self._adapter.send(conversation, message)

    async def send_private(self, user_id: int, message: Any) -> Any:
        """Send *message* to a private chat identified by *user_id*.

        Delegates to ``adapter.send_private_msg(user_id, message)``.
        """
        return await self._adapter.send_private_msg(user_id, message)

    async def send_group(self, group_id: int, message: Any) -> Any:
        """Send *message* to a group chat identified by *group_id*.

        Delegates to ``adapter.send_group_msg(group_id, message)``.
        """
        return await self._adapter.send_group_msg(group_id, message)
