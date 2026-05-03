"""ReplyOrchestrator — 管理回复事件的创建与异步执行，支持 common/agent 两种模式"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from neobot_contracts.models import ConversationRef
from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.reply.event import ReplyEvent, ReplyState
from neobot_app.reply.postprocess import process_reply_text
from neobot_app.time_context import monotonic_seconds

if TYPE_CHECKING:
    from neobot_adapter import OneBotAdapter
    from neobot_adapter.model.message import GroupMessage, PrivateMessage
    from neobot_chat import AgentRegistry
    from neobot_chat.providers.base import Provider
    from neobot_app.config.schemas.bot import BotConfig
    from neobot_app.emoji.service import EmojiService
    from neobot_app.observability.debug import DebugRecorder
    from neobot_app.message.numbering import MessageNumbering
    from neobot_app.message.queue import MessageQueue
    from neobot_app.prompt.builder import PromptBuilder
    from neobot_app.willing.models import WillingDecision
    from neobot_app.willing.service import WillingService
    from neobot_app.image import ImageParseService


def _msg_id_of(entry) -> int | None:
    """从 QueueEntry 中提取 message_id，不存在则返回 None。"""
    from neobot_app.message.queue_impl import QueueEntryType

    if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
        return entry.message.message_id
    return None


def _entry_fingerprint(entry) -> str:
    """为 QueueEntry 生成去重指纹。

    MESSAGE 条目使用 message_id；非 MESSAGE 条目使用类型+内容哈希。
    确保 TIMESTAMP / RECALL / REACTION / POKE 等条目也能正确去重。
    """
    from neobot_app.message.queue_impl import QueueEntryType

    if entry.kind == QueueEntryType.MESSAGE and entry.message is not None:
        mid = entry.message.message_id
        if mid is not None:
            return f"msg:{mid}"
        return f"msg:hash:{hash(str(entry.message.model_dump(mode='json')))}"

    if entry.kind == QueueEntryType.TIMESTAMP:
        return f"ts:{entry.occurred_at}"

    if entry.kind == QueueEntryType.RECALL and entry.notice is not None:
        nid = entry.notice.message_id
        uid = getattr(entry.notice, "user_id", "")
        oid = getattr(entry.notice, "operator_id", "")
        return f"recall:{nid}:{uid}:{oid}:{entry.occurred_at}"

    if entry.kind == QueueEntryType.REACTION and entry.reaction is not None:
        r = entry.reaction
        return f"reaction:{r.target_message_id}:{r.emoji_id}:{r.operator_user_id}"

    if entry.kind == QueueEntryType.POKE and entry.poke is not None:
        p = entry.poke
        return f"poke:{p.sender_id}:{p.target_id}:{p.sub_type}:{entry.occurred_at}"

    return f"unknown:{entry.kind.value}:{hash(str(entry))}"


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
        tts_service: Any = None,
        provider_error_message: str | None = None,
        debug_recorder: DebugRecorder | None = None,
        logger: Logger | None = None,
        drawing_manager: Any = None,
        scheduled_task_manager: Any = None,
        notification_hub: Any = None,
        reply_block_registry: Any = None,
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
        self._tts_service = tts_service
        self._provider_error_message = (
            provider_error_message or "当前主回复模型不可用，请检查模型配置"
        )
        self._debug_recorder = debug_recorder
        self._logger = logger or NullLogger()
        self._drawing_manager = drawing_manager
        self._scheduled_task_manager = scheduled_task_manager
        self._notification_hub = notification_hub
        self._reply_block_registry = reply_block_registry
        self._tasks: set[asyncio.Task[None]] = set()
        self._active_pipelines: dict[str, asyncio.Task[None]] = {}
        self._last_reply_time: dict[str, float] = {}
        self._last_sentence_time: dict[str, float] = {}

    def start_reply(
        self,
        *,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
        decision: WillingDecision,
        pre_reply_message_id: int | None = None,
        on_reply_done: Callable[[], Awaitable[None]] | None = None,
        skip_cooldown: bool = False,
        background_content: str | None = None,
    ) -> ReplyEvent | None:
        mode = self._resolve_mode()
        conversation_ref = self._build_conversation_ref(message, queue_key)
        event = ReplyEvent(
            mode=mode,
            message=message,
            willing_decision=decision,
            conversation_ref=conversation_ref,
            pre_reply_message_id=pre_reply_message_id,
            background_content=background_content,
        )

        # 按 kind:queue_key 组合键去重，避免群号与 QQ 号相同时互相阻塞
        pipeline_key = f"{conversation_ref.kind}:{queue_key}"
        existing = self._active_pipelines.get(pipeline_key)
        if existing is not None and existing.done():
            self._active_pipelines.pop(pipeline_key, None)
            existing = None
        if existing is not None and not existing.done():
            self._logger.debug(
                "回复管线已在运行，跳过创建",
                event_id=event.event_id,
                pipeline_key=pipeline_key,
            )
            self._record_debug(
                "skipped_pipeline_overlap",
                event,
                queue_key=queue_key,
                pipeline_key=pipeline_key,
            )
            return None

        # 冷却检查：距上次回复结束不足冷却时间则跳过（后台通知可绕过）
        if not skip_cooldown:
            cooldown = self._get_cooldown_seconds()
            last_time = self._last_reply_time.get(pipeline_key, 0.0)
            elapsed = monotonic_seconds() - last_time
            if elapsed < cooldown:
                self._logger.debug(
                    "冷却中，跳过创建回复",
                    event_id=event.event_id,
                    pipeline_key=pipeline_key,
                    elapsed=f"{elapsed:.1f}s",
                    cooldown=f"{cooldown}s",
                )
                self._record_debug(
                    "skipped_cooldown",
                    event,
                    queue_key=queue_key,
                    pipeline_key=pipeline_key,
                    elapsed_seconds=elapsed,
                    cooldown_seconds=cooldown,
                )
                return None

        self._logger.info(
            "创建回复事件",
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

        def _cleanup(task: asyncio.Task[None]) -> None:
            self._tasks.discard(task)
            if self._active_pipelines.get(pipeline_key) is task:
                self._active_pipelines.pop(pipeline_key, None)
            if on_reply_done is not None:
                callback_task = asyncio.create_task(on_reply_done())

                def _callback_done(done_task: asyncio.Task[None]) -> None:
                    try:
                        done_task.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        self._logger.warning(
                            "reply done callback failed",
                            event_id=event.event_id,
                            pipeline_key=pipeline_key,
                            error=str(exc),
                        )

                callback_task.add_done_callback(_callback_done)

        task = asyncio.create_task(self._run(event, queue, queue_key))
        self._tasks.add(task)
        self._active_pipelines[pipeline_key] = task
        task.add_done_callback(_cleanup)
        return event

    def is_pipeline_active(self, kind: str, conversation_id: str) -> bool:
        pipeline_key = f"{kind}:{conversation_id}"
        task = self._active_pipelines.get(pipeline_key)
        if task is not None and task.done():
            self._active_pipelines.pop(pipeline_key, None)
            return False
        return task is not None

    def is_pipeline_key_active(self, pipeline_key: str) -> bool:
        task = self._active_pipelines.get(pipeline_key)
        if task is not None and task.done():
            self._active_pipelines.pop(pipeline_key, None)
            return False
        return task is not None

    def start_background_reply(
        self,
        *,
        kind: str,
        conversation_id: str,
        content: str,
        manager_name: str = "background_drawing",
        reasons: list[str] | None = None,
    ) -> Any | None:
        """程序化启动回复管线，用于后台绘图等系统通知。

        当绘图完成但对应聊天流无活跃管线时，由 BackgroundDrawingManager 调用。
        """
        from neobot_app.willing.models import WillingDecision

        queue_key = str(conversation_id)
        pipeline_key = f"{kind}:{queue_key}"

        existing = self._active_pipelines.get(pipeline_key)
        if existing is not None and existing.done():
            self._active_pipelines.pop(pipeline_key, None)
            existing = None
        if existing is not None and not existing.done():
            self._logger.debug(
                "后台回复管线已在运行，跳过创建",
                pipeline_key=pipeline_key,
            )
            return None

        queue = (
            self._group_queue if kind == "group" else self._friend_queue
        )
        if queue is None:
            self._logger.error(
                "无法启动后台回复：消息队列未配置",
                kind=kind,
                conversation_id=conversation_id,
            )
            return None

        # 将通知内容推入消息队列作为触发消息
        from neobot_app.message.queue_impl import QueueEntryType

        @dataclass
        class _SyntheticSender:
            card: str = ""
            nickname: str = "系统"

        @dataclass
        class _SyntheticMessage:
            time: int = 0
            self_id: int = 0
            post_type: str = "message"
            message_type: str = kind
            sub_type: str = "normal"
            message_id: int = 0
            user_id: int = 0
            group_id: int = int(conversation_id) if kind == "group" and conversation_id.isdigit() else 0
            message: list = field(default_factory=lambda: [{"type": "text", "data": {"text": content}}])
            raw_message: str = ""
            font: int = 0
            sender: Any = field(default_factory=_SyntheticSender)
            message_seq: int = 0
            target_id: int = 0
            temp_source: int = 0

        synthetic_msg = _SyntheticMessage()

        decision = WillingDecision(
            manager_name=manager_name,
            probability=1.0,
            should_reply=True,
            reasons=reasons or ["后台绘图任务完成通知"],
        )

        self._logger.info(
            "启动后台回复管线",
            pipeline_key=pipeline_key,
            kind=kind,
            conversation_id=conversation_id,
        )
        return self.start_reply(
            message=synthetic_msg,
            queue=queue,
            queue_key=queue_key,
            decision=decision,
            skip_cooldown=True,
            background_content=content,
        )

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._active_pipelines.clear()
        self._last_reply_time.clear()
        self._last_sentence_time.clear()
        if self._drawing_manager is not None:
            await self._drawing_manager.shutdown()
        if self._scheduled_task_manager is not None:
            await self._scheduled_task_manager.shutdown()
        if self._notification_hub is not None:
            self._notification_hub.clear()
        if self._agent_registry is not None:
            await self._agent_registry.close()
        self._logger.info("ReplyOrchestrator 已关闭")

    def _resolve_mode(self) -> str:
        if self._config is not None:
            mode = getattr(self._config.chat, "reply_mode", "common") or "common"
            if mode in ("common", "agent"):
                return mode
        return "common"

    def _get_cooldown_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "reply_cooldown_seconds", None)
            if isinstance(val, int):
                return val
        return 2

    def _get_wait_cooldown_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "wait_cooldown_seconds", None)
            if isinstance(val, int):
                return val
        return 60

    def _get_sentence_cooldown_seconds(self) -> float:
        if self._config is not None:
            val = getattr(self._config.chat, "reply_sentence_cooldown_seconds", None)
            if isinstance(val, (int, float)):
                return float(val)
        return 2.0

    def _get_private_chat_sentence_cooldown_seconds(self) -> float:
        if self._config is not None:
            val = getattr(self._config.chat, "private_chat_sentence_cooldown_seconds", None)
            if isinstance(val, (int, float)):
                return float(val)
        return 2.0

    def _get_max_wait_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "agent_wait_max_seconds", None)
            if isinstance(val, int) and val > 0:
                return val
        return 60

    def _get_private_chat_suspend_wait_seconds(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "private_chat_suspend_wait_seconds", None)
            if isinstance(val, int) and val > 0:
                return val
        return 300

    def _get_group_agent_silent_timeout_seconds(self) -> float:
        if self._config is not None:
            val = getattr(self._config.chat, "group_agent_silent_timeout_seconds", None)
            if isinstance(val, (int, float)):
                return max(0.0, float(val))
        return 60.0

    def _get_io_timeout_seconds(self) -> float:
        return 30.0

    def _get_dependency_timeout_seconds(self) -> float:
        return 10.0

    def _get_prompt_timeout_seconds(self) -> float:
        return 30.0

    def _get_model_response_timeout_seconds(self, event: ReplyEvent) -> float:
        if event.conversation_ref is not None and event.conversation_ref.kind == "group":
            timeout = self._get_group_agent_silent_timeout_seconds()
            if timeout > 0:
                return timeout
        return 120.0

    async def _send_with_timeout(self, conversation_ref: ConversationRef, payload: object) -> Any:
        return await asyncio.wait_for(
            self._adapter.send(conversation_ref, payload),
            timeout=self._get_io_timeout_seconds(),
        )

    async def _call_api_with_timeout(self, action: str, params: dict[str, Any]) -> Any:
        return await asyncio.wait_for(
            self._adapter.call_api(action, params),
            timeout=self._get_io_timeout_seconds(),
        )

    def _get_private_chat_max_tokens(self) -> int:
        if self._config is not None:
            val = getattr(self._config.chat, "private_chat_max_tokens", None)
            if isinstance(val, int) and val > 0:
                return val
        return 10000

    def _get_private_chat_new_message_collect_seconds(self) -> float:
        if self._config is not None:
            val = getattr(self._config.chat, "private_chat_new_message_collect_seconds", None)
            if isinstance(val, (int, float)) and val > 0:
                return float(val)
        return 5.0

    @staticmethod
    def _estimate_tokens(messages: list[dict]) -> int:
        total_chars = sum(len(str(m)) for m in messages)
        return int(total_chars / 1.5)

    def _get_ai_reply_check(self) -> bool:
        if self._config is None:
            return False
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "ai_reply_check", False)
        return value if isinstance(value, bool) else False

    def _get_ai_reply_check_lightweight(self) -> bool:
        """轻量检查仅在完整检查关闭时生效。"""
        if self._get_ai_reply_check():
            return False
        if self._config is None:
            return True
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "ai_reply_check_lightweight", True)
        return value if isinstance(value, bool) else True

    def _get_bot_name(self) -> str:
        if self._config is None:
            return "Bot"
        bot = getattr(self._config, "bot", None)
        value = getattr(bot, "nick_name", "Bot")
        return value.strip() if isinstance(value, str) and value.strip() else "Bot"

    def _get_long_reply_fallback_template(self) -> str:
        if self._config is None:
            return "{bot_name}懒得和你说道理，你不配听"
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "long_reply_fallback_template", "")
        if isinstance(value, str) and value.strip():
            return value
        return "{bot_name}懒得和你说道理，你不配听"

    def _get_long_reply_max_length(self) -> int:
        if self._config is None:
            return 300
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "long_reply_max_length", 300)
        return value if isinstance(value, int) and value > 0 else 300

    def _get_long_reply_max_sentence_count(self) -> int:
        if self._config is None:
            return 12
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "long_reply_max_sentence_count", 12)
        return value if isinstance(value, int) and value > 0 else 12

    def _get_enable_ai_reply_regenerate(self) -> bool:
        if self._config is None:
            return True
        chat = getattr(self._config, "chat", None)
        value = getattr(chat, "enable_ai_reply_regenerate_on_length_limit", True)
        return bool(value)

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
            await self._send_with_timeout(event.conversation_ref, self._provider_error_message)
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
        started_at = monotonic_seconds()
        try:
            if event.mode == "agent":
                await self._run_agent_mode(event, queue, queue_key)
            else:
                await self._run_common_mode(event, queue, queue_key)
            # 记录完成时间用于冷却
            if event.conversation_ref is not None:
                pipeline_key = f"{event.conversation_ref.kind}:{queue_key}"
                self._last_reply_time[pipeline_key] = monotonic_seconds()
            # 记录上次回复位置
            enable_tracking = (
                getattr(getattr(self._config, "chat", None), "enable_last_reply_tracking", True)
                if self._config else True
            )
            if enable_tracking:
                queue.set_last_reply_position(
                    queue_key,
                    before_message_id=event.pre_reply_message_id,
                )
            elapsed = monotonic_seconds() - started_at
            self._logger.info(
                "回复事件结束",
                event_id=event.event_id,
                mode=event.mode,
                state=event.state.name,
                duration=f"{elapsed:.1f}s",
                reply_preview=event.generated_text[:80] if event.generated_text else "",
            )
            self._record_debug("completed", event, queue_key=queue_key)
        except asyncio.CancelledError:
            event.error = "cancelled"
            self._logger.warning("回复事件被取消", event_id=event.event_id)
            self._record_debug("cancelled", event, queue_key=queue_key)
            raise
        except Exception as exc:
            try:
                event.transition(ReplyState.FAILED)
            except RuntimeError:
                pass
            event.error = f"{type(exc).__name__}: {exc}"
            self._logger.error(
                "回复事件失败",
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
        await self._maybe_trigger_sticker(queue, queue_key, event)

        last_reply_message_id, all_new = self._resolve_last_reply(queue, queue_key)
        prompt = await self._build_prompt(
            event, queue, queue_key,
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
        )
        self._record_debug("base_prompt_built", event, queue_key=queue_key, prompt=prompt)
        reply_text = await self._generate_reply(event, prompt)
        self._record_debug("reply_generated", event, queue_key=queue_key, reply_text=reply_text)
        await self._send_reply(event, reply_text)

    async def _maybe_trigger_sticker(
        self,
        queue: MessageQueue,
        queue_key: str,
        event: ReplyEvent | None = None,
    ) -> None:
        """按配置概率随机发送一张表情包到当前会话。

        后台通知（绘图完成、定时任务等）触发的管线不适用——没有用户交互上下文。
        """
        import random

        if event is not None and event.willing_decision is not None:
            mgr = event.willing_decision.manager_name
            if mgr in ("background_drawing", "scheduled_task"):
                return

        prob = getattr(
            self._config.chat, "random_sticker_probability", 0.1
        ) if self._config else 0.1
        try:
            prob = float(prob)
        except (TypeError, ValueError):
            prob = 0.1
        prob = max(0.0, min(1.0, prob))
        if random.random() >= prob:
            return
        if self._emoji_service is None or self._emoji_service.emoji_count == 0:
            return
        if event is None or event.conversation_ref is None:
            return

        number = random.randint(1, self._emoji_service.emoji_count)
        entry = self._emoji_service.get_entry(number)
        if entry is None:
            return

        segments: list[dict] = [{
            "type": "image",
            "data": {"file": f"file:///{entry.file_path.as_posix()}"},
        }]
        try:
            await self._send_with_timeout(event.conversation_ref, segments)
            # 记录表情包使用次数
            await self._emoji_service.record_usage(number)
            self._logger.debug(
                "已随机发送表情包",
                event_id=event.event_id,
                number=number,
                file=entry.file_name,
            )
        except Exception as exc:
            self._logger.debug(
                "随机表情包发送失败",
                event_id=event.event_id,
                error=str(exc),
            )

    # ── Agent 模式 ──

    async def _run_agent_mode(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
    ) -> None:
        from neobot_app.message.numbering import MessageNumbering
        from neobot_app.reply.tools import build_reply_toolset

        # 随机触发表情包发送
        await self._maybe_trigger_sticker(queue, queue_key, event)

        numbering = MessageNumbering()

        # 1. 克隆消息队列
        queue_copy = queue.clone(queue_key)

        # 2. 构建 prompt（带编号）
        last_reply_message_id, all_new = self._resolve_last_reply(queue, queue_key)
        prompt = await self._build_prompt(
            event, queue_copy, queue_key, numbering=numbering,
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
        )
        self._record_debug("prompt_built", event, queue_key=queue_key, prompt=prompt)

        # 注入表情包列表
        if self._emoji_service is not None:
            emoji_page_size = getattr(
                getattr(self._config, "chat", None), "emoji_page_size", 50
            ) if self._config else 50
            emoji_text = self._emoji_service.build_prompt_text(limit=emoji_page_size)
            if emoji_text:
                emoji_total = self._emoji_service.emoji_count
                search_hint = (
                    f"\n当表情包数量过多（如{emoji_total}个）时可能需要搜索，"
                    "正常情况下直接列表查看即可。可用 search_custom_emoji 按关键词搜索。"
                    if emoji_total > emoji_page_size else ""
                )
                prompt += (
                    "\n\n<可用的表情包>\n"
                    f"{emoji_text}\n"
                    "发送表情包时请使用 send_emoji 工具，参数 number 为表情包编号。\n"
                    "表情包按使用次数从少到多排列（使用次数均衡器），优先使用不常用的表情包。\n"
                    f"{search_hint}\n"
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
        if event.background_content:
            messages.append({"role": "user", "content": event.background_content})
            self._logger.info(
                "注入后台通知（新管线初始消息）",
                event_id=event.event_id,
                queue_key=queue_key,
            )
            self._record_debug(
                "background_notification_injected_initial",
                event,
                queue_key=queue_key,
                notification=event.background_content[:200],
            )

        # 4. 构建工具集
        reply_sent = False
        cancelled = False

        async def cancel_handler(reason: str | None = None) -> None:
            nonlocal cancelled
            cancelled = True
            event.error = reason or "agent 主动取消回复"
            event.transition(ReplyState.CANCELLED)
            self._logger.debug(
                "Agent主动取消回复",
                event_id=event.event_id,
                reason=reason,
            )

        async def send_reply_handler(
            text: str,
            reply_to: int | None = None,
            mention: list[int] | None = None,
            segments: list[str] | None = None,
            send_original: bool = False,
        ) -> None:
            nonlocal reply_sent
            reply_sent = True
            event.generated_text = text
            if reply_to is not None:
                event.reply_to_number = reply_to
                msg_id = numbering.get_message_id(reply_to)
                await self._send_reply(
                    event,
                    text,
                    reply_to_message_id=msg_id,
                    mention_user_ids=mention,
                    segments=segments,
                    send_original=send_original,
                )
            else:
                await self._send_reply(
                    event,
                    text,
                    mention_user_ids=mention,
                    segments=segments,
                    send_original=send_original,
                )

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
            await self._send_with_timeout(event.conversation_ref, segments)
            # 记录表情包使用次数
            await self._emoji_service.record_usage(number)

        async def wait_handler(seconds: int = 20) -> str:
            max_wait = self._get_max_wait_seconds()
            wait_time = max(1, min(seconds, max_wait))
            await asyncio.sleep(wait_time)
            previous_entries = queue_copy.entries(queue_key)
            new_entries = self._collect_new_entries(queue, queue_copy, queue_key)
            if new_entries:
                new_text = numbering.apply_new(
                    new_entries,
                    queue_copy,
                    context_entries=queue_copy.entries(queue_key),
                    previous_entries=previous_entries,
                )
                if new_text:
                    return f"等待了 {wait_time} 秒，期间收到新消息：\n{new_text}"
            return f"等待了 {wait_time} 秒，期间没有收到新消息。"

        async def react_emoji_handler(message_number: int, emoji_id: int) -> str:
            from neobot_adapter.request.message import set_msg_emoji_like
            from neobot_app.message.queue_impl import ReactionEntry

            msg_id = numbering.get_message_id(message_number)
            if msg_id is None:
                return f"错误：消息编号 {message_number} 不存在于当前上下文中"

            await asyncio.wait_for(
                set_msg_emoji_like(message_id=msg_id, emoji_id=emoji_id),
                timeout=self._get_io_timeout_seconds(),
            )

            # 获取操作者名称（bot 自身）
            bot_name = getattr(self._config.bot, "nick_name", "Bot") if self._config else "Bot"

            reaction = ReactionEntry(
                target_message_id=msg_id,
                emoji_id=emoji_id,
                operator_user_id=getattr(self._config.bot, "account", 0) if self._config else 0,
                operator_name=bot_name,
            )
            # 同时推送到源队列和快照队列
            queue.push_reaction(queue_key, reaction)
            queue_copy.push_reaction(queue_key, reaction)

            from neobot_app.emoji.mapping import lookup_emoji
            emoji_info = lookup_emoji(emoji_id)
            emoji_label = emoji_info[0] if emoji_info else f"#{emoji_id}"
            return f"已对消息{message_number}做出表情回应:{emoji_label}"

        def search_emoji_handler(keyword: str) -> str:
            from neobot_app.emoji.mapping import search_emoji

            results = search_emoji(keyword)
            if not results:
                return f"未找到与“{keyword}”相关的QQ表情"
            lines = [f"搜索“{keyword}”的结果："]
            for item in results:
                lines.append(f"  ID {item['id']}: {item['name']} ({item['hint']})")
            return "\n".join(lines)

        async def speak_handler(text: str) -> str:
            if self._tts_service is None:
                return "错误：TTS 服务未配置"
            segment = await asyncio.wait_for(
                self._tts_service.synthesize_segment(text),
                timeout=self._get_io_timeout_seconds(),
            )
            await self._send_with_timeout(event.conversation_ref, [segment])
            return f"语音消息已发送，内容：{text[:50]}{'...' if len(text) > 50 else ''}"

        async def poke_user_handler(user_id: int) -> str:
            if conv_kind == "group":
                result = await self._call_api_with_timeout(
                    "group_poke",
                    {
                        "group_id": int(conv_id),
                        "user_id": user_id,
                    },
                )
                return f"已在群{conv_id}中戳一戳 QQ:{user_id}" if self._api_succeeded(result) else f"群戳一戳失败: {result}"
            else:
                result = await self._call_api_with_timeout(
                    "friend_poke",
                    {
                        "user_id": user_id,
                    },
                )
                return f"已戳一戳好友 QQ:{user_id}" if self._api_succeeded(result) else f"好友戳一戳失败: {result}"

        conv_kind = event.conversation_ref.kind if event.conversation_ref else ""
        conv_id = event.conversation_ref.id if event.conversation_ref else ""
        reply_toolset = build_reply_toolset(
            send_reply_handler=send_reply_handler,
            willing_service=self._willing_service,
            numbering=numbering,
            send_emoji_handler=send_emoji_handler,
            emoji_service=self._emoji_service,
            agent_registry=self._agent_registry,
            wait_handler=wait_handler,
            react_emoji_handler=react_emoji_handler,
            search_emoji_handler=search_emoji_handler,
            cancel_handler=cancel_handler,
            tts_service=self._tts_service,
            speak_handler=speak_handler,
            poke_user_handler=poke_user_handler,
            drawing_manager=self._drawing_manager,
            scheduled_task_manager=self._scheduled_task_manager,
            notification_hub=self._notification_hub,
            chat_context=prompt,
            conv_kind=conv_kind,
            conv_id=conv_id,
            wait_cooldown_seconds=self._get_wait_cooldown_seconds(),
            ai_reply_check=self._get_ai_reply_check(),
            ai_reply_check_lightweight=self._get_ai_reply_check_lightweight(),
            bot_name=self._get_bot_name(),
            long_reply_fallback_template=self._get_long_reply_fallback_template(),
            long_reply_max_length=self._get_long_reply_max_length(),
            long_reply_max_sentence_count=self._get_long_reply_max_sentence_count(),
            enable_ai_reply_regenerate=self._get_enable_ai_reply_regenerate(),
            logger=self._logger,
        )

        tools = reply_toolset.definitions()

        # 5. Agent 循环（外层 while 支持私聊连续会话）
        max_iterations = 12
        ai_check_prompted = False
        is_private = (
            event.conversation_ref is not None
            and event.conversation_ref.kind == "private"
        )
        is_group = (
            event.conversation_ref is not None
            and event.conversation_ref.kind == "group"
        )
        silent_timeout = self._get_group_agent_silent_timeout_seconds() if is_group else 0.0
        silent_deadline = (
            monotonic_seconds() + silent_timeout
            if silent_timeout > 0
            else 0.0
        )

        def reset_silent_deadline(extra_seconds: float = 0.0) -> None:
            nonlocal silent_deadline
            if silent_timeout <= 0:
                return
            silent_deadline = monotonic_seconds() + silent_timeout + max(0.0, extra_seconds)

        def silent_remaining() -> float | None:
            if silent_timeout <= 0:
                return None
            return silent_deadline - monotonic_seconds()

        def cancel_for_silence(phase: str) -> None:
            event.error = (
                f"群聊 agent 管线静默超过 {silent_timeout:.0f} 秒，"
                f"已强制关闭（阶段：{phase}）"
            )
            try:
                event.transition(ReplyState.CANCELLED)
            except RuntimeError:
                pass
            self._logger.warning(
                "群聊 agent 管线静默超时，强制关闭",
                event_id=event.event_id,
                queue_key=queue_key,
                phase=phase,
                timeout_seconds=silent_timeout,
            )
            self._record_debug(
                "group_agent_silent_timeout",
                event,
                queue_key=queue_key,
                phase=phase,
                timeout_seconds=silent_timeout,
            )

        while True:
            reply_sent = False
            cancelled = False
            ai_check_prompted = False

            for iteration in range(max_iterations):
                if self._provider is None:
                    raise RuntimeError("未配置 chat provider，无法生成回复")

                pipeline_key = f"{conv_kind}:{conv_id}"
                notification_text = await self._poll_background_notifications(pipeline_key)
                if notification_text:
                    messages.append({"role": "user", "content": notification_text})
                    self._logger.info(
                        "注入后台通知",
                        event_id=event.event_id,
                        pipeline_key=pipeline_key,
                    )
                    self._record_debug(
                        "background_notification_injected",
                        event,
                        queue_key=queue_key,
                        notification=notification_text[:200],
                    )

                remaining = silent_remaining()
                if remaining is not None and remaining <= 0:
                    cancel_for_silence("before_model")
                    return
                try:
                    model_timeout = (
                        max(0.1, remaining)
                        if remaining is not None
                        else self._get_model_response_timeout_seconds(event)
                    )
                    response = await asyncio.wait_for(
                        self._provider.chat(messages, tools=tools if tools else None),
                        timeout=model_timeout,
                    )
                except asyncio.TimeoutError:
                    if remaining is not None:
                        cancel_for_silence("model")
                        return
                    event.error = "AI response timed out"
                    try:
                        event.transition(ReplyState.CANCELLED)
                    except RuntimeError:
                        pass
                    self._logger.warning(
                        "agent mode model call timed out",
                        event_id=event.event_id,
                        queue_key=queue_key,
                        timeout_seconds=self._get_model_response_timeout_seconds(event),
                    )
                    return
                reset_silent_deadline()
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
                    if not reply_sent:
                        content = response.get("content", "")
                        text = content.strip() if isinstance(content, str) else str(content)
                        if text:
                            full_check = self._get_ai_reply_check()
                            light_check = self._get_ai_reply_check_lightweight()
                            need_check = full_check
                            if not need_check and light_check:
                                pre_check = process_reply_text(
                                    text,
                                    bot_name=self._get_bot_name(),
                                    fallback_template=self._get_long_reply_fallback_template(),
                                    max_length=self._get_long_reply_max_length(),
                                    max_sentence_count=self._get_long_reply_max_sentence_count(),
                                )
                                need_check = pre_check.fallback_used
                            if need_check and not ai_check_prompted:
                                ai_check_prompted = True
                                check_prompt = self._build_ai_reply_check_prompt(text)
                                messages.append({"role": "user", "content": check_prompt})
                                self._record_debug(
                                    "ai_reply_check_requested",
                                    event,
                                    queue_key=queue_key,
                                    reply_text=text,
                                    check_prompt=check_prompt,
                                    check_mode="full" if full_check else "lightweight",
                                )
                                continue
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

                for tc in tool_calls:
                    name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    self._logger.info(
                        f"工具调用: {name}",
                        event_id=event.event_id,
                        tool=name,
                        args=str(args),
                    )
                    self._record_debug(
                        "tool_called",
                        event,
                        queue_key=queue_key,
                        iteration=iteration + 1,
                        tool_name=name,
                        tool_args=args,
                    )
                    wait_extra_seconds = 0.0
                    if name == "wait":
                        raw_seconds = args.get("seconds", 20)
                        try:
                            parsed_seconds = int(raw_seconds)
                        except (ValueError, TypeError):
                            parsed_seconds = 20
                        wait_extra_seconds = float(
                            max(1, min(parsed_seconds, self._get_max_wait_seconds()))
                        )
                    reset_silent_deadline(wait_extra_seconds)
                    try:
                        remaining = silent_remaining()
                        tool_timeout = (
                            max(0.1, remaining)
                            if remaining is not None
                            else max(
                                self._get_model_response_timeout_seconds(event),
                                wait_extra_seconds + self._get_dependency_timeout_seconds(),
                            )
                        )
                        result = await asyncio.wait_for(
                            reply_toolset.executor.execute(name, args),
                            timeout=tool_timeout,
                        )
                        tool_error = None
                    except asyncio.TimeoutError:
                        if remaining is not None:
                            cancel_for_silence(f"tool:{name}")
                            return
                        tool_error = f"TimeoutError: tool {name} timed out"
                        self._logger.warning(
                            "agent tool timed out",
                            event_id=event.event_id,
                            queue_key=queue_key,
                            tool=name,
                        )
                    except Exception as tool_exc:
                        result = None
                        tool_error = f"{type(tool_exc).__name__}: {tool_exc}"
                        self._logger.warning(
                            f"工具调用失败: {name}",
                            event_id=event.event_id,
                            tool=name,
                            error=tool_error,
                        )
                    if tool_error is not None:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": f"工具调用失败：{tool_error}",
                        })
                        self._record_debug(
                            "tool_failed",
                            event,
                            queue_key=queue_key,
                            iteration=iteration + 1,
                            tool_name=name,
                            tool_args=args,
                            tool_error=tool_error,
                        )
                    else:
                        self._logger.info(
                            f"工具返回: {name}",
                            event_id=event.event_id,
                            tool=name,
                            result=str(result),
                        )
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

                if reply_sent or cancelled:
                    break

                # 注入此期间的新消息
                previous_entries = queue_copy.entries(queue_key)
                new_entries = self._collect_new_entries(queue, queue_copy, queue_key)
                if new_entries:
                    new_text = numbering.apply_new(
                        new_entries,
                        queue_copy,
                        context_entries=queue_copy.entries(queue_key),
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

            # 保存编号映射（每轮更新）
            event.message_number_map = numbering.mapping

            # 不回复或取消 → 结束
            if not reply_sent or cancelled:
                break

            # 非私聊 → 结束
            if not is_private:
                break

            # Token 超限 → 结束（下次消息触发管线重启）
            if self._estimate_tokens(messages) >= self._get_private_chat_max_tokens():
                self._logger.info(
                    "私聊token超限，结束当前会话",
                    event_id=event.event_id,
                    queue_key=queue_key,
                    estimated_tokens=self._estimate_tokens(messages),
                )
                break

            # 私聊挂起，等待新消息或后台通知
            self._logger.debug(
                "私聊会话挂起等待新消息或通知",
                event_id=event.event_id,
                queue_key=queue_key,
            )
            new_entries, notification_text = await self._suspend_private_chat(
                queue, queue_copy, queue_key
            )
            if not new_entries and not notification_text:
                self._logger.debug(
                    "私聊挂起超时，结束会话",
                    event_id=event.event_id,
                    queue_key=queue_key,
                )
                break

            # 注入后台通知（视作新消息，结束挂起状态）
            if notification_text:
                messages.append({"role": "user", "content": notification_text})
                self._logger.info(
                    "注入后台通知（挂起期间）",
                    event_id=event.event_id,
                    queue_key=queue_key,
                )
                self._record_debug(
                    "background_notification_injected_during_suspend",
                    event,
                    queue_key=queue_key,
                    notification=notification_text[:200],
                )

            # 注入新消息，继续下一轮 agent 循环
            if new_entries:
                new_text = numbering.apply_new(
                    new_entries,
                    queue_copy,
                    context_entries=queue_copy.entries(queue_key),
                    previous_entries=[],
                )
                if new_text:
                    messages.append({
                        "role": "user",
                        "content": (
                            f"[收到新消息]\n{new_text}\n\n"
                            "这是私聊对话。如果对方话没有说完或可能还有更多内容，"
                            "请使用 wait 等待更多消息，不要直接结束对话。"
                            "如果对话已自然结束或对方明确表示结束，可以不再回复。"
                        ),
                    })
                    self._record_debug(
                        "private_chat_new_messages_injected",
                        event,
                        queue_key=queue_key,
                        injected_text=new_text,
                    )

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
        """收集源队列中比快照新的条目并更新快照。

        使用指纹集合比对，而非位置分割：
        - 指纹在 snapshot 中已存在 → 不是新条目（即使推送顺序与 message_id 顺序不一致）
        - 指纹不在 snapshot 中 → 新条目（支持队列驱逐后的安全回退）
        """
        from neobot_app.message.queue_impl import QueueEntryType

        source_entries = source.entries(queue_key)
        if not source_entries:
            return []

        snapshot_entries = snapshot.entries(queue_key)

        # 收集 snapshot 中所有条目的指纹
        snapshot_fingerprints: set[str] = set()
        for entry in snapshot_entries:
            fp = _entry_fingerprint(entry)
            if fp:
                snapshot_fingerprints.add(fp)

        # 在 source 中找出指纹不在 snapshot 中的新条目
        new_entries: list = []
        for entry in source_entries:
            fp = _entry_fingerprint(entry)
            if fp and fp in snapshot_fingerprints:
                continue  # 已存在于快照中
            new_entries.append(entry)

        snapshot.append_entries(queue_key, new_entries)

        return [
            entry for entry in new_entries
            if entry.kind == QueueEntryType.MESSAGE and entry.message is not None
        ]

    def _consume_ai_reply_blocked_entries(self, entries: list) -> list:
        if self._reply_block_registry is None:
            return entries
        consume = getattr(self._reply_block_registry, "consume_message", None)
        if not callable(consume):
            return entries
        kept = []
        for entry in entries:
            message = getattr(entry, "message", None)
            if message is not None and consume(message):
                self._logger.info("插件监听器已阻止挂起期间私聊消息触发 AI 回复")
                continue
            kept.append(entry)
        return kept

    async def _poll_background_notifications(self, pipeline_key: str) -> str | None:
        """轮询所有后台通知源，返回通知文本或 None。"""
        try:
            if self._notification_hub is not None:
                notification = await asyncio.wait_for(
                    self._notification_hub.poll(pipeline_key),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if notification:
                    return notification.content
                return None

            # 向后兼容：未迁移到统一通知中心的后台管理器
            if self._drawing_manager is not None:
                notification = await asyncio.wait_for(
                    self._drawing_manager.poll_notification(pipeline_key),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if notification:
                    return notification

            if self._scheduled_task_manager is not None:
                notification = await asyncio.wait_for(
                    self._scheduled_task_manager.poll_notification(pipeline_key),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if notification:
                    return notification
        except asyncio.TimeoutError:
            self._logger.warning(
                "background notification poll timed out",
                pipeline_key=pipeline_key,
                timeout_seconds=self._get_dependency_timeout_seconds(),
            )

        return None

    async def _suspend_private_chat(
        self,
        source: MessageQueue,
        snapshot: MessageQueue,
        queue_key: str,
    ) -> tuple[list, str | None]:
        """挂起等待私聊新消息或后台通知。

        首条消息后额外收集一段时间；后台通知会立即中断挂起。
        返回 (新消息条目列表, 通知文本或None)。
        """
        suspend_secs = self._get_private_chat_suspend_wait_seconds()
        collect_secs = self._get_private_chat_new_message_collect_seconds()
        deadline = monotonic_seconds() + suspend_secs
        first_new_time = 0.0
        all_new_entries: list = []
        notification_text: str | None = None

        self._logger.debug(
            "私聊挂起循环开始轮询",
            queue_key=queue_key,
            suspend_secs=suspend_secs,
            collect_secs=collect_secs,
        )
        pipeline_key = f"private:{queue_key}"

        while monotonic_seconds() < deadline:
            await asyncio.sleep(1.0)
            current_new: list = []
            try:
                current_new = self._collect_new_entries(source, snapshot, queue_key)
            except Exception as exc:
                self._logger.debug(
                    "私聊挂起收集新消息异常",
                    queue_key=queue_key,
                    error=str(exc),
                )
                continue
            if current_new:
                current_new = self._consume_ai_reply_blocked_entries(current_new)
            if current_new:
                if not all_new_entries:
                    first_new_time = monotonic_seconds()
                    self._logger.debug(
                        "私聊挂起检测到首条新消息",
                        queue_key=queue_key,
                        count=len(current_new),
                    )
                all_new_entries.extend(current_new)

            # 轮询后台通知，有通知立即中断挂起
            if notification_text is None:
                notification_text = await self._poll_background_notifications(pipeline_key)

            if notification_text:
                self._logger.debug(
                    "私聊挂起检测到后台通知，结束挂起",
                    queue_key=queue_key,
                )
                break

            if all_new_entries:
                elapsed_since_first = monotonic_seconds() - first_new_time
                if elapsed_since_first >= collect_secs:
                    self._logger.debug(
                        "私聊挂起收集窗口结束",
                        queue_key=queue_key,
                        total_new=len(all_new_entries),
                        elapsed=f"{elapsed_since_first:.1f}s",
                    )
                    break

        if all_new_entries:
            self._logger.debug(
                "私聊挂起收集到新消息",
                queue_key=queue_key,
                count=len(all_new_entries),
            )
        elif notification_text:
            self._logger.debug(
                "私聊挂起收到后台通知",
                queue_key=queue_key,
            )
        else:
            self._logger.debug(
                "私聊挂起超时未收到新消息或通知",
                queue_key=queue_key,
            )
        return all_new_entries, notification_text

    # ── Prompt 构建 ──

    async def _build_prompt(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
        numbering: MessageNumbering | None = None,
        last_reply_message_id: int | None = None,
        all_new: bool = False,
    ) -> str:
        # 等待该队列所有待处理的图片解析完成
        if self._image_parse_service is not None:
            image_wait_timeout = None
            if event.conversation_ref is not None and event.conversation_ref.kind == "group":
                image_wait_timeout = self._get_group_agent_silent_timeout_seconds()
            await self._image_parse_service.wait_for_queue(
                queue_key,
                timeout=image_wait_timeout,
            )

        event.transition(ReplyState.BUILDING_PROMPT)
        if event.conversation_ref is None:
            raise ValueError("ReplyEvent.conversation_ref is None")

        if event.conversation_ref.kind == "group":
            try:
                return await asyncio.wait_for(
                    self._prompt_builder.build_group_chat_prompt(
                        group_id=int(queue_key),
                        message_queue=queue,
                        numbering=numbering,
                        last_reply_message_id=last_reply_message_id,
                        all_new=all_new,
                    ),
                    timeout=self._get_prompt_timeout_seconds(),
                )
            except asyncio.TimeoutError:
                self._logger.warning(
                    "group prompt build timed out",
                    event_id=event.event_id,
                    queue_key=queue_key,
                    timeout_seconds=self._get_prompt_timeout_seconds(),
                )
                raise
        try:
            return await asyncio.wait_for(
                self._prompt_builder.build_friend_chat_prompt(
                    user_id=int(queue_key),
                    message_queue=queue,
                    numbering=numbering,
                    last_reply_message_id=last_reply_message_id,
                    all_new=all_new,
                ),
                timeout=self._get_prompt_timeout_seconds(),
            )
        except asyncio.TimeoutError:
            self._logger.warning(
                "private prompt build timed out",
                event_id=event.event_id,
                queue_key=queue_key,
                timeout_seconds=self._get_prompt_timeout_seconds(),
            )
            raise

    # ── LLM 生成 ──

    def _resolve_last_reply(
        self,
        queue: MessageQueue,
        queue_key: str,
    ) -> tuple[int | None, bool]:
        """Return (last_reply_message_id, all_new) for the given queue key.

        Returns (None, False) when tracking is disabled.
        Returns (None, True) when tracking is enabled but no position has been recorded.
        Returns (message_id, False) when a last-reply position exists.
        """
        enable_tracking = (
            getattr(getattr(self._config, "chat", None), "enable_last_reply_tracking", True)
            if self._config else True
        )
        if not enable_tracking:
            return None, False
        last_msg_id = queue.get_last_reply_position(queue_key)
        if last_msg_id is None:
            return None, True
        return last_msg_id, False

    async def _generate_reply(self, event: ReplyEvent, prompt: str) -> str:
        event.transition(ReplyState.GENERATING)
        if self._provider is None:
            raise RuntimeError("未配置 chat provider，无法生成回复")

        messages: list[dict[str, str]] = [
            {"role": "system", "content": prompt},
        ]
        timeout = self._get_model_response_timeout_seconds(event)
        try:
            response = await asyncio.wait_for(
                self._provider.chat(messages),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            event.error = f"AI response timed out after {timeout:.0f}s"
            self._logger.warning(
                "common mode model call timed out",
                event_id=event.event_id,
                timeout_seconds=timeout,
            )
            raise
        content = response.get("content", "")
        text = content.strip() if isinstance(content, str) else str(content)
        event.generated_text = text
        self._record_debug("reply_generated", event, reply_text=text, response=response)
        return text

    def _build_ai_reply_check_prompt(self, text: str) -> str:
        result = process_reply_text(
            text,
            bot_name=self._get_bot_name(),
            fallback_template=self._get_long_reply_fallback_template(),
            max_length=self._get_long_reply_max_length(),
            max_sentence_count=self._get_long_reply_max_sentence_count(),
        )
        lines = [
            "[AI回复检查]",
            "你刚才准备直接发送以下回复，但配置要求先检查切分后的分条回复。",
            f"原文：{result.original_text}",
            "切分结果：",
        ]
        for index, message in enumerate(result.messages, start=1):
            lines.append(f"{index}. {message}")
        if result.fallback_used:
            lines.append(f"注意：因 {result.reason or '未知原因'}，已触发默认回复替换，当前切分结果为默认回复文本。")
            if self._get_enable_ai_reply_regenerate():
                lines.append(
                    "默认回复不是你的原意，请重新生成一个更简短的版本（不超过"
                    f"{self._get_long_reply_max_length()}字符、不超过"
                    f"{self._get_long_reply_max_sentence_count()}条），"
                    "然后直接调用 send_reply 发送新文本，无需设置 ai_check_approved。"
                )
            else:
                lines.append(
                    "如确认使用当前默认回复，请调用 send_reply，传入原 text、"
                    "segments 为上述切分结果、ai_check_approved=true。"
                    "如不应发送任何回复，请调用 cancel。"
                )
        else:
            lines.append(
                "如果没有严重问题或歧义，请调用 send_reply，传入原 text、segments 为上述切分结果、ai_check_approved=true。"
            )
            lines.append(
                "如果切分有问题但仍要发送原文，请调用 send_reply 并设置 send_original=true；不应发送则调用 cancel。"
            )
        return "\n".join(lines)

    # ── 发送回复 ──

    async def _send_reply(
        self,
        event: ReplyEvent,
        text: str,
        reply_to_message_id: int | None = None,
        mention_user_ids: list[int] | None = None,
        segments: list[str] | None = None,
        send_original: bool = False,
    ) -> None:
        event.transition(ReplyState.SENDING)
        if event.conversation_ref is None:
            raise ValueError("ReplyEvent.conversation_ref is None")

        reply_messages = self._build_reply_messages(
            text,
            segments=segments,
            send_original=send_original,
        )
        send_results: list[object] = []
        formatted_messages: list[list[dict]] = []

        is_group = event.conversation_ref.kind == "group"
        pipeline_key = f"{event.conversation_ref.kind}:{event.conversation_ref.id}"

        for index, message_text in enumerate(reply_messages):
            if index > 0:
                if is_group:
                    cooldown = self._get_sentence_cooldown_seconds()
                else:
                    cooldown = self._get_private_chat_sentence_cooldown_seconds()
                last_time = self._last_sentence_time.get(pipeline_key, 0.0)
                elapsed = monotonic_seconds() - last_time
                if elapsed < cooldown:
                    await asyncio.sleep(cooldown - elapsed)

            formatted = self._build_reply_segments(
                text=message_text,
                conversation_kind=event.conversation_ref.kind,
                reply_to_message_id=reply_to_message_id if index == 0 else None,
                mention_user_ids=mention_user_ids if index == 0 else None,
            )
            formatted_messages.append(formatted)
            send_results.append(await self._send_with_timeout(event.conversation_ref, formatted))

            self._last_sentence_time[pipeline_key] = monotonic_seconds()

        event.send_response = send_results[0] if len(send_results) == 1 else send_results
        # 私聊连续会话：回到 GENERATING 等待下一轮；群聊/普通：直接完成
        if event.conversation_ref is not None and event.conversation_ref.kind == "private":
            event.transition(ReplyState.GENERATING)
        else:
            event.transition(ReplyState.COMPLETED)
        self._record_debug(
            "reply_sent",
            event,
            formatted=formatted_messages[0] if len(formatted_messages) == 1 else formatted_messages,
            reply_to_message_id=reply_to_message_id,
        )

    def _build_reply_messages(
        self,
        text: str,
        *,
        segments: list[str] | None = None,
        send_original: bool = False,
    ) -> list[str]:
        if send_original:
            return [text.strip()]
        if segments:
            cleaned_segments = [segment.strip() for segment in segments if segment.strip()]
            if cleaned_segments:
                return cleaned_segments
        result = process_reply_text(
            text,
            bot_name=self._get_bot_name(),
            fallback_template=self._get_long_reply_fallback_template(),
            max_length=self._get_long_reply_max_length(),
            max_sentence_count=self._get_long_reply_max_sentence_count(),
        )
        return result.messages

    @staticmethod
    def _build_reply_segments(
        *,
        text: str,
        conversation_kind: str,
        reply_to_message_id: int | None = None,
        mention_user_ids: list[int] | None = None,
    ) -> list[dict]:
        segments: list[dict] = []
        if mention_user_ids and conversation_kind == "group":
            for qq in mention_user_ids:
                segments.append({
                    "type": "at",
                    "data": {"qq": str(qq)},
                })

        if reply_to_message_id is not None:
            segments.append({"type": "reply", "data": {"id": str(reply_to_message_id)}})

        segments.append({"type": "text", "data": {"text": text}})
        return segments

    # ── 工具方法 ──

    @staticmethod
    def _api_succeeded(result: Any) -> bool:
        if result is None:
            return False
        if not isinstance(result, dict):
            return True
        status = result.get("status")
        if status is None:
            return True
        return status == "ok"

    @staticmethod
    def _build_conversation_ref(
        message: PrivateMessage | GroupMessage,
        queue_key: str,
    ) -> ConversationRef:
        from neobot_adapter.model.message import GroupMessage

        if isinstance(message, GroupMessage):
            return ConversationRef(kind="group", id=queue_key)
        # 处理合成的后台通知消息（非标准 GroupMessage/PrivateMessage 实例）
        msg_type = getattr(message, "message_type", "")
        if msg_type == "group":
            return ConversationRef(kind="group", id=queue_key)
        return ConversationRef(kind="private", id=queue_key)

    @staticmethod
    def _build_chat_context(event: ReplyEvent, queue_key: str) -> str | None:
        """构建当前聊天环境描述，注入给子 Agent。"""
        from neobot_adapter.model.message import GroupMessage

        message = event.message
        if message is None:
            return None

        sender_name = ""
        sender_id = ""
        if hasattr(message, "sender") and message.sender is not None:
            sender_name = (message.sender.card or message.sender.nickname or "").strip()
        if hasattr(message, "user_id") and message.user_id is not None:
            sender_id = str(message.user_id)

        msg_type = getattr(message, "message_type", "")
        if isinstance(message, GroupMessage) or msg_type == "group":
            group_id = getattr(message, "group_id", None) or queue_key
            lines = [
                "[当前聊天环境]",
                "会话类型：群聊",
                f"群号：{group_id}",
            ]
            if sender_name and sender_id:
                lines.append(f"消息发送者：{sender_name}（QQ：{sender_id}）")
            elif sender_id:
                lines.append(f"消息发送者QQ：{sender_id}")
            return "\n".join(lines)

        lines = [
            "[当前聊天环境]",
            "会话类型：私聊",
        ]
        if sender_name and sender_id:
            lines.append(f"聊天对象：{sender_name}（QQ：{sender_id}）")
        elif sender_id:
            lines.append(f"聊天对象QQ：{sender_id}")
        return "\n".join(lines)
