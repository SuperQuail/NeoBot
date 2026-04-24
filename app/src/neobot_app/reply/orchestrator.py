"""ReplyOrchestrator — 管理回复事件的创建与异步执行，支持 common/agent 两种模式"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.reply.event import ReplyEvent, ReplyState

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter
    from neobot_adapter.model.message import GroupMessage, PrivateMessage
    from neobot_chat import AgentRegistry
    from neobot_chat.providers.base import Provider
    from neobot_chat.schema.types import ToolDefinition
    from neobot_app.config.schemas.bot import BotConfig
    from neobot_app.emoji.service import EmojiService
    from neobot_app.observability.debug import DebugRecorder
    from neobot_app.message.numbering import MessageNumbering
    from neobot_app.message.queue import MessageQueue
    from neobot_app.prompt.builder import PromptBuilder
    from neobot_app.willing.models import WillingDecision
    from neobot_app.willing.service import WillingService
    from neobot_app.image import ImageParseService


class ReplyOrchestrator:
    def __init__(
        self,
        *,
        adapter: OneBotAdapter,
        prompt_builder: PromptBuilder,
        provider: Provider | None = None,
        group_message_queue: MessageQueue | None = None,
        friend_message_queue: MessageQueue | None = None,
        config: BotConfig | None = None,
        willing_service: WillingService | None = None,
        image_parse_service: ImageParseService | None = None,
        emoji_service: EmojiService | None = None,
        agent_registry: AgentRegistry | None = None,
        provider_error_message: str | None = None,
        debug_recorder: DebugRecorder | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._adapter = adapter
        self._prompt_builder = prompt_builder
        self._provider = provider
        self._group_queue = group_message_queue
        self._friend_queue = friend_message_queue
        self._config = config
        self._willing_service = willing_service
        self._image_parse_service = image_parse_service
        self._emoji_service = emoji_service
        self._agent_registry = agent_registry
        self._provider_error_message = (
            provider_error_message or "当前主回复模型不可用，请检查模型配置"
        )
        self._debug_recorder = debug_recorder
        self._logger = logger or NullLogger()
        self._tasks: set[asyncio.Task[None]] = set()

    def start_reply(
        self,
        *,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
        decision: WillingDecision,
    ) -> ReplyEvent:
        mode = self._resolve_mode()
        event = ReplyEvent(
            mode=mode,
            message=message,
            willing_decision=decision,
            conversation_ref=self._build_conversation_ref(message, queue_key),
        )
        self._logger.info(
            "ReplyEvent created",
            event_id=event.event_id,
            conversation_id=queue_key,
            conversation_kind=getattr(event.conversation_ref, "kind", ""),
            probability=f"{decision.probability:.3f}",
            mode=mode,
        )
        self._record_debug(
            "created",
            event,
            queue_key=queue_key,
            decision={
                "manager_name": decision.manager_name,
                "probability": decision.probability,
                "should_reply": decision.should_reply,
                "reasons": list(decision.reasons),
            },
        )

        task = asyncio.create_task(self._run(event, queue, queue_key))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return event

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._agent_registry is not None:
            await self._agent_registry.close()
        self._logger.info("ReplyOrchestrator 已关闭")

    def _resolve_mode(self) -> str:
        if self._config is not None:
            mode = getattr(self._config.chat, "reply_mode", "common") or "common"
            if mode in ("common", "agent"):
                return mode
        return "common"

    def _record_debug(self, stage: str, event: ReplyEvent, **extra: object) -> None:
        if self._debug_recorder is None:
            return
        self._debug_recorder.record_reply_event(stage, event, **extra)

    async def _handle_runtime_failure(self, event: ReplyEvent, exc: Exception) -> None:
        if not isinstance(exc, RuntimeError):
            return
        if "chat provider" not in str(exc):
            return
        if event.conversation_ref is None:
            return
        try:
            await self._adapter.send(event.conversation_ref, self._provider_error_message)
        except Exception as send_exc:
            self._logger.error(
                "Provider unavailable notice failed",
                event_id=event.event_id,
                error=str(send_exc),
            )
            self._record_debug(
                "provider_unavailable_notice_failed",
                event,
                send_error=str(send_exc),
            )
            return
        self._record_debug(
            "provider_unavailable_notice_sent",
            event,
            notice=self._provider_error_message,
        )

    async def _run(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
    ) -> None:
        try:
            if event.mode == "agent":
                await self._run_agent_mode(event, queue, queue_key)
            else:
                await self._run_common_mode(event, queue, queue_key)
            self._logger.info(
                "ReplyEvent completed",
                event_id=event.event_id,
                mode=event.mode,
                reply_preview=event.generated_text[:80] if event.generated_text else "",
            )
            self._record_debug("completed", event, queue_key=queue_key)
        except asyncio.CancelledError:
            event.error = "cancelled"
            self._logger.warning("ReplyEvent cancelled", event_id=event.event_id)
            self._record_debug("cancelled", event, queue_key=queue_key)
            raise
        except Exception as exc:
            try:
                event.transition(ReplyState.FAILED)
            except RuntimeError:
                pass
            event.error = f"{type(exc).__name__}: {exc}"
            self._logger.error(
                "ReplyEvent failed",
                event_id=event.event_id,
                mode=event.mode,
                error=event.error,
            )
            self._record_debug("failed", event, queue_key=queue_key)
            await self._handle_runtime_failure(event, exc)

    # ── Common 模式 ──

    async def _run_common_mode(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
    ) -> None:
        prompt = await self._build_prompt(event, queue, queue_key)
        self._record_debug("base_prompt_built", event, queue_key=queue_key, prompt=prompt)
        reply_text = await self._generate_reply(event, prompt)
        self._record_debug("reply_generated", event, queue_key=queue_key, reply_text=reply_text)
        await self._send_reply(event, reply_text)

    # ── Agent 模式 ──

    async def _run_agent_mode(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
    ) -> None:
        from neobot_app.message.numbering import MessageNumbering
        from neobot_app.reply.tools import build_reply_toolset

        numbering = MessageNumbering()

        # 1. 克隆消息队列
        queue_copy = queue.clone(queue_key)

        # 2. 构建 prompt（带编号）
        prompt = await self._build_prompt(event, queue_copy, queue_key, numbering=numbering)
        self._record_debug("prompt_built", event, queue_key=queue_key, prompt=prompt)

        # 注入表情包列表
        if self._emoji_service is not None:
            emoji_text = self._emoji_service.build_prompt_text()
            if emoji_text:
                prompt += (
                    "\n\n<可用的表情包>\n"
                    f"{emoji_text}\n"
                    "发送表情包时请使用 send_emoji 工具，参数 number 为表情包编号。\n"
                    "</可用的表情包>"
                )
        self._record_debug("prompt_built", event, queue_key=queue_key, prompt=prompt)
        if self._agent_registry is not None:
            self._record_debug(
                "sub_agents_enabled",
                event,
                queue_key=queue_key,
                sub_agents=self._agent_registry.snapshot(),
            )

        # 3. 准备消息列表
        event.transition(ReplyState.GENERATING)
        messages: list[dict] = [{"role": "system", "content": prompt}]

        # 4. 构建工具集
        reply_sent = False

        async def send_reply_handler(text: str, reply_to: int | None = None) -> None:
            nonlocal reply_sent
            reply_sent = True
            event.generated_text = text
            if reply_to is not None:
                event.reply_to_number = reply_to
                msg_id = numbering.get_message_id(reply_to)
                await self._send_reply(event, text, reply_to_message_id=msg_id)
            else:
                await self._send_reply(event, text)

        async def send_emoji_handler(number: int, text: str = "") -> None:
            if self._emoji_service is None:
                return
            entry = self._emoji_service.get_entry(number)
            if entry is None:
                return
            # 构建消息段：可选文字 + 图片
            segments: list[dict] = []
            if text.strip():
                segments.append({"type": "text", "data": {"text": text.strip()}})
            segments.append({
                "type": "image",
                "data": {"file": f"file:///{entry.file_path.as_posix()}"},
            })
            await self._adapter.send(event.conversation_ref, segments)

        from neobot_chat.tools.toolset import Toolset

        reply_toolset = build_reply_toolset(
            send_reply_handler=send_reply_handler,
            willing_service=self._willing_service,
            numbering=numbering,
            send_emoji_handler=send_emoji_handler,
            emoji_service=self._emoji_service,
            agent_registry=self._agent_registry,
        )

        tools = reply_toolset.definitions()

        # 5. Agent 循环
        max_iterations = 12
        for iteration in range(max_iterations):
            if self._provider is None:
                raise RuntimeError("未配置 chat provider，无法生成回复")

            response = await self._provider.chat(messages, tools=tools if tools else None)
            self._record_debug(
                "agent_iteration",
                event,
                queue_key=queue_key,
                iteration=iteration + 1,
                response=response,
            )
            messages.append(response)

            tool_calls = response.get("tool_calls")
            if not tool_calls:
                # 无工具调用 → 若未调用 send_reply 则用 content 作为回复
                if not reply_sent:
                    content = response.get("content", "")
                    text = content.strip() if isinstance(content, str) else str(content)
                    if text:
                        event.generated_text = text
                        self._record_debug(
                            "reply_generated",
                            event,
                            queue_key=queue_key,
                            reply_text=text,
                        )
                        await self._send_reply(event, text)
                        reply_sent = True
                break

            # 执行工具调用
            for tc in tool_calls:
                name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}
                self._record_debug(
                    "tool_called",
                    event,
                    queue_key=queue_key,
                    iteration=iteration + 1,
                    tool_name=name,
                    tool_args=args,
                )
                result = await reply_toolset.executor.execute(name, args)
                self._record_debug(
                    "tool_returned",
                    event,
                    queue_key=queue_key,
                    iteration=iteration + 1,
                    tool_name=name,
                    tool_args=args,
                    tool_result=result,
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": str(result),
                })

            if reply_sent:
                break

            # 注入此期间的新消息
            previous_entries = list(queue_copy._queues.get(queue_key, []))
            new_entries = self._collect_new_entries(queue, queue_copy, queue_key)
            if new_entries:
                new_text = numbering.apply_new(
                    new_entries,
                    queue_copy,
                    context_entries=list(queue_copy._queues.get(queue_key, [])),
                    previous_entries=previous_entries,
                )
                if new_text:
                    messages.append({
                        "role": "user",
                        "content": f"[期间新消息]\n{new_text}",
                    })
                    self._record_debug(
                        "agent_new_messages_injected",
                        event,
                        queue_key=queue_key,
                        injected_text=new_text,
                    )

        # 保存编号映射
        event.message_number_map = numbering.mapping
        if event.state == ReplyState.GENERATING and not event.is_terminal:
            try:
                event.transition(ReplyState.COMPLETED)
            except RuntimeError:
                pass

    def _collect_new_entries(
        self,
        source: MessageQueue,
        snapshot: MessageQueue,
        queue_key: str,
    ) -> list:
        """收集源队列中比快照多的新条目，并更新快照"""
        from collections import deque
        from neobot_app.message.queue_impl import QueueEntry, QueueEntryType

        source_entries = list(source._queues.get(queue_key, []))
        snapshot_entries = list(snapshot._queues.get(queue_key, []))
        snapshot_count = len(snapshot_entries)
        new_entries = source_entries[snapshot_count:]

        # 将新条目加入快照
        if new_entries:
            if queue_key not in snapshot._queues:
                snapshot._queues[queue_key] = deque()
            for entry in new_entries:
                snapshot._queues[queue_key].append(entry)

        return [
            entry for entry in new_entries
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None
        ]

    # ── Prompt 构建 ──

    async def _build_prompt(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
        numbering: MessageNumbering | None = None,
    ) -> str:
        # 等待该队列所有待处理的图片解析完成
        if self._image_parse_service is not None:
            await self._image_parse_service.wait_for_queue(queue_key)

        event.transition(ReplyState.BUILDING_PROMPT)
        if event.conversation_ref is None:
            raise ValueError("ReplyEvent.conversation_ref is None")

        if event.conversation_ref.kind == "group":
            return await self._prompt_builder.build_group_chat_prompt(
                group_id=int(queue_key),
                message_queue=queue,
                numbering=numbering,
            )
        return await self._prompt_builder.build_friend_chat_prompt(
            user_id=int(queue_key),
            message_queue=queue,
            numbering=numbering,
        )

    # ── LLM 生成 ──

    async def _generate_reply(self, event: ReplyEvent, prompt: str) -> str:
        event.transition(ReplyState.GENERATING)
        if self._provider is None:
            raise RuntimeError("未配置 chat provider，无法生成回复")

        messages: list[dict[str, str]] = [
            {"role": "system", "content": prompt},
        ]
        response = await self._provider.chat(messages)
        content = response.get("content", "")
        text = content.strip() if isinstance(content, str) else str(content)
        event.generated_text = text
        self._record_debug("reply_generated", event, reply_text=text, response=response)
        return text

    # ── 发送回复 ──

    async def _send_reply(
        self,
        event: ReplyEvent,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> None:
        event.transition(ReplyState.SENDING)
        if event.conversation_ref is None:
            raise ValueError("ReplyEvent.conversation_ref is None")

        if reply_to_message_id is not None:
            # 构造 @ 回复格式
            formatted = f"[CQ:reply,id={reply_to_message_id}]{text}"
        else:
            formatted = text

        result = await self._adapter.send(event.conversation_ref, formatted)
        event.send_response = result
        event.transition(ReplyState.COMPLETED)
        self._record_debug(
            "reply_sent",
            event,
            formatted=formatted,
            reply_to_message_id=reply_to_message_id,
        )

    # ── 工具方法 ──

    @staticmethod
    def _build_conversation_ref(
        message: PrivateMessage | GroupMessage,
        queue_key: str,
    ) -> ConversationRef:
        from neobot_adapter.model.message import GroupMessage

        if isinstance(message, GroupMessage):
            return ConversationRef(kind="group", id=queue_key)
        return ConversationRef(kind="private", id=queue_key)
