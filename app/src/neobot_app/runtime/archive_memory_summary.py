"""对实时聊天消息进行档案记忆自动摘要。"""

from __future__ import annotations

import asyncio
import json
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

# 总结失败后的冷却窗口：失败一次至少要等这么久才会再次尝试。
# 没有它时，计数器一旦越过间隔且总结持续失败，每条新消息都会重跑一整轮工具循环，
# 形成「每条消息 = 一次 60 秒超时」的 token 风暴。
RETRY_BACKOFF_BASE_SECONDS = 60.0
# 连续失败时的退避上限，避免长时间完全不总结。
RETRY_BACKOFF_MAX_SECONDS = 900.0
# 退避翻倍的最大次数(1→2→4→8→16 倍)。
RETRY_BACKOFF_MAX_DOUBLINGS = 4
# 单次总结的总时长预算(秒)：超过即中止本轮并进入冷却，
# 避免多轮工具调用把一次总结拖成数十分钟。
DEFAULT_SUMMARY_BUDGET_SECONDS = 180.0
# 单次总结内层模型调用的超时(秒)，同时也是单轮上限。
DEFAULT_SUMMARY_CALL_TIMEOUT_SECONDS = 60.0
# 单条工具返回写入上下文的最大字符数。read_pending_messages 会返回 500 条消息全文，
# list_archive 会返回整条档案 value，原样追加会让之后每一轮都把这几百 KB 重发一遍。
MAX_TOOL_RESULT_CHARS = 4000
# 整个总结过程中保留的工具返回总量上限；超出后丢弃最早的工具返回。
MAX_TOOL_RESULT_TOTAL_CHARS = 60_000
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
    ) -> None:
        self._archive = archive_memory_service
        self._provider = provider
        self._config = config
        self._logger = logger or NullLogger()
        self._locks: dict[str, asyncio.Lock] = {}
        # 正在执行总结的会话键集合。同一会话同时只允许一次总结，
        # 否则消息持续到来时任务会排成长队，每个都跑满一次模型超时。
        self._active_summaries: set[str] = set()
        self._tool_definitions = tool_definitions or []
        self._tool_executor = tool_executor
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
        self._item_archive_enabled: bool = bool(item_archive_config.enabled) if item_archive_config else True
        self._item_archive_table: str = (
            str(item_archive_config.table_name).strip() or ITEM_ARCHIVE_TABLE
        ) if item_archive_config else ITEM_ARCHIVE_TABLE

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
        # 计数器读写只占锁的极短时间：总结本身在锁外执行，
        # 否则消息持续到来时每个调用都会卡在锁上排成一长队。
        async with self._counter_lock(counter_key):
            state = await self._load_counter(counter_key)
            messages = list(state.get("messages", []))
            messages.append(
                {
                    "sender_id": str(sender_id or ""),
                    "sender_name": str(sender_name or ""),
                    "text": clean_text[:MAX_STORED_MESSAGE_CHARS],
                }
            )
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
        # 但不会为每条消息都排一个「必然超时」的任务。
        if not self._begin_summary(counter_key):
            self._logger.debug(
                "档案自动总结已在执行，跳过本次调度",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
            )
            return

        try:
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
            )
        finally:
            self._end_summary(counter_key)

    async def _summarize_and_reset(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        counter_key: str,
        messages: list[Any],
    ) -> bool:
        """执行一次总结。返回 True 表示计数器已复位（含空消息），False 表示保留待重试。"""
        if not messages:
            await self._save_counter(counter_key, {"count": 0, "messages": []})
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
                    self._logger.warning(
                        "档案自动总结超出单次时长预算，已中止并进入冷却",
                        conversation_kind=conversation_kind,
                        conversation_id=conversation_id,
                        budget_seconds=int(self._summary_budget_seconds),
                    )
                    await self._defer_after_failure(counter_key)
                    return False
                call_timeout = min(DEFAULT_SUMMARY_CALL_TIMEOUT_SECONDS, remaining)
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
                    )
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
                # 全程没有任何工具成功 = 什么都没写进去，保留计数器待下次重试。
                failures = await self._defer_after_failure(counter_key)
                self._logger.warning(
                    "档案自动总结未写入任何内容，进入冷却后重试",
                    conversation_kind=conversation_kind,
                    conversation_id=conversation_id,
                    tool_failures=tool_failures,
                    consecutive_failures=failures,
                )
                return False

            await self._save_counter(counter_key, {"count": 0, "messages": []})
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
        # failures / retry_after 必须原样保留，否则失败冷却会随每次读取丢失。
        return self._counter_state(
            count=count,
            messages=[_normalize_counter_message(message) for message in messages],
            failures=data.get("failures"),
            retry_after=data.get("retry_after"),
        )

    async def _save_counter(self, key: str, state: dict[str, Any]) -> None:
        await self._archive.set(
            COUNTER_TABLE,
            key,
            json.dumps(state, ensure_ascii=False),
            ["auto_summary_counter"],
        )

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

    async def _defer_after_failure(self, counter_key: str) -> int:
        """总结失败后保留待总结消息,并写入指数退避冷却。

        没有冷却时，计数器一旦越过阈值且总结持续失败，每条新消息都会重跑
        一整轮工具调用循环，把「失败重试」放大成按消息计费的 token 风暴。
        """
        try:
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
                # 失败冷却期内不在关机时强行重跑：待总结消息留在计数器里，
                # 下次启动后继续累计，避免关机瞬间再触发一次完整总结。
                if not self._retry_ready(state):
                    return False

                messages = state.get("messages", [])
                if not messages:
                    return False

                counter_key = item.key
                async with semaphore:
                    async with self._counter_lock(counter_key):
                        current = await self._load_counter(counter_key)
                        current_count = int(current.get("count", 0))
                        if current_count <= 0 or current_count >= interval:
                            return False
                        current_messages = current.get("messages", [])
                        if not current_messages:
                            return False
                        return await self._summarize_and_reset(
                            conversation_kind=conversation_kind,
                            conversation_id=conversation_id,
                            counter_key=counter_key,
                            messages=current_messages,
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
        return (
            f"Current time: {current_time}\n"
            f"Conversation: {kind_label}\n"
            f"conversation_key: {conversation_key}\n"
            f"The messages below were generated shortly before this time. "
            f"Use the available tools to update the archive records based on these messages.\n"
            f"{profile_instruction}{favorability_instruction}{item_instruction}"
            f"{truncation_note}"
            f"\nRecent messages (each line is '[index] sender: text'):\n{recent}"
        )

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
