"""回复管线入口：common / agent 两种模式的分派与执行。"""
from __future__ import annotations

from typing import TYPE_CHECKING
from neobot_chat.runtime.agent import SILENT_HEARTBEAT
from neobot_contracts.ports.speaking import SpeechBlocked
from neobot_app.reply.event import ReplyEvent, ReplyState
from ._runtime import asyncio, monotonic_seconds
if TYPE_CHECKING:
    from neobot_app.message.queue import MessageQueue

class ModesMixin:


    def _record_reply_delivered(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
        *,
        before_message_id: int | None = None,
    ) -> None:
        """每条真实发出的消息都推进冷却与 last_reply_position（长期管线的语义）。"""
        conv = event.conversation_ref
        if conv is None:
            return
        self._last_reply_time[f"{conv.kind}:{queue_key}"] = monotonic_seconds()
        enable_tracking = (
            getattr(
                getattr(self._config, "chat", None),
                "enable_last_reply_tracking",
                True,
            )
            if self._config
            else True
        )
        if not enable_tracking:
            return
        if before_message_id is None or before_message_id <= 0:
            # Bot 自身消息使用负合成 id，不能拿它当“已回复到”的位置。
            before_message_id = event.pre_reply_message_id
        if before_message_id is not None and before_message_id > 0:
            queue.set_last_reply_position(queue_key, before_message_id=before_message_id)

    async def _run(
        self,
        event: ReplyEvent,
        queue: MessageQueue,
        queue_key: str,
    ) -> None:
        started_at = monotonic_seconds()
        try:
            policy = getattr(getattr(self._adapter, "core", None), "speaking_policy", None)
            if policy is not None and event.conversation_ref is not None:
                decision = policy.evaluate(event.conversation_ref)
                if not decision.allowed:
                    raise SpeechBlocked(decision.reason)
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
            self._normalize_delivered_terminal(event, queue_key=queue_key)
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
            # 冷却与 last_reply_position 已在每条消息发出时更新；这里只补事件终态。
            if event.state is ReplyState.GENERATING and event.send_response is not None:
                event.transition(ReplyState.COMPLETED)
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
        except SpeechBlocked as exc:
            event.speech_blocked = exc
            self._set_flow_active(event, queue_key, False)
            event.error = f"SpeechBlocked: {exc}"
            if not event.is_terminal:
                event.transition(ReplyState.CANCELLED)
            self._logger.info("发言策略取消回复", event_id=event.event_id, reason=str(exc))
            self._record_debug("speaking_policy_blocked", event, queue_key=queue_key)
            await self._emit_runtime_event("reply.cancel", event, queue_key=queue_key)
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
            if event.send_response is not None:
                # 回复已经真实发出；发送之后的异常不能把用户看到的“已回复”改写成失败。
                original_state = event.state.name
                event.state = ReplyState.COMPLETED
                event.error = None
                self._logger.warning(
                    "回复已发出，后续异常按完成收尾",
                    event_id=event.event_id,
                    original_state=original_state,
                    error=f"{type(exc).__name__}: {exc}",
                )
                self._record_debug(
                    "post_reply_terminal_normalized",
                    event,
                    queue_key=queue_key,
                    original_state=original_state,
                )
                await self._emit_runtime_event(
                    "reply.complete",
                    event,
                    queue_key=queue_key,
                    duration_seconds=monotonic_seconds() - started_at,
                )
                return
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


    def _normalize_delivered_terminal(
        self, event: ReplyEvent, *, queue_key: str
    ) -> bool:
        """已经真实发出回复后，后续的取消/失败不能撤销“已回复”事实。

        语义：send_reply 是普通工具，回复发出后模型仍可能继续执行工具，
        随后 cancel、空轮次、超时等都可能把事件置为 CANCELLED/FAILED。
        但消息已经送达用户，这轮必须按 COMPLETED 收尾，冷却与
        last_reply_position 才能正常推进；错误只留在日志/调试记录里。
        """
        if event.send_response is None:
            return False
        if event.state not in (ReplyState.CANCELLED, ReplyState.FAILED):
            if event.error:
                self._logger.warning(
                    "回复已发出，忽略后续错误标记",
                    event_id=event.event_id,
                    state=event.state.name,
                    error=event.error,
                )
                event.error = None
            return False
        original_state = event.state.name
        event.state = ReplyState.COMPLETED
        event.error = None
        self._logger.warning(
            "回复已发出，后续取消/失败按完成收尾",
            event_id=event.event_id,
            original_state=original_state,
        )
        self._record_debug(
            "post_reply_terminal_normalized",
            event,
            queue_key=queue_key,
            original_state=original_state,
        )
        return True

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

        before_message_id = queue.get_last_message_id(queue_key)
        delivered = await self._send_reply(
            event, reply_text, self_sent=self._self_sent_sink(queue, queue, queue_key)
        )
        if delivered is not False:
            self._record_reply_delivered(
                event, queue, queue_key, before_message_id=before_message_id
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
