"""回复事件创建与工具执行器释放。"""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING
from neobot_app.reply.event import ReplyEvent, ReplyState
from ._runtime import asyncio, monotonic_seconds
if TYPE_CHECKING:
    from neobot_adapter.model.message import GroupMessage, PrivateMessage
    from neobot_app.message.queue import MessageQueue
    from neobot_app.willing.models import WillingDecision

class LifecycleStartMixin:
    @property
    def speaking_policy(self):
        return getattr(getattr(self._adapter, "core", None), "speaking_policy", None)

    async def wait_reply_delivery(self, event: ReplyEvent) -> bool:
        """Wait only for this event, bounded by existing reply phase limits."""
        task = next(
            (task for task in self._tasks if task.get_name() == f"reply:{event.event_id}"),
            None,
        )
        if task is None:
            if event.speech_blocked is not None:
                raise event.speech_blocked
            return event.send_response is not None
        if task is asyncio.current_task():
            return False
        timeout = (
            self._get_prompt_timeout_seconds()
            + self._get_model_response_timeout_seconds(event)
            + self._get_io_timeout_seconds()
        )
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except TimeoutError:
            return event.send_response is not None
        if event.speech_blocked is not None:
            raise event.speech_blocked
        return event.send_response is not None

    def start_reply(
        self,
        *,
        message: PrivateMessage | GroupMessage,
        queue: MessageQueue,
        queue_key: str,
        decision: WillingDecision,
        pre_reply_message_id: int | None = None,
        on_reply_done: Callable[[], Awaitable[None]] | None = None,
        skip_cooldown: bool = False,
        background_content: str | None = None,
        preactivate: Sequence[str] = (),
    ) -> ReplyEvent | None:
        if self._closed:
            self._logger.warning("ReplyOrchestrator 已关闭，拒绝创建回复管线")
            return None
        mode = self._resolve_mode()
        conversation_ref = self._build_conversation_ref(message, queue_key)
        from neobot_app.agent_tools.invocation import CURRENT_HUMAN_MESSAGE
        event = ReplyEvent(
            mode=mode,
            human_request=CURRENT_HUMAN_MESSAGE.get() and background_content is None,
            message=message,
            willing_decision=decision,
            conversation_ref=conversation_ref,
            pre_reply_message_id=pre_reply_message_id,
            background_content=background_content,
            preactivate=tuple(str(item) for item in (preactivate or ()) if str(item)),
        )

        # 按 kind:queue_key 组合键去重，避免群号与 QQ 号相同时互相阻塞
        pipeline_key = f"{conversation_ref.kind}:{queue_key}"
        existing = self._active_pipelines.get(pipeline_key)
        if existing is not None and existing.done():
            self._active_pipelines.pop(pipeline_key, None)
            existing = None
        if existing is not None and not existing.done():
            self._logger.debug(
                "回复管线已在运行，跳过创建",
                event_id=event.event_id,
                pipeline_key=pipeline_key,
            )
            self._record_debug(
                "skipped_pipeline_overlap",
                event,
                queue_key=queue_key,
                pipeline_key=pipeline_key,
            )
            return None

        # 冷却检查：距上次回复结束不足冷却时间则跳过（后台通知可绕过）
        if not skip_cooldown:
            cooldown = self._get_cooldown_seconds()
            last_time = self._last_reply_time.get(pipeline_key, 0.0)
            elapsed = monotonic_seconds() - last_time
            if elapsed < cooldown:
                self._logger.debug(
                    "冷却中，跳过创建回复",
                    event_id=event.event_id,
                    pipeline_key=pipeline_key,
                    elapsed=f"{elapsed:.1f}s",
                    cooldown=f"{cooldown}s",
                )
                self._record_debug(
                    "skipped_cooldown",
                    event,
                    queue_key=queue_key,
                    pipeline_key=pipeline_key,
                    elapsed_seconds=elapsed,
                    cooldown_seconds=cooldown,
                )
                return None

        self._logger.info(
            "创建回复事件",
            event_id=event.event_id,
            conversation_id=queue_key,
            conversation_kind=getattr(event.conversation_ref, "kind", ""),
            probability=f"{decision.probability:.3f}",
            mode=mode,
        )
        self._record_debug(
            "created",
            event,
            queue_key=queue_key,
            decision={
                "manager_name": decision.manager_name,
                "probability": decision.probability,
                "should_reply": decision.should_reply,
                "reasons": list(decision.reasons),
            },
        )

        def _cleanup(task: asyncio.Task[None]) -> None:
            self._tasks.discard(task)
            if self._active_pipelines.get(pipeline_key) is task:
                self._active_pipelines.pop(pipeline_key, None)
            shared_turn = self._agent_tool_turns.pop(event.event_id, None)
            if shared_turn is not None:
                runtime, context, history = shared_turn
                try:
                    runtime.finish_turn(context, history, cancelled=event.state in {ReplyState.CANCELLED, ReplyState.FAILED})
                except Exception as exc:
                    self._logger.warning("agent 目标续跑未能调度", error=str(exc))
            self._release_executor(event.event_id)
            if on_reply_done is not None:
                callback_task = asyncio.ensure_future(on_reply_done())
                self._callback_tasks.add(callback_task)

                def _callback_done(done_task: asyncio.Future[None]) -> None:
                    self._callback_tasks.discard(callback_task)
                    try:
                        done_task.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception as exc:
                        self._logger.warning(
                            "回复完成回调失败",
                            event_id=event.event_id,
                            pipeline_key=pipeline_key,
                            error=str(exc),
                        )

                callback_task.add_done_callback(_callback_done)

        task = asyncio.create_task(
            self._run(event, queue, queue_key), name=f"reply:{event.event_id}"
        )
        self._tasks.add(task)
        self._active_pipelines[pipeline_key] = task
        task.add_done_callback(_cleanup)
        return event
    def _release_executor(self, event_id: str) -> None:
        """释放某次回复创建的工具执行器。

        执行器持有该轮完整对话历史与技能 token，必须随管线结束释放；但不能直接
        ``close()``：close() 会取消在途的会话工具（download__url / parse_image
        等），而它们的契约是活过本轮回复、完成后由通知中心唤醒下一次回复。
        所以先等在途会话任务自然结束，再关闭执行器——内存依然会被释放，只是
        释放时机推迟到后台工作完成。关闭失败只记日志，不能影响管线收尾。
        """
        executor = self._tool_executors.pop(event_id, None)
        if executor is None:
            return

        async def _drain_and_close() -> None:
            drain = getattr(executor, "drain_sessions", None)
            if callable(drain):
                await drain()
            await executor.close()

        close_task: asyncio.Future[None]
        try:
            close_task = asyncio.ensure_future(_drain_and_close())
        except Exception as exc:
            # 同步异常绝不能冒泡到 done 回调：那会连带跳过 on_reply_done，
            # 让「回复中」标记永久残留。
            self._logger.warning(
                "回复工具执行器释放失败", event_id=event_id, error=str(exc)
            )
            return
        self._callback_tasks.add(close_task)

        def _done(done_task: asyncio.Future[None]) -> None:
            self._callback_tasks.discard(close_task)
            try:
                done_task.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                self._logger.warning(
                    "回复工具执行器释放失败",
                    event_id=event_id,
                    error=str(exc),
                )

        close_task.add_done_callback(_done)
