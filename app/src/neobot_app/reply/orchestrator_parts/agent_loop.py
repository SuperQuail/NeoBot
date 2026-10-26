"""agent 回复管线主循环。"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from neobot_app.reply.event import ReplyEvent, ReplyState
from ._runtime import monotonic_seconds
from .agent_state import AgentLoopState
from .prompt_blocks import _NO_TOOL_CALL_REMINDER

if TYPE_CHECKING:
    from neobot_app.message.queue import MessageQueue


class AgentLoopMixin:

    async def _run_agent_mode_inner(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
        *,
        silent_timeout: float,
        reset_silent_deadline: Callable[[float], None],
        silent_remaining: Callable[[], float | None],
        cancel_for_silence: Callable[[str], None],
    ) -> None:
        (
            numbering,
            queue_copy,
            messages,
            prompt,
            allowed_tools,
            native_vision_active,
        ) = await self._prepare_agent_messages(event, queue, queue_key)
        state = AgentLoopState()
        conv_kind, conv_id, current_user_id = self._agent_conversation_ids(event)
        reply_toolset, tools, vision_context, default_image_loader = (
            await self._build_agent_toolset(
                event=event,
                queue=queue,
                queue_copy=queue_copy,
                queue_key=queue_key,
                prompt=prompt,
                messages=messages,
                allowed_tools=allowed_tools,
                numbering=numbering,
                conv_kind=conv_kind,
                conv_id=conv_id,
                current_user_id=current_user_id,
                state=state,
            )
        )
        # 5. Agent 循环（外层 while 支持私聊连续会话）
        loop_context = await self._agent_prepare_loop_state(
            event, queue, queue_copy, queue_key
        )
        if loop_context is None:
            return
        (
            max_iterations,
            is_private,
            is_group,
            group_lifespan,
            cost_pipeline_extension_budget,
            rendered_user_ids,
            compressed_tool_call_ids,
            tool_name_by_call_id,
            tool_failure_streak,
        ) = loop_context
        state.is_group = is_group
        state.rendered_user_ids = rendered_user_ids
        # 回复前追加的 <当前时间> user 块:每次调用模型前追加一条最新时间,
        # 已追加的时间块保留在对话历史里(不清理),让模型能看到时间推进。
        # 分级注入:每次管线激活的第一次模型调用用完整 [current_time],
        # 同一激活内的后续调用只追加 [current_time_short](短时间戳)。
        state.time_block_full_sent = False
        state.previous_entries = queue_copy.entries(queue_key)
        round_index = 0
        while True:
            # 需要重新构建/续用提示词的新一轮:把较早的工具返回压缩,
            # 只保留最近 N 条完整内容,控制上下文成本
            if round_index > 0:
                self._compress_stale_tool_results(
                    messages,
                    compressed_tool_call_ids,
                    tool_name_by_call_id,
                    event=event,
                    queue_key=queue_key,
                )
            round_index += 1
            state.reply_sent = False
            state.cancelled = False
            no_tool_reminders = 0
            # 时间块分级:每轮(每次管线激活)重置为"尚未注入完整时间块"
            state.time_block_full_sent = False
            # 防重复提醒:每次管线激活只追加一次
            avoid_repeat_sent = False
            # 沉默提醒记录器:轮次归零、阶梯阈值取首次值、时间基准从本轮开始
            (
                _nudge_enabled,
                nudge_first_rounds,
                nudge_repeat_rounds,
                nudge_seconds,
                _nudge_max,
            ) = self._get_silent_nudge_settings()
            nudge_rounds = 0
            nudge_emitted = 0
            nudge_next_at = nudge_first_rounds
            nudge_deadline = monotonic_seconds() + nudge_seconds

            vision_fallback_bonus = False
            for iteration in range(max_iterations + 1):
                if iteration >= max_iterations and not vision_fallback_bonus:
                    break
                keep_going, native_vision_active, tools = await self._agent_pre_model_check(
                    iteration=iteration,
                    event=event,
                    queue_key=queue_key,
                    messages=messages,
                    native_vision_active=native_vision_active,
                    tools=tools,
                    reply_toolset=reply_toolset,
                )
                if not keep_going:
                    return
                pipeline_key = f"{conv_kind}:{conv_id}"
                notification_text = await self._poll_background_notifications(
                    pipeline_key
                )
                if notification_text:
                    messages.append({"role": "user", "content": notification_text})
                    self._logger.info(
                        "orchestrator 注入通知到消息列表",
                        event_id=event.event_id,
                        pipeline_key=pipeline_key,
                        iteration=iteration,
                        notification_preview=notification_text[:120],
                    )
                    self._record_debug(
                        "background_notification_injected",
                        event,
                        queue_key=queue_key,
                        notification=notification_text[:200],
                    )

                # 沉默提醒:读完后台通知之后、发起模型调用之前判定。
                # 模型长时间只调用工具、对用户一条消息都不发时注入一条 user 提醒;
                # 提醒后刷新记录器(轮次归零、时间基准重置、阶梯阈值切到 repeat_rounds),
                # 于是之后可再次提醒;提醒次数上限 silent_nudge_max。
                nudge_reason = self._nudge_reason(
                    reply_sent=state.reply_sent,
                    rounds=nudge_rounds,
                    next_at=nudge_next_at,
                    emitted=nudge_emitted,
                    deadline=nudge_deadline,
                )
                if nudge_reason is not None:
                    messages.append({"role": "user", "content": self._nudge_text()})
                    nudge_rounds = 0
                    nudge_deadline = monotonic_seconds() + nudge_seconds
                    nudge_next_at = nudge_repeat_rounds
                    nudge_emitted += 1
                    self._logger.info(
                        "长任务沉默提醒已注入",
                        event_id=event.event_id,
                        queue_key=queue_key,
                        iteration=iteration + 1,
                        emitted=nudge_emitted,
                        reason=nudge_reason,
                    )
                    self._record_debug(
                        "silent_nudge",
                        event,
                        queue_key=queue_key,
                        iteration=iteration + 1,
                        emitted=nudge_emitted,
                        reason=nudge_reason,
                    )

                if native_vision_active:
                    await self._agent_refresh_default_images(
                        vision_context=vision_context,
                        queue_copy=queue_copy,
                        queue_key=queue_key,
                        numbering=numbering,
                        default_image_loader=default_image_loader,
                        pipeline_key=pipeline_key,
                        silent_remaining=silent_remaining,
                    )
                # 回复前:追加独立的 <当前时间> user 块(始终是最后一条消息)
                self._append_current_time_block(state, messages)
                # 防重复提醒:每次管线激活只追加一次,节奏独立于时间块
                if not avoid_repeat_sent:
                    avoid_repeat_sent = True
                    avoid_repeat_message = self._build_avoid_repeat_message()
                    if avoid_repeat_message is not None:
                        messages.append(avoid_repeat_message)
                request_messages = (
                    vision_context.request_messages(messages) if native_vision_active else list(messages)
                )
                self._record_flow_request(
                    event, queue_key, request_messages, iteration=iteration + 1
                )
                remaining = silent_remaining()
                if remaining is not None and remaining <= 0:
                    cancel_for_silence("before_model")
                    return
                model_result = await self._agent_call_model(
                    event=event,
                    queue_key=queue_key,
                    iteration=iteration,
                    remaining=remaining,
                    request_messages=request_messages,
                    tools=tools,
                    reset_silent_deadline=reset_silent_deadline,
                    cancel_for_silence=cancel_for_silence,
                )
                if model_result is None:
                    return
                response, request_messages, tools = model_result
                (
                    vision_just_disabled,
                    tool_calls,
                    tools,
                    native_vision_active,
                ) = await self._agent_after_model_response(
                    event=event,
                    queue_key=queue_key,
                    iteration=iteration,
                    request_messages=request_messages,
                    response=response,
                    messages=messages,
                    tools=tools,
                    native_vision_active=native_vision_active,
                    reply_toolset=reply_toolset,
                )
                if not tool_calls and vision_just_disabled:
                    vision_fallback_bonus = True
                    # Retry once with the restored parser tools rather than sending
                    # an answer produced without either images or a parser.
                    messages.append({"role": "user", "content": "[原生视觉回退] 图片无法发送，非视觉模型及图片解析工具已恢复。请按需调用 image_parse__parse_image，不能声称已经看到图片。"})
                    continue
                if not tool_calls:
                    if not state.reply_sent:
                        if no_tool_reminders < 1:
                            no_tool_reminders += 1
                            messages.append({"role": "user", "content": _NO_TOOL_CALL_REMINDER})
                            self._record_debug(
                                "no_tool_call_reminder",
                                event,
                                queue_key=queue_key,
                                iteration=iteration + 1,
                            )
                            self._logger.info(
                                "模型未调用工具，已追加 send_reply/cancel 确认提示",
                                event_id=event.event_id,
                                queue_key=queue_key,
                                iteration=iteration + 1,
                            )
                            continue
                        content = response.get("content", "")
                        text = (
                            content.strip()
                            if isinstance(content, str)
                            else str(content)
                        )
                        review_pending = bool(
                            getattr(reply_toolset.executor, "ai_check_pending", False)
                        )
                        if text or review_pending:
                            # agent 模式的对外发言只能经 send_reply/cancel。没有工具
                            # 调用的正文是模型写给自己看的判断/草稿，直接发送就是
                            # 把内部判断泄漏给用户；这里不重试、不追问，只留审计。
                            self._handle_unsent_prose(
                                event,
                                text,
                                response,
                                queue_key=queue_key,
                                iteration=iteration + 1,
                                review_pending=review_pending,
                            )
                        else:
                            # 空轮次：正文为空且没有工具调用。旧实现在这里直接
                            # break，事件以 COMPLETED/err=None 收尾，回复丢失且
                            # 完全不可观测；现在必须显式记录并置为 FAILED。
                            self._handle_empty_turn(
                                event,
                                response,
                                queue_key=queue_key,
                                iteration=iteration + 1,
                            )
                    break
                # 只有本轮确实产生了 tool_calls 才计入"埋头干"轮数
                nudge_rounds += 1
                image_parts = await self._agent_execute_tool_calls(
                    event=event,
                    queue_key=queue_key,
                    iteration=iteration,
                    tool_calls=tool_calls,
                    messages=messages,
                    reply_toolset=reply_toolset,
                    tool_name_by_call_id=tool_name_by_call_id,
                    tool_failure_streak=tool_failure_streak,
                    silent_remaining=silent_remaining,
                    reset_silent_deadline=reset_silent_deadline,
                )
                (
                    tools,
                    nudge_rounds,
                    nudge_deadline,
                    tool_turn_done,
                ) = await self._agent_after_tool_calls(
                    event=event,
                    messages=messages,
                    tools=tools,
                    reply_toolset=reply_toolset,
                    vision_context=vision_context,
                    image_parts=image_parts,
                    vision_just_disabled=vision_just_disabled,
                    state=state,
                    nudge_rounds=nudge_rounds,
                    nudge_deadline=nudge_deadline,
                    nudge_seconds=nudge_seconds,
                )
                if tool_turn_done:
                    break
                await self._agent_inject_new_entries(
                    event=event,
                    queue_key=queue_key,
                    queue=queue,
                    queue_copy=queue_copy,
                    numbering=numbering,
                    messages=messages,
                    is_group=is_group,
                    rendered_user_ids=rendered_user_ids,
                )
            # 保存编号映射（每轮更新）
            event.message_number_map = numbering.mapping

            # CANCELLED 是终态；不得通过群聊寿命循环把它直接改回 GENERATING。
            if state.cancelled or event.state == ReplyState.CANCELLED:
                break

            # 未回复且非取消 → 异常，结束
            if not state.reply_sent and not state.cancelled:
                break
            if is_group:
                (
                    group_lifespan,
                    cost_pipeline_extension_budget,
                    resume_pipeline,
                ) = await self._agent_group_pipeline_tail(
                    event=event,
                    queue=queue,
                    queue_copy=queue_copy,
                    queue_key=queue_key,
                    messages=messages,
                    numbering=numbering,
                    rendered_user_ids=rendered_user_ids,
                    state=state,
                    is_group=is_group,
                    group_lifespan=group_lifespan,
                    cost_pipeline_extension_budget=cost_pipeline_extension_budget,
                    prompt=prompt,
                    vision_context=vision_context,
                    native_vision_active=native_vision_active,
                    reset_silent_deadline=reset_silent_deadline,
                )
                if resume_pipeline:
                    continue
                break
            # 非私聊 → 结束（兜底）
            if not is_private:
                break
            if not await self._agent_private_pipeline_tail(
                event=event,
                queue_key=queue_key,
                queue=queue,
                queue_copy=queue_copy,
                numbering=numbering,
                messages=messages,
                native_vision_active=native_vision_active,
                vision_context=vision_context,
            ):
                break
        if event.state == ReplyState.GENERATING and not event.is_terminal:
            try:
                event.transition(ReplyState.COMPLETED)
            except RuntimeError:
                pass
