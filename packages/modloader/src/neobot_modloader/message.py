from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MessageSegment:
    type: str
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Any) -> MessageSegment:
        if isinstance(raw, MessageSegment):
            return raw
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump(mode="python")
        if not isinstance(raw, Mapping):
            return text(str(raw))
        segment_type = str(raw.get("type") or "text")
        data = raw.get("data") or {}
        if not isinstance(data, Mapping):
            data = {}
        if segment_type == "image":
            return ImageSegment(dict(data))
        return cls(type=segment_type, data=dict(data))

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "data": dict(self.data)}

    @property
    def text(self) -> str:
        if self.type != "text":
            return ""
        return str(self.data.get("text", ""))


class ImageSegment(MessageSegment):
    def __init__(self, data: Mapping[str, Any] | None = None) -> None:
        super().__init__(type="image", data=dict(data or {}))

    @property
    def file(self) -> str | None:
        value = self.data.get("file")
        return str(value) if value is not None else None

    @property
    def url(self) -> str | None:
        value = self.data.get("url")
        return str(value) if value is not None else None

    @property
    def id(self) -> int | None:
        value = self.data.get("id")
        return int(value) if value is not None else None

    @property
    def sub_type(self) -> Any:
        return self.data.get("subType", self.data.get("sub_type", self.data.get("subtype")))


class Message:
    def __init__(self, raw_event: Mapping[str, Any] | None = None) -> None:
        self.raw_event: dict[str, Any] = dict(raw_event or {})
        self.raw_message: str = str(self.raw_event.get("raw_message") or "")
        self.segments: list[MessageSegment] = _normalize_segments(self.raw_event)

    @property
    def text(self) -> str:
        return "".join(segment.text for segment in self.segments)

    @property
    def images(self) -> list[ImageSegment]:
        return [segment for segment in self.segments if isinstance(segment, ImageSegment)]

    @property
    def first_image(self) -> ImageSegment | None:
        return self.images[0] if self.images else None

    @property
    def has_image(self) -> bool:
        return self.first_image is not None

    def of_type(self, segment_type: str) -> list[MessageSegment]:
        return [segment for segment in self.segments if segment.type == segment_type]

    def to_list(self) -> list[dict[str, Any]]:
        return [segment.to_dict() for segment in self.segments]


class MessageChain:
    def __init__(self, segments: Iterable[MessageSegment | Mapping[str, Any]] | None = None) -> None:
        self._segments: list[MessageSegment] = []
        for segment in segments or ():
            self.segment(segment)

    @property
    def segments(self) -> list[MessageSegment]:
        return list(self._segments)

    def segment(self, segment: MessageSegment | Mapping[str, Any]) -> MessageChain:
        self._segments.append(MessageSegment.from_raw(segment))
        return self

    def text(self, value: str) -> MessageChain:
        self._segments.append(text(value))
        return self

    def image(self, *, url: str | None = None, file: str | None = None, **data: Any) -> MessageChain:
        self._segments.append(image(url=url, file=file, **data))
        return self

    def to_list(self) -> list[dict[str, Any]]:
        return [segment.to_dict() for segment in self._segments]


def text(value: str) -> MessageSegment:
    return MessageSegment(type="text", data={"text": str(value)})


def image(*, url: str | None = None, file: str | None = None, **data: Any) -> ImageSegment:
    payload = dict(data)
    if url is not None:
        payload["url"] = url
    if file is not None:
        payload["file"] = file
    return ImageSegment(payload)


def normalize_message_payload(payload: Any) -> str | list[dict[str, Any]]:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, Message):
        return payload.to_list()
    if isinstance(payload, MessageChain):
        return payload.to_list()
    if isinstance(payload, MessageSegment):
        return [payload.to_dict()]
    if isinstance(payload, Mapping):
        return [MessageSegment.from_raw(payload).to_dict()]
    if isinstance(payload, Iterable):
        normalized: list[dict[str, Any]] = []
        for item in payload:
            normalized.append(MessageSegment.from_raw(item).to_dict())
        return normalized
    return str(payload)


def _normalize_segments(raw_event: Mapping[str, Any]) -> list[MessageSegment]:
    message = raw_event.get("message")
    if isinstance(message, list):
        return [MessageSegment.from_raw(item) for item in message]
    if isinstance(message, str):
        return [text(message)]
    raw_message = raw_event.get("raw_message")
    if raw_message is not None:
        return [text(str(raw_message))]
    return []
