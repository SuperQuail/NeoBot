from __future__ import annotations

from neobot_app.agent_tools.invocation import human_message_entry, CURRENT_HUMAN_MESSAGE

import asyncio
import inspect
import time
from collections import deque
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List

from neobot_adapter import OneBotAdapter, Subscription
from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_adapter.model.notice import (
    EmojiReaction,
    GroupMessageDelete,
    GroupPoke,
    PrivateMessageDelete,
    PrivatePoke,
)
from neobot_adapter.utils.parse import safe_parse_model

from neobot_contracts.ports.logging import Logger, NullLogger

from neobot_app.config.schemas.bot import BotConfig
from neobot_app.image import ImageParseService
from neobot_app.message.process import event_message__to_text
from neobot_app.message.queue import MessageQueue
from neobot_app.reply import ReplyOrchestrator
from neobot_app.runtime.archive_memory_summary import ArchiveMemoryAutoSummaryService
from neobot_app.runtime.inbound_pipeline import InboundPipeline
from neobot_app.time_context import epoch_seconds
from neobot_app.user_profiles import UserProfileService
from neobot_app.willing import WillingService
from neobot_app.willing.models import WillingDecision


def _build_poke_action_text(
    raw_info: list | None,
    sender_name: str,
    target_name: str,
) -> str:
    """从 raw_info 构建完整的戳一戳动作文本，如 '唐天揉了揉弥音的脸'。

    raw_info 结构示例:
    [
        {"col": "0", ...},
        {"col": "1", ...},
        {"col": "2", "txt": "揉了揉"},   # 动作前缀
        {"col": "3", ...},               # 目标占位
        {"col": "4", "txt": "的脸"},     # 动作后缀
    ]
    """
    if not isinstance(raw_info, list) or not raw_info:
        return ""

    sender = sender_name or "QQ用户"
    target = target_name or "QQ用户"

    try:
        first_txt = ""
        second_txt = ""
        # raw_info[2] 是动作前缀，raw_info[4] 是动作后缀
        if len(raw_info) > 2 and isinstance(raw_info[2], dict):
            first_txt = str(raw_info[2].get("txt", "") or "")
        if len(raw_info) > 4 and isinstance(raw_info[4], dict):
            second_txt = str(raw_info[4].get("txt", "") or "")

        if first_txt:
            return f"{sender}{first_txt}{target}{second_txt}"
    except Exception:
        pass

    return ""


