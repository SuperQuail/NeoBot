"""Automatic archive-memory summarization for live chat messages."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_memory import ArchiveMemoryService

from neobot_app.time_context import get_current_time_and_lunar_date

if TYPE_CHECKING:
    from neobot_app.config.schemas.bot import AgentMemoryItemArchive, BotConfig
    from neobot_chat.providers.base import Provider


COUNTER_TABLE = "memory_counter"
ITEM_ARCHIVE_TABLE = "item_archive"
MAX_STORED_MESSAGE_CHARS = 800


class ArchiveMemoryAutoSummaryService:
    """Count live messages and periodically update archive profiles via tools."""

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
        """Record one live message and trigger summarization at the configured interval."""
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
        lock = self._locks.setdefault(counter_key, asyncio.Lock())
        async with lock:
            state = await self._load_counter(counter_key)
            # 防止残留的高计数（如之前摘要失败未复位）导致一条消息就触发
            if int(state.get("count", 0)) >= interval:
                state = {"count": 0, "messages": []}
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
    ) -> None:
        if not messages:
            await self._save_counter(counter_key, {"count": 0, "messages": []})
            return

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
                        "Use the available tools to update archive records based on the recent messages. "
                        "When you are done, simply respond without tool calls."
                    ),
                },
                {"role": "user", "content": prompt},
            ]
            tools = self._tool_definitions if self._tool_definitions else None

            for _iteration in range(50):
                response = await asyncio.wait_for(
                    self._provider.chat(chat_messages, tools=tools),
                    timeout=60.0,
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
                    chat_messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": str(result),
                    })

            await self._save_counter(counter_key, {"count": 0, "messages": []})
            self._logger.info(
                "archive profiles updated",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                message_count=len(messages),
            )
        except Exception as exc:
            self._logger.warning(
                "archive auto summary failed",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                error=str(exc),
            )
            await self._save_counter(counter_key, {"count": 0, "messages": []})

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
        """Flush all pending counters on shutdown concurrently.

        Iterates every counter that has unsummarized messages (count > 0) but
        hasn't reached the configured interval yet, and triggers summarisation
        immediately so no messages are lost on exit.
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
                lock = self._locks.setdefault(counter_key, asyncio.Lock())
                async with semaphore:
                    async with lock:
                        current = await self._load_counter(counter_key)
                        current_count = int(current.get("count", 0))
                        if current_count <= 0 or current_count >= interval:
                            return False
                        current_messages = current.get("messages", [])
                        if not current_messages:
                            return False
                        await self._summarize_and_reset(
                            conversation_kind=conversation_kind,
                            conversation_id=conversation_id,
                            counter_key=counter_key,
                            messages=current_messages,
                        )
                        return True
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
        recent = "\n".join(f"- {_format_counter_message(message)}" for message in messages)

        if conversation_kind == "group":
            profile_instruction = (
                f"\nUse archive_crud__read_archive to read the current 'group_profile' "
                f"(key='{conversation_id}'), then use archive_crud__save_archive to update it "
                f"with stable facts you've learned from the recent messages: group interests, "
                f"atmosphere, inside jokes, common topics, member dynamics, group norms, "
                f"recurring events, etc. Merge new findings into the existing profile. "
                f"Keep it compact and factual.\n"
            )
            favorability_instruction = (
                f"\nFor each active speaker in the recent messages, evaluate their behavior "
                f"(attitude, interaction quality, cooperativeness, etc.) and use "
                f"favorability__update_favorability to adjust their favorability. "
                f"Positive behavior increases favorability, negative behavior decreases it. "
                f"Each change must be within ±{self._favorability_max_change}. "
                f"Only adjust for users who clearly showed notable behavior worth recording.\n"
            )
        else:
            profile_instruction = (
                f"\nUse archive_crud__read_archive to read the current 'user_profile' "
                f"(key='{conversation_id}'), then use archive_crud__save_archive to update it "
                f"with stable facts you've learned from the recent messages: their preferences, "
                f"interests, hobbies, personality traits, important life events, relationships, "
                f"recurring concerns, etc. Merge new findings into the existing profile. "
                f"Keep it compact and factual.\n"
            )
            favorability_instruction = (
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
                f"\nAlso, identify any items, events, or topics discussed that are worth "
                f"recording in the '{self._item_archive_table}' archive. "
                f"For each item, use descriptive keywords as the key (joined with underscores, "
                f"e.g. 'game_原神' or 'event_2026春游'), and write a compact summary of what was "
                f"learned or discussed about that item/event. "
                f"Use archive_crud__read_archive first to get any existing entry, then use "
                f"archive_crud__save_archive to merge.\n"
            )
        return (
            f"Current time: {current_time}\n"
            f"Conversation: {kind_label}\n"
            f"The messages below were generated shortly before this time. "
            f"Use the available tools to update the archive records based on these messages.\n"
            f"{profile_instruction}{favorability_instruction}{item_instruction}\n"
            f"Recent messages:\n{recent}"
        )

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


def _format_counter_message(message: Any) -> str:
    item = _normalize_counter_message(message)
    sender_bits = []
    if item["sender_name"]:
        sender_bits.append(item["sender_name"])
    if item["sender_id"]:
        sender_bits.append(f"QQ:{item['sender_id']}")
    sender = " / ".join(sender_bits) or "未知发送者"
    return f"{sender}: {item['text']}"
