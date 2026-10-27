"""对实时聊天消息进行档案记忆自动摘要。

实现按职责拆在 ``archive_parts``：常量、纯函数、服务装配、计数器、总结执行、
提示词、超限压缩与面板手动/批量压缩。本模块保留原有模块级名称与
``ArchiveMemoryAutoSummaryService`` 的公开 API（薄门面 + re-export）。
"""

from __future__ import annotations

from neobot_app.time_context import (
    epoch_seconds,
    epoch_seconds_int,
    get_current_time_and_lunar_date,
    monotonic_seconds,
)

from .archive_parts.constants import (
    COUNTER_TABLE,
    ITEM_ARCHIVE_TABLE,
    MAX_STORED_MESSAGE_CHARS,
    DEFAULT_PROMPT_SNIPPET_CHARS,
    DEFAULT_MAX_TOOL_ROUNDS,
    MAX_TOOL_FAILURES,
    _TOOL_FAILURE_MARKERS,
    _COUNTER_CACHE_TTL_SECONDS,
    RETRY_BACKOFF_BASE_SECONDS,
    RETRY_BACKOFF_MAX_SECONDS,
    RETRY_BACKOFF_MAX_DOUBLINGS,
    DEFAULT_SUMMARY_BUDGET_SECONDS,
    DEFAULT_SUMMARY_CALL_TIMEOUT_SECONDS,
    PROVIDER_TIMEOUT_MARGIN_SECONDS,
    MAX_TOOL_RESULT_CHARS,
    MAX_TOOL_RESULT_TOTAL_CHARS,
    MAX_OVERFLOW_PROMPT_CHARS,
    _ARCHIVE_PROMPT_OMITTED,
    MAX_OVERFLOW_BACKOFF_ENTRIES,
    AUTO_COMPRESSION_TARGET_CHARS,
    MIN_MANUAL_TARGET_CHARS,
    MANUAL_TARGET_FALLBACK_MAX_CHARS,
    MAX_BATCH_COMPRESS_ITEMS,
    MAX_MANUAL_TASKS,
    MANUAL_TASK_TTL_SECONDS,
    MANUAL_COMPRESSION_USAGE_KIND,
    AUTO_COMPRESSION_USAGE_KIND,
    DEFAULT_OVERFLOW_COOLDOWN_SECONDS,
    _TOOL_TRUNCATED_MARKER,
    _TOOL_DROPPED_MARKER,
)
from .archive_parts.helpers import (
    _consume_flush_result,
    _settled_flush_result,
    _unfinished_flush_count,
    _compression_usage_kind,
    _positive_int_or_zero,
    _cooldown_seconds_or_default,
    _bounded_archive_text,
    _request_chars,
    _bounded_tool_result,
    _trim_tool_history,
    _is_tool_failure,
    _normalize_message_text,
    _normalize_counter_message,
    _format_sender,
    _format_counter_message,
)
from .archive_parts.manual_compression import ManualCompressionMixin
from .archive_parts.manual_tasks import ManualTaskMixin
from .archive_parts.overflow_job import OverflowJobMixin
from .archive_parts.overflow_tools import OverflowToolMixin
from .archive_parts.service_state import ServiceStateMixin
from .archive_parts.summary_counter import SummaryCounterMixin
from .archive_parts.summary_flush import SummaryFlushMixin
from .archive_parts.summary_prompt import SummaryPromptMixin
from .archive_parts.summary_run import SummaryRunMixin


class ArchiveMemoryAutoSummaryService(
    ServiceStateMixin,
    SummaryCounterMixin,
    SummaryFlushMixin,
    SummaryRunMixin,
    SummaryPromptMixin,
    OverflowJobMixin,
    OverflowToolMixin,
    ManualCompressionMixin,
    ManualTaskMixin,
):
    """统计实时消息数量，并按配置间隔通过工具定期更新档案画像。"""


__all__ = [
    "COUNTER_TABLE",
    "ITEM_ARCHIVE_TABLE",
    "MAX_STORED_MESSAGE_CHARS",
    "DEFAULT_PROMPT_SNIPPET_CHARS",
    "DEFAULT_MAX_TOOL_ROUNDS",
    "MAX_TOOL_FAILURES",
    "_TOOL_FAILURE_MARKERS",
    "_COUNTER_CACHE_TTL_SECONDS",
    "RETRY_BACKOFF_BASE_SECONDS",
    "RETRY_BACKOFF_MAX_SECONDS",
    "RETRY_BACKOFF_MAX_DOUBLINGS",
    "DEFAULT_SUMMARY_BUDGET_SECONDS",
    "DEFAULT_SUMMARY_CALL_TIMEOUT_SECONDS",
    "PROVIDER_TIMEOUT_MARGIN_SECONDS",
    "MAX_TOOL_RESULT_CHARS",
    "MAX_TOOL_RESULT_TOTAL_CHARS",
    "MAX_OVERFLOW_PROMPT_CHARS",
    "_ARCHIVE_PROMPT_OMITTED",
    "MAX_OVERFLOW_BACKOFF_ENTRIES",
    "AUTO_COMPRESSION_TARGET_CHARS",
    "MIN_MANUAL_TARGET_CHARS",
    "MANUAL_TARGET_FALLBACK_MAX_CHARS",
    "MAX_BATCH_COMPRESS_ITEMS",
    "MAX_MANUAL_TASKS",
    "MANUAL_TASK_TTL_SECONDS",
    "MANUAL_COMPRESSION_USAGE_KIND",
    "AUTO_COMPRESSION_USAGE_KIND",
    "DEFAULT_OVERFLOW_COOLDOWN_SECONDS",
    "_TOOL_TRUNCATED_MARKER",
    "_TOOL_DROPPED_MARKER",
    "_consume_flush_result",
    "_settled_flush_result",
    "_unfinished_flush_count",
    "_compression_usage_kind",
    "_positive_int_or_zero",
    "_cooldown_seconds_or_default",
    "_bounded_archive_text",
    "_request_chars",
    "_bounded_tool_result",
    "_trim_tool_history",
    "_is_tool_failure",
    "_normalize_message_text",
    "_normalize_counter_message",
    "_format_sender",
    "_format_counter_message",
    "epoch_seconds",
    "epoch_seconds_int",
    "get_current_time_and_lunar_date",
    "monotonic_seconds",
    "ArchiveMemoryAutoSummaryService",
]
