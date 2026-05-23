from __future__ import annotations

from typing import Any

from neobot_contracts.ports.logging import Logger, NullLogger
from neobot_contracts.ports.output import OutputMessage
from neobot_contracts.ports.runtime_event import RuntimeEnvelope


class RuntimeOutput:
    def __init__(self, *, logger: Logger | None = None, runtime_events: Any = None) -> None:
        self._logger = logger or NullLogger()
        self._runtime_events = runtime_events

    def set_runtime_events(self, runtime_events: Any) -> None:
        self._runtime_events = runtime_events

    def write(
        self,
        text: str,
        *,
        channel: str = "stdout",
        source: str = "",
        target: str | None = None,
        **metadata: Any,
    ) -> None:
        message = OutputMessage(
            text=text,
            channel=channel,
            source=source,
            target=target,
            metadata=dict(metadata),
        )
        self._logger.info(
            message.text,
            output_channel=message.channel,
            output_source=message.source,
            output_target=message.target or "",
        )
        dispatch = getattr(self._runtime_events, "dispatch_envelope", None)
        if callable(dispatch):
            try:
                import asyncio

                asyncio.get_running_loop().create_task(
                    dispatch(
                        RuntimeEnvelope(
                            kind="output",
                            stage=message.channel,
                            source=message.source,
                            target=message.target,
                            payload={"message": message},
                            context=dict(message.metadata),
                        )
                    )
                )
            except RuntimeError:
                pass

    def status(self, text: str, *, source: str = "", **metadata: Any) -> None:
        self.write(text, channel="status", source=source, **metadata)

    def error(self, text: str, *, source: str = "", **metadata: Any) -> None:
        self.write(text, channel="stderr", source=source, **metadata)
