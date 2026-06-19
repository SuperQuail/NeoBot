"""Content structurer — organize extracted content into a unified format."""

from __future__ import annotations

from neobot_app.web_parser.models import ParsedPage

AGENT_FORMAT = """## {title}

**来源**: {url}
**作者**: {author}
**发布日期**: {date}

### 摘要

{summary}

### 正文

{content}
"""


class ContentStructurer:
    """Structures and formats parsed page content for downstream use."""

    def structure(self, page: ParsedPage) -> ParsedPage:
        """Normalize a ParsedPage."""
        return page

    def to_agent_context(self, page: ParsedPage) -> str:
        """Format a ParsedPage as context for an LLM agent."""
        meta = page.metadata
        date_str = meta.publish_date.strftime("%Y-%m-%d") if meta.publish_date else "未知"
        return AGENT_FORMAT.format(
            title=meta.title or "无标题",
            url=page.url,
            author=meta.author or "未知",
            date=date_str,
            summary=page.summary or "无摘要",
            content=page.content_text or page.content_markdown or "无内容",
        )

    def to_compact(self, page: ParsedPage, max_chars: int = 4000) -> str:
        """Format as compact agent context, truncating body to max_chars."""
        meta = page.metadata
        date_str = meta.publish_date.strftime("%Y-%m-%d") if meta.publish_date else "?"

        body = page.content_text or page.content_markdown or ""
        if len(body) > max_chars:
            body = body[:max_chars] + f"\n\n... (截断, 原文共 {len(body)} 字)"

        return AGENT_FORMAT.format(
            title=meta.title or "无标题",
            url=page.url,
            author=meta.author or "未知",
            date=date_str,
            summary=page.summary or "无摘要",
            content=body,
        )

    def to_search_result_format(self, page: ParsedPage) -> dict:
        return page.to_dict()


def format_pages_for_agent(pages: list[ParsedPage], compact: bool = True) -> str:
    """Format multiple parsed pages as a single agent context string."""
    struct = ContentStructurer()
    parts = []
    for i, page in enumerate(pages, 1):
        if compact:
            parts.append(f"### 页面 {i}\n\n{struct.to_compact(page)}")
        else:
            parts.append(struct.to_agent_context(page))
    return "\n\n---\n\n".join(parts)
