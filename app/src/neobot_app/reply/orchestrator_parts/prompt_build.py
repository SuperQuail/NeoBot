"""system 提示词与角色消息构建。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any
from neobot_contracts.models import ConversationRef
from neobot_app.bot_accounts import bot_account_for_event
from neobot_app.user_identity import group_label, group_number_for, id_label, qq_for_user
from neobot_app.prompt.blocks import Stage, blocks_for
from neobot_app.prompt.context import Scope
from neobot_app.reply.event import ReplyEvent, ReplyState
from ._runtime import asyncio
if TYPE_CHECKING:
    from neobot_adapter.model.message import GroupMessage, PrivateMessage
    from neobot_app.message.numbering import MessageNumbering
    from neobot_app.message.queue import MessageQueue


class PromptBuildMixin:
    #: 官方通道提示词最前面的身份说明（按需求原文，不改标点）
    _OFFICIAL_PROMPT_PREFIX = (
        "当前你是使用官方渠道搭建的QQ机器人,所以你看不到QQ号和群号,只看得到QQ ID和群ID,"
    )
    #: 官方通道没有真实 QQ 号/群号，提示词里的「QQ号」「群号」统一改称 ID。
    _OFFICIAL_PROMPT_REPLACEMENTS = (
        ("QQ群号", "QQ群 ID"),
        ("QQ号", "QQ ID"),
        ("QQ 号", "QQ ID"),
        ("群号", "群 ID"),
        ("群 号", "群 ID"),
    )

    @classmethod
    def _official_replace_text(cls, text: str) -> str:
        for old, new in cls._OFFICIAL_PROMPT_REPLACEMENTS:
            text = text.replace(old, new)
        return text

    @classmethod
    def _official_prompt_text(cls, text: str) -> str:
        # 先替换再加前缀：前缀里的「QQ号」「群号」是需求原文，不能再被替换
        return f"{cls._OFFICIAL_PROMPT_PREFIX}\n{cls._official_replace_text(text)}"

    def _officialize_prompt(
        self,
        event: ReplyEvent,
        prompt: str,
        context_blocks: list[dict[str, str]] | None = None,
    ) -> str:
        if not self._is_official_platform(event):
            return prompt
        if context_blocks:
            for block in context_blocks:
                content = block.get("content")
                if isinstance(content, str):
                    block["content"] = self._official_replace_text(content)
        return self._official_prompt_text(prompt)

    def _is_official_platform(self, event: ReplyEvent) -> bool:
        """当前事件是否来自官方机器人通道。

        双待模式下事件自带 neobot_channel，直接看它；旧路径（单通道/未标注）没有
        这个字段，回退到身份判定（profile 未解析时按非官方处理）。
        """
        channel = str(getattr(event, "neobot_channel", "") or "")
        if channel:
            return channel == "official"
        profile = getattr(getattr(self, "_bot_profile", None), "profile", None)
        return getattr(profile, "kind", None) == "official"

    def _event_bot_account(self, event: ReplyEvent) -> int:
        """本次回复的机器人 QQ 号统一由提供者解析（事件/通道/config 细节不可见）。"""
        return bot_account_for_event(event, self._config)

    def _append_round_blocks(
        self,
        prompt: str,
        *,
        scope: Scope,
        dynamic: dict[str, Any],
        features: dict[str, bool],
    ) -> str:
        """把编排器负责的 system 块按注册表顺序追加到 system 末尾。

        这些块的内容每轮由调用方给出（@ 提示 / agent 模式技能说明 / 原生视觉），
        注入时机决定上下文缓存能否命中，所以不交给 builder 的稳定 system 构建；
        文本、启停与相对顺序仍来自注册表，由组合器渲染。
        """
        ctx = self._runtime_ctx(scope=scope, dynamic=dynamic)
        ctx.features.update(features)
        composer = self._prompt_composer_service()
        parts = [prompt]
        for block in blocks_for(Stage.SYSTEM_APPEND, scope):
            if block.per_round:
                text = composer.render_status_text(block.id, ctx)
                if text:
                    parts.append(text)
        return "\n".join(parts)

    async def _build_prompt(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
        numbering: MessageNumbering | None = None,
        last_reply_message_id: int | None = None,
        all_new: bool = False,
        context_blocks: list[dict[str, str]] | None = None,
        agent_mode: bool = False,
        dynamic: dict[str, Any] | None = None,
        features: dict[str, bool] | None = None,
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
            return self._officialize_prompt(
                event, str(before_prompt.result or before_prompt.payload.get("prompt", ""))
            )
        event.transition(ReplyState.BUILDING_PROMPT)
        if event.conversation_ref is None:
            raise ValueError("ReplyEvent.conversation_ref is None")

        round_dynamic = dict(dynamic or {})
        bot_account = self._event_bot_account(event)
        round_features = {
            "agent_mode": agent_mode,
            "official_platform": self._is_official_platform(event),
            **dict(features or {}),
        }

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
                        bot_account=bot_account,
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
                    round_dynamic["at_mention"] = True
                prompt = self._append_round_blocks(
                    prompt,
                    scope=Scope.GROUP,
                    dynamic=round_dynamic,
                    features=round_features,
                )
                after_prompt = await self._emit_runtime_event(
                    "prompt.build.after", event, queue_key=queue_key, prompt=prompt
                )
                return self._officialize_prompt(
                    event, str(after_prompt.payload.get("prompt", prompt)), context_blocks
                )
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
                    bot_account=bot_account,
                ),
                timeout=self._get_prompt_timeout_seconds(),
            )
            prompt = self._append_round_blocks(
                prompt,
                scope=Scope.PRIVATE,
                dynamic=round_dynamic,
                features=round_features,
            )
            after_prompt = await self._emit_runtime_event(
                "prompt.build.after", event, queue_key=queue_key, prompt=prompt
            )
            return self._officialize_prompt(
                event, str(after_prompt.payload.get("prompt", prompt)), context_blocks
            )
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
        bot_account = self._event_bot_account(event)
        if event.conversation_ref is not None and event.conversation_ref.kind == "group":
            return await self._prompt_builder.build_group_chat_messages(
                group_id=int(queue_key),
                message_queue=queue,
                numbering=numbering,
                last_reply_message_id=last_reply_message_id,
                all_new=all_new,
                bot_account=bot_account,
            )
        return await self._prompt_builder.build_friend_chat_messages(
            user_id=int(queue_key),
            message_queue=queue,
            numbering=numbering,
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
            bot_account=bot_account,
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
        # 官方通道的 user/group id 是开放平台 13 位合成 ID，不是 QQ 号；提示词
        # 里按 ID 规模统一标注，避免模型拿合成 ID 去拼 qlogo/资料链接或加好友。
        event_channel = str(getattr(event, "neobot_channel", "") or "") or None
        # 人工映射过的官方合成 ID 在提示词里直接显示真实 QQ 号。
        sender_value = (qq_for_user(sender_id, event_channel) or sender_id) if sender_id else ""
        sender_label = id_label(sender_id, event_channel) if sender_id else "QQ"
        if isinstance(message, GroupMessage) or msg_type == "group":
            group_id = getattr(message, "group_id", None) or queue_key
            mapped_group = group_number_for(group_id, event_channel)
            group_line = f"{group_label(group_id, event_channel)}：{mapped_group or group_id}"
            lines = ["[当前聊天环境]", "会话类型：群聊", group_line]
            if sender_name and sender_id:
                lines.append(f"消息发送者：{sender_name}（{sender_label}：{sender_value}）")
            elif sender_id:
                lines.append(f"消息发送者{sender_label}：{sender_value}")
            return "\n".join(lines)

        lines = [
            "[当前聊天环境]",
            "会话类型：私聊",
        ]
        if sender_name and sender_id:
            lines.append(f"聊天对象：{sender_name}（{sender_label}：{sender_value}）")
        elif sender_id:
            lines.append(f"聊天对象{sender_label}：{sender_value}")
        return "\n".join(lines)
