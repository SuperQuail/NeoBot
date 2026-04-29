"""Automatic archive-memory summarization for live chat messages."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_memory import ArchiveMemoryService

from neobot_app.favorability import favorability_to_text
from neobot_app.time_context import get_current_time_and_lunar_date

if TYPE_CHECKING:
    from neobot_app.config.schemas.bot import BotConfig
    from neobot_chat.providers.base import Provider
    from neobot_chat.tools.registry import AgentRegistry


COUNTER_TABLE = "memory_counter"
GROUP_SUMMARY_TABLE = "group_summary"
PRIVATE_SUMMARY_TABLE = "private_summary"
SUMMARY_TAGS = ["auto_summary"]
MAX_STORED_MESSAGE_CHARS = 800


class ArchiveMemoryAutoSummaryService:
    """Count live messages and periodically write merged archive summaries."""

    def __init__(
        self,
        *,
        archive_memory_service: ArchiveMemoryService,
        provider: "Provider | None",
        config: "BotConfig",
        agent_registry: "AgentRegistry | None" = None,
        logger: Logger | None = None,
    ) -> None:
        self._archive = archive_memory_service
        self._provider = provider
        self._config = config
        self._agent_registry = agent_registry
        self._logger = logger or NullLogger()
        self._locks: dict[str, asyncio.Lock] = {}
        fav_cfg = getattr(getattr(getattr(config, "agent", None), "memory", None), "favorability", None)
        self._favorability_max_change: int = int(getattr(fav_cfg, "max_change_per_summary", 5) or 5)
        self._favorability_min: int = int(getattr(fav_cfg, "min_value", -1000) or -1000)
        self._favorability_max: int = int(getattr(fav_cfg, "max_value", 1000) or 1000)

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
        has_memory_agent = self._agent_registry is not None and "memory" in self._agent_registry.names
        if self._provider is None and not has_memory_agent:
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

        if self._agent_registry is not None and "memory" in self._agent_registry.names:
            await self._delegate_memory_agent_and_reset(
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                counter_key=counter_key,
                messages=messages,
            )
            return

        summary_table = self._summary_table_for(conversation_kind)
        existing = await self._archive.get(summary_table, conversation_id)
        old_summary = existing.value.strip() if existing is not None and existing.value else ""
        prompt = self._build_summary_prompt(
            conversation_kind=conversation_kind,
            conversation_id=conversation_id,
            old_summary=old_summary,
            messages=messages,
        )

        try:
            response = await asyncio.wait_for(
                self._provider.chat(
                    [
                        {
                            "role": "system",
                            "content": (
                                "You maintain concise long-term archive summaries for a chat bot. "
                                "Return only the updated summary text."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ]
                ),
                timeout=60.0,
            )
            new_summary = _extract_response_text(response).strip()
            if not new_summary:
                raise ValueError("summary provider returned empty content")
            await self._archive.set(summary_table, conversation_id, new_summary, SUMMARY_TAGS)
            await self._save_counter(counter_key, {"count": 0, "messages": []})
            self._logger.info(
                "archive auto summary saved",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                summary_table=summary_table,
                message_count=len(messages),
            )
        except Exception as exc:
            self._logger.warning(
                "archive auto summary failed",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                error=str(exc),
            )

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

    async def _delegate_memory_agent_and_reset(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        counter_key: str,
        messages: list[Any],
    ) -> None:
        task = self._build_agent_task(
            conversation_kind=conversation_kind,
            conversation_id=conversation_id,
            messages=messages,
        )
        try:
            result = await self._agent_registry.delegate(
                agent="memory",
                task=task,
                session_id=f"auto:{conversation_kind}:{conversation_id}",
            )
            await self._save_counter(counter_key, {"count": 0, "messages": []})
            self._logger.info(
                "memory agent auto processing completed",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                message_count=len(messages),
                result=str(result),
            )
        except Exception as exc:
            self._logger.warning(
                "memory agent auto processing failed",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                error=str(exc),
            )

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

    @staticmethod
    def _summary_table_for(conversation_kind: str) -> str:
        return GROUP_SUMMARY_TABLE if conversation_kind == "group" else PRIVATE_SUMMARY_TABLE

    @staticmethod
    def _build_summary_prompt(
        *,
        conversation_kind: str,
        conversation_id: str,
        old_summary: str,
        messages: list[Any],
    ) -> str:
        current_time = get_current_time_and_lunar_date()
        kind_label = (
            f"群聊(群号:{conversation_id})"
            if conversation_kind == "group"
            else f"私聊(QQ号:{conversation_id})"
        )
        old = old_summary or "(none)"
        recent = "\n".join(f"- {_format_counter_message(message)}" for message in messages)
        return (
            f"Summary time: {current_time}\n"
            f"Conversation: {kind_label}\n"
            f"The messages below were generated shortly before this summary time.\n"
            "Update the existing archive summary with stable facts, recurring preferences, "
            "important decisions, relationships, and topic changes from the recent messages. "
            "Keep it compact. Do not include trivial small talk unless it changes the long-term context.\n\n"
            f"Existing summary:\n{old}\n\n"
            f"Recent messages:\n{recent}\n\n"
            "Updated summary:"
        )

    def _build_agent_task(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        messages: list[Any],
    ) -> str:
        current_time = get_current_time_and_lunar_date()
        recent = "\n".join(f"- {_format_counter_message(message)}" for message in messages)
        fav_instruction = ""
        if self._favorability_max_change > 0:
            fav_instruction = (
                f"此外，根据近期聊天中用户的行为综合评估并调整好感度：\n"
                f"正向互动（友好、配合、积极）适当增加好感度，负向（冒犯、骚扰、恶意）减少好感度。\n"
                f"每次变更上限 ±{self._favorability_max_change}，范围 {self._favorability_min}~{self._favorability_max}。\n"
                f"使用 update_favorability 工具执行变更，不要遗漏任何值得调整的用户。\n"
            )
        if conversation_kind == "group":
            conversation_label = f"群聊(群号:{conversation_id})"
            workflow = (
                "这是自动触发的群聊记忆处理。请按顺序执行：\n"
                "1. 依次检查本轮参与聊天的所有群友，读取他们现有 user_profile 档案，只记录了解到的新个人信息，不记录具体聊天事件。\n"
                "2. 如果聊天中明确要求你记住某些事情，而对应档案没有，加入对应档案记录。\n"
                "3. 没有需要记录的新信息时允许不写。\n"
                f"4. {fav_instruction}"
                "5. 最后读取并更新 group_profile，只记录对群的新稳定信息，不记录具体事件。\n"
            )
        else:
            conversation_label = f"私聊(QQ号:{conversation_id})"
            workflow = (
                "这是自动触发的好友聊天记忆处理。请读取该好友现有 user_profile 档案，"
                "只记录好友新的稳定信息或明确要求记住的内容，不记录具体聊天事件；没有新信息时允许不写。\n"
                f"{fav_instruction}"
            )
        return (
            f"当前时间(记忆总结时间): {current_time}\n"
            f"会话: {conversation_label}\n"
            "以下待总结消息是当前时间不久前产生的近期消息。\n"
            f"{workflow}"
            "如果近期消息含义不明确或指代不清，可以调用 read_earlier_messages 拉取更早消息确认。\n"
            "近期消息:\n"
            f"{recent}"
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


def _extract_response_text(response: dict[str, Any]) -> str:
    content = response.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if value is not None:
                    parts.append(str(value))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content or "")
