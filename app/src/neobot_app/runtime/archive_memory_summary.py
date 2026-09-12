"""对实时聊天消息进行档案记忆自动摘要。"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_memory import ArchiveMemoryService

from neobot_app.time_context import (
    epoch_seconds,
    get_current_time_and_lunar_date,
    monotonic_seconds,
)

if TYPE_CHECKING:
    from neobot_app.config.schemas.bot import AgentMemoryItemArchive, BotConfig
    from neobot_chat.providers.base import Provider


COUNTER_TABLE = "memory_counter"
ITEM_ARCHIVE_TABLE = "item_archive"
MAX_STORED_MESSAGE_CHARS = 800
DEFAULT_PROMPT_SNIPPET_CHARS = 120
DEFAULT_MAX_TOOL_ROUNDS = 20
# 工具执行失败(未知工具/执行异常)累计达到该次数即中止本次总结，避免模型反复重试烧 token。
MAX_TOOL_FAILURES = 3
_TOOL_FAILURE_MARKERS = ("未知工具", "工具执行失败", "Tool error")
#: 计数器解析缓存的存活时间：缓存把「每条消息一次 DB 读 + json.loads」降到
#: 「每 30 秒一次」，同时保证外部对该行的修改（模型经 archive_crud 写
#: memory_counter、另一进程、人工改库）在有限时间内重新可见。
_COUNTER_CACHE_TTL_SECONDS = 30.0

# 总结失败后的冷却窗口：失败一次至少要等这么久才会再次尝试。
# 没有它时，计数器一旦越过间隔且总结持续失败，每条新消息都会重跑一整轮工具循环，
# 形成「每条消息 = 一次模型超时」的 token 风暴。
RETRY_BACKOFF_BASE_SECONDS = 60.0
# 连续失败时的退避上限，避免长时间完全不总结。
RETRY_BACKOFF_MAX_SECONDS = 900.0
# 退避翻倍的最大次数(1→2→4→8→16 倍)。
RETRY_BACKOFF_MAX_DOUBLINGS = 4
# 单次总结的总时长预算(秒)：超过即中止本轮并进入冷却，
# 避免多轮工具调用把一次总结拖成数十分钟。
# 取值要能装下至少两轮完整调用（第一轮工具调用 + 第二轮收尾）：单次调用超时
# 默认跟随模型的请求超时(常见 120 秒)再留余量，180 秒会让第二轮必然被腰斩。
DEFAULT_SUMMARY_BUDGET_SECONDS = 300.0
# 单次总结内层模型调用的超时(秒)，同时也是单轮上限。
# 仅作为兜底：配置 agent.memory.trigger.model_call_timeout_seconds 为 0（默认）时
# 跟随总结模型自身的请求超时，provider 不暴露超时时才用它。
DEFAULT_SUMMARY_CALL_TIMEOUT_SECONDS = 60.0
#: 自动模式(配置为 0)下给 provider 自身超时留的余量：让 httpx 先超时并返回可读错误，
#: 而不是被外层 wait_for 在模型仍在正常推理时掐断。
PROVIDER_TIMEOUT_MARGIN_SECONDS = 15.0
# 单条工具返回写入上下文的最大字符数。read_pending_messages 会返回 500 条消息全文，
# list_archive 会返回整条档案 value，原样追加会让之后每一轮都把这几百 KB 重发一遍。
MAX_TOOL_RESULT_CHARS = 4000
# 整个总结过程中保留的工具返回总量上限；超出后丢弃最早的工具返回。
MAX_TOOL_RESULT_TOTAL_CHARS = 60_000

# ── 档案长度硬上限（spec(1)）──
#: 「档案超限压缩」单次注入提示词的档案内容上限（字符）：超限档案在冷却/失败期间可能
#: 继续变大，全量塞进提示词会顶爆上下文；超过时保留首尾（头通常是总体概述、尾是最新
#: 内容），中间部分省略。
MAX_OVERFLOW_PROMPT_CHARS = 60_000
_ARCHIVE_PROMPT_OMITTED = "\n...[档案中间部分已省略，仅保留首尾用于压缩]...\n"
#: 失败退避表最多保留的条目数（防止长时间运行后无界增长）。
MAX_OVERFLOW_BACKOFF_ENTRIES = 512
#: 配置缺省时使用的超限压缩冷却秒数（与 AgentMemoryArchive 默认值一致）。
DEFAULT_OVERFLOW_COOLDOWN_SECONDS = 600.0
_TOOL_TRUNCATED_MARKER = "\n...[工具返回已截断，需要更多内容请缩小查询范围后重试]"
_TOOL_DROPPED_MARKER = "[已省略：更早的工具返回，避免上下文膨胀]"


class ArchiveMemoryAutoSummaryService:
    """统计实时消息数量，并按配置间隔通过工具定期更新档案画像。"""

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

    async def record_message(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        message_text: str,
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> None:
        """记录一条实时消息，并在达到配置间隔时触发摘要。"""
        if conversation_kind not in {"group", "private"}:
            return
        if self.is_standby():
            self._logger.debug(
                "Bot 已进入待机，跳过档案自动总结记录",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
            )
            return
        interval = self._interval_for(conversation_kind)
        if interval <= 0:
            return
        if self._provider is None:
            self._logger.debug(
                "档案自动总结跳过：provider 不可用",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
            )
            return

        clean_text = _normalize_message_text(message_text)
        if not clean_text:
            return

        counter_key = self._counter_key(conversation_kind, conversation_id)
        entry = {
            "sender_id": str(sender_id or ""),
            "sender_name": str(sender_name or ""),
            "text": clean_text[:MAX_STORED_MESSAGE_CHARS],
        }
        async with self._counter_lock(counter_key):
            state = await self._cached_counter(counter_key)
            if int(state.get("count", 0)) + 1 >= interval:
                # 将要触发总结：以库里的最新状态为准。计数器读路径带 30 秒缓存，
                # 若直接写回缓存内容，会把外部对计数器（清零、改冷却）的修改覆盖掉。
                state = await self._load_counter(counter_key)
            messages = list(state.get("messages", []))
            messages.append(entry)
            count = int(state.get("count", 0)) + 1

            state = self._counter_state(
                count=count,
                messages=messages[-max(interval, 1) :],
                failures=state.get("failures"),
                retry_after=state.get("retry_after"),
            )
            await self._save_counter(counter_key, state)

        if count < interval:
            return

        # 同一会话只允许一次总结在跑：消息在总结期间继续累计，
        # 但不会为每条消息都排一个「必然超时」的任务。占位由
        # _summarize_and_reset 内部统一持有（flush_all 路径共用），这里只预检。
        if counter_key in self._active_summaries:
            self._logger.debug(
                "档案自动总结已在执行，跳过本次调度",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
            )
            return

        if not self._retry_ready(state):
            self._logger.debug(
                "档案自动总结处于失败冷却中，保留待总结消息",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                retry_after=state.get("retry_after"),
                failures=state.get("failures"),
            )
            return
        await self._summarize_and_reset(
            conversation_kind=conversation_kind,
            conversation_id=conversation_id,
            counter_key=counter_key,
            messages=list(state.get("messages", [])),
            snapshot_count=count,
        )

    def is_standby(self) -> bool:
        """Bot 是否处于待机状态。"""
        service = getattr(self, "_standby_service", None)
        return bool(service is not None and service.is_standby())

    async def _summarize_and_reset(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        counter_key: str,
        messages: list[Any],
        snapshot_count: int,
    ) -> bool:
        """执行一次总结。返回 True 表示计数器已复位（含空消息），False 表示保留待重试。

        并发协议：总结占位在方法内统一持有（record_message 与 flush_all 共用），
        模型调用期间不持计数器锁；成功/失败都在短锁内基于库内最新状态合并，
        绝不回写快照。snapshot_count 是快照对应的 count，用来算出总结期间新到的
        消息条数——这些消息必须保留到下一轮，不能被成功路径清零。
        """
        if not self._begin_summary(counter_key):
            return False
        try:
            return await self._run_summary(
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                counter_key=counter_key,
                messages=messages,
                snapshot_count=snapshot_count,
            )
        finally:
            self._end_summary(counter_key)

    def _next_call_timeout(self, remaining: float) -> float:
        """算出本轮模型调用的超时，并保证不超出总预算。

        默认跟随总结模型自身的请求超时（再留一点余量让 httpx 先超时并返回可读错误，
        而不是被外层 wait_for 在模型仍正常推理时掐断）。开启思考、推理强度拉满的模型
        单次调用经常超过 60 秒，用固定 60 秒会稳定超时并反复重试，每次都要重发完整
        上下文，既浪费时间又烧 token。配置 model_call_timeout_seconds 可显式覆盖。
        """
        limit = self._model_call_timeout_seconds
        if limit <= 0.0:
            provider_timeout = getattr(self._provider, "timeout", None)
            try:
                limit = float(provider_timeout) + PROVIDER_TIMEOUT_MARGIN_SECONDS
            except (TypeError, ValueError):
                limit = DEFAULT_SUMMARY_CALL_TIMEOUT_SECONDS
        return max(1.0, min(limit, remaining))

    async def _commit_partial_success(
        self,
        counter_key: str,
        *,
        conversation_kind: str,
        conversation_id: str,
        snapshot_count: int,
        message_count: int,
        tool_successes: int,
        round_index: int,
        reason: str,
    ) -> None:
        """写入过内容后中止：按部分成功清账，不重跑整批消息。

        档案是增量 append 语义，重跑会把同一批事实再写一遍；而重试本身还要把同一批
        消息再烧一遍 token，且大概率以同样的方式再次中止。但必须留下可排查的告警，
        否则"模型没处理完就被销账"是完全静默的。
        """
        await self._commit_success(counter_key, snapshot_count=snapshot_count)
        self._logger.warning(
            "档案自动总结在写入部分内容后中止，按部分成功清账不再重试",
            conversation_kind=conversation_kind,
            conversation_id=conversation_id,
            message_count=message_count,
            round=round_index,
            tool_calls_succeeded=tool_successes,
            reason=reason,
        )

    async def _run_summary(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        counter_key: str,
        messages: list[Any],
        snapshot_count: int,
    ) -> bool:
        if not messages:
            await self._commit_success(counter_key, snapshot_count=snapshot_count)
            return True

        prompt = self._build_summary_prompt(
            conversation_kind=conversation_kind,
            conversation_id=conversation_id,
            messages=messages,
        )

        try:
            chat_messages: list[dict] = [
                {
                    "role": "system",
                    "content": (
                        "You maintain chat archives for a chat bot. "
                        "Update records incrementally: use patch_archive to append only the new facts, "
                        "never rewrite a whole record unless you are compressing the strict-length summary. "
                        "When you are done, simply respond without tool calls."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            tools = self._tool_definitions if self._tool_definitions else None
            tool_failures = 0
            tool_successes = 0
            # 单次总结的总时长预算：工具轮次再多也不能把一次总结拖成数十分钟。
            deadline = monotonic_seconds() + self._summary_budget_seconds

            for _iteration in range(self._max_tool_rounds):
                remaining = deadline - monotonic_seconds()
                if remaining <= 1.0:
                    if tool_successes:
                        # 预算耗尽但已经写过档案：同上，清账优于重跑。
                        await self._commit_partial_success(
                            counter_key,
                            conversation_kind=conversation_kind,
                            conversation_id=conversation_id,
                            snapshot_count=snapshot_count,
                            message_count=len(messages),
                            tool_successes=tool_successes,
                            round_index=_iteration + 1,
                            reason="budget_exhausted",
                        )
                        return True
                    self._logger.warning(
                        "档案自动总结超出单次时长预算，已中止并进入冷却",
                        conversation_kind=conversation_kind,
                        conversation_id=conversation_id,
                        budget_seconds=int(self._summary_budget_seconds),
                    )
                    await self._defer_after_failure(counter_key)
                    return False
                call_timeout = self._next_call_timeout(remaining)
                try:
                    response = await asyncio.wait_for(
                        self._provider.chat(chat_messages, tools=tools),
                        timeout=call_timeout,
                    )
                except asyncio.TimeoutError:
                    # 超时请求不会返回 usage：这次调用在本地用量统计里完全不存在，
                    # 但服务端已经按实际生成计费。必须留下可排查的痕迹，
                    # 否则账单与「费用统计」的差额永远找不到来源。
                    self._logger.warning(
                        "档案自动总结模型调用超时，本次调用不会计入用量统计",
                        conversation_kind=conversation_kind,
                        conversation_id=conversation_id,
                        timeout_seconds=int(call_timeout),
                        request_chars=_request_chars(chat_messages),
                        messages_count=len(chat_messages),
                        round=_iteration + 1,
                        tool_calls_succeeded=tool_successes,
                    )
                    if tool_successes:
                        await self._commit_partial_success(
                            counter_key,
                            conversation_kind=conversation_kind,
                            conversation_id=conversation_id,
                            snapshot_count=snapshot_count,
                            message_count=len(messages),
                            tool_successes=tool_successes,
                            round_index=_iteration + 1,
                            reason="model_call_timeout",
                        )
                        return True
                    raise
                await self._record_usage(
                    response,
                    conversation_kind=conversation_kind,
                    conversation_id=conversation_id,
                )
                chat_messages.append(response)

                tool_calls = response.get("tool_calls")
                if not tool_calls:
                    break

                if self._tool_executor is None:
                    break

                for tc in tool_calls:
                    name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    try:
                        result = await self._tool_executor(name, args)
                    except Exception as tool_exc:
                        result = f"Tool error: {tool_exc}"
                    if _is_tool_failure(result):
                        tool_failures += 1
                    else:
                        tool_successes += 1
                    chat_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": _bounded_tool_result(result),
                    })
                # 每轮都收紧一次：工具返回是上下文膨胀的唯一来源，
                # 不收紧时后续每一轮都要重发全部历史工具返回。
                _trim_tool_history(chat_messages)

                if tool_failures >= MAX_TOOL_FAILURES:
                    self._logger.warning(
                        "档案自动总结因工具连续失败而中止",
                        conversation_kind=conversation_kind,
                        conversation_id=conversation_id,
                        tool_failures=tool_failures,
                    )
                    break

            if tool_failures and not tool_successes:
                # 全程没有任何工具成功 = 什么都没写进去，保留计数器并进入冷却。
                failures = await self._defer_after_failure(counter_key)
                self._logger.warning(
                    "档案自动总结未写入任何内容，进入冷却后重试",
                    conversation_kind=conversation_kind,
                    conversation_id=conversation_id,
                    tool_failures=tool_failures,
                    consecutive_failures=failures,
                )
                return False

            await self._commit_success(counter_key, snapshot_count=snapshot_count)
            if tool_failures:
                # 部分工具失败仍按"至少写入过内容"清账：档案是增量 append 语义，
                # 重跑同一批消息可能重复写入事实。但必须留下可排查的告警，
                # 否则"模型没处理完就被销账"是完全静默的。
                self._logger.warning(
                    "档案自动总结存在工具失败，已按部分成功清账",
                    conversation_kind=conversation_kind,
                    conversation_id=conversation_id,
                    message_count=len(messages),
                    tool_failures=tool_failures,
                    tool_calls_succeeded=tool_successes,
                )
            self._logger.info(
                "档案已更新",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                message_count=len(messages),
                tool_calls_succeeded=tool_successes,
            )
            return True
        except Exception as exc:
            failures = await self._defer_after_failure(counter_key)
            self._logger.warning(
                "档案自动总结失败，进入冷却后重试",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                error=str(exc) or type(exc).__name__,
                consecutive_failures=failures,
            )

    async def _record_usage(
        self,
        response: Any,
        *,
        conversation_kind: str,
        conversation_id: str,
    ) -> None:
        """把一次总结调用的 token 用量计入统计（统计失败不影响总结流程）。

        档案总结此前完全不记录用量，成本在统计里是黑盒；记录后可在
        「统计与计费」中直接看到 agent:memory 的消耗。
        """
        try:
            extensions = response.get("extensions") if isinstance(response, dict) else None
            usage = (extensions or {}).get("usage") or {}
            input_tokens = int(usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("output_tokens") or 0)
            if not input_tokens and not output_tokens:
                return
            from neobot_app.statistics.tracker import get_usage_tracker

            await get_usage_tracker().record(
                module="agent:memory",
                model_name=getattr(self._provider, "model", "") or "",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_hit_tokens=int(usage.get("cache_hit_tokens") or 0),
                cache_miss_tokens=int(usage.get("cache_miss_tokens") or 0),
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
            )
        except Exception:
            return

    @asynccontextmanager
    async def _counter_lock(self, counter_key: str) -> AsyncIterator[asyncio.Lock]:
        """按 counter_key 分片的计数锁：get-or-create，释放后从注册表回收 key。

        回收时检查注册表中仍是本锁才删除，防止等待者与新建锁并发持有。
        """
        while True:
            lock = self._locks.get(counter_key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[counter_key] = lock
            await lock.acquire()
            if self._locks.get(counter_key) is lock:
                break
            lock.release()
        try:
            yield lock
        finally:
            if self._locks.get(counter_key) is lock:
                del self._locks[counter_key]
            lock.release()

    async def _cached_counter(self, key: str) -> dict[str, Any]:
        """读取计数器状态（带进程内解析缓存，缓存有 TTL）。

        record_message 每条消息都要读一次计数器，而它是一整个 JSON blob
        （间隔 500 条 × 800 字符 ≈ 400KB）：在事件循环上每条消息做一次 DB 读 +
        json.loads 是实实在在的开销。缓存解析结果后，读路径只在缓存过期（或首次）
        时落到 DB；写路径仍然每条都落库，因此崩溃丢失窗口与原来一致。

        缓存必须过期：计数器行的外部修改（模型通过 archive_crud 写
        memory_counter、另一个进程、人工改库）在旧实现里是可见的——永不重读会
        让本进程把陈旧 blob 整块写回，撤消外部的删除/清零。
        """
        now = time.monotonic()
        cached = self._counter_cache.get(key)
        if cached is not None and now - cached[1] < _COUNTER_CACHE_TTL_SECONDS:
            return cached[0]
        fresh = await self._load_counter(key)
        self._counter_cache[key] = (fresh, now)
        return fresh

    async def _load_counter(self, key: str) -> dict[str, Any]:
        item = await self._archive.get(COUNTER_TABLE, key)
        if item is None or not item.value:
            return {"count": 0, "messages": []}
        try:
            data = json.loads(item.value)
        except json.JSONDecodeError:
            return {"count": 0, "messages": []}
        raw_count = data.get("count", 0)
        messages = data.get("messages", [])
        if not isinstance(messages, list):
            messages = []
        try:
            count = int(raw_count)
        except (TypeError, ValueError):
            count = 0
        state: dict[str, Any] = {
            "count": count,
            "messages": [_normalize_counter_message(message) for message in messages],
        }
        # 失败冷却信息随计数器一起保存，缺省不写（保持存量数据的原有形态）。
        failures = data.get("failures")
        retry_after = data.get("retry_after")
        if failures:
            state["failures"] = failures
        if retry_after:
            state["retry_after"] = retry_after
        return state

    async def _save_counter(self, key: str, state: dict[str, Any]) -> None:
        await self._archive.set(
            COUNTER_TABLE,
            key,
            json.dumps(state, ensure_ascii=False),
            ["auto_summary_counter"],
        )
        # 同步缓存，避免下次读到过期内容（尤其是总结成功后的清零）
        self._counter_cache[key] = (state, time.monotonic())

    @staticmethod
    def _counter_state(
        *,
        count: int,
        messages: list[Any],
        failures: Any = None,
        retry_after: Any = None,
    ) -> dict[str, Any]:
        """构造计数器状态；默认值不落盘，保持存量数据的原有形态。"""
        state: dict[str, Any] = {"count": int(count), "messages": list(messages)}
        try:
            failure_count = int(failures)
        except (TypeError, ValueError):
            failure_count = 0
        if failure_count > 0:
            state["failures"] = failure_count
        try:
            retry_at = float(retry_after)
        except (TypeError, ValueError):
            retry_at = 0.0
        if retry_at > 0:
            state["retry_after"] = retry_at
        return state

    @staticmethod
    def _retry_ready(state: dict[str, Any]) -> bool:
        """冷却窗口是否已过；无冷却信息时随时可重试。"""
        try:
            retry_after = float(state.get("retry_after") or 0.0)
        except (TypeError, ValueError):
            return True
        return retry_after <= 0 or epoch_seconds() >= retry_after

    def _begin_summary(self, counter_key: str) -> bool:
        """占位：同一会话同时只允许一次总结(无 await，检查与占位是原子的)。"""
        if counter_key in self._active_summaries:
            return False
        self._active_summaries.add(counter_key)
        return True

    def _end_summary(self, counter_key: str) -> None:
        self._active_summaries.discard(counter_key)

    @staticmethod
    def _backoff_seconds(failures: int) -> float:
        """连续失败次数 → 冷却秒数(指数退避,带上限)。"""
        doublings = min(max(int(failures) - 1, 0), RETRY_BACKOFF_MAX_DOUBLINGS)
        return min(
            RETRY_BACKOFF_BASE_SECONDS * (2**doublings), RETRY_BACKOFF_MAX_SECONDS
        )

    async def _commit_success(self, counter_key: str, *, snapshot_count: int) -> None:
        """总结成功后清账：只移除已总结的消息，保留总结期间新到的消息。

        计数器读路径带 30 秒缓存，这里必须回库读最新状态。用 count 差值而不是
        消息下标计算新到条数：总结期间消息会因 interval 截断把最早的挤掉，
        下标会错位；count 每条消息恰好 +1，差值就是新到条数（截断只影响队列）。
        """
        async with self._counter_lock(counter_key):
            state = await self._load_counter(counter_key)
            messages = list(state.get("messages", []))
            count = int(state.get("count", 0) or 0)
            arrivals = max(0, count - int(snapshot_count))
            kept = messages[-arrivals:] if arrivals else []
            # count 语义 = 缓冲中尚未总结的消息条数：下一次攒满 interval 才总结，
            # 总量与旧行为一致，但不再丢掉总结期间到的那几条。
            await self._save_counter(
                counter_key, {"count": len(kept), "messages": kept}
            )

    async def _defer_after_failure(self, counter_key: str) -> int:
        """总结失败后保留待总结消息,并写入指数退避冷却。

        没有冷却时，计数器一旦越过阈值且总结持续失败，每条新消息都会重跑
        一整轮工具调用循环，把「失败重试」放大成按消息计费的 token 风暴。
        整个读-改-写必须在计数器锁内完成：否则会把总结期间新到消息的追加
        用旧快照覆盖掉（失败路径只允许合并冷却字段，不得改写 count/messages）。
        """
        try:
            async with self._counter_lock(counter_key):
                state = await self._load_counter(counter_key)
                failures = int(state.get("failures", 0) or 0) + 1
                await self._save_counter(
                    counter_key,
                    self._counter_state(
                        count=int(state.get("count", 0) or 0),
                        messages=list(state.get("messages", [])),
                        failures=failures,
                        retry_after=epoch_seconds() + self._backoff_seconds(failures),
                    ),
                )
                return failures
        except Exception:
            return 0

    async def flush_all(self) -> None:
        """关闭时并发刷新所有待处理的计数器。

        遍历每个存在未摘要消息（count > 0）但尚未达到配置间隔的计数器，
        立即触发摘要，确保退出时消息不丢失。
        """
        try:
            items = await self._archive.list(
                COUNTER_TABLE, tags=["auto_summary_counter"], limit=10_000,
            )
        except Exception as exc:
            self._logger.warning(
                "档案自动总结刷新：列举计数器失败",
                error=str(exc),
            )
            return

        semaphore = asyncio.Semaphore(50)

        async def _flush_one(item: Any) -> bool:
            if not item.key or not item.value:
                return False
            try:
                parts = item.key.split(":", 1)
                if len(parts) != 2:
                    return False
                conversation_kind, conversation_id = parts
                if conversation_kind not in ("group", "private"):
                    return False

                state = json.loads(item.value)
                count = int(state.get("count", 0))
                interval = self._interval_for(conversation_kind)
                if count <= 0 or count >= interval:
                    return False

                messages = state.get("messages", [])
                if not messages:
                    return False

                counter_key = item.key
                async with semaphore:
                    # 只在锁内读最新状态并判断条件；总结本身不持锁——
                    # 持锁跑模型会让总结期间每条消息都卡在这把锁上。
                    async with self._counter_lock(counter_key):
                        current = await self._load_counter(counter_key)
                        current_count = int(current.get("count", 0))
                        if current_count <= 0 or current_count >= interval:
                            return False
                        current_messages = list(current.get("messages", []))
                        if not current_messages:
                            return False
                    return await self._summarize_and_reset(
                        conversation_kind=conversation_kind,
                        conversation_id=conversation_id,
                        counter_key=counter_key,
                        messages=current_messages,
                        snapshot_count=current_count,
                    )
            except Exception as exc:
                self._logger.warning(
                    "档案自动总结刷新：处理计数器失败",
                    key=item.key,
                    error=str(exc),
                )
                return False

        results = await asyncio.gather(
            *(_flush_one(item) for item in items),
            return_exceptions=True,
        )
        flushed = sum(1 for r in results if r is True)

        if flushed:
            self._logger.info(
                "关闭时已刷新档案自动总结",
                flushed_count=flushed,
            )

    async def wait_pending_overflow_tasks(self, timeout: float = 30.0) -> None:
        """等待所有在途的「档案超限」压缩任务结束（测试与关闭路径使用）。"""
        pending = [task for task in self._overflow_tasks if not task.done()]
        if pending:
            await asyncio.wait(pending, timeout=timeout)

    # ── 档案超限 → 后台压缩（spec(1)）──

    def _schedule_overflow_compression(self, table_name: str, key: str) -> bool:
        """档案超限触发入口：由 ArchiveMemoryService 在写路径同步调用。

        只做「要不要调度」的判定并立刻返回；真正的压缩在后台任务里跑。这是「先写后
        压缩」的关键：写入工具不会被一次完整的模型调用拖住（max_summary_seconds 量级）。
        单飞复用总结的 _active_summaries 占位（同一 (table_name, key) 同时只跑一个）。
        """
        if self._overflow_max_total_chars <= 0:
            return False
        task_key = self._overflow_task_key(table_name, key)
        if self._provider is None:
            # D3 选项一：AI 不可用时保留原内容、不截断，等下次写入再试。
            self._logger.warning(
                "档案超过存储上限但总结模型不可用，保留原内容等待下次写入重试",
                table_name=table_name,
                key=key,
            )
            return False
        if not self._overflow_retry_ready(task_key):
            self._logger.debug(
                "档案超限压缩处于失败冷却中，跳过本次触发",
                table_name=table_name,
                key=key,
                retry_after=self._overflow_retry_after.get(task_key),
            )
            return False
        if not self._begin_summary(task_key):
            self._logger.debug(
                "档案超限压缩已在执行，跳过本次触发",
                table_name=table_name,
                key=key,
            )
            return False
        try:
            task = asyncio.create_task(
                self._run_overflow_compression(table_name, key, task_key)
            )
        except RuntimeError as exc:
            self._end_summary(task_key)
            self._logger.warning(
                "档案超限压缩无法调度（没有运行中的事件循环）",
                table_name=table_name,
                key=key,
                error=str(exc),
            )
            return False
        self._overflow_tasks.add(task)
        task.add_done_callback(self._overflow_tasks.discard)
        self._logger.info(
            "档案超过存储上限，已调度后台压缩",
            table_name=table_name,
            key=key,
        )
        return True

    async def _run_overflow_compression(
        self, table_name: str, key: str, task_key: str
    ) -> bool:
        """后台压缩任务入口：异常一律转成「保留原文 + 失败退避」，绝不影响写入方。"""
        try:
            return await self._compress_overflow_archive(table_name, key, task_key)
        except Exception as exc:
            failures = self._record_overflow_failure(task_key)
            # 异常同样算失败：清掉服务侧冷却，重试节奏交给这里的失败退避，
            # 否则一次异常会把「下次写入再试」压成 600 秒的静默。
            self._clear_overflow_cooldown(table_name, key)
            self._logger.warning(
                "档案超限压缩失败，保留原内容等待下次写入重试",
                table_name=table_name,
                key=key,
                error=str(exc) or type(exc).__name__,
                consecutive_failures=failures,
            )
            return False
        finally:
            self._end_summary(task_key)

    async def _compress_overflow_archive(
        self, table_name: str, key: str, task_key: str
    ) -> bool:
        """对单条超限档案跑一轮「压缩」工具循环，并把结果落库。

        复用总结的预算与保护：max_tool_rounds / max_summary_seconds / 单次调用超时 /
        用量统计 / 工具连续失败熔断 / 失败指数退避。
        """
        limit = self._overflow_max_total_chars
        if limit <= 0:
            return True
        item = await self._archive.get(table_name, key)
        value = (item.value or "") if item is not None else ""
        if not value:
            return False
        if len(value) <= limit:
            # 已被别的路径压缩过（例如同一批写入共享一次压缩），无需再跑模型。
            return True

        prompt = self._build_overflow_compression_prompt(
            table_name=table_name,
            key=key,
            value=value,
            limit=limit,
        )
        tool_successes, tool_failures = await self._run_overflow_tool_loop(
            prompt, table_name=table_name, key=key
        )

        after = await self._archive.get(table_name, key)
        remaining = len((after.value if after is not None else "") or "")
        if tool_successes <= 0 or remaining > limit:
            failures = self._record_overflow_failure(task_key)
            # 压缩没成功 → 清掉服务侧冷却，让「下次写入再试」不被 600 秒冷却掩盖；
            # 真正的重试节奏由这里的失败退避控制。
            self._clear_overflow_cooldown(table_name, key)
            self._logger.warning(
                "档案超限压缩未压到上限内，保留原内容等待下次写入重试",
                table_name=table_name,
                key=key,
                chars_before=len(value),
                chars_after=remaining,
                max_total_chars=limit,
                tool_calls_succeeded=tool_successes,
                tool_failures=tool_failures,
                consecutive_failures=failures,
            )
            return False

        self._overflow_failures.pop(task_key, None)
        self._overflow_retry_after.pop(task_key, None)
        self._logger.info(
            "档案超限压缩完成",
            table_name=table_name,
            key=key,
            chars_before=len(value),
            chars_after=remaining,
            max_total_chars=limit,
        )
        return True

    async def _run_overflow_tool_loop(
        self, prompt: str, *, table_name: str, key: str
    ) -> tuple[int, int]:
        """压缩专用的模型工具循环，返回 (成功工具调用数, 失败工具调用数)。"""
        chat_messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "You compress a single chat archive record that exceeded its storage "
                    "limit. Rewrite it with the archive tools: keep every durable fact, "
                    "drop redundancy. When you are done, respond without tool calls."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        tools = self._tool_definitions if self._tool_definitions else None
        tool_failures = 0
        tool_successes = 0
        deadline = monotonic_seconds() + self._summary_budget_seconds

        for iteration in range(self._max_tool_rounds):
            remaining = deadline - monotonic_seconds()
            if remaining <= 1.0:
                self._logger.warning(
                    "档案超限压缩超出单次时长预算，已中止",
                    table_name=table_name,
                    key=key,
                    budget_seconds=int(self._summary_budget_seconds),
                )
                break
            call_timeout = self._next_call_timeout(remaining)
            try:
                response = await asyncio.wait_for(
                    self._provider.chat(chat_messages, tools=tools),
                    timeout=call_timeout,
                )
            except asyncio.TimeoutError:
                self._logger.warning(
                    "档案超限压缩模型调用超时，本次调用不会计入用量统计",
                    table_name=table_name,
                    key=key,
                    timeout_seconds=int(call_timeout),
                    request_chars=_request_chars(chat_messages),
                    round=iteration + 1,
                )
                break
            await self._record_usage(
                response,
                conversation_kind="archive_overflow",
                conversation_id=f"{table_name}:{key}",
            )
            chat_messages.append(response)

            tool_calls = response.get("tool_calls")
            if not tool_calls or self._tool_executor is None:
                break
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}
                try:
                    result = await self._tool_executor(name, args)
                except Exception as tool_exc:
                    result = f"Tool error: {tool_exc}"
                if _is_tool_failure(result):
                    tool_failures += 1
                else:
                    tool_successes += 1
                chat_messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": _bounded_tool_result(result),
                })
            _trim_tool_history(chat_messages)

            if tool_failures >= MAX_TOOL_FAILURES:
                self._logger.warning(
                    "档案超限压缩因工具连续失败而中止",
                    table_name=table_name,
                    key=key,
                    tool_failures=tool_failures,
                )
                break
        return tool_successes, tool_failures

    def _build_overflow_compression_prompt(
        self, *, table_name: str, key: str, value: str, limit: int
    ) -> str:
        """构造「压缩单条超限档案」的提示词（要求保留事实、只丢冗余）。"""
        current_time = get_current_time_and_lunar_date()
        return (
            f"Current time: {current_time}\n"
            f"The archive record below exceeded its storage limit and must be compressed now.\n"
            f"table_name: {table_name}\n"
            f"key: {key}\n"
            f"current_chars: {len(value)}\n"
            f"hard_limit: {limit}\n"
            f"Compression rules:\n"
            f"- Call archive_crud__save_archive with table_name='{table_name}', "
            f"key='{key}' and the FULL compressed record.\n"
            f"- Keep every durable fact (names, dates, numbers, preferences, decisions, "
            f"unresolved items); merge duplicates and drop repetition/verbose wording.\n"
            f"- Never invent facts that are not in the original record.\n"
            f"- The compressed record MUST be <= {limit} characters; "
            f"aim for roughly {max(limit // 2, 1)} characters.\n"
            f"- Do not touch any other archive record.\n"
            f"\nRecord to compress:\n{_bounded_archive_text(value)}"
        )

    @staticmethod
    def _overflow_task_key(table_name: str, key: str) -> str:
        return f"overflow:{table_name}:{key}"

    def _overflow_retry_ready(self, task_key: str) -> bool:
        retry_after = self._overflow_retry_after.get(task_key, 0.0)
        return retry_after <= 0.0 or epoch_seconds() >= retry_after

    def _record_overflow_failure(self, task_key: str) -> int:
        """记录一次压缩失败并写入指数退避（复用计数器的退避算法）。"""
        failures = int(self._overflow_failures.get(task_key, 0)) + 1
        self._overflow_failures[task_key] = failures
        self._overflow_retry_after[task_key] = epoch_seconds() + self._backoff_seconds(failures)
        self._prune_overflow_backoff()
        return failures

    def _prune_overflow_backoff(self) -> None:
        """退避表只保留未过期条目，避免长期运行后无界增长。"""
        if len(self._overflow_retry_after) <= MAX_OVERFLOW_BACKOFF_ENTRIES:
            return
        now = epoch_seconds()
        for task_key, retry_after in list(self._overflow_retry_after.items()):
            if retry_after <= now:
                self._overflow_retry_after.pop(task_key, None)
                self._overflow_failures.pop(task_key, None)

    def _clear_overflow_cooldown(self, table_name: str, key: str) -> None:
        """压缩失败后清除服务侧冷却，让下次写入能立刻再试。"""
        clearer = getattr(self._archive, "clear_overflow_cooldown", None)
        if callable(clearer):
            try:
                clearer(table_name, key)
            except Exception:
                return

    async def close(self) -> None:
        if self._provider is not None:
            await self._provider.close()

    def _interval_for(self, conversation_kind: str) -> int:
        trigger = getattr(getattr(self._config, "agent", None), "memory", None)
        trigger = getattr(trigger, "trigger", None)
        value = (
            getattr(trigger, "group_interval", 0)
            if conversation_kind == "group"
            else getattr(trigger, "private_interval", 0)
        )
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _counter_key(conversation_kind: str, conversation_id: str) -> str:
        return f"{conversation_kind}:{conversation_id}"

    def _summary_limits(self) -> tuple[int, int]:
        """返回 (个人 summary 上限, 群聊 summary 上限)。"""
        archive = getattr(
            getattr(getattr(self._config, "agent", None), "memory", None),
            "archive",
            None,
        )
        user_limit = 500
        group_limit = 1500
        if archive is not None:
            raw_user = getattr(archive, "max_chars", None)
            if isinstance(raw_user, int) and raw_user > 0:
                user_limit = raw_user
            raw_group = getattr(archive, "group_profile_max_chars", None)
            if isinstance(raw_group, int) and raw_group > 0:
                group_limit = raw_group
        return user_limit, group_limit

    def _render_recent_messages(self, messages: list[Any]) -> tuple[str, list[int]]:
        """渲染待总结消息：每条截断到 prompt_snippet_chars，返回 (文本, 被截断的序号)。

        截断的消息可由模型用 archive_crud__read_pending_messages 按需读取全文，
        避免把超长消息全文注入提示词。
        """
        snippet_chars = self._prompt_snippet_chars
        lines: list[str] = []
        truncated: list[int] = []
        for index, message in enumerate(messages, start=1):
            item = _normalize_counter_message(message)
            text = item["text"]
            if snippet_chars > 0 and len(text) > snippet_chars:
                text = f"{text[:snippet_chars]}…"
                truncated.append(index)
            lines.append(f"[{index}] {_format_sender(item)}: {text}")
        return "\n".join(lines), truncated

    # ── 提示词规范化：实现 agent_prompt_parts() 即被分析页自动收集 ──

    agent_name = "档案自动总结 Agent"
    agent_note = "空会话 + 群聊模板；运行时还会按会话追加用户画像/好感度/条目归档等指令"

    def agent_prompt_parts(self) -> list[tuple[str, str, str]]:
        from neobot_app.analysis.prompt_analysis import tools_to_text

        try:
            prompt = self._build_summary_prompt(
                conversation_kind="group", conversation_id="0", messages=[]
            )
        except Exception as exc:
            prompt = f"（装配失败: {type(exc).__name__}: {exc}）"
        parts = [("总结指令（群聊 · 空会话）", "system", prompt)]
        definitions = list(getattr(self, "_tool_definitions", []) or [])
        if definitions:
            parts.append(
                (f"工具定义（{len(definitions)} 个）", "tools", tools_to_text(definitions))
            )
        return parts

    def _build_summary_prompt(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        messages: list[Any],
    ) -> str:
        current_time = get_current_time_and_lunar_date()
        kind_label = (
            f"群聊(群号:{conversation_id})"
            if conversation_kind == "group"
            else f"私聊(QQ号:{conversation_id})"
        )
        conversation_key = self._counter_key(conversation_kind, conversation_id)
        recent, truncated_indices = self._render_recent_messages(messages)

        user_limit, group_limit = self._summary_limits()
        if conversation_kind == "group":
            summary_table = "group_summary"
            full_table = "group_profile"
            summary_limit = group_limit
            content_scope = (
                "the group's stable traits: members, atmosphere, inside jokes, "
                "common topics, group norms, recurring events"
            )
        else:
            summary_table = "user_summary"
            full_table = "user_profile"
            summary_limit = user_limit
            content_scope = (
                "the user's stable traits: preferences, interests, hobbies, personality, "
                "important life events, relationships, recurring concerns"
            )

        profile_instruction = (
            f"\nUpdate the archive records INCREMENTALLY with the available tools. "
            f"Never resend a whole record unless you are explicitly compressing it.\n"
            f"1. '{full_table}' (key='{conversation_id}') — the full long-term archive "
            f"(unabridged, keeps growing).\n"
            f"   - New stable facts: archive_crud__patch_archive with op='append'. "
            f"Send ONLY the new lines; do NOT read the record first and do NOT rewrite it.\n"
            f"   - Existing content that must be corrected or merged: locate it with "
            f"archive_crud__read_archive (mode='outline'), read only the relevant page "
            f"(offset, negative offset reads from the tail), then edit it with "
            f"patch_archive (op='replace'/'delete').\n"
            f"   - save_archive on this table is forbidden unless the record must be "
            f"fully rewritten.\n"
            f"2. '{summary_table}' (key='{conversation_id}') — the strict-length summary.\n"
            f"   Structure: write an OVERALL summary of {content_scope} FIRST at the very top, "
            f"then summarize the recent content item by item (chronological order).\n"
            f"   HARD LIMIT: {summary_limit} characters. This is the ONLY record you may "
            f"rewrite with archive_crud__save_archive, and only when it actually needs to "
            f"change. If it is already at/near the limit, compress it (merge into a tighter "
            f"overall summary + chronological digest); NEVER exceed the limit.\n"
        )
        favorability_instruction = (
            f"\nFor each active speaker in the recent messages, evaluate their behavior "
            f"(attitude, interaction quality, cooperativeness, etc.) and use "
            f"favorability__update_favorability to adjust their favorability. "
            f"Positive behavior increases favorability, negative behavior decreases it. "
            f"Each change must be within ±{self._favorability_max_change}. "
            f"Only adjust for users who clearly showed notable behavior worth recording.\n"
        ) if conversation_kind == "group" else (
            f"\nEvaluate the user's behavior in the recent messages (attitude, interaction "
            f"quality, cooperativeness, etc.) and use favorability__update_favorability "
            f"(user_id='{conversation_id}') to adjust their favorability. "
            f"Positive behavior increases favorability, negative behavior decreases it. "
            f"Change must be within ±{self._favorability_max_change}. "
            f"Only adjust if the user clearly showed notable behavior worth recording.\n"
        )

        item_instruction = ""
        if self._item_archive_enabled:
            item_instruction = (
                f"\n3. '{self._item_archive_table}' — items, events, or topics worth keeping. "
                f"Use descriptive keyword keys joined with underscores (e.g. 'game_原神' or "
                f"'event_2026春游'). For a new item call archive_crud__patch_archive "
                f"(op='append') with a compact note — no read needed. Only if the item "
                f"already exists, read it first and then patch or merge it.\n"
            )
        truncation_note = ""
        if truncated_indices:
            shown = ",".join(str(index) for index in truncated_indices[:20])
            truncation_note = (
                f"\nMessage texts marked with … were truncated (indices: {shown}"
                f"{'...' if len(truncated_indices) > 20 else ''}). "
                f"If the full text matters, call archive_crud__read_pending_messages with "
                f"conversation_key='{conversation_key}' and indices=[...]; "
                f"only fetch what you actually need.\n"
            )
        overflow_note = ""
        overflow_limit = getattr(self, "_overflow_max_total_chars", 0)
        if overflow_limit > 0:
            overflow_note = (
                f"\nArchive records have a storage cap of {overflow_limit} characters per record. "
                f"Keep appends compact; a record that exceeds the cap is compressed automatically "
                f"in the background, so never rewrite a whole record just to shrink it yourself.\n"
            )
        return (
            f"Current time: {current_time}\n"
            f"Conversation: {kind_label}\n"
            f"conversation_key: {conversation_key}\n"
            f"The messages below were generated shortly before this time. "
            f"Use the available tools to update the archive records based on these messages.\n"
            f"{overflow_note}{profile_instruction}{favorability_instruction}{item_instruction}"
            f"{truncation_note}"
            f"\nRecent messages (each line is '[index] sender: text'):\n{recent}"
        )

def _positive_int_or_zero(value: Any) -> int:
    """配置读取：非负整数上限；None/非法值/负数一律视为 0（禁用）。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _cooldown_seconds_or_default(value: Any, default: float = DEFAULT_OVERFLOW_COOLDOWN_SECONDS) -> float:
    """配置读取：冷却秒数；None/非法值回落默认值，0 表示不冷却。"""
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, parsed)


