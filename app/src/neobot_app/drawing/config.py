"""Drawing configuration and exceptions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neobot_app.config.schemas.bot import ImageCreationConfig


TMP_SOURCE = "tmp"
GALLERY_SOURCE = "gallery"
DEFAULT_IMAGE_SIZE = "512x512"
DEFAULT_OUTPUT_FORMAT = "png"
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


class ImageGenerationError(Exception):
    """Drawing API error carrying full error info for agent diagnostics."""

    def __init__(self, error_info: dict[str, Any]) -> None:
        self.error_info = error_info
        super().__init__(json.dumps(error_info, ensure_ascii=False))


@dataclass(frozen=True)
class DrawServiceConfig:
    enabled: bool = False
    gallery_capacity: int = 10
    gallery_page_size: int = 50
    emoji_page_size: int = 50
    allow_emoji_add: bool = False
    allow_emoji_delete: bool = False
    draw_cooldown_seconds: int = 60
    draw_notification_retry_seconds: int = 30
    draw_max_retries: int = 1
    draw_background_enabled: bool = True
    draw_startup_grace_seconds: float = 3.0
    draw_max_tasks_per_pipeline: int = 20

    @classmethod
    def from_schema(cls, config: "ImageCreationConfig | None") -> "DrawServiceConfig":
        if config is None:
            return cls()
        gallery = getattr(config, "gallery", None)
        emoji = getattr(config, "emoji", None)
        drawing_cfg = getattr(config, "drawing", None)
        return cls(
            enabled=bool(getattr(config, "enabled", False)),
            gallery_capacity=max(int(getattr(gallery, "capacity", 10) or 0), 0),
            gallery_page_size=max(int(getattr(gallery, "page_size", 50) or 1), 1),
            emoji_page_size=max(int(getattr(emoji, "page_size", 50) or 1), 1),
            allow_emoji_add=bool(getattr(emoji, "allow_add", False)),
            allow_emoji_delete=bool(getattr(emoji, "allow_delete", False)),
            draw_cooldown_seconds=int(getattr(drawing_cfg, "cooldown_seconds", 60) or 60),
            draw_notification_retry_seconds=int(getattr(drawing_cfg, "notification_retry_seconds", 30) or 30),
            draw_max_retries=int(getattr(drawing_cfg, "max_retries", 1) or 0),
            draw_background_enabled=bool(getattr(drawing_cfg, "background_enabled", True)),
            draw_startup_grace_seconds=float(getattr(drawing_cfg, "startup_grace_seconds", 3.0) or 3.0),
            draw_max_tasks_per_pipeline=int(getattr(drawing_cfg, "max_tasks_per_pipeline", 20) or 20),
        )
