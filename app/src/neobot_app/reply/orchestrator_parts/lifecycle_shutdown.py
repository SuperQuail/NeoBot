"""后台回复启动与整体关闭。"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from ._runtime import asyncio


class LifecycleShutdownMixin:
    def start_background_reply(
        self,
        *,
        kind: str,
        conversation_id: str,
        content: str,
        manager_name: str = "background_drawing",
        reasons: list[str] | None = None,
    ) -> Any | None:
        """程序化启动回复管线，用于后台绘图等系统通知。

        当绘图完成但对应聊天流无活跃管线时，由 BackgroundDrawingManager 调用。
        """
        if self._closed:
            self._logger.warning("ReplyOrchestrator 已关闭，拒绝创建后台回复管线")
            return None
        from neobot_app.willing.models import WillingDecision

        queue_key = str(conversation_id)
        pipeline_key = f"{kind}:{queue_key}"

        if not kind or not conversation_id:
            self._logger.error(
                "start_background_reply: 无效的会话参数",
                kind=kind,
                conversation_id=conversation_id,
                manager_name=manager_name,
            )
            return None

        existing = self._active_pipelines.get(pipeline_key)
        if existing is not None and existing.done():
            self._active_pipelines.pop(pipeline_key, None)
            existing = None
        if existing is not None and not existing.done():
            self._logger.debug(
                "后台回复管线已在运行，跳过创建",
                pipeline_key=pipeline_key,
            )
            return None

        queue = self._group_queue if kind == "group" else self._friend_queue
        if queue is None:
            self._logger.error(
                "无法启动后台回复：消息队列未配置",
                kind=kind,
                conversation_id=conversation_id,
            )
            return None

        # 将通知内容推入消息队列作为触发消息
        @dataclass
        class _SyntheticSender:
            card: str = ""
            nickname: str = "系统"

        @dataclass
        class _SyntheticMessage:
            time: int = 0
            self_id: int = 0
            post_type: str = "message"
            message_type: str = kind
            sub_type: str = "normal"
            message_id: int = 0
            user_id: int = 0
            group_id: int = int(conversation_id) if kind == "group" and conversation_id.isdigit() else 0
            message: list = field(default_factory=lambda: [{"type": "text", "data": {"text": content}}])
            raw_message: str = ""
            font: int = 0
            sender: Any = field(default_factory=_SyntheticSender)
            message_seq: int = 0
            target_id: int = 0
            temp_source: int = 0

        synthetic_msg = _SyntheticMessage()

        decision = WillingDecision(
            manager_name=manager_name,
            probability=1.0,
            should_reply=True,
            reasons=tuple(reasons) if reasons else ("后台绘图任务完成通知",),
        )

        return self.start_reply(
            message=synthetic_msg,
            queue=queue,
            queue_key=queue_key,
            decision=decision,
            skip_cooldown=True,
            background_content=content,
        )

    async def shutdown(self) -> None:
        self._closed = True
        deferred: BaseException | None = None

        async def _run_step(label: str, action: Callable[[], Any]) -> None:
            nonlocal deferred
            deferred_cancel: asyncio.CancelledError | None = None
            cleanup_task: asyncio.Future[Any] | None = None
            try:
                result = action()
                if inspect.isawaitable(result):
                    cleanup_task = asyncio.ensure_future(result)
                    while not cleanup_task.done():
                        try:
                            await asyncio.shield(cleanup_task)
                        except asyncio.CancelledError as exc:
                            current = asyncio.current_task()
                            if current is not None and current.cancelling():
                                deferred_cancel = deferred_cancel or exc
                                continue
                            raise
                    cleanup_task.result()
            except BaseException as exc:
                if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                    self._logger.error(
                        f"{label} 在关闭编排器时被中断",
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
                    deferred = exc
                elif isinstance(exc, asyncio.CancelledError):
                    self._logger.warning(f"{label} 在关闭编排器时被取消")
                    current = asyncio.current_task()
                    if deferred_cancel is not None:
                        deferred = deferred or deferred_cancel
                    elif current is not None and current.cancelling():
                        deferred = deferred or exc
                else:
                    self._logger.warning(
                        f"{label} 在关闭编排器时失败",
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
            if deferred_cancel is not None:
                deferred = deferred or deferred_cancel

        async def _cancel_tasks(tasks: set[asyncio.Task[None]]) -> None:
            pending = list(tasks)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        async def _close_executors() -> None:
            executors = list(self._tool_executors.values())
            if not executors:
                return
            fatal: BaseException | None = None
            results = await asyncio.gather(
                *(executor.close() for executor in executors),
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, BaseException):
                    self._logger.warning(
                        "回复工具执行器关闭失败",
                        error_type=type(result).__name__,
                        error=str(result),
                    )
                    if isinstance(result, (KeyboardInterrupt, SystemExit)):
                        fatal = result
            if fatal is not None:
                raise fatal

        await _run_step("reply pipelines", lambda: _cancel_tasks(self._tasks))
        await _run_step("reply completion callbacks", lambda: _cancel_tasks(self._callback_tasks))
        await _run_step("reply tool executors", _close_executors)
        if self._skill_manager is not None:
            shared_tools = self._skill_manager.get("agent_tools")
            if shared_tools is not None:
                await _run_step("shared agent tools", shared_tools.close)
        if self._drawing_manager is not None:
            await _run_step("drawing manager", self._drawing_manager.shutdown)
        if self._scheduled_task_manager is not None:
            await _run_step("scheduled task manager", self._scheduled_task_manager.shutdown)
        if self._notification_hub is not None:
            await _run_step("notification hub", self._notification_hub.clear)
        if self._provider is not None:
            await _run_step("reply provider", self._provider.close)

        self._tool_executors.clear()
        self._active_pipelines.clear()
        self._tasks.clear()
        self._callback_tasks.clear()
        self._last_reply_time.clear()
        self._last_sentence_time.clear()
        self._logger.info("ReplyOrchestrator 已关闭")
        if deferred is not None:
            raise deferred
