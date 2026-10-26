"""agent 循环的工具后续处理与管线挂起恢复。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from neobot_app.reply.event import ReplyState
from ._runtime import monotonic_seconds
from .agent_state import AgentLoopState

if TYPE_CHECKING:
    from neobot_app.message.numbering import MessageNumbering
    from neobot_app.message.queue import MessageQueue
    from neobot_app.reply.event import ReplyEvent
    from neobot_app.reply.vision_context import ReplyVisionContext


class AgentPipelineMixin:

    async def _agent_inject_new_entries(
        self,
        *,
        event: ReplyEvent,
        queue_key: str,
        queue: MessageQueue,
        queue_copy: MessageQueue,
        numbering: MessageNumbering,
        messages: list[dict],
        is_group: bool,
        rendered_user_ids: set[str],
    ) -> None:
        """把本轮工具执行期间到达的新消息注入上下文。"""
        # 注入此期间的新消息
        new_entries = self._collect_new_entries(queue, queue_copy, queue_key)
        if new_entries:
            from neobot_app.prompt.role_messages import (
                build_role_messages_from_entries,
            )

            new_role_messages = build_role_messages_from_entries(
                new_entries,
                queue_copy,
                queue_key,
                numbering=numbering,
                bot_account=self._get_bot_account(),
                include_boundary_markers=self._show_boundary_markers(),
            )
            member_block = ""
            if is_group:
                member_block = await self._render_new_member_block(
                    new_entries, rendered_user_ids
                )
            if new_role_messages:
                if member_block:
                    messages.append({"role": "user", "content": member_block})
                    self._record_debug(
                        "agent_new_member_profiles_injected",
                        event,
                        queue_key=queue_key,
                    )
                messages.extend(new_role_messages)
                self._record_debug(
                    "agent_new_messages_injected",
                    event,
                    queue_key=queue_key,
                    injected_count=len(new_role_messages),
                )

    async def _agent_after_tool_calls(
        self,
        *,
        event: ReplyEvent,
        messages: list[dict],
        tools: list[dict],
        reply_toolset: Any,
        vision_context: ReplyVisionContext,
        image_parts: list[dict],
        vision_just_disabled: bool,
        state: AgentLoopState,
        nudge_rounds: int,
        nudge_deadline: float,
        nudge_seconds: float,
    ) -> tuple[list[dict], int, float, bool]:
        """工具轮后的状态刷新；返回 (工具定义, 提醒轮次, 提醒截止, 是否结束本轮)。"""
        # 技能按需加载：模型调用 skills__load_tools 后，新工具立即补进下一轮的
        # tools 列表，不必等到下一次回复管线。
        if reply_toolset.executor.consume_tools_dirty():
            tools = reply_toolset.executor.definitions()
            self._logger.info(
                "技能工具已按需加载",
                event_id=event.event_id,
                skills=reply_toolset.executor.activated_skill_names(),
                tools_count=len(tools),
            )

        # Keep history textual; all automatic/manual images are assembled
        # into a labelled user appendix at the END of every model request.
        vision_context.manual_parts.extend(image_parts)
        if vision_just_disabled:
            messages.append({"role": "user", "content": "[原生视觉回退] 图片未发送；非视觉模型和外部图片解析工具已恢复。"})

        # 已经回复过:清零轮次与时间基准,本次管线激活不再提醒
        if state.reply_sent:
            nudge_rounds = 0
            nudge_deadline = monotonic_seconds() + nudge_seconds
        return tools, nudge_rounds, nudge_deadline, state.reply_sent or state.cancelled

    async def _agent_group_pipeline_tail(
        self,
        *,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_copy: MessageQueue,
        queue_key: str,
        messages: list[dict],
        numbering: MessageNumbering,
        rendered_user_ids: set[str],
        state: AgentLoopState,
        is_group: bool,
        group_lifespan: int,
        cost_pipeline_extension_budget: int,
        prompt: str,
        vision_context: ReplyVisionContext,
        native_vision_active: bool,
        reset_silent_deadline,
    ) -> tuple[int, int, bool]:
        """群聊寿命机制与挂起恢复；返回 (寿命, 续用预算, 是否继续外层循环)。"""
        # ── 群聊寿命机制 ──
        if is_group:
            if group_lifespan > 0:
                group_lifespan -= 1
                action = "cancel消耗寿命" if state.cancelled else "回复消耗寿命"
                self._logger.info(
                    f"群聊回复管线{action}",
                    event_id=event.event_id,
                    queue_key=queue_key,
                    remaining_lifespan=group_lifespan,
                    cancelled=state.cancelled,
                )
                if group_lifespan <= 0:
                    # 基础寿命耗尽:成本管线续用判断(缓存命中后继续成本
                    # 低于重启管线输入成本时,额外续用,受阈值上限约束)
                    if cost_pipeline_extension_budget > 0 and self._cache_continue_cheaper_than_restart(
                        vision_context.request_messages(messages) if native_vision_active else messages,
                        prompt, queue, queue_key, numbering
                    ):
                        cost_pipeline_extension_budget -= 1
                        group_lifespan = 1
                        self._logger.info(
                            "群聊回复管线成本续用(缓存命中后继续成本低于重启管线)",
                            event_id=event.event_id,
                            queue_key=queue_key,
                            remaining_extension_budget=cost_pipeline_extension_budget,
                        )
                        self._record_debug(
                            "group_pipeline_cost_extended",
                            event,
                            queue_key=queue_key,
                            remaining_extension_budget=cost_pipeline_extension_budget,
                        )
                    else:
                        self._logger.info(
                            "群聊回复管线寿命归零，结束管线",
                            event_id=event.event_id,
                            queue_key=queue_key,
                        )
                        return group_lifespan, cost_pipeline_extension_budget, False

                # 群聊挂起，等待新消息或后台通知
                self._logger.debug(
                    "群聊管线挂起等待新消息或通知",
                    event_id=event.event_id,
                    queue_key=queue_key,
                    remaining_lifespan=group_lifespan,
                )
                new_entries, notification_text, wake_prompt = (
                    await self._suspend_group_chat(queue, queue_copy, queue_key)
                )
                if not new_entries and not notification_text:
                    self._logger.debug(
                        "群聊挂起超时，结束管线",
                        event_id=event.event_id,
                        queue_key=queue_key,
                    )
                    return group_lifespan, cost_pipeline_extension_budget, False

                # 注入后台通知
                if notification_text:
                    messages.append({"role": "user", "content": notification_text})
                    self._logger.info(
                        "注入后台通知（群聊挂起期间）",
                        event_id=event.event_id,
                        queue_key=queue_key,
                    )
                    self._record_debug(
                        "background_notification_injected_during_group_suspend",
                        event,
                        queue_key=queue_key,
                        notification=notification_text[:200],
                    )

                # 注入睡眠唤醒提示词(挂起期间被@唤醒)
                if wake_prompt:
                    messages.append(
                        {"role": "user", "content": f"[系统状态]{wake_prompt}"}
                    )
                    self._logger.info(
                        "注入睡眠唤醒提示词(挂起期间被@唤醒)",
                        event_id=event.event_id,
                        queue_key=queue_key,
                    )

                # 构建增量提示并注入（角色消息 + 新成员档案说明）
                if new_entries:
                    resume_messages = await self._build_group_chat_resume_messages(
                        new_entries,
                        queue_key,
                        rendered_user_ids,
                        numbering,
                        queue_copy,
                    )

                    for resume_message in resume_messages:
                        messages.append(resume_message)
                    if resume_messages:
                        self._record_debug(
                            "group_chat_resume_content_injected",
                            event,
                            queue_key=queue_key,
                            injected_messages=[
                                {
                                    "role": m.get("role"),
                                    "content": (m.get("content") or "")[:200],
                                }
                                for m in resume_messages
                            ],
                        )

                # 重置静默超时计时器，避免挂起耗时触发超时保护
                reset_silent_deadline()
                # 重置事件状态，允许下一轮回复
                event.state = ReplyState.GENERATING
                event.completed_at = None
                return group_lifespan, cost_pipeline_extension_budget, True  # 继续外层 while 循环，重新进入 agent 回复流程

            # 寿命为 0（禁用寿命机制），正常结束管线
            return group_lifespan, cost_pipeline_extension_budget, False
        return group_lifespan, cost_pipeline_extension_budget, False

    async def _agent_private_pipeline_tail(
        self,
        *,
        event: ReplyEvent,
        queue_key: str,
        queue: MessageQueue,
        queue_copy: MessageQueue,
        numbering: MessageNumbering,
        messages: list[dict],
        native_vision_active: bool,
        vision_context: ReplyVisionContext,
    ) -> bool:
        """私聊 token 守护与挂起恢复；返回 False 表示结束会话。"""
        # Count the image appendix too; the automatic image budget must not
        # bypass the existing total-context lifetime guard.
        estimated_tokens = self._estimate_tokens(
            vision_context.request_messages(messages) if native_vision_active else messages
        )
        # Token 超限 → 先做 compact 检查点；失败才结束会话。
        if estimated_tokens >= self._get_private_chat_max_tokens():
            self._logger.info(
                "私聊token超限，尝试 compact",
                event_id=event.event_id,
                queue_key=queue_key,
                estimated_tokens=estimated_tokens,
            )
            if not await self._compact_private_history(
                messages, event=event, queue_key=queue_key
            ):
                self._logger.info(
                    "私聊token超限且 compact 未成功，结束当前会话",
                    event_id=event.event_id,
                    queue_key=queue_key,
                    estimated_tokens=estimated_tokens,
                )
                return False

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
            return False

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

        # 注入新消息(按发送者拆分为角色消息),继续下一轮 agent 循环
        if new_entries:
            from neobot_app.prompt.role_messages import (
                build_role_messages_from_entries,
            )

            new_role_messages = build_role_messages_from_entries(
                new_entries,
                queue_copy,
                queue_key,
                numbering=numbering,
                bot_account=self._get_bot_account(),
                include_boundary_markers=self._show_boundary_markers(),
            )
            if new_role_messages:
                messages.extend(new_role_messages)
                self._record_debug(
                    "private_chat_new_messages_injected",
                    event,
                    queue_key=queue_key,
                    injected_count=len(new_role_messages),
                )
        return True
