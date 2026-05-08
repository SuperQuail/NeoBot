"""Web parser module — content extraction, structuring, and dynamic rendering."""

from neobot_app.toolpackage.web_parser.extractor import ContentExtractor
from neobot_app.toolpackage.web_parser.models import PageMetadata, ParsedPage
from neobot_app.toolpackage.web_parser.renderer import DynamicRenderer, RenderedPage
from neobot_app.toolpackage.web_parser.structurer import (
    ContentStructurer,
    format_pages_for_agent,
)

__all__ = [
    "ContentExtractor",
    "ContentStructurer",
    "DynamicRenderer",
    "PageMetadata",
    "ParsedPage",
    "RenderedPage",
    "format_pages_for_agent",
]
