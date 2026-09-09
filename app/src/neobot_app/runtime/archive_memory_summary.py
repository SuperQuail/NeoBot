"""对实时聊天消息进行档案记忆自动摘要。"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncIterator

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_memory import ArchiveMemoryService

from neobot_app.time_context import get_current_time_and_lunar_date

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
                "archive auto summary skipped because provider is unavailable",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
            )
            return

        clean_text = _normalize_message_text(message_text)
        if not clean_text:
            return

        counter_key = self._counter_key(conversation_kind, conversation_id)
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

            state = {"count": count, "messages": messages[-max(interval, 1) :]}
            await self._save_counter(counter_key, state)

            if count < interval:
                return

            await self._summarize_and_reset(
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                counter_key=counter_key,
                messages=state["messages"],
            )

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

            for _iteration in range(self._max_tool_rounds):
                response = await asyncio.wait_for(
                    self._provider.chat(chat_messages, tools=tools),
                    timeout=60.0,
                )
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
                        "content": str(result),
                    })

                if tool_failures >= MAX_TOOL_FAILURES:
                    self._logger.warning(
                        "archive auto summary aborted after repeated tool failures",
                        conversation_kind=conversation_kind,
                        conversation_id=conversation_id,
                        tool_failures=tool_failures,
                    )
                    break

            if tool_failures and not tool_successes:
                # 全程没有任何工具成功 = 什么都没写进去，保留计数器待下次重试。
                self._logger.warning(
                    "archive auto summary wrote nothing, counter preserved for retry",
                    conversation_kind=conversation_kind,
                    conversation_id=conversation_id,
                    tool_failures=tool_failures,
                )
                return False

            await self._save_counter(counter_key, {"count": 0, "messages": []})
            self._logger.info(
                "archive profiles updated",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                message_count=len(messages),
                tool_calls_succeeded=tool_successes,
            )
            return True
        except Exception as exc:
            self._logger.warning(
                "archive auto summary failed, counter preserved for retry",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                error=str(exc),
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
        return {
            "count": count,
            "messages": [_normalize_counter_message(message) for message in messages],
        }

    async def _save_counter(self, key: str, state: dict[str, Any]) -> None:
        await self._archive.set(
            COUNTER_TABLE,
            key,
            json.dumps(state, ensure_ascii=False),
            ["auto_summary_counter"],
        )

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
                "archive auto summary flush: failed to list counters",
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
                    "archive auto summary flush: failed for counter",
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
                "archive auto summary flushed on shutdown",
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