def _bounded_archive_text(value: str) -> str:
    """限制注入压缩提示词的档案长度：超长时保留首尾，中间省略。"""
    if len(value) <= MAX_OVERFLOW_PROMPT_CHARS:
        return value
    head_chars = MAX_OVERFLOW_PROMPT_CHARS // 2
    tail_chars = MAX_OVERFLOW_PROMPT_CHARS - head_chars
    return f"{value[:head_chars]}{_ARCHIVE_PROMPT_OMITTED}{value[-tail_chars:]}"


def _request_chars(messages: list[Any]) -> int:
    """估算一次请求的可见字符数(图片按固定额度计，不把 base64 当文本)。"""
    total = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in {"image_url", "image", "file"}:
                    total += 3072
                else:
                    total += len(str(part.get("text", "")))
        tool_calls = message.get("tool_calls")
        if isinstance(tool_calls, list):
            total += sum(len(str(item)) for item in tool_calls)
    return total


def _bounded_tool_result(result: Any) -> str:
    """限制单条工具返回的字符数。

    read_pending_messages / list_archive / read_archive 都会返回大块内容，
    而这些内容会被追加进 chat_messages 并在之后每一轮重新发送；
    不设上限时一次总结就能把上下文顶到几十万 token。
    """
    text = str(result or "")
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return text
    return text[:MAX_TOOL_RESULT_CHARS] + _TOOL_TRUNCATED_MARKER


