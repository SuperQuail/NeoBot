"""Web 搜索数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class SearchResult:
    """单条搜索结果。"""

    index: int
    title: str
    url: str
    snippet: str
    engine: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    content: Optional[str] = None
    content_fetched: bool = False

    # fix(9) D1：出口归一化留痕与来源信息。全部有默认值，保持向后兼容；
    # raw_url 保留页面上的原始 href（未去壳/未去跟踪参数），便于排障与判据复核。
    raw_url: str = ""
    channel: str = ""
    published_at: Optional[str] = None
    site_name: str = ""

    def __post_init__(self) -> None:
        if not self.raw_url:
            self.raw_url = self.url


@dataclass
class SearchResponse:
    """一次搜索查询的响应。

    success 是严格语义（fix(9) D1/D2）：必须 error is None 且至少有一条结果。
    0 结果、校验判失败、抓取异常都算失败，调用方据此回退或如实报错，
    不再出现「error is None 即成功」把空结果/错配结果当成功交给模型的情况。
    """

    query: str
    results: list[SearchResult]
    engine: str
    total_estimated: int = 0
    error: Optional[str] = None
    search_time_ms: float = 0.0

    # fix(9) D1：降级标记（走过回退/判失败路径）与尝试次数；signals 保留校验判据明细。
    degraded: bool = False
    attempts: int = 1
    signals: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.results)

    @property
    def validation(self) -> dict[str, Any]:
        """最近一次出口校验的判据明细（无则空 dict）。"""
        return dict(self.signals.get("validation") or {})

    def summary(self) -> str:
        """将结果格式化为供智能体审阅与选择的内容。"""
        if self.error is not None:
            return f"[错误] 搜索 '{self.query}' 失败: {self.error}"
        if not self.results:
            return f"搜索 '{self.query}' 未找到相关结果。"
        lines = [f"搜索 '{self.query}' 返回 {len(self.results)} 条结果 (引擎: {self.engine}):"]
        for r in self.results:
            status = "[已读]" if r.content_fetched else "[未读]"
            lines.append(f"  [{r.index}] {status} {r.title}\n      {r.url}\n      {r.snippet[:120]}...")
        return "\n".join(lines)
