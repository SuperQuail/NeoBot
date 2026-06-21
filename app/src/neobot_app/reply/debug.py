"""DebugHelper — lightweight wrapper for recording reply lifecycle events."""

from __future__ import annotations

from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.runtime_event import RuntimeEnvelope


class DebugHelper:
    """Encapsulates debug recording and runtime event emission for the reply pipeline."""

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
            target=(
                f"{conv_ref.kind}:{conv_ref.id}"
                if conv_ref is not None
                else None
            ),
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
        conv_ref = getattr(event, "conversation_ref", None)
        if conv_ref is None:
            return
        try:
            await send_with_timeout(conv_ref, provider_error_message)
        except Exception as send_exc:
            self._logger.error(
                "Provider unavailable notice failed",
                event_id=getattr(event, "event_id", "?"),
                error=str(send_exc),
            )
            self.record(
                "provider_unavailable_notice_failed",
                event,
                send_error=str(send_exc),
            )
            return
        self.record(
            "provider_unavailable_notice_sent",
            event,
            notice=provider_error_message,
        )
