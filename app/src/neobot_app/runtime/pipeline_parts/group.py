"""群聊消息入口与 @ 关键词快速通道、回复启动追踪。"""

from __future__ import annotations

from neobot_app.agent_tools.invocation import human_message_entry
import asyncio
from typing import Any
from typing import Dict
from neobot_adapter.model.message import GroupMessage
from neobot_adapter.model.message import PrivateMessage
from neobot_adapter.utils.parse import safe_parse_model
from neobot_app.message.fast_reply_keywords import matches_reply_trigger
from neobot_app.message.process import event_message__to_text
from neobot_app.message.queue import MessageQueue
from neobot_app.willing.models import WillingDecision

from .helpers import _message_has_images, _sender_name


class _PipelineGroupMixin:
    @human_message_entry
    async def handle_group_message_event(
        self,
        event: Dict[str, Any],
        *,
        skip_ai_reply: bool = False,
        agent_intent: Dict[str, Any] | None = None,
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
        replied_messages = await self._fetch_replied_messages(message, self._group_queue, queue_key)

        # 命令系统处理:入队之前解析;命令命中则拦截回复管线并标记消息。
        # (允许 bot 自己触发,群聊需被 @bot;未命中时消息按普通消息继续走管线)
        command_consumed = False
        command_background: str | None = None
        if self._command_service is not None:
            result = await self._command_service.handle_message(message, kind="group", queue_key=queue_key)
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
        if self._skip_while_standby(kind="group", queue_key=queue_key, message=message):
            return

        # 消息始终入队(命令消息作为上下文保留),但命令消息打上"已消费"标记,
        # 挂起中的回复管线(_collect_new_entries)不会把它当作新消息再次注入回复
        self._group_queue.push(queue_key, message, replied_messages=replied_messages)
        if command_consumed:
            self._group_queue.mark_command_consumed(queue_key, getattr(message, "message_id", None))

        await self._refresh_profile_for_message(message)
        await self._maybe_refresh_avatar(message)
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

        # 命令已消费:回复管线在此拦截(不再进入意愿判断/回复触发);
        # sync_reply 命令额外以命令结果为背景触发回复管线
        if command_consumed:
            if command_background or agent_preactivate:
                self._start_command_sync_reply(
                    message=message,
                    queue=self._group_queue,
                    queue_key=queue_key,
                    background=command_background or "",
                    preactivate=agent_preactivate,
                )
            return

        # 凭据签发:管理员发送凭据文本
        if self._credential_manager is not None and await self._try_issue_credential(
            message,
            kind="group",
            queue_key=queue_key,
            queue=self._group_queue,
        ):
            return

        # Bot 自己的消息不触发回复
        if self._is_bot_self(message):
            return

        ai_reply_blocked = self._consume_ai_reply_block(message)
        if skip_ai_reply or ai_reply_blocked:
            self._logger.info("插件监听器已阻止本条群消息触发 AI 回复", queue_key=queue_key)
            return

        # 如果当前正在回复中，新消息入 post-reply 队列，不计算意愿
        if queue_key in self._replying_queues:
            if self._has_active_reply_pipeline("group", queue_key):
                self._post_reply_willing.setdefault(queue_key, []).append(message)
                return
            self._logger.debug(
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

        await self._handle_willing_decision(message=message, queue=self._group_queue, queue_key=queue_key)

    def _at_mention_instant_keyword(self, message: Any) -> str:
        """被 @ 的正文是否命中「跳过收集等待」的插件关键词（命中返回关键词）。

        关键词由插件登记（见 neobot_app.message.fast_reply_keywords）：玩法类
        关键词（漂流瓶 / 签到 / 抽签 …）意图明确，不必再等收集窗口。
        这里吞掉全部异常：关键词表坏掉不能影响消息管线。
        """
        try:
            return matches_reply_trigger(message)
        except Exception:  # pragma: no cover - 关键词表异常只降级
            return ""

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
            # 标记归「真正启动成功的那条管线」所有：这里若 discard，会把同会话
            # 正在运行的另一条管线的标记一并删掉（分流守卫被静默破坏）。
            return False
        self._replying_queues.add(queue_key)
        return True
