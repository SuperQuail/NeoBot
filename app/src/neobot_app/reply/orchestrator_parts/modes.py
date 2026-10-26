"""回复管线入口：common / agent 两种模式的分派与执行。"""
from __future__ import annotations

from typing import TYPE_CHECKING
from neobot_chat.runtime.agent import SILENT_HEARTBEAT
from neobot_app.reply.event import ReplyEvent, ReplyState
from ._runtime import asyncio, monotonic_seconds
if TYPE_CHECKING:
    from neobot_app.message.queue import MessageQueue

class ModesMixin:
    async def _run(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
    ) -> None:
        started_at = monotonic_seconds()
        try:
            before_decide = await self._emit_runtime_event(
                "reply.decide.before", event, queue_key=queue_key
            )
            if before_decide.consumed:
                event.error = "reply lifecycle consumed before decision"
                event.transition(ReplyState.CANCELLED)
                await self._emit_runtime_event(
                    "reply.cancel", event, queue_key=queue_key
                )
                return
            start_envelope = await self._emit_runtime_event(
                "reply.decide.after", event, queue_key=queue_key
            )
            if start_envelope.consumed:
                event.error = "reply lifecycle consumed before run"
                event.transition(ReplyState.CANCELLED)
                await self._emit_runtime_event(
                    "reply.cancel", event, queue_key=queue_key
                )
                return
            self._set_flow_active(event, queue_key, True)
            if event.mode == "agent":
                await self._run_agent_mode(event, queue, queue_key)
            else:
                await self._run_common_mode(event, queue, queue_key)
            self._set_flow_active(event, queue_key, False)
            if event.state == ReplyState.CANCELLED:
                self._record_debug("cancelled", event, queue_key=queue_key)
                await self._emit_runtime_event(
                    "reply.cancel", event, queue_key=queue_key
                )
                return
            if event.state == ReplyState.FAILED:
                # 管线内部判定失败（例如模型空轮次）。必须走失败收尾：旧实现
                # 一路记成 completed，日志里看不出「这条消息根本没回复」。
                self._logger.warning(
                    "回复事件失败（管线内部判定）",
                    event_id=event.event_id,
                    mode=event.mode,
                    error=event.error,
                )
                self._record_debug("failed", event, queue_key=queue_key)
                await self._emit_runtime_event(
                    "reply.fail", event, queue_key=queue_key, error=event.error
                )
                return
            # 记录完成时间用于冷却
            if event.conversation_ref is not None:
                pipeline_key = f"{event.conversation_ref.kind}:{queue_key}"
                self._last_reply_time[pipeline_key] = monotonic_seconds()
            # 记录上次回复位置
            enable_tracking = (
                getattr(
                    getattr(self._config, "chat", None),
                    "enable_last_reply_tracking",
                    True,
                )
                if self._config
                else True
            )
            if enable_tracking:
                queue.set_last_reply_position(
                    queue_key,
                    before_message_id=event.pre_reply_message_id,
                )
            elapsed = monotonic_seconds() - started_at
            self._logger.info(
                "回复事件结束",
                event_id=event.event_id,
                mode=event.mode,
                state=event.state.name,
                duration=f"{elapsed:.1f}s",
                reply_preview=event.generated_text[:80] if event.generated_text else "",
            )
            self._record_debug("completed", event, queue_key=queue_key)
            await self._emit_runtime_event(
                "reply.complete", event, queue_key=queue_key, duration_seconds=elapsed
            )
        except asyncio.CancelledError:
            self._set_flow_active(event, queue_key, False)
            event.error = "cancelled"
            if not event.is_terminal:
                try:
                    event.transition(ReplyState.CANCELLED)
                except RuntimeError:
                    pass
            self._logger.warning("回复事件被取消", event_id=event.event_id)
            self._record_debug("cancelled", event, queue_key=queue_key)
            await self._emit_runtime_event("reply.cancel", event, queue_key=queue_key)
            raise
        except Exception as exc:
            self._set_flow_active(event, queue_key, False)
            try:
                event.transition(ReplyState.FAILED)
            except RuntimeError:
                pass
            event.error = f"{type(exc).__name__}: {exc}"
            self._logger.error(
                "回复事件失败",
                event_id=event.event_id,
                mode=event.mode,
                error=event.error,
            )
            self._record_debug("failed", event, queue_key=queue_key)
            await self._emit_runtime_event(
                "reply.fail", event, queue_key=queue_key, error=event.error
            )
            await self._handle_runtime_failure(event, exc)
    async def _run_common_mode(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
    ) -> None:

        last_reply_message_id, all_new = self._resolve_last_reply(queue, queue_key)
        role_messages = await self._build_role_messages(
            event,
            queue,
            queue_key,
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
        )
        context_messages: list[dict[str, str]] = []
        prompt = await self._build_prompt(
            event,
            queue,
            queue_key,
            last_reply_message_id=last_reply_message_id,
            all_new=all_new,
            context_blocks=context_messages,
        )
        self._record_flow_prompt(event, queue_key, prompt)
        self._record_debug(
            "base_prompt_built", event, queue_key=queue_key, prompt=prompt
        )

        # pre-reply hooks：可短路跳过 AI 生成
        reply_text = await self._apply_pre_reply_hooks(event)
        if reply_text is None:
            reply_text = await self._generate_reply(
                event, prompt, role_messages, context_messages
            )

        self._record_debug(
            "reply_generated", event, queue_key=queue_key, reply_text=reply_text
        )

        await self._send_reply(
            event, reply_text, self_sent=self._self_sent_sink(queue, queue, queue_key)
        )
    async def _run_agent_mode(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
    ) -> None:
        is_group = (
            event.conversation_ref is not None
            and event.conversation_ref.kind == "group"
        )
        silent_timeout = (
            self._get_group_agent_silent_timeout_seconds() if is_group else 0.0
        )
        silent_deadline = (
            monotonic_seconds() + silent_timeout if silent_timeout > 0 else 0.0
        )

        def reset_silent_deadline(extra_seconds: float = 0.0) -> None:
            nonlocal silent_deadline
            if silent_timeout <= 0:
                return
            silent_deadline = (
                monotonic_seconds() + silent_timeout + max(0.0, extra_seconds)
            )

        def silent_remaining() -> float | None:
            if silent_timeout <= 0:
                return None
            return silent_deadline - monotonic_seconds()

        def cancel_for_silence(phase: str) -> None:
            event.error = (
                f"群聊 agent 管线静默超过 {silent_timeout:.0f} 秒，"
                f"已强制关闭（阶段：{phase}）"
            )
            if not event.is_terminal:
                event.transition(ReplyState.CANCELLED)
            self._logger.warning(
                "群聊 agent 管线静默超时，强制关闭",
                event_id=event.event_id,
                queue_key=queue_key,
                phase=phase,
                timeout_seconds=silent_timeout,
            )
            self._record_debug(
                "group_agent_silent_timeout",
                event,
                queue_key=queue_key,
                phase=phase,
                timeout_seconds=silent_timeout,
            )

        heartbeat_token = SILENT_HEARTBEAT.set(reset_silent_deadline)
        try:
            await self._run_agent_mode_inner(
                event,
                queue,
                queue_key,
                silent_timeout=silent_timeout,
                reset_silent_deadline=reset_silent_deadline,
                silent_remaining=silent_remaining,
                cancel_for_silence=cancel_for_silence,
            )
        finally:
            SILENT_HEARTBEAT.reset(heartbeat_token)
