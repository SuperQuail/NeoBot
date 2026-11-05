from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, TypeVar, overload


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
        if segment_type == "at":
            return AtSegment(dict(data))
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


class AtSegment(MessageSegment):
    def __init__(self, data: Mapping[str, Any] | None = None) -> None:
        super().__init__(type="at", data=dict(data or {}))

    @property
    def qq(self) -> str | None:
        value = self.data.get("qq")
        return str(value) if value is not None else None

    @property
    def name(self) -> str | None:
        value = self.data.get("name")
        return str(value) if value is not None else None

    @property
    def is_all(self) -> bool:
        return self.qq == "all"


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

    @property
    def ats(self) -> list[AtSegment]:
        return [segment for segment in self.segments if isinstance(segment, AtSegment)]

    @property
    def first_at(self) -> AtSegment | None:
        return self.ats[0] if self.ats else None

    @property
    def has_at(self) -> bool:
        return self.first_at is not None

    def of_type(self, segment_type: str) -> list[MessageSegment]:
        return [segment for segment in self.segments if segment.type == segment_type]

    def to_list(self) -> list[dict[str, Any]]:
        return [segment.to_dict() for segment in self.segments]

    def to_chain(self) -> MessageChain:
        """取得独立消息链，处理器修改嵌套段数据时不会污染收到的消息。"""
        return MessageChain(self.segments).copy()


_SegmentT = TypeVar("_SegmentT", bound=MessageSegment)
_SegmentKind = str | type[MessageSegment]


class MessageChain:
    """有序消息段容器；查询不修改原链，copy() 深复制消息段及其数据。"""

    def __init__(self, segments: Iterable[MessageSegment | Mapping[str, Any]] | None = None) -> None:
        self._segments: list[MessageSegment] = []
        for segment in segments or ():
            self.segment(segment)

    def __len__(self) -> int:
        return len(self._segments)

    @property
    def plain_text(self) -> str:
        """按原顺序读取文本段，不把图片、@ 或引用转换为命令文本。"""
        return "".join(segment.text for segment in self._segments)

    def __iter__(self) -> Iterator[MessageSegment]:
        return iter(self._segments)

    @overload
    def __getitem__(self, index: int) -> MessageSegment: ...

    @overload
    def __getitem__(self, index: slice) -> MessageChain: ...

    def __getitem__(self, index: int | slice) -> MessageSegment | MessageChain:
        if isinstance(index, slice):
            return MessageChain(self._segments[index])
        return self._segments[index]

    @property
    def segments(self) -> list[MessageSegment]:
        return list(self._segments)

    @overload
    def get(self, kind: type[_SegmentT]) -> list[_SegmentT]: ...

    @overload
    def get(self, kind: str) -> list[MessageSegment]: ...

    def get(self, kind: str | type[_SegmentT]) -> list[MessageSegment] | list[_SegmentT]:
        if isinstance(kind, str):
            return [segment for segment in self._segments if segment.type == kind]
        return [segment for segment in self._segments if isinstance(segment, kind)]

    def has(self, kind: _SegmentKind) -> bool:
        return any(_matches_segment_kind(segment, kind) for segment in self._segments)

    @overload
    def first(self, kind: type[_SegmentT]) -> _SegmentT | None: ...

    @overload
    def first(self, kind: str) -> MessageSegment | None: ...

    def first(self, kind: _SegmentKind) -> MessageSegment | None:
        return next(
            (segment for segment in self._segments if _matches_segment_kind(segment, kind)),
            None,
        )

    def include(self, *kinds: _SegmentKind) -> MessageChain:
        return MessageChain(
            segment for segment in self._segments if any(_matches_segment_kind(segment, kind) for kind in kinds)
        )

    def exclude(self, *kinds: _SegmentKind) -> MessageChain:
        return MessageChain(
            segment for segment in self._segments if not any(_matches_segment_kind(segment, kind) for kind in kinds)
        )

    def copy(self) -> MessageChain:
        """复制消息段对象及嵌套 data，保留自定义消息段的运行时类型。"""
        return MessageChain(deepcopy(self._segments))

    def segment(self, segment: MessageSegment | Mapping[str, Any]) -> MessageChain:
        self._segments.append(MessageSegment.from_raw(segment))
        return self

    def text(self, value: str) -> MessageChain:
        self._segments.append(text(value))
        return self

    def image(self, *, url: str | None = None, file: str | None = None, **data: Any) -> MessageChain:
        self._segments.append(image(url=url, file=file, **data))
        return self

    def at(self, qq: str | None = None, name: str | None = None, **data: Any) -> MessageChain:
        self._segments.append(at(qq=qq, name=name, **data))
        return self

    def to_list(self) -> list[dict[str, Any]]:
        return [segment.to_dict() for segment in self._segments]


def _matches_segment_kind(segment: MessageSegment, kind: _SegmentKind) -> bool:
    if isinstance(kind, str):
        return segment.type == kind
    return isinstance(segment, kind)


def text(value: str) -> MessageSegment:
    return MessageSegment(type="text", data={"text": str(value)})


def image(*, url: str | None = None, file: str | None = None, **data: Any) -> ImageSegment:
    payload = dict(data)
    if url is not None:
        payload["url"] = url
    if file is not None:
        payload["file"] = file
    return ImageSegment(payload)


def at(qq: str | None = None, name: str | None = None, **data: Any) -> AtSegment:
    payload: dict[str, Any] = dict(data)
    if qq is not None:
        payload["qq"] = str(qq)
    if name is not None:
        payload["name"] = name
    return AtSegment(payload)


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
