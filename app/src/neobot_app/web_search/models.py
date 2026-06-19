"""Web search data models."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class SearchResult:
    """A single search result."""

    index: int
    title: str
    url: str
    snippet: str
    engine: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    content: Optional[str] = None
    content_fetched: bool = False


@dataclass
class SearchResponse:
    """Response from a search query."""

    query: str
    results: list[SearchResult]
    engine: str
    total_estimated: int = 0
    error: Optional[str] = None
    search_time_ms: float = 0.0

    @property
    def success(self) -> bool:
        return self.error is None

    def summary(self) -> str:
        """Format results for agent to review and select."""
        if not self.success:
            return f"[错误] 搜索 '{self.query}' 失败: {self.error}"
        if not self.results:
            return f"搜索 '{self.query}' 未找到相关结果。"
        lines = [f"搜索 '{self.query}' 返回 {len(self.results)} 条结果 (引擎: {self.engine}):"]
        for r in self.results:
            status = "[已读]" if r.content_fetched else "[未读]"
            lines.append(f"  [{r.index}] {status} {r.title}\n      {r.url}\n      {r.snippet[:120]}...")
        return "\n".join(lines)