class EventPipeline:
    def __init__(
        self,
        adapter: OneBotAdapter,
        group_message_queue: MessageQueue,
        friend_message_queue: MessageQueue,
        profile_service: UserProfileService | None = None,
        willing_service: WillingService | None = None,
        reply_orchestrator: ReplyOrchestrator | None = None,
        image_parse_service: ImageParseService | None = None,
        inbound_pipeline: InboundPipeline | None = None,
        archive_summary_service: ArchiveMemoryAutoSummaryService | None = None,
        config: BotConfig | None = None,
        logger: Logger | None = None,
        reply_block_registry: Any | None = None,
        command_service: Any | None = None,
        credential_manager: Any | None = None,
        sleep_service: Any | None = None,
    ) -> None:
        self.adapter = adapter
        self._group_queue = group_message_queue
        self._friend_queue = friend_message_queue
        self._profile_service = profile_service
        self._willing_service = willing_service
        self._reply_orchestrator = reply_orchestrator
        self._image_parse_service = image_parse_service
        self._inbound_pipeline = inbound_pipeline
        self._archive_summary_service = archive_summary_service
        self._config = config
        self._logger = logger or NullLogger()
        self._reply_block_registry = reply_block_registry
        self._command_service = command_service
        self._credential_manager = credential_manager
        self._sleep_service = sleep_service
        self._subscriptions: List[Subscription] = []
        self._started = False
        self._warmed_up_friends: set[str] = set()
        self._warmup_lock = asyncio.Lock()
        self._replying_queues: set[str] = set()
        self._post_reply_willing: dict[str, list] = {}
        self._pending_image_willing: dict[str, list] = {}
        self._recent_message_ids: deque[int] = deque(maxlen=200)
        self._recent_message_ids_lock = asyncio.Lock()
        self._image_willing_locks: dict[str, asyncio.Lock] = {}
        self._background_tasks: set[asyncio.Task[None]] = set()
        self._stopping = False

    def start(self) -> None:
        if self._started:
            return

        self._stopping = False
        self._subscriptions = [
            self.adapter.subscribe(
                "message",
                self._handle_private_message,
                message_type="private",
            ),
            self.adapter.subscribe(
                "message",
                self._handle_group_message,
                message_type="group",
            ),
            self.adapter.subscribe(
                "notice",
                self._handle_notice,
            ),
            self.adapter.subscribe(
                "request",
                self._handle_request,
            ),
        ]
        self._started = True
        self._logger.info("实时事件管线已启动")

    def stop(self) -> None:
        self._stopping = True
        if self._started:
            for subscription in self._subscriptions:
                subscription.unsubscribe()
            self._subscriptions.clear()
            self._started = False
            self._logger.info("实时事件管线已停止")
        for task in list(self._background_tasks):
            task.cancel()

    async def flush_pending_summaries(self) -> None:
        """对所有未达到阈值但有待处理消息的计数器触发摘要。"""
        restore_scheduling = self._started and not self._stopping
        self._stopping = True
        try:
            await self._cancel_background_tasks()
            if self._archive_summary_service is not None:
                await self._archive_summary_service.flush_all()
        finally:
            if restore_scheduling:
                self._stopping = False

    def _track_background_task(
        self,
        task: asyncio.Task[None],
        *,
        label: str,
        context: dict[str, object] | None = None,
    ) -> None:
        if self._stopping:
            task.cancel()
        self._background_tasks.add(task)

        def _done(done_task: asyncio.Task[None]) -> None:
            self._background_tasks.discard(done_task)
            try:
                done_task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self._logger.warning(
                    f"{label} 后台任务失败",
                    error=str(exc),
                    **(context or {}),
                )

        task.add_done_callback(_done)

    async def _cancel_background_tasks(self) -> None:
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._background_tasks.clear()

    def _has_active_reply_pipeline(self, kind: str, queue_key: str) -> bool:
        if self._reply_orchestrator is None:
            return False
        is_active = getattr(self._reply_orchestrator, "is_pipeline_active", None)
        if callable(is_active):
            return bool(is_active(kind, queue_key))
        return False

    def _get_group_agent_silent_timeout_seconds(self) -> float:
        if self._config is not None:
            value = getattr(
                self._config.chat, "group_agent_silent_timeout_seconds", None
            )
            if isinstance(value, (int, float)):
                return max(0.0, float(value))
        return 60.0

    def _get_dependency_timeout_seconds(self) -> float:
        return 10.0

    async def _handle_inbound_raw_event(self, event: Dict[str, Any]) -> None:
        if self._inbound_pipeline is None:
            return
        try:
            await asyncio.wait_for(
                self._inbound_pipeline.handle_raw_event(event),
                timeout=self._get_dependency_timeout_seconds(),
            )
        except asyncio.TimeoutError:
            self._logger.warning(
                "入站处理管线超时",
                timeout_seconds=self._get_dependency_timeout_seconds(),
                event_type=event.get("post_type"),
                message_type=event.get("message_type"),
            )
        except Exception as exc:
            self._logger.warning(
                "入站处理管线失败",
                error=str(exc),
                event_type=event.get("post_type"),
                message_type=event.get("message_type"),
            )

    def _schedule_archive_summary(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        message_text: str,
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> None:
        if (
            self._stopping
            or self._archive_summary_service is None
            or not conversation_id
        ):
            return

        async def _run() -> None:
            await self._record_archive_summary(
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                message_text=message_text,
                sender_id=sender_id,
                sender_name=sender_name,
            )

        task = asyncio.create_task(_run())
        self._track_background_task(
            task,
            label="archive auto summary",
            context={
                "conversation_kind": conversation_kind,
                "conversation_id": conversation_id,
            },
        )

    async def _is_duplicate_message(
        self, message: PrivateMessage | GroupMessage
    ) -> bool:
        """按 message_id 对真实消息去重：断线重连重投的同一条消息直接丢弃。"""
        message_id = getattr(message, "message_id", None)
        if message_id is None:
            return False
        async with self._recent_message_ids_lock:
            if message_id in self._recent_message_ids:
                return True
            self._recent_message_ids.append(message_id)
        return False

    async def _handle_agent_tool_input(self, message: Any, *, kind: str, queue_key: str, queue: Any) -> bool:
        if self._is_bot_self(message) or not CURRENT_HUMAN_MESSAGE.get():
            return False
        handler = getattr(self._reply_orchestrator, "handle_agent_tool_input", None)
        if not inspect.iscoroutinefunction(handler):
            return False
        reply = await handler(message, kind=kind, queue_key=queue_key)
        if reply is None:
            return False
        queue.push(queue_key, message)
        queue.mark_command_consumed(queue_key, getattr(message, "message_id", None))
        self._start_command_sync_reply(message=message, queue=queue, queue_key=queue_key, background=reply)
        return True

    @human_message_entry
    async def handle_private_message_event(
        self,
        event: Dict[str, Any],
        *,
        skip_ai_reply: bool = False,
    ) -> None:
        message = safe_parse_model(event, PrivateMessage)
        if await self._is_duplicate_message(message):
            self._logger.debug(
                "重复消息已丢弃（message_id 去重）",
                message_id=message.message_id,
                user_id=message.user_id,
            )
            return
        queue_key = str(message.user_id or "")
        if await self._handle_agent_tool_input(message, kind="private", queue_key=queue_key, queue=self._friend_queue):
            return
        await self._handle_inbound_raw_event(event)
        replied_messages = await self._fetch_replied_messages(
            message, self._friend_queue, queue_key
        )

        # 命令系统处理:入队之前解析;命令命中则拦截回复管线并标记消息。
        # (私聊无需 @;未命中时消息按普通消息继续走管线)
        command_consumed = False
        command_background: str | None = None
        if self._command_service is not None:
            result = await self._command_service.handle_message(
                message, kind="private", queue_key=queue_key
            )
            if result is not None and result.consumed:
                command_consumed = True
                command_background = result.background

        # 消息始终入队(命令消息作为上下文保留),但命令消息打上"已消费"标记,
        # 挂起中的回复管线(_collect_new_entries)不会把它当作新消息再次注入回复
        self._friend_queue.push(queue_key, message, replied_messages=replied_messages)
        if command_consumed:
            self._friend_queue.mark_command_consumed(
                queue_key, getattr(message, "message_id", None)
            )

        await self._refresh_profile_for_message(message)
        if self._image_parse_service is not None:
            await self._image_parse_service.parse_message_images(message, queue_key)
        text = await event_message__to_text(message)
        self._schedule_archive_summary(
            conversation_kind="private",
            conversation_id=queue_key,
            message_text=text,
            sender_id=str(message.user_id or ""),
            sender_name=_sender_name(message),
        )
        if queue_key:
            await self._maybe_warmup_friend_chat(queue_key)
        self._logger.info(f"收到私聊消息: {text}")

        # 命令已消费:回复管线在此拦截(不再进入延迟回复/意愿判断);
        # sync_reply 命令额外以命令结果为背景触发回复管线
        if command_consumed:
            if command_background:
                self._start_command_sync_reply(
                    message=message, queue=self._friend_queue,
                    queue_key=queue_key, background=command_background,
                )
            return

        # 凭据签发:管理员发送凭据文本
        if self._credential_manager is not None and await self._try_issue_credential(
            message, kind="private", queue_key=queue_key,
            queue=self._friend_queue,
        ):
            return

        # Bot 自己的消息不触发回复
        if self._is_bot_self(message):
            return

        ai_reply_blocked = self._consume_ai_reply_block(message)
        if skip_ai_reply or ai_reply_blocked:
            self._logger.info(
                "插件监听器已阻止本条私聊消息触发 AI 回复", queue_key=queue_key
            )
            return

        await self._handle_private_reply(message=message, queue_key=queue_key)

    async def _handle_private_message(self, event: Dict[str, Any]) -> None:
        await self.handle_private_message_event(event)

    async def _maybe_warmup_friend_chat(self, user_id: str) -> None:
        if self._config is None:
            return
        if not getattr(self._config.chat, "private_chat_dynamic_warmup", True):
            return
        if user_id in self._warmed_up_friends:
            return

        async with self._warmup_lock:
            if user_id in self._warmed_up_friends:
                return
            count = getattr(self._config.chat, "private_chat_warmup_history_count", 100)
            self._logger.info("私聊动态预热开始", user_id=user_id, history_count=count)
            try:
                result = await asyncio.wait_for(
                    self.adapter.get_friend_msg_history(
                        user_id=int(user_id),
                        count=count,
                        reverse_order=False,
                    ),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if result and result.data and result.data.messages:
                    for msg in result.data.messages:
                        if isinstance(msg, tuple):
                            continue
                        try:
                            self._friend_queue.push(user_id, msg)
                        except Exception as exc:
                            self._logger.debug(
                                "预热推送消息失败",
                                user_id=user_id,
                                error=str(exc),
                            )
                    self._logger.info(
                        "私聊动态预热完成",
                        user_id=user_id,
                        message_count=len(result.data.messages),
                    )
            except asyncio.TimeoutError:
                self._logger.warning(
                    "私聊预热超时",
                    user_id=user_id,
                    timeout_seconds=self._get_dependency_timeout_seconds(),
                )
                return
            except Exception as exc:
                self._logger.warning(
                    "私聊动态预热失败",
                    user_id=user_id,
                    error=str(exc),
                )
                return
            self._warmed_up_friends.add(user_id)

    async def _handle_private_reply(self, message: Any, queue_key: str) -> None:
        """私聊直接触发回复（跳过意愿管理器），延迟指定秒数以收集后续消息。"""
        delay = 5.0
        if self._config is not None:
            val = getattr(self._config.chat, "private_chat_reply_delay_seconds", None)
            if isinstance(val, (int, float)) and val >= 0:
                delay = float(val)

        if delay > 0:
            self._logger.debug(
                "私聊延迟回复等待中", queue_key=queue_key, delay_seconds=delay
            )
            await asyncio.sleep(delay)

        if self._reply_orchestrator is None:
            return

        from neobot_app.willing.models import WillingDecision

        decision = WillingDecision(
            manager_name="private_direct",
            probability=1.0,
            should_reply=True,
            reasons=("私聊直接回复（跳过意愿管理器）",),
        )
        self._logger.info(
            "私聊触发回复",
            queue_key=queue_key,
            delay_seconds=delay,
        )
        self._reply_orchestrator.start_reply(
            message=message,
            queue=self._friend_queue,
            queue_key=queue_key,
            decision=decision,
        )

    @human_message_entry
    async def handle_group_message_event(
        self,
        event: Dict[str, Any],
        *,
        skip_ai_reply: bool = False,
    ) -> None:
        message = safe_parse_model(event, GroupMessage)
        if await self._is_duplicate_message(message):
            self._logger.debug(
                "重复消息已丢弃（message_id 去重）",
                message_id=message.message_id,
                group_id=message.group_id,
            )
            return
        queue_key = str(message.group_id or "")
        if await self._handle_agent_tool_input(message, kind="group", queue_key=queue_key, queue=self._group_queue):
            return
        await self._handle_inbound_raw_event(event)
        replied_messages = await self._fetch_replied_messages(
            message, self._group_queue, queue_key
        )

        # 命令系统处理:入队之前解析;命令命中则拦截回复管线并标记消息。
        # (允许 bot 自己触发,群聊需被 @bot;未命中时消息按普通消息继续走管线)
        command_consumed = False
        command_background: str | None = None
        if self._command_service is not None:
            result = await self._command_service.handle_message(
                message, kind="group", queue_key=queue_key
            )
            if result is not None and result.consumed:
                command_consumed = True
                command_background = result.background

        # 消息始终入队(命令消息作为上下文保留),但命令消息打上"已消费"标记,
        # 挂起中的回复管线(_collect_new_entries)不会把它当作新消息再次注入回复
        self._group_queue.push(queue_key, message, replied_messages=replied_messages)
        if command_consumed:
            self._group_queue.mark_command_consumed(
                queue_key, getattr(message, "message_id", None)
            )

        await self._refresh_profile_for_message(message)
        if self._image_parse_service is not None:
            await self._image_parse_service.parse_message_images(message, queue_key)
        text = await event_message__to_text(message)
        self._schedule_archive_summary(
            conversation_kind="group",
            conversation_id=queue_key,
            message_text=text,
            sender_id=str(message.user_id or ""),
            sender_name=_sender_name(message),
        )
        self._logger.info(f"收到群消息[{message.group_id or '未知'}]: {text}")

        # 命令已消费:回复管线在此拦截(不再进入意愿判断/回复触发);
        # sync_reply 命令额外以命令结果为背景触发回复管线
        if command_consumed:
            if command_background:
                self._start_command_sync_reply(
                    message=message, queue=self._group_queue,
                    queue_key=queue_key, background=command_background,
                )
            return

        # 凭据签发:管理员发送凭据文本
        if self._credential_manager is not None and await self._try_issue_credential(
            message, kind="group", queue_key=queue_key,
            queue=self._group_queue,
        ):
            return

        # Bot 自己的消息不触发回复
        if self._is_bot_self(message):
            return

        ai_reply_blocked = self._consume_ai_reply_block(message)
        if skip_ai_reply or ai_reply_blocked:
            self._logger.info(
                "插件监听器已阻止本条群消息触发 AI 回复", queue_key=queue_key
            )
            return

        # 如果当前正在回复中，新消息入 post-reply 队列，不计算意愿
        if queue_key in self._replying_queues:
            if self._has_active_reply_pipeline("group", queue_key):
                self._post_reply_willing.setdefault(queue_key, []).append(message)
                return
            self._logger.warning(
                "已清理过期的回复中队列状态",
                queue_key=queue_key,
                kind="group",
            )
            self._replying_queues.discard(queue_key)

        # 如果消息含图片，延迟意愿计算，等图片解析完成后处理
        if _message_has_images(message):
            self._pending_image_willing.setdefault(queue_key, []).append(message)
            task = asyncio.create_task(self._process_pending_image_willing(queue_key))
            self._track_background_task(
                task,
                label="pending image willingness",
                context={"queue_key": queue_key},
            )
            return

        await self._handle_willing_decision(
            message=message, queue=self._group_queue, queue_key=queue_key
        )

    async def _handle_group_message(self, event: Dict[str, Any]) -> None:
        await self.handle_group_message_event(event)

    async def _record_archive_summary(
        self,
        *,
        conversation_kind: str,
        conversation_id: str,
        message_text: str,
        sender_id: str | None = None,
        sender_name: str | None = None,
    ) -> None:
        if self._archive_summary_service is None or not conversation_id:
            return
        try:
            await self._archive_summary_service.record_message(
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                message_text=message_text,
                sender_id=sender_id,
                sender_name=sender_name,
            )
        except Exception as exc:
            self._logger.warning(
                "档案自动总结记录失败",
                conversation_kind=conversation_kind,
                conversation_id=conversation_id,
                error=str(exc),
            )

    async def _fetch_replied_messages(
        self,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
    ) -> list:
        replied_messages: list = []
        for message_id in _extract_reply_message_ids(message):
            existing = queue.find_by_message_id(queue_key, message_id)
            if existing is not None:
                replied_messages.append(existing)
                continue
            try:
                response = await asyncio.wait_for(
                    self.adapter.get_msg(message_id),
                    timeout=self._get_dependency_timeout_seconds(),
                )
            except asyncio.TimeoutError:
                self._logger.warning(
                    "获取被回复消息超时",
                    message_id=message_id,
                    queue_key=queue_key,
                    timeout_seconds=self._get_dependency_timeout_seconds(),
                )
                continue
            except Exception as exc:
                self._logger.debug(
                    "获取被回复消息失败",
                    message_id=message_id,
                    error=str(exc),
                )
                continue
            data = getattr(response, "data", None)
            if data is not None:
                replied_messages.append(data)
        return replied_messages

    async def _handle_willing_decision(
        self,
        *,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
    ) -> bool:
        if self._willing_service is None or not queue_key:
            return False

        conversation_type = "group" if isinstance(message, GroupMessage) else "private"
        chat_type = "群聊" if conversation_type == "group" else "私聊"

        # 睡眠拦截:睡眠期间群聊不触发回复事件(消息已入队);
        # 被@时唤醒并注入唤醒提示词回复;私聊不睡眠,不走本函数。
        if (
            getattr(self, "_sleep_service", None) is not None
            and self._sleep_service.is_sleeping()
        ):
            return await self._handle_sleeping_message(
                message=message,
                queue=queue,
                queue_key=queue_key,
                chat_type=chat_type,
            )

        # 被@时直接触发回复，跳过意愿计算
        if self._willing_service.is_at_mentioned(message):
            block_reason = self._willing_service.block_reason_for_message(
                message=message,
                queue_key=queue_key,
            )
            if block_reason:
                self._logger.info(
                    "回复意愿",
                    会话类型=chat_type,
                    会话ID=queue_key,
                    概率="0.000",
                    决策="不回复",
                    详情=f"原因: 已屏蔽: {block_reason}",
                )
                return False

            # 读取 @ 提及回复延迟配置
            delay = 5.0
            if self._config is not None:
                val = getattr(self._config.chat, "at_mention_reply_delay_seconds", None)
                if isinstance(val, (int, float)) and val >= 0:
                    delay = float(val)

            if delay > 0:
                self._logger.debug(
                    "群聊@提及延迟回复等待中",
                    queue_key=queue_key,
                    delay_seconds=delay,
                )
                await asyncio.sleep(delay)

            decision = WillingDecision(
                manager_name="Quail",
                probability=1.0,
                should_reply=True,
                reasons=("被@提及，直接触发回复",),
            )
            self._logger.info(
                "回复意愿",
                会话类型=chat_type,
                会话ID=queue_key,
                概率="1.000",
                决策="回复",
                详情="原因: 被@提及，直接触发",
            )
            if self._reply_orchestrator is not None:
                return self._start_reply_with_tracking(
                    message=message, queue=queue, queue_key=queue_key, decision=decision
                )
            return False

        try:
            decision = self._willing_service.evaluate(
                message=message,
                queue=queue,
                queue_key=queue_key,
            )
        except Exception as exc:
            self._logger.warning(
                "回复意愿计算失败",
                会话类型=chat_type,
                会话ID=queue_key,
                错误=str(exc),
            )
            return False

        detail = " | ".join(decision.reasons)
        self._logger.info(
            "回复意愿",
            会话类型=chat_type,
            会话ID=queue_key,
            概率=f"{decision.probability:.3f}",
            决策="回复" if decision.should_reply else "不回复",
            详情=detail,
        )

        if decision.should_reply and self._reply_orchestrator is not None:
            return self._start_reply_with_tracking(
                message=message, queue=queue, queue_key=queue_key, decision=decision
            )
        return False

    async def _handle_sleeping_message(
        self,
        *,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
        chat_type: str,
    ) -> bool:
        """睡眠中的群消息处理:仅被@可唤醒回复,其余消息只入队不触发回复。"""
        at_mentioned = (
            self._willing_service is not None
            and self._willing_service.is_at_mentioned(message)
        )
        if not at_mentioned:
            self._logger.info(
                "睡眠中,消息仅入队不触发回复",
                会话类型=chat_type,
                会话ID=queue_key,
            )
            return False

        # 硬性屏蔽优先于唤醒:被屏蔽的会话即使@也不回复
        if self._willing_service is not None:
            block_reason = self._willing_service.block_reason_for_message(
                message=message,
                queue_key=queue_key,
            )
            if block_reason:
                self._logger.info(
                    "回复意愿",
                    会话类型=chat_type,
                    会话ID=queue_key,
                    概率="0.000",
                    决策="不回复",
                    详情=f"原因: 已屏蔽: {block_reason}",
                )
                return False

        # 被@唤醒:结束睡眠并注入唤醒提示词回复
        self._sleep_service.wake(reason="at_mention_event")
        delay = 5.0
        if self._config is not None:
            val = getattr(self._config.chat, "at_mention_reply_delay_seconds", None)
            if isinstance(val, (int, float)) and val >= 0:
                delay = float(val)
        if delay > 0:
            self._logger.debug(
                "睡眠中被@唤醒,延迟回复等待中",
                queue_key=queue_key,
                delay_seconds=delay,
            )
            await asyncio.sleep(delay)

        decision = WillingDecision(
            manager_name="wake_up",
            probability=1.0,
            should_reply=True,
            reasons=("睡眠中被@唤醒,直接回复",),
        )
        self._logger.info(
            "回复意愿",
            会话类型=chat_type,
            会话ID=queue_key,
            概率="1.000",
            决策="回复",
            详情="原因: 睡眠中被@唤醒,注入唤醒提示词",
        )
        if self._reply_orchestrator is None:
            return False
        return self._start_reply_with_tracking(
            message=message,
            queue=queue,
            queue_key=queue_key,
            decision=decision,
            background_content=self._sleep_service.wake_prompt(),
        )

    def _start_reply_with_tracking(
        self,
        *,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
        decision: WillingDecision,
        background_content: str | None = None,
    ) -> bool:
        """发起回复并设置回复状态追踪与完成后回调。"""
        if self._reply_orchestrator is None:
            return False

        pre_reply_msg_id = queue.get_last_message_id(queue_key)
        self._replying_queues.add(queue_key)

        # 群聊寿命机制：寿命>0时，回复后队列由管线挂起循环处理，
        # 管线结束时直接丢弃_避免唤起新回复管线
        _use_lifespan = False
        if isinstance(message, GroupMessage) and self._config is not None:
            lifespan = getattr(self._config.chat, "group_chat_reply_lifespan", 0)
            _use_lifespan = isinstance(lifespan, int) and lifespan > 0

        async def on_reply_done() -> None:
            self._replying_queues.discard(queue_key)
            if _use_lifespan:
                # 寿命机制下不处理回复后队列：消息已在挂起循环中处理
                self._post_reply_willing.pop(queue_key, None)
                return
            await self._process_post_reply_queue(queue_key)

        event = self._reply_orchestrator.start_reply(
            message=message,
            queue=queue,
            queue_key=queue_key,
            decision=decision,
            pre_reply_message_id=pre_reply_msg_id,
            on_reply_done=on_reply_done,
            background_content=background_content,
        )
        if event is None:
            self._replying_queues.discard(queue_key)
            return False
        return True

    @asynccontextmanager
    async def _image_willing_lock(self, queue_key: str) -> AsyncIterator[asyncio.Lock]:
        """按 queue_key 分片的图片意愿处理锁：只保护取列表/清理阶段。"""
        while True:
            lock = self._image_willing_locks.get(queue_key)
            if lock is None:
                lock = asyncio.Lock()
                self._image_willing_locks[queue_key] = lock
            await lock.acquire()
            if self._image_willing_locks.get(queue_key) is lock:
                break
            lock.release()
        try:
            yield lock
        finally:
            if self._image_willing_locks.get(queue_key) is lock:
                del self._image_willing_locks[queue_key]
            lock.release()

    async def _process_pending_image_willing(self, queue_key: str) -> None:
        """等待图片解析完成，然后按序处理待处理队列。若触发回复则清空剩余。"""
        try:
            if self._image_parse_service is not None:
                await self._image_parse_service.wait_for_queue(
                    queue_key,
                    timeout=self._get_group_agent_silent_timeout_seconds(),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # 等待失败也必须继续往下走：旧实现直接抛出会让 pending 列表既不
            # 被取出也不被处理，这些消息会永久滞留（不再触发回复）。
            self._logger.warning(
                "等待图片解析失败，继续处理待处理消息",
                queue_key=queue_key,
                error=str(exc),
            )

        async with self._image_willing_lock(queue_key):
            pending = self._pending_image_willing.pop(queue_key, [])
        if not pending:
            return

        for msg in pending:
            if (
                queue_key in self._replying_queues
                and not self._has_active_reply_pipeline("group", queue_key)
            ):
                self._logger.warning(
                    "已清理过期的回复中队列状态",
                    queue_key=queue_key,
                    kind="group",
                )
                self._replying_queues.discard(queue_key)
            if queue_key in self._replying_queues:
                # 已在回复中，剩余消息放入 post-reply 队列
                idx = pending.index(msg)
                if idx >= 0:
                    self._post_reply_willing.setdefault(queue_key, []).extend(
                        pending[idx:]
                    )
                break

            triggered = await self._handle_willing_decision(
                message=msg, queue=self._group_queue, queue_key=queue_key
            )
            if triggered:
                break

    async def _process_post_reply_queue(self, queue_key: str) -> None:
        """回复结束后依次处理期间收到的新消息。"""
        pending = self._post_reply_willing.pop(queue_key, [])
        if not pending:
            return

        timeout = 60.0
        if self._config is not None:
            val = getattr(self._config.chat, "post_reply_message_timeout_seconds", None)
            if isinstance(val, (int, float)) and val >= 0:
                timeout = float(val)

        self._logger.info(
            "开始处理回复后队列",
            queue_key=queue_key,
            count=len(pending),
        )

        for msg in pending:
            if (
                queue_key in self._replying_queues
                and not self._has_active_reply_pipeline("group", queue_key)
            ):
                self._logger.warning(
                    "已清理过期的回复中队列状态",
                    queue_key=queue_key,
                    kind="group",
                )
                self._replying_queues.discard(queue_key)
            if queue_key in self._replying_queues:
                self._post_reply_willing.setdefault(queue_key, []).extend(
                    pending[pending.index(msg) :]
                )
                return

            if timeout > 0 and self._is_message_stale(msg, timeout):
                self._logger.debug(
                    "回复后队列消息超时跳过",
                    queue_key=queue_key,
                    msg_time=getattr(msg, "time", None),
                )
                continue

            if _message_has_images(msg):
                self._pending_image_willing.setdefault(queue_key, []).append(msg)
                await self._process_pending_image_willing(queue_key)
            else:
                await self._handle_willing_decision(
                    message=msg, queue=self._group_queue, queue_key=queue_key
                )

    async def _refresh_profile_for_message(
        self,
        message: PrivateMessage | GroupMessage,
    ) -> None:
        if self._profile_service is None or message.user_id is None:
            return

        observed_fields: dict[str, Any] = {}
        if message.sender is not None:
            if message.sender.nickname:
                observed_fields["nick_name"] = message.sender.nickname
            if message.sender.sex is not None:
                observed_fields["sex"] = getattr(
                    message.sender.sex, "value", message.sender.sex
                )

        try:
            await asyncio.wait_for(
                self._profile_service.ensure_user_profile(
                    str(message.user_id),
                    observed_fields=observed_fields,
                ),
                timeout=self._get_dependency_timeout_seconds(),
            )
        except asyncio.TimeoutError:
            self._logger.warning(
                "刷新用户资料超时",
                user_id=message.user_id,
                timeout_seconds=self._get_dependency_timeout_seconds(),
            )
        except Exception as exc:
            self._logger.warning(
                "刷新消息发送者资料失败",
                user_id=message.user_id,
                error=str(exc),
            )

    async def _handle_notice(self, event: Dict[str, Any]) -> None:
        notice_type = event.get("notice_type", "未知")
        sub_type = event.get("sub_type", "")
        label = f"{notice_type}" + (f".{sub_type}" if sub_type else "")
        if notice_type in {"private_message_delete", "friend_recall"}:
            notice = safe_parse_model(event, PrivateMessageDelete)
            queue_key = str(notice.user_id or "")
            if queue_key:
                self._friend_queue.push_notice(queue_key, notice)
        elif notice_type in {"group_message_delete", "group_recall"}:
            notice = safe_parse_model(event, GroupMessageDelete)
            queue_key = str(notice.group_id or "")
            if queue_key:
                self._group_queue.push_notice(queue_key, notice)
        elif notice_type == "message_reaction":
            await self._handle_reaction_notice(event)
        elif notice_type == "notify" and sub_type == "poke":
            await self._handle_poke_notice(event)

        # 构建详情
        details: list[str] = []
        for key in (
            "user_id",
            "operator_id",
            "sender_id",
            "target_id",
            "group_id",
            "message_id",
            "file",
            "duration",
            "honor_type",
            "title",
            "card_new",
            "card_old",
            "emoji_id",
        ):
            val = event.get(key)
            if val is not None:
                details.append(f"{key}={val}")

        info = " ".join(details)
        self._logger.info(f"收到通知[{label}] {info}".rstrip())

    async def _handle_reaction_notice(self, event: Dict[str, Any]) -> None:
        from neobot_app.message.queue import ReactionEntry

        notice = safe_parse_model(event, EmojiReaction)
        if notice.message_id is None or notice.emoji_id is None:
            return

        group_id = notice.group_id or event.get("group_id")
        user_id = notice.user_id or event.get("user_id")
        if group_id is not None:
            queue_key = str(group_id)
            queue = self._group_queue
        elif user_id is not None:
            queue_key = str(user_id)
            queue = self._friend_queue
        else:
            return

        operator_name = f"QQ:{user_id}" if user_id is not None else "未知用户"
        if user_id is not None and self._profile_service is not None:
            try:
                profile = await asyncio.wait_for(
                    self._profile_service.get_user(str(user_id)),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if profile is not None and getattr(profile, "nick_name", None):
                    operator_name = profile.nick_name
            except asyncio.TimeoutError:
                self._logger.warning(
                    "表情回应用户资料查询超时",
                    user_id=user_id,
                    timeout_seconds=self._get_dependency_timeout_seconds(),
                )
            except Exception:
                pass

        queue.push_reaction(
            queue_key,
            ReactionEntry(
                target_message_id=notice.message_id,
                emoji_id=notice.emoji_id,
                operator_user_id=user_id or 0,
                operator_name=operator_name,
            ),
        )

    async def _handle_poke_notice(self, event: Dict[str, Any]) -> None:
        from neobot_app.message.queue import PokeEntry

        group_id = event.get("group_id")
        if group_id is not None:
            notice = safe_parse_model(event, GroupPoke)
            queue_key = str(notice.group_id or group_id)
            queue = self._group_queue
            sender_id = notice.user_id or 0
            target_id = notice.target_id or 0
            resolved_group_id = notice.group_id or int(group_id)

            sender_name = await self._resolve_name(
                sender_id, group_id=resolved_group_id
            )
            target_name = await self._resolve_name(
                target_id, group_id=resolved_group_id
            )
            action_text = _build_poke_action_text(
                event.get("raw_info"), sender_name, target_name
            )

            poke = PokeEntry(
                sender_id=sender_id,
                user_id=sender_id,
                target_id=target_id,
                sub_type=getattr(notice.sub_type, "value", "poke")
                if notice.sub_type
                else "poke",
                group_id=resolved_group_id,
                sender_name=sender_name,
                target_name=target_name,
                action_text=action_text,
            )
        else:
            notice = safe_parse_model(event, PrivatePoke)
            queue_key = str(notice.user_id or "")
            queue = self._friend_queue
            sender_id = notice.sender_id or notice.user_id or 0
            target_id = notice.target_id or 0

            sender_name = await self._resolve_name(sender_id, group_id=None)
            target_name = await self._resolve_name(target_id, group_id=None)
            action_text = _build_poke_action_text(
                event.get("raw_info"), sender_name, target_name
            )

            poke = PokeEntry(
                sender_id=sender_id,
                user_id=notice.user_id or 0,
                target_id=target_id,
                sub_type=getattr(notice.sub_type, "value", "poke")
                if notice.sub_type
                else "poke",
                group_id=None,
                sender_name=sender_name,
                target_name=target_name,
                action_text=action_text,
            )

        if queue_key:
            queue.push_poke(queue_key, poke)

    async def _resolve_name(self, user_id: int, group_id: int | None = None) -> str:
        """解析用户的显示名称。

        优先级：
        1. 数据库（user_profiles.nick_name / remark）
        2. API：群聊取群成员信息（card > nickname），私聊取陌生人信息
        3. 兜底返回 QQ:xxx
        """
        if not user_id:
            return ""

        # 1. Try database first
        if self._profile_service is not None:
            try:
                profile = await asyncio.wait_for(
                    self._profile_service.get_user(str(user_id)),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if profile is not None:
                    remark = getattr(profile, "remark", None)
                    nick_name = getattr(profile, "nick_name", None)
                    if remark:
                        return str(remark)
                    if nick_name:
                        return str(nick_name)
            except asyncio.TimeoutError:
                self._logger.warning(
                    "解析名称时用户资料查询超时",
                    user_id=user_id,
                    timeout_seconds=self._get_dependency_timeout_seconds(),
                )
            except Exception:
                pass

        # 2. API fallback
        if group_id is not None:
            try:
                resp = await asyncio.wait_for(
                    self.adapter.get_group_member_info(group_id, user_id),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if resp and resp.data:
                    return (
                        resp.data.card
                        or resp.data.nickname
                        or resp.data.card_or_nickname
                        or f"QQ:{user_id}"
                    )
            except asyncio.TimeoutError:
                self._logger.warning(
                    "解析群成员名称超时",
                    group_id=group_id,
                    user_id=user_id,
                    timeout_seconds=self._get_dependency_timeout_seconds(),
                )
            except Exception:
                pass
        else:
            try:
                resp = await asyncio.wait_for(
                    self.adapter.get_stranger_info(user_id),
                    timeout=self._get_dependency_timeout_seconds(),
                )
                if resp and resp.data:
                    return resp.data.nickname or f"QQ:{user_id}"
            except asyncio.TimeoutError:
                self._logger.warning(
                    "解析陌生人名称超时",
                    user_id=user_id,
                    timeout_seconds=self._get_dependency_timeout_seconds(),
                )
            except Exception:
                pass

        return f"QQ:{user_id}"

    async def _handle_request(self, event: Dict[str, Any]) -> None:
        request_type = event.get("request_type", "未知")
        sub_type = event.get("sub_type", "")
        label = f"{request_type}" + (f".{sub_type}" if sub_type else "")

        details: list[str] = []
        for key in ("user_id", "group_id", "comment", "flag"):
            val = event.get(key)
            if val is not None:
                details.append(f"{key}={val}")

        info = " ".join(details)
        self._logger.info(f"收到请求[{label}] {info}".rstrip())

    def _consume_ai_reply_block(self, message: PrivateMessage | GroupMessage) -> bool:
        if self._reply_block_registry is None:
            return False
        consume = getattr(self._reply_block_registry, "consume_message", None)
        if not callable(consume):
            return False
        return bool(consume(message))

    def _start_command_sync_reply(
        self,
        *,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
        background: str,
    ) -> None:
        """sync_reply 命令:命令结果作为背景内容触发回复管线。"""
        if self._reply_orchestrator is None:
            return
        from neobot_app.willing.models import WillingDecision

        decision = WillingDecision(
            manager_name="command",
            probability=1.0,
            should_reply=True,
            reasons=("command_sync_reply",),
        )
        pre_reply_msg_id = queue.get_last_message_id(queue_key)
        self._replying_queues.add(queue_key)

        async def on_reply_done() -> None:
            self._replying_queues.discard(queue_key)
            await self._process_post_reply_queue(queue_key)

        started = self._reply_orchestrator.start_reply(
            message=message,
            queue=queue,
            queue_key=queue_key,
            decision=decision,
            pre_reply_message_id=pre_reply_msg_id,
            on_reply_done=on_reply_done,
            background_content=background,
        )
        if started is None:
            # 管线被拒（编排器已关闭／同会话管线在跑／冷却中）：on_reply_done 永远
            # 不会被调用，必须自己回滚刚打上的标记，否则该会话会永久留在
            # _replying_queues 里——命令的 sync_reply 结果再也不会投递，
            # 后续新消息也一律被当「回复中」处理。
            self._replying_queues.discard(queue_key)
            self._logger.debug(
                "命令同步回复未能启动，已回滚回复中标记", queue_key=queue_key
            )

    async def _try_issue_credential(
        self,
        message: PrivateMessage | GroupMessage,
        *,
        kind: str,
        queue_key: str,
        queue: MessageQueue,
    ) -> bool:
        """检查消息是否为待签发凭据文本;是则签发并返回 True(已处理)。"""
        credential_manager = self._credential_manager
        if credential_manager is None:
            return False
        issuer_id = int(getattr(message, "user_id", 0) or 0)
        bot_account = self._bot_account_id()
        # bot 自己发送的消息不能触发自我签发(防审批失效)
        if bot_account and issuer_id == bot_account:
            return False
        # 使用纯文本内容匹配(不含"发送者: "前缀)
        text = _credential_message_text(message)
        text = text.strip()
        if not text:
            return False
        self._maybe_cleanup_credentials()
        chat_flow = f"{kind}:{queue_key}"
        issue = credential_manager.try_issue(
            chat_flow=chat_flow,
            code=text,
            issuer_id=issuer_id,
        )
        if not issue.ok:
            if issue.error == "permission_denied" and issue.credential is not None:
                # 权限不足:明确拒绝,避免 AI 误回复
                await self._send_credential_notice(
                    message, queue, queue_key,
                    "该凭据需要更高级别的管理员签发,你没有权限。",
                )
                return True
            return False  # 非凭据文本(not_found/expired/状态异常):正常管线
        credential = issue.credential
        if credential is None:
            return False
        # 仅首次签发(pending → active)时通知并触发 bot 继续执行;
        # 重复发送(幂等)静默,避免任意成员反复触发
        if issue.newly_issued:
            await self._send_credential_notice(
                message, queue, queue_key,
                f"凭据已确认(用途: {credential.action}),可以执行对应操作了。",
            )
            background = (
                "<这是新的必须要回答的内容>\n"
                f"凭据已签发: 用途 {credential.action},会话 {chat_flow}。\n"
                "如正在等待此凭据执行风险操作(踢人/退群等),现在可以继续执行。\n"
                "</这是新的必须要回答的内容>"
            )
            self._start_command_sync_reply(
                message=message, queue=queue, queue_key=queue_key, background=background,
            )
        return True

    def _bot_account_id(self) -> int:
        if self._config is None:
            return 0
        try:
            return int(getattr(self._config.bot, "account", 0) or 0)
        except (TypeError, ValueError):
            return 0

    def _maybe_cleanup_credentials(self) -> None:
        """定期清理过期/已用凭据(避免内存无界增长)。"""
        credential_manager = self._credential_manager
        if credential_manager is None:
            return
        now = time.time()
        if now - getattr(self, "_last_credential_cleanup", 0.0) < 60.0:
            return
        self._last_credential_cleanup = now
        try:
            credential_manager.cleanup()
        except Exception:
            pass

    async def _send_credential_notice(
        self,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
        text: str,
    ) -> None:
        """发送凭据相关提示(不触发 AI 回复)。"""
        from neobot_contracts.models import ConversationRef

        conv_ref = ConversationRef(
            kind="group" if isinstance(message, GroupMessage) else "private",
            id=queue_key,
        )
        try:
            await self.adapter.send(
                conv_ref, [{"type": "text", "data": {"text": text}}]
            )
        except Exception as exc:
            self._logger.warning(f"凭据提示发送失败: {exc}")

    def _is_bot_self(self, message) -> bool:
        """检查消息是否由 Bot 自己发送。"""
        if self._config is None:
            return False
        bot_account = self._config.bot.account
        if not bot_account:
            return False
        msg_user_id = getattr(message, "user_id", None)
        if msg_user_id is None:
            return False
        return int(msg_user_id) == int(bot_account)

    @staticmethod
    def _is_message_stale(message, timeout_seconds: float) -> bool:
        """检查消息时间戳是否超过超时秒数。"""
        msg_time = getattr(message, "time", None)
        if msg_time is None:
            return False
        return epoch_seconds() - int(msg_time) > timeout_seconds


def _extract_reply_message_ids(message: PrivateMessage | GroupMessage) -> list[int]:
    ids: list[int] = []
    for segment in getattr(message, "message", None) or []:
        segment_type = getattr(segment, "type", None)
        if hasattr(segment_type, "value"):
            segment_type = segment_type.value
        if str(segment_type) != "reply":
            continue
        raw_data = getattr(segment, "data", None)
        if isinstance(raw_data, dict):
            data = raw_data
        elif hasattr(raw_data, "model_dump"):
            data = raw_data.model_dump(exclude_none=True)
        else:
            data = {}
        message_id = _safe_int(data.get("id"))
        if message_id is not None and message_id not in ids:
            ids.append(message_id)
    return ids


def _sender_name(message: PrivateMessage | GroupMessage) -> str:
    sender = getattr(message, "sender", None)
    if sender is not None:
        for field in ("card", "nickname"):
            value = getattr(sender, field, None)
            if value:
                return str(value)
    user_id = getattr(message, "user_id", None)
    return f"QQ:{user_id}" if user_id is not None else ""


def _credential_message_text(message: PrivateMessage | GroupMessage) -> str:
    """提取消息的纯文本内容(不含"发送者: "前缀,用于凭据匹配)。

    注意:event_message__to_text 会拼接发送者名前缀,凭据文本匹配必须
    使用纯文本段拼接,否则签发永远无法命中。
    """
    parts: list[str] = []
    segments = getattr(message, "message", None)
    if not segments:
        return ""
    for segment in segments:
        segment_type = getattr(segment, "type", None)
        segment_type = getattr(segment_type, "value", segment_type)
        if str(segment_type or "") != "text":
            continue
        data = getattr(segment, "data", None)
        if isinstance(data, dict):
            text = data.get("text")
        else:
            text = getattr(data, "text", None)
        if text:
            parts.append(str(text))
    return "".join(parts)


def _safe_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _message_has_images(message: PrivateMessage | GroupMessage) -> bool:
    """检查消息是否包含图片段（image 或 cardimage）。"""
    segments = getattr(message, "message", None)
    if not segments:
        return False
    for seg in segments:
        seg_type = getattr(seg, "type", None)
        if hasattr(seg_type, "value"):
            seg_type = seg_type.value
        if str(seg_type or "") in ("image", "cardimage"):
            return True
    return False
