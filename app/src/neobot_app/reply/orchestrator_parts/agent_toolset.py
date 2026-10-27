"""agent 回复的一次性工具集装配（工具回调绑定 + 技能预激活 + 表情包候选）。"""

from __future__ import annotations

import random
from functools import partial
from typing import TYPE_CHECKING, Any

from neobot_app.reply.vision_context import ReplyVisionContext
from .agent_state import AgentLoopState

if TYPE_CHECKING:
    from neobot_app.message.numbering import MessageNumbering
    from neobot_app.message.queue import MessageQueue
    from neobot_app.reply.event import ReplyEvent


class AgentToolsetMixin:

    def _agent_conversation_ids(self, event: ReplyEvent) -> tuple[str, str, int | None]:
        """本轮会话 kind/id 与当前用户 id（工具回调与工具集构建共用）。"""
        conv_kind = event.conversation_ref.kind if event.conversation_ref else ""
        conv_id = event.conversation_ref.id if event.conversation_ref else ""
        current_user_id = None
        try:
            raw_user = getattr(event.message, "user_id", None)
            if raw_user is not None:
                current_user_id = int(raw_user)
        except (TypeError, ValueError):
            current_user_id = None
        return conv_kind, conv_id, current_user_id

    async def _build_agent_toolset(
        self,
        *,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_copy: MessageQueue,
        queue_key: str,
        prompt: str,
        messages: list[dict],
        allowed_tools: set[str] | None,
        numbering: MessageNumbering,
        conv_kind: str,
        conv_id: str,
        current_user_id: int | None,
        state: AgentLoopState,
    ) -> tuple[Any, list[dict], ReplyVisionContext, Any]:
        """装配本轮工具集：工具回调绑定、技能预激活、表情包候选注入。"""
        from neobot_app.reply.tools import build_reply_toolset

        cancel_handler = partial(self._agent_cancel_handler, state, event)
        send_reply_handler = partial(
            self._agent_send_reply_handler,
            state,
            event,
            queue,
            queue_copy,
            queue_key,
            numbering,
        )
        send_emoji_handler = partial(
            self._agent_send_emoji_handler,
            state,
            event,
            queue,
            queue_copy,
            queue_key,
        )
        wait_handler = partial(
            self._agent_wait_handler,
            state,
            queue,
            queue_copy,
            queue_key,
            numbering,
        )
        react_emoji_handler = partial(
            self._agent_react_emoji_handler,
            queue,
            queue_copy,
            queue_key,
            numbering,
        )
        search_emoji_handler = self._agent_search_emoji_handler
        speak_handler = partial(
            self._agent_speak_handler,
            state,
            event,
            queue,
            queue_copy,
            queue_key,
        )
        poke_user_handler = partial(self._agent_poke_user_handler, conv_kind, conv_id)
        send_long_reply_handler = partial(
            self._agent_send_long_reply_handler,
            state,
            event,
            queue,
            queue_copy,
            queue_key,
            numbering,
        )

        reply_toolset = build_reply_toolset(
            send_reply_handler=send_reply_handler,
            willing_service=self._willing_service,
            numbering=numbering,
            send_emoji_handler=send_emoji_handler,
            emoji_service=self._emoji_service,
            wait_handler=wait_handler,
            react_emoji_handler=react_emoji_handler,
            search_emoji_handler=search_emoji_handler,
            cancel_handler=cancel_handler,
            tts_service=self._tts_service,
            speak_handler=speak_handler,
            poke_user_handler=poke_user_handler,
            drawing_manager=self._drawing_manager,
            scheduled_task_manager=self._scheduled_task_manager,
            problem_solver_manager=self._problem_solver_manager,
            skill_manager=self._skill_manager,
            notification_hub=self._notification_hub,
            markdown_image_converter=self._markdown_image_converter,
            send_long_reply_handler=send_long_reply_handler,
            chat_context=prompt,
            conv_kind=conv_kind,
            conv_id=conv_id,
            current_user_id=current_user_id,
            human_request=event.human_request,
            agent_history=messages,
            skills_registry=self._markdown_skills,
            allowed_tools=allowed_tools,
            wait_cooldown_seconds=self._get_wait_cooldown_seconds(),
            ai_reply_check=self._get_ai_reply_check(),            ai_reply_check_lightweight=self._get_ai_reply_check_lightweight(),
            bot_name=self._get_bot_name(),
            long_reply_fallback_template=self._get_long_reply_fallback_template(),
            long_reply_max_length=self._get_long_reply_max_length(),
            long_reply_max_sentence_count=self._get_long_reply_max_sentence_count(),
            enable_ai_reply_regenerate=self._get_enable_ai_reply_regenerate(),
            logger=self._logger,
            credential_manager=self._credential_manager,
            config=self._config,
            config_update_callback=self._config_update_callback,
            native_vision_provider=self._provider,
            reviewer=self._provider,
            auto_review=bool(
                getattr(getattr(getattr(self._config, "agent", None), "tools", None), "auto_review", True)
            ),
            review_timeout_seconds=float(
                getattr(getattr(getattr(self._config, "agent", None), "tools", None), "review_timeout_seconds", 30.0)
                or 30.0
            ),
        )
        self._tool_executors[event.event_id] = reply_toolset.executor
        # 本轮预激活（插件消息意图入口）：在构建工具表**之前**加载指定技能包，
        # 使这些 {plugin}__{tool} 在本轮模型调用里即可直接调用。
        if event.preactivate and self._skill_manager is not None:
            try:
                loaded = reply_toolset.executor.preactivate_skills(event.preactivate)
                self._logger.info(
                    "本轮预激活技能包",
                    event_id=event.event_id,
                    requested=list(event.preactivate),
                    loaded=loaded,
                )
            except Exception as exc:  # 预激活失败不能影响回复
                self._logger.warning(
                    "预激活技能包失败，已忽略",
                    event_id=event.event_id,
                    error=str(exc),
                )
        if self._skill_manager is not None and conv_kind in {"group", "private"} and str(conv_id).isdigit():
            from neobot_app.skills.agent_tools_skill import AgentToolsSkill
            from neobot_app.agent_tools.contracts import ToolContext
            shared_tools = self._skill_manager.get("agent_tools")
            if isinstance(shared_tools, AgentToolsSkill):
                flow = f"{conv_kind}:{conv_id}"
                allowed = reply_toolset.executor.agent_tool_capabilities()
                context = ToolContext(owner=f"{flow}:main", chat_flow_id=flow, user_id=current_user_id,
                                      human_request=event.human_request, allowed_tools=allowed)
                self._agent_tool_turns[event.event_id] = (shared_tools.runtime, context, messages)

        cross_chat_loaded = self._preactivate_cross_chat_tools(
            reply_toolset, queue, queue_key, event
        )
        tools = (
            reply_toolset.executor.definitions()
            if cross_chat_loaded
            else reply_toolset.definitions()
        )
        vision_context = ReplyVisionContext()
        from neobot_app.skills.image_context_skill import ImageContextSkill

        default_image_loader = ImageContextSkill(
            adapter=self._adapter,
            group_message_queue=queue_copy if conv_kind == "group" else None,
            friend_message_queue=queue_copy if conv_kind != "group" else None,
        )

        await self._maybe_prepare_emoji_choice(event, messages, vision_context)
        return reply_toolset, tools, vision_context, default_image_loader

    async def _maybe_prepare_emoji_choice(
        self,
        event: ReplyEvent,
        messages: list[dict],
        vision_context: ReplyVisionContext,
    ) -> None:
        """按概率准备一轮表情包选择：把候选图片直接注入上下文，由 agent 决定发不发。

        这里不再直接发送表情包。候选 = 固定爱用表情包 + 使用次数最少的随机槽位；
        所有候选都记 0.5 次曝光，避免不合适的表情包反复占用上下文。
        """
        if self._emoji_service is None or self._emoji_service.emoji_count == 0:
            return
        if event is None or event.conversation_ref is None:
            return
        if event.willing_decision is not None:
            if event.willing_decision.manager_name in ("background_drawing", "scheduled_task"):
                return
        if getattr(self._provider, "native_vision", False) is not True:
            return

        prob = 0.1
        random_limit = 10
        favorite_limit = 10
        if self._config is not None:
            try:
                prob = float(getattr(self._config.chat, "random_sticker_probability", 0.1))
            except (TypeError, ValueError):
                prob = 0.1
            try:
                random_limit = int(
                    getattr(self._config.chat, "emoji_random_candidate_count", 10)
                )
            except (TypeError, ValueError):
                random_limit = 10
            try:
                favorite_limit = int(
                    getattr(self._config.chat, "emoji_favorite_limit", 10)
                )
            except (TypeError, ValueError):
                favorite_limit = 10
        if random.random() >= max(0.0, min(1.0, prob)):
            return

        try:
            candidates = self._emoji_service.pick_context_candidates(
                random_limit=max(1, random_limit),
                favorite_limit=max(0, favorite_limit),
            )
        except Exception as exc:
            self._logger.warning("准备表情包候选失败", error=str(exc))
            return
        if not candidates:
            return

        from neobot_app.image.parser import _build_vision_image_part

        parts: list[dict] = []
        numbers: list[int] = []
        labels: list[str] = []
        for number, entry in candidates:
            try:
                image_part = _build_vision_image_part(
                    entry.file_path.read_bytes(), logger=self._logger
                )
            except Exception as exc:
                self._logger.debug("表情包候选图片读取失败", number=number, error=str(exc))
                continue
            numbers.append(number)
            favourite = "（爱用）" if getattr(entry, "is_favorite", False) else ""
            label = (
                f"[表情包候选] 编号 {number}{favourite}："
                f"{entry.analysis_text or entry.file_name}"
            )
            labels.append(label)
            parts.extend([{"type": "text", "text": label}, image_part])
        if not parts:
            return

        vision_context.manual_parts.extend(parts)
        messages.append(
            {
                "role": "user",
                "content": (
                    "[表情包选择] 你觉得现在发一张表情包比较合适。"
                    "下面是候选表情包的编号和图片；可以用 send_emoji 工具选择一张发出去，"
                    "如果觉得没有合适的，就不要发表情包，继续正常回复。"
                    "候选编号：" + "、".join(str(n) for n in numbers) + "。"
                ),
            }
        )
        try:
            await self._emoji_service.record_candidate_round(numbers)
        except Exception as exc:
            self._logger.warning("记录表情包候选曝光失败", error=str(exc))
        self._logger.info(
            "表情包选择上下文已注入",
            event_id=event.event_id,
            candidates=numbers,
            favourite=sum(1 for entry in candidates if getattr(entry, "is_favorite", False)),
        )
