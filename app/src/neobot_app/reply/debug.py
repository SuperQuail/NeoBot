"""DebugHelper —— 轻量包装器，用于记录回复生命周期事件。"""

from __future__ import annotations

from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.runtime_event import RuntimeEnvelope


class DebugHelper:
    """封装回复流水线的调试记录与运行时事件上报。"""

    def __init__(
        self,
        *,
        debug_recorder: Any = None,
        runtime_events: Any = None,
        logger: Logger | None = None,
    ) -> None:
        self._debug_recorder = debug_recorder
        self._runtime_events = runtime_events
        self._logger = logger or NullLogger()

    def record(self, stage: str, event: Any, **extra: object) -> None:
        if self._debug_recorder is None:
            return
        self._debug_recorder.record_reply_event(stage, event, **extra)

    async def emit_runtime_event(self, stage: str, event: Any, **payload: object) -> RuntimeEnvelope:
        conv_ref = getattr(event, "conversation_ref", None)
        envelope = RuntimeEnvelope(
            kind="reply_lifecycle",
            stage=stage,
            source="app.reply",
            target=(f"{conv_ref.kind}:{conv_ref.id}" if conv_ref is not None else None),
            payload={"reply_event": event, **payload},
            context={
                "event_id": event.event_id,
                "mode": getattr(event, "mode", ""),
                "state": getattr(event, "state", None),
            },
        )
        dispatch = getattr(self._runtime_events, "dispatch_envelope", None)
        if callable(dispatch):
            return await dispatch(envelope)
        return envelope

    async def handle_runtime_failure(
        self,
        event: Any,
        exc: Exception,
        *,
        provider_error_message: str,
        send_with_timeout: Any,
    ) -> None:
        if not isinstance(exc, RuntimeError):
            return
        if "chat provider" not in str(exc):
            return
        # 模型不可用只写日志；不向任何聊天流发送错误提示。
        # 失败由回复管线的唯一收尾点记录；这里只补充详细调试事件。
        self.record(
            "provider_unavailable_notice_suppressed",
            event,
            error=str(exc),
        )
