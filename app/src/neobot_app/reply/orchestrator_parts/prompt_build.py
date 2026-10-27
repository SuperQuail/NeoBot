"""system 提示词与角色消息构建。"""
from __future__ import annotations

from typing import TYPE_CHECKING
from neobot_contracts.models import ConversationRef
from neobot_app.reply.event import ReplyEvent, ReplyState
from ._runtime import asyncio
from .prompt_blocks import _AT_MENTION_PRIORITY_BLOCK
if TYPE_CHECKING:
    from neobot_adapter.model.message import GroupMessage, PrivateMessage
    from neobot_app.message.numbering import MessageNumbering
    from neobot_app.message.queue import MessageQueue

class PromptBuildMixin:
    async def _build_prompt(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
        numbering: MessageNumbering | None = None,
        last_reply_message_id: int | None = None,
        all_new: bool = False,
        context_blocks: list[dict[str, str]] | None = None,
    ) -> str:
        # 等待该队列所有待处理的图片解析完成
        if self._image_parse_service is not None:
            image_wait_timeout: float | None = None
            if (
                event.conversation_ref is not None
                and event.conversation_ref.kind == "group"
            ):
                image_wait_timeout = self._get_group_agent_silent_timeout_seconds()
            else:
                # 私聊不能无限等：视觉模型慢/抖动时会把整条私聊回复卡在 prompt
                # 构建阶段。给一个有限上限（与视觉模型调用超时 60s 对齐并留余量），
                # 超时后未替换的图片段按原始“图片 [url]”占位进 prompt 即可。
                image_wait_timeout = self._get_private_image_wait_timeout_seconds()
            await self._image_parse_service.wait_for_queue(
                queue_key,
                timeout=image_wait_timeout,
            )

        before_prompt = await self._emit_runtime_event(
            "prompt.build.before", event, queue_key=queue_key
        )
        if before_prompt.consumed:
            return str(before_prompt.result or before_prompt.payload.get("prompt", ""))
        event.transition(ReplyState.BUILDING_PROMPT)
        if event.conversation_ref is None:
            raise ValueError("ReplyEvent.conversation_ref is None")

        if event.conversation_ref.kind == "group":
            try:
                prompt = await asyncio.wait_for(
                    self._prompt_builder.build_group_chat_prompt(
                        group_id=int(queue_key),
                        message_queue=queue,
                        numbering=numbering,
                        last_reply_message_id=last_reply_message_id,
                        all_new=all_new,
                        context_blocks=context_blocks,
                    ),
                    timeout=self._get_prompt_timeout_seconds(),
                )
                # 被 @ 触发的那一轮补一条等待指引（本体延迟默认已关，见 _at_mention_wait_message）
                if context_blocks is not None:
                    wait_hint = self._at_mention_wait_message(event)
                    if wait_hint is not None:
                        context_blocks.append(wait_hint)
                        self._record_debug(
                            "at_mention_wait_hint_injected", event, queue_key=queue_key
                        )
                if self._is_at_mentioned_event(event):
                    prompt = prompt + "\n" + _AT_MENTION_PRIORITY_BLOCK
                after_prompt = await self._emit_runtime_event(
                    "prompt.build.after", event, queue_key=queue_key, prompt=prompt
                )
                return str(after_prompt.payload.get("prompt", prompt))
            except asyncio.TimeoutError:
                self._logger.warning(
                    "群聊提示词构建超时",
                    event_id=event.event_id,
                    queue_key=queue_key,
                    timeout_seconds=self._get_prompt_timeout_seconds(),
                )
                raise

        try:
            prompt = await asyncio.wait_for(
                self._prompt_builder.build_friend_chat_prompt(
                    user_id=int(queue_key),
                    message_queue=queue,
                    numbering=numbering,
                    last_reply_message_id=last_reply_message_id,
                    all_new=all_new,
                    context_blocks=context_blocks,
                ),
                timeout=self._get_prompt_timeout_seconds(),
            )
            after_prompt = await self._emit_runtime_event(
                "prompt.build.after", event, queue_key=queue_key, prompt=prompt
            )
            return str(after_prompt.payload.get("prompt", prompt))
        except asyncio.TimeoutError:
            self._logger.warning(
                "私聊提示词构建超时",
                event_id=event.event_id,
                queue_key=queue_key,
                timeout_seconds=self._get_prompt_timeout_seconds(),
            )
            raise
    async def _build_role_messages(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
        *,
        numbering: MessageNumbering | None = None,
        last_reply_message_id: int | None = None,
        all_new: bool = False,
    ) -> list[dict[str, str]]:
        """构建聊天记录的角色消息列表(user/assistant)。

        必须优先于 system 提示词构建(消息编号在构建过程中填充,
        system 中的 [聊天消息编号映射] 依赖这些编号)。
        """
        if self._prompt_builder is None:
            return []
        if event.conversation_ref is not None and event.conversation_ref.kind == "group":
            return await self._prompt_builder.build_group_chat_messages(
                group_id=int(queue_key),
                message_queue=queue,
                numbering=numbering,
                last_reply_message_id=last_reply_message_id,
                all_new=all_new,
            )
        return await self._prompt_builder.build_friend_chat_messages(
            user_id=int(queue_key),
            message_queue=queue,
            numbering=numbering,
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
        )
    def _resolve_last_reply(
        self,
        queue: MessageQueue,
        queue_key: str,
    ) -> tuple[int | None, bool]:
        """返回指定队列键对应的 (last_reply_message_id, all_new)。

        跟踪被禁用时返回 (None, False)。
        跟踪启用但尚未记录位置时返回 (None, True)。
        已存在最后回复位置时返回 (message_id, False)。
        """
        enable_tracking = (
            getattr(
                getattr(self._config, "chat", None), "enable_last_reply_tracking", True
            )
            if self._config
            else True
        )
        if not enable_tracking:
            return None, False
        last_msg_id = queue.get_last_reply_position(queue_key)
        if last_msg_id is None:
            return None, True
        return last_msg_id, False
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
