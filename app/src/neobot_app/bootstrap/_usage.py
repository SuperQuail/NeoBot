"""用量追踪与报告"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker

from neobot_app.statistics.tracker import UsageTracker, initialize_usage_tracker
from neobot_app.statistics.reporter import UsageReportService


def build_usage_components(
    *,
    _engine: Any,
    logger_factory: Any,
) -> dict[str, Any]:
    usage_session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    usage_tracker = UsageTracker(
        usage_session_factory,
        logger=logger_factory.get_logger("app.usage"),
    )
    initialize_usage_tracker(usage_tracker)
    report_service = UsageReportService(
        usage_session_factory,
        logger=logger_factory.get_logger("app.usage_report"),
    )
    return {"tracker": usage_tracker, "report_service": report_service}
