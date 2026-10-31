"""事件流水线的公开入口：实现按职责拆到 pipeline_parts/，本模块只保留门面。"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Any
from neobot_adapter import OneBotAdapter
from neobot_adapter.model.message import GroupMessage
from neobot_adapter.model.message import PrivateMessage
from neobot_contracts.ports.logging import Logger
from neobot_contracts.ports.logging import NullLogger
from neobot_app.config.schemas.bot import BotConfig
from neobot_app.image import ImageParseService
from neobot_app.message.queue import MessageQueue
from neobot_app.reply import ReplyOrchestrator
from neobot_app.runtime.archive_memory_summary import ArchiveMemoryAutoSummaryService
from neobot_app.runtime.inbound_pipeline import InboundPipeline
from neobot_app.user_profiles import UserProfileService
from neobot_app.willing import WillingService
from neobot_app.willing.models import WillingDecision

from .pipeline_parts.helpers import (
    _build_poke_action_text as _build_poke_action_text,
    _extract_reply_message_ids as _extract_reply_message_ids,
    _sender_name as _sender_name,
    _credential_message_text as _credential_message_text,
    _safe_int as _safe_int,
    _message_has_images as _message_has_images,
)
from .pipeline_parts.lifecycle import _PipelineLifecycleMixin
from .pipeline_parts.private import _PipelinePrivateMixin
from .pipeline_parts.group import _PipelineGroupMixin
from .pipeline_parts.willing import _PipelineWillingMixin
from .pipeline_parts.notice import _PipelineNoticeMixin
from .pipeline_parts.credential import _PipelineCredentialMixin

__all__ = [
    "EventPipeline",
]


class EventPipeline(
    _PipelineLifecycleMixin,
    _PipelinePrivateMixin,
    _PipelineGroupMixin,
    _PipelineWillingMixin,
    _PipelineNoticeMixin,
    _PipelineCredentialMixin,
):
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
        standby_service: Any | None = None,
        avatar_store: Any | None = None,
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
        # 待机状态：命令已在上游处理完，这里丢弃后续回复与记忆管线。
        # 旧实现漏了这行赋值，导致丢弃门在生产装配下恒不生效（只有测试手工赋值才通过）。
        self._standby_service = standby_service
        self._credential_manager = credential_manager
        self._sleep_service = sleep_service
        # 本体级头像存储（spec(5) §4.9 / R34）：消息路径只做过期判定并触发后台下载。
        self._avatar_store = avatar_store
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
        if getattr(self, "_sleep_service", None) is not None and self._sleep_service.is_sleeping():
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
                self._logger.debug(
                    "回复意愿判定",
                    event="reply.decided",
                    chat_flow_id=f"{conversation_type}:{queue_key}",
                    message_id=message.message_id,
                    conversation_kind=conversation_type,
                    conversation_id=queue_key,
                    probability=0.0,
                    should_reply=False,
                    reasons=f"原因: 已屏蔽: {block_reason}",
                )
                return False

            # 读取 @ 提及回复延迟配置（默认 0：被 @ 立即回复，等待交给模型自己决定）
            delay = 0.0
            if self._config is not None:
                val = getattr(self._config.chat, "at_mention_reply_delay_seconds", None)
                if isinstance(val, (int, float)) and val >= 0:
                    delay = float(val)

            # 正文命中插件登记的玩法关键词（漂流瓶 / 签到 / 抽签 …）时，
            # 意图已经足够明确，不再等这几秒收集上下文，直接触发回复事件
            instant_keyword = self._at_mention_instant_keyword(message)
            if instant_keyword:
                self._logger.info(
                    "群聊@提及命中关键词，跳过收集等待",
                    queue_key=queue_key,
                    keyword=instant_keyword,
                    delay_seconds=delay,
                )
            elif delay > 0:
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
            self._logger.debug(
                "回复意愿判定",
                event="reply.decided",
                chat_flow_id=f"{conversation_type}:{queue_key}",
                message_id=message.message_id,
                conversation_kind=conversation_type,
                conversation_id=queue_key,
                probability=1.0,
                should_reply=True,
                reasons="原因: 被@提及，直接触发",
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
                "回复意愿计算失败，本条消息未触发回复",
                event="reply.decision_failed",
                chat_flow_id=f"{conversation_type}:{queue_key}",
                message_id=message.message_id,
                error_type=type(exc).__name__,
                conversation_kind=conversation_type,
                conversation_id=queue_key,
                error=str(exc),
            )
            return False

        detail = " | ".join(decision.reasons)
        self._logger.debug(
            "回复意愿判定",
            event="reply.decided",
            chat_flow_id=f"{conversation_type}:{queue_key}",
            message_id=message.message_id,
            conversation_kind=conversation_type,
            conversation_id=queue_key,
            probability=decision.probability,
            should_reply=decision.should_reply,
            reasons=detail,
        )

        if decision.should_reply and self._reply_orchestrator is not None:
            return self._start_reply_with_tracking(message=message, queue=queue, queue_key=queue_key, decision=decision)
        return False
