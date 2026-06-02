"""MediaSender port — protocol for sending media (image/audio) messages."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from neobot_contracts.models import ConversationRef


@runtime_checkable
class MediaSender(Protocol):
    """Protocol for sending image and audio media through a file server.

    Implementations bind infrastructure details (e.g. FileServer) and expose
    a uniform interface that plugin code can call without importing app-layer
    modules.
    """

    async def send_image(
        self,
        adapter: Any,
        conversation: ConversationRef,
        *,
        path: Path | None = None,
        data: bytes | None = None,
        filename: str | None = None,
    ) -> Any:
        """Send an image to a conversation.

        Provide either a file *path* or raw *data* (with *filename*).
        """
        ...

    async def send_audio(
        self,
        adapter: Any,
        conversation: ConversationRef,
        *,
        path: Path,
    ) -> Any:
        """Send an audio clip to a conversation."""
        ...

    def prepare_image_segment(self, file_server: Any, file_path: Path) -> dict:
        """Prepare an image message segment dict using the given file server."""
        ...

    def prepare_audio_segment(self, file_server: Any, file_path: Path) -> dict:
        """Prepare an audio message segment dict using the given file server."""
        ...
