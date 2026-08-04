"""Web 搜索模块 — 多引擎搜索，支持检索-阅读工作流。"""

from neobot_app.web_search.engine import (
    BingSearchEngine,
    DuckDuckGoSearchEngine,
    get_engine,
)
from neobot_app.web_search.manager import SearchManager
from neobot_app.web_search.models import SearchResponse, SearchResult
from neobot_app.web_search.session import SearchSession

__all__ = [
    "BingSearchEngine",
    "DuckDuckGoSearchEngine",
    "get_engine",
    "SearchManager",
    "SearchResponse",
    "SearchResult",
    "SearchSession",
]