def _trim_tool_history(chat_messages: list[dict]) -> None:
    """从最新往旧保留工具返回，超出总量预算的早期工具返回替换为占位符。

    直接改写在原地进行，system / user / assistant 消息不受影响。
    """
    budget = MAX_TOOL_RESULT_TOTAL_CHARS
    for message in reversed(chat_messages):
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        content = str(message.get("content") or "")
        if content == _TOOL_DROPPED_MARKER:
            continue
        if budget - len(content) >= 0:
            budget -= len(content)
            continue
        message["content"] = _TOOL_DROPPED_MARKER


def _is_tool_failure(result: Any) -> bool:
    """判断工具结果是否属于失败（未知工具/执行异常），用于中止重试风暴。"""
    text = str(result or "")
    return any(marker in text for marker in _TOOL_FAILURE_MARKERS)


def _normalize_message_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _normalize_counter_message(message: Any) -> dict[str, str]:
    if isinstance(message, dict):
        return {
            "sender_id": str(message.get("sender_id") or ""),
            "sender_name": str(message.get("sender_name") or ""),
            "text": str(message.get("text") or ""),
        }
    return {"sender_id": "", "sender_name": "", "text": str(message)}


def _format_sender(item: dict[str, str]) -> str:
    sender_bits = []
    if item["sender_name"]:
        sender_bits.append(item["sender_name"])
    if item["sender_id"]:
        sender_bits.append(f"QQ:{item['sender_id']}")
    return " / ".join(sender_bits) or "未知发送者"


def _format_counter_message(message: Any) -> str:
    item = _normalize_counter_message(message)
    return f"{_format_sender(item)}: {item['text']}"
