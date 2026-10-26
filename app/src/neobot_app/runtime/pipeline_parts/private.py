"""私聊消息入口与私聊专属的预热、资料刷新、头像刷新。"""

from __future__ import annotations

from neobot_app.agent_tools.invocation import human_message_entry
from neobot_app.agent_tools.invocation import CURRENT_HUMAN_MESSAGE
import asyncio
import inspect
from typing import Any
from typing import Dict
from neobot_adapter.model.message import GroupMessage
from neobot_adapter.model.message import PrivateMessage
from neobot_adapter.utils.parse import safe_parse_model
from neobot_app.message.process import event_message__to_text
from neobot_app.message.queue import MessageQueue

from .helpers import _extract_reply_message_ids, _sender_name


class _PipelinePrivateMixin:
    @human_message_entry
    async def handle_private_message_event(
        self,
        event: Dict[str, Any],
        *,
        skip_ai_reply: bool = False,
        agent_intent: Dict[str, Any] | None = None,
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

        # 插件消息处理器请求的「交主管线」意图（spec(5) R13/R14）：与命令
        # sync_reply 共用同一条通路 —— 消息照常入队（作为上下文保留），但由
        # 背景内容触发一次回复；preactivate 让指定技能包在**本轮**工具表生效。
        agent_preactivate: tuple[str, ...] = ()
        if not command_consumed and agent_intent:
            command_consumed = True
            command_background = str(agent_intent.get("background") or "") or None
            agent_preactivate = tuple(agent_intent.get("preactivate") or ())
        if self._skip_while_standby(
            kind="private", queue_key=queue_key, message=message
        ):
            return

        # 消息始终入队(命令消息作为上下文保留),但命令消息打上"已消费"标记,
        # 挂起中的回复管线(_collect_new_entries)不会把它当作新消息再次注入回复
        self._friend_queue.push(queue_key, message, replied_messages=replied_messages)
        if command_consumed:
            self._friend_queue.mark_command_consumed(
                queue_key, getattr(message, "message_id", None)
            )

        await self._refresh_profile_for_message(message)
        await self._maybe_refresh_avatar(message)
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
            if command_background or agent_preactivate:
                self._start_command_sync_reply(
                    message=message, queue=self._friend_queue,
                    queue_key=queue_key, background=command_background or "",
                    preactivate=agent_preactivate,
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

    async def _maybe_refresh_avatar(self, message: PrivateMessage | GroupMessage) -> None:
        """用户再次出现在聊天流 → 头像惰性刷新判定（spec(5) §4.9 / R34）。

        本方法只做「一次 DB 读 + 一次时间比较」：下载由 AvatarStore 自己派生
        后台任务，因此消息路径不会等网络。AvatarStore.maybe_refresh 内部已吞掉
        全部异常，这里的 try 只是防御（宿主服务换成第三方实现时也不该影响收消息）。
        """
        store = getattr(self, "_avatar_store", None)
        user_id = getattr(message, "user_id", None)
        if store is None or user_id is None:
            return
        try:
            await store.maybe_refresh(str(user_id))
        except Exception as exc:
            self._logger.debug(
                "头像刷新判定失败", user_id=str(user_id), error=str(exc)
            )

    def _consume_ai_reply_block(self, message: PrivateMessage | GroupMessage) -> bool:
        if self._reply_block_registry is None:
            return False
        consume = getattr(self._reply_block_registry, "consume_message", None)
        if not callable(consume):
            return False
        return bool(consume(message))
