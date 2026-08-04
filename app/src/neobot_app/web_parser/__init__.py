"""Web 解析模块 — 内容提取、结构化与动态渲染。"""

from neobot_app.web_parser.extractor import ContentExtractor
from neobot_app.web_parser.models import PageMetadata, ParsedPage
from neobot_app.web_parser.renderer import DynamicRenderer, RenderedPage
from neobot_app.web_parser.structurer import (
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
