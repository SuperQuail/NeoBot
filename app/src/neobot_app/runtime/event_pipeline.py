from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from neobot_adapter import OneBotAdapter, Subscription
from neobot_adapter.model.message import GroupMessage, PrivateMessage
from neobot_adapter.model.notice import EmojiReaction, GroupMessageDelete, GroupPoke, PrivateMessageDelete, PrivatePoke
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
        self._subscriptions: List[Subscription] = []
        self._started = False
        self._warmed_up_friends: set[str] = set()
        self._warmup_lock = asyncio.Lock()
        self._replying_queues: set[str] = set()
        self._post_reply_willing: dict[str, list] = {}
        self._pending_image_willing: dict[str, list] = {}
        self._image_willing_lock = asyncio.Lock()

    def start(self) -> None:
        if self._started:
            return

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
        if not self._started:
            return

        for subscription in self._subscriptions:
            subscription.unsubscribe()
        self._subscriptions.clear()
        self._started = False
        self._logger.info("实时事件管线已停止")

    async def flush_pending_summaries(self) -> None:
        """Trigger summarisation for all counters that have pending messages below the threshold."""
        if self._archive_summary_service is not None:
            await self._archive_summary_service.flush_all()

    async def _handle_private_message(self, event: Dict[str, Any]) -> None:
        message = safe_parse_model(event, PrivateMessage)
        queue_key = str(message.user_id or "")
        if self._inbound_pipeline is not None:
            await self._inbound_pipeline.handle_raw_event(event)
        replied_messages = await self._fetch_replied_messages(message, self._friend_queue, queue_key)
        self._friend_queue.push(queue_key, message, replied_messages=replied_messages)
        await self._refresh_profile_for_message(message)
        if self._image_parse_service is not None:
            await self._image_parse_service.parse_message_images(message, queue_key)
        text = await event_message__to_text(message)
        await self._record_archive_summary(
            conversation_kind="private",
            conversation_id=queue_key,
            message_text=text,
            sender_id=str(message.user_id or ""),
            sender_name=_sender_name(message),
        )
        if queue_key:
            await self._maybe_warmup_friend_chat(queue_key)

        # Bot 自己的消息不触发回复
        if self._is_bot_self(message):
            return

        await self._handle_private_reply(message=message, queue_key=queue_key)
        self._logger.info(f"收到私聊消息: {text}")

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
                result = await self.adapter.get_friend_msg_history(
                    user_id=int(user_id),
                    count=count,
                    reverse_order=False,
                )
                if result and result.data and result.data.messages:
                    for msg in result.data.messages:
                        if isinstance(msg, tuple):
                            continue
                        try:
                            self._friend_queue.push(user_id, msg)
                        except Exception as exc:
                            self._logger.debug(
                                "warmup push message failed",
                                user_id=user_id,
                                error=str(exc),
                            )
                    self._logger.info(
                        "私聊动态预热完成",
                        user_id=user_id,
                        message_count=len(result.data.messages),
                    )
            except Exception as exc:
                self._logger.warning(
                    "私聊动态预热失败",
                    user_id=user_id,
                    error=str(exc),
                )
            finally:
                self._warmed_up_friends.add(user_id)

    async def _handle_private_reply(self, message: Any, queue_key: str) -> None:
        """私聊直接触发回复（跳过意愿管理器），延迟指定秒数以收集后续消息。"""
        delay = 5.0
        if self._config is not None:
            val = getattr(self._config.chat, "private_chat_reply_delay_seconds", None)
            if isinstance(val, (int, float)) and val >= 0:
                delay = float(val)

        if delay > 0:
            self._logger.debug("私聊延迟回复等待中", queue_key=queue_key, delay_seconds=delay)
            await asyncio.sleep(delay)

        if self._reply_orchestrator is None:
            return

        from neobot_app.willing.models import WillingDecision

        decision = WillingDecision(
            manager_name="private_direct",
            probability=1.0,
            should_reply=True,
            reasons=["私聊直接回复（跳过意愿管理器）"],
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

    async def _handle_group_message(self, event: Dict[str, Any]) -> None:
        message = safe_parse_model(event, GroupMessage)
        queue_key = str(message.group_id or "")
        if self._inbound_pipeline is not None:
            await self._inbound_pipeline.handle_raw_event(event)
        replied_messages = await self._fetch_replied_messages(message, self._group_queue, queue_key)
        self._group_queue.push(queue_key, message, replied_messages=replied_messages)
        await self._refresh_profile_for_message(message)
        if self._image_parse_service is not None:
            await self._image_parse_service.parse_message_images(message, queue_key)
        text = await event_message__to_text(message)
        await self._record_archive_summary(
            conversation_kind="group",
            conversation_id=queue_key,
            message_text=text,
            sender_id=str(message.user_id or ""),
            sender_name=_sender_name(message),
        )
        self._logger.info(f"收到群消息[{message.group_id or '未知'}]: {text}")

        # Bot 自己的消息不触发回复
        if self._is_bot_self(message):
            return

        # 如果当前正在回复中，新消息入 post-reply 队列，不计算意愿
        if queue_key in self._replying_queues:
            self._post_reply_willing.setdefault(queue_key, []).append(message)
            return

        # 如果消息含图片，延迟意愿计算，等图片解析完成后处理
        if _message_has_images(message):
            self._pending_image_willing.setdefault(queue_key, []).append(message)
            asyncio.create_task(self._process_pending_image_willing(queue_key))
            return

        await self._handle_willing_decision(message=message, queue=self._group_queue, queue_key=queue_key)

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
                "archive auto summary record failed",
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
                response = await self.adapter.get_msg(message_id)
            except Exception as exc:
                self._logger.debug(
                    "failed to fetch replied message",
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

    def _start_reply_with_tracking(
        self,
        *,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
        decision: WillingDecision,
    ) -> bool:
        """发起回复并设置回复状态追踪与完成后回调。"""
        pre_reply_msg_id = queue.get_last_message_id(queue_key)
        self._replying_queues.add(queue_key)

        async def on_reply_done() -> None:
            self._replying_queues.discard(queue_key)
            await self._process_post_reply_queue(queue_key)

        event = self._reply_orchestrator.start_reply(
            message=message,
            queue=queue,
            queue_key=queue_key,
            decision=decision,
            pre_reply_message_id=pre_reply_msg_id,
            on_reply_done=on_reply_done,
        )
        if event is None:
            self._replying_queues.discard(queue_key)
            return False
        return True

    async def _process_pending_image_willing(self, queue_key: str) -> None:
        """等待图片解析完成，然后按序处理待处理队列。若触发回复则清空剩余。"""
        if self._image_parse_service is not None:
            await self._image_parse_service.wait_for_queue(queue_key)

        async with self._image_willing_lock:
            pending = self._pending_image_willing.pop(queue_key, [])
            if not pending:
                return

            for msg in pending:
                if queue_key in self._replying_queues:
                    # 已在回复中，剩余消息放入 post-reply 队列
                    idx = pending.index(msg)
                    if idx >= 0:
                        self._post_reply_willing.setdefault(queue_key, []).extend(pending[idx:])
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
            if queue_key in self._replying_queues:
                self._post_reply_willing.setdefault(queue_key, []).extend(
                    pending[pending.index(msg):]
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
                observed_fields["sex"] = getattr(message.sender.sex, "value", message.sender.sex)

        try:
            await self._profile_service.ensure_user_profile(
                str(message.user_id),
                observed_fields=observed_fields,
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
        for key in ("user_id", "operator_id", "sender_id", "target_id",
                     "group_id", "message_id", "file", "duration",
                     "honor_type", "title", "card_new", "card_old",
                     "emoji_id"):
            val = event.get(key)
            if val is not None:
                details.append(f"{key}={val}")

        info = " ".join(details)
        self._logger.info(f"收到通知[{label}] {info}".rstrip())

    async def _handle_reaction_notice(self, event: Dict[str, Any]) -> None:
        from neobot_app.message.queue_impl import ReactionEntry

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
                profile = await self._profile_service.get_user(str(user_id))
                if profile is not None and getattr(profile, "nick_name", None):
                    operator_name = profile.nick_name
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
        from neobot_app.message.queue_impl import PokeEntry

        group_id = event.get("group_id")
        if group_id is not None:
            notice = safe_parse_model(event, GroupPoke)
            queue_key = str(notice.group_id or group_id)
            queue = self._group_queue
            sender_id = notice.user_id or 0
            target_id = notice.target_id or 0
            resolved_group_id = notice.group_id or int(group_id)

            sender_name = await self._resolve_name(sender_id, group_id=resolved_group_id)
            target_name = await self._resolve_name(target_id, group_id=resolved_group_id)
            action_text = _build_poke_action_text(event.get("raw_info"), sender_name, target_name)

            poke = PokeEntry(
                sender_id=sender_id,
                user_id=sender_id,
                target_id=target_id,
                sub_type=getattr(notice.sub_type, "value", "poke") if notice.sub_type else "poke",
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
            action_text = _build_poke_action_text(event.get("raw_info"), sender_name, target_name)

            poke = PokeEntry(
                sender_id=sender_id,
                user_id=notice.user_id or 0,
                target_id=target_id,
                sub_type=getattr(notice.sub_type, "value", "poke") if notice.sub_type else "poke",
                group_id=None,
                sender_name=sender_name,
                target_name=target_name,
                action_text=action_text,
            )

        if queue_key:
            queue.push_poke(queue_key, poke)

    async def _resolve_name(self, user_id: int, group_id: int | None = None) -> str:
        """Resolve a user's display name.

        Priority:
        1. Database (user_profiles.nick_name / remark)
        2. API: group member info (card > nickname) for group, stranger info for private
        3. Fallback to QQ:xxx
        """
        if not user_id:
            return ""

        # 1. Try database first
        if self._profile_service is not None:
            try:
                profile = await self._profile_service.get_user(str(user_id))
                if profile is not None:
                    remark = getattr(profile, "remark", None)
                    nick_name = getattr(profile, "nick_name", None)
                    if remark:
                        return str(remark)
                    if nick_name:
                        return str(nick_name)
            except Exception:
                pass

        # 2. API fallback
        if group_id is not None:
            try:
                resp = await self._adapter.get_group_member_info(group_id, user_id)
                if resp and resp.data:
                    return resp.data.card or resp.data.nickname or resp.data.card_or_nickname or f"QQ:{user_id}"
            except Exception:
                pass
        else:
            try:
                resp = await self._adapter.get_stranger_info(user_id)
                if resp and resp.data:
                    return resp.data.nickname or f"QQ:{user_id}"
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
