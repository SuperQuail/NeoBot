"""内容结构化器 — 将提取的内容整理为统一格式。"""

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
    """将解析后的页面内容结构化并格式化，供下游使用。"""

    def structure(self, page: ParsedPage) -> ParsedPage:
        """规范化一个 ParsedPage。"""
        return page

    def to_agent_context(self, page: ParsedPage) -> str:
        """将 ParsedPage 格式化为供 LLM 智能体使用的上下文。"""
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
        """格式化为紧凑的智能体上下文，正文截断至 max_chars。"""
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
    """将多个解析页面格式化为单个智能体上下文字符串。"""
    struct = ContentStructurer()
    parts = []
    for i, page in enumerate(pages, 1):
        if compact:
            parts.append(f"### 页面 {i}\n\n{struct.to_compact(page)}")
        else:
            parts.append(struct.to_agent_context(page))
    return "\n\n---\n\n".join(parts)
