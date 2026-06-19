"""Web parser data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class PageMetadata:
    """Extracted page metadata."""

    title: str = ""
    author: str = ""
    publish_date: Optional[datetime] = None
    language: str = ""
    description: str = ""
    site_name: str = ""
    favicon_url: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "author": self.author,
            "publish_date": self.publish_date.isoformat() if self.publish_date else None,
            "language": self.language,
            "description": self.description,
            "site_name": self.site_name,
        }


@dataclass
class ParsedPage:
    """Result of parsing a web page."""

    url: str
    metadata: PageMetadata = field(default_factory=PageMetadata)
    content_html: str = ""
    content_text: str = ""
    content_markdown: str = ""
    summary: str = ""
    images: list[str] = field(default_factory=list)
    error: Optional[str] = None
    parse_time_ms: float = 0.0

    @property
    def success(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "metadata": self.metadata.to_dict(),
            "content_text": self.content_text,
            "content_markdown": self.content_markdown,
            "summary": self.summary,
            "images": self.images,
            "error": self.error,
        }
