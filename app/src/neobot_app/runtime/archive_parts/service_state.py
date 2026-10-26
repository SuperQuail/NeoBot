"""服务装配与容量策略接线：构造参数解析、provider 热替换、待机判断与关闭。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_memory import ArchiveMemoryService

from .constants import (
    COUNTER_TABLE,
    DEFAULT_MAX_TOOL_ROUNDS,
    DEFAULT_PROMPT_SNIPPET_CHARS,
    DEFAULT_SUMMARY_BUDGET_SECONDS,
    ITEM_ARCHIVE_TABLE,
)
from .helpers import _cooldown_seconds_or_default, _positive_int_or_zero

if TYPE_CHECKING:
    from neobot_app.config.schemas.bot import AgentMemoryItemArchive, BotConfig
    from neobot_chat.providers.base import Provider


class ServiceStateMixin:
    """ArchiveMemoryAutoSummaryService 的构造、依赖替换与待机状态。"""

    def __init__(
        self,
        *,
        archive_memory_service: ArchiveMemoryService,
        provider: "Provider | None",
        config: "BotConfig",
        item_archive_config: "AgentMemoryItemArchive | None" = None,
        logger: Logger | None = None,
        tool_definitions: list[dict] | None = None,
        tool_executor: Any = None,
        standby_service: Any = None,
    ) -> None:
        self._archive = archive_memory_service
        self._provider = provider
        self._config = config
        self._logger = logger or NullLogger()
        self._locks: dict[str, asyncio.Lock] = {}
        # 正在执行总结的会话键集合。同一会话同时只允许一次总结，
        # 否则消息持续到来时任务会排成长队，每个都跑满一次模型超时。
        self._active_summaries: set[str] = set()
        #: 计数器状态的解析缓存（键 = conversation_kind:conversation_id，值 =
        #: (计数器, 载入时刻)）。见 _cached_counter：避免每条消息都重新读库并
        #: json.loads 整个 blob，同时靠 TTL 让外部修改在有限时间内可见。
        self._counter_cache: dict[str, tuple[dict[str, Any], float]] = {}
        self._tool_definitions = tool_definitions or []
        self._tool_executor = tool_executor
        # 待机熔断:即使消息管线漏掉了拦截,总结本身也必须停。
        self._standby_service = standby_service
        fav_cfg = getattr(getattr(getattr(config, "agent", None), "memory", None), "favorability", None)
        self._favorability_max_change: int = int(getattr(fav_cfg, "max_change_per_summary", 5) or 5)
        self._favorability_min: int = int(getattr(fav_cfg, "min_value", -1000) or -1000)
        self._favorability_max: int = int(getattr(fav_cfg, "max_value", 1000) or 1000)
        trigger_cfg = getattr(getattr(getattr(config, "agent", None), "memory", None), "trigger", None)
        snippet = getattr(trigger_cfg, "prompt_snippet_chars", DEFAULT_PROMPT_SNIPPET_CHARS)
        try:
            self._prompt_snippet_chars: int = max(0, int(snippet))
        except (TypeError, ValueError):
            self._prompt_snippet_chars = DEFAULT_PROMPT_SNIPPET_CHARS
        rounds = getattr(trigger_cfg, "max_tool_rounds", DEFAULT_MAX_TOOL_ROUNDS)
        try:
            self._max_tool_rounds: int = max(1, int(rounds))
        except (TypeError, ValueError):
            self._max_tool_rounds = DEFAULT_MAX_TOOL_ROUNDS
        budget = getattr(
            trigger_cfg, "max_summary_seconds", DEFAULT_SUMMARY_BUDGET_SECONDS
        )
        try:
            self._summary_budget_seconds: float = max(1.0, float(budget))
        except (TypeError, ValueError):
            self._summary_budget_seconds = DEFAULT_SUMMARY_BUDGET_SECONDS
        call_timeout = getattr(trigger_cfg, "model_call_timeout_seconds", 0.0)
        try:
            # 0 = 自动（跟随 provider 自身的请求超时）
            self._model_call_timeout_seconds: float = max(0.0, float(call_timeout or 0.0))
        except (TypeError, ValueError):
            self._model_call_timeout_seconds = 0.0
        self._item_archive_enabled: bool = bool(item_archive_config.enabled) if item_archive_config else True
        self._item_archive_table: str = (
            str(item_archive_config.table_name).strip() or ITEM_ARCHIVE_TABLE
        ) if item_archive_config else ITEM_ARCHIVE_TABLE
        # ── 档案长度硬上限（spec(1)）──
        archive_cfg = getattr(
            getattr(getattr(config, "agent", None), "memory", None), "archive", None
        )
        #: 单条档案的存储上限；0 = 未配置/已禁用（行为与现状一致）。
        self._overflow_max_total_chars: int = _positive_int_or_zero(
            getattr(archive_cfg, "max_total_chars", None)
        )
        self._overflow_cooldown_seconds: float = _cooldown_seconds_or_default(
            getattr(archive_cfg, "overflow_summary_cooldown_seconds", None)
        )
        #: 每个档案条目（overflow:table:key）的连续失败次数与冷却到期时刻（epoch 秒）。
        #: 复用计数器那套指数退避：没有它时压缩失败会在每次写入时重跑一整轮模型调用。
        self._overflow_failures: dict[str, int] = {}
        self._overflow_retry_after: dict[str, float] = {}
        #: 在途的「档案超限」压缩任务（单飞占位复用 self._active_summaries）。
        self._overflow_tasks: set[asyncio.Task] = set()
        # ── 面板手动 / 批量压缩的状态表（spec(4) Part C / §4.10.4）──
        #: task_id -> 任务状态字典。**进程内**：进程重启即清空，面板只当
        #: 「最近一次操作结果」，不当历史（历史在 archive_snapshots 表里）。
        self._manual_tasks: dict[str, dict[str, Any]] = {}
        self._manual_task_seq = 0
        self._configure_archive_overflow_policy(archive_memory_service, archive_cfg)

    def install_provider(self, provider: "Provider | None") -> "Provider | None":
        """换用新的总结 provider，返回被替换下来的旧 provider。

        只换引用、不关闭旧 provider：由调用方在替换成功后统一清理，避免替换
        失败时旧 provider 已被关闭。
        """
        previous = self._provider
        self._provider = provider
        return previous

    def _configure_archive_overflow_policy(self, archive_service: Any, archive_cfg: Any) -> None:
        """把存储上限接到档案服务的写路径上（D1-B：上限收口在 ArchiveMemoryService.set）。

        档案服务在 packages/memory 里，是纯服务、读不到 BotConfig；由装配期在这里注入
        「上限策略 + 超限触发回调」，避免 memory 包反向依赖 app 层。
        """
        configure = getattr(archive_service, "configure_overflow_policy", None)
        if not callable(configure):
            # 测试替身 / 旧实现没有容量治理接口：保持原行为。
            return
        configure(
            max_total_chars=self._overflow_max_total_chars,
            overflow_action=str(getattr(archive_cfg, "overflow_action", None) or "summarize"),
            cooldown_seconds=self._overflow_cooldown_seconds,
            # 豁免名单以 COUNTER_TABLE 为唯一事实来源：内部计数表永不参与容量治理，
            # 否则自动总结要么写不进计数（reject），要么压缩器把待总结消息吃掉。
            exempt_tables=(COUNTER_TABLE,),
        )
        setter = getattr(archive_service, "set_overflow_trigger", None)
        if callable(setter):
            setter(self._schedule_overflow_compression)
        self._logger.debug(
            "档案长度上限已接线",
            max_total_chars=self._overflow_max_total_chars,
            cooldown_seconds=int(self._overflow_cooldown_seconds),
        )

    def is_standby(self) -> bool:
        """Bot 是否处于待机状态。"""
        service = getattr(self, "_standby_service", None)
        return bool(service is not None and service.is_standby())

    async def close(self) -> None:
        if self._provider is not None:
            await self._provider.close()
