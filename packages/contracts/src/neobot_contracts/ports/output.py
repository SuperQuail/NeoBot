from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class OutputMessage:
    text: str
    channel: str = "stdout"
    source: str = ""
    target: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class OutputPort(Protocol):
    def write(
        self,
        text: str,
        *,
        channel: str = "stdout",
        source: str = "",
        target: str | None = None,
        **metadata: Any,
    ) -> None: ...

    def status(self, text: str, *, source: str = "", **metadata: Any) -> None: ...

    def error(self, text: str, *, source: str = "", **metadata: Any) -> None: ...


class NullOutput:
    def write(
        self,
        text: str,
        *,
        channel: str = "stdout",
        source: str = "",
        target: str | None = None,
        **metadata: Any,
    ) -> None:
        return None

    def status(self, text: str, *, source: str = "", **metadata: Any) -> None:
        return None

    def error(self, text: str, *, source: str = "", **metadata: Any) -> None:
        return None


class CapturingOutput:
    def __init__(self) -> None:
        self.messages: list[OutputMessage] = []

    def write(
        self,
        text: str,
        *,
        channel: str = "stdout",
        source: str = "",
        target: str | None = None,
        **metadata: Any,
    ) -> None:
        self.messages.append(
            OutputMessage(
                text=text,
                channel=channel,
                source=source,
                target=target,
                metadata=dict(metadata),
            )
        )

    def status(self, text: str, *, source: str = "", **metadata: Any) -> None:
        self.write(text, channel="status", source=source, **metadata)

    def error(self, text: str, *, source: str = "", **metadata: Any) -> None:
        self.write(text, channel="stderr", source=source, **metadata)
