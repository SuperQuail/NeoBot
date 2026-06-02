from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any

from neobot_modloader.message import ImageSegment, Message, MessageSegment


class PatternError(ValueError):
    pass


class PatternMatchError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PatternElement:
    kind: str
    value: str
    name: str | None = None
    value_type: str = "str"
    optional: bool = False
    list_value: bool = False


@dataclass(frozen=True, slots=True)
class PatternMatch:
    matched: bool
    values: dict[str, Any]
    error: str | None = None
    command_matched: bool = False


class MessagePattern:
    def __init__(self, pattern: str | None = None, *, command: bool = False, aliases: tuple[str, ...] = ()) -> None:
        self.pattern = (pattern or "").strip()
        self.command = command
        self.aliases = tuple(aliases)
        self.elements = _parse_pattern(self.pattern)
        if self.command:
            if not self.elements or self.elements[0].kind != "literal":
                raise PatternError("command pattern must start with a command name")
            self.command_name = self.elements[0].value.lstrip("/")
            self.body = self.elements[1:]
        else:
            self.command_name = ""
            self.body = self.elements

    @property
    def usage(self) -> str:
        return f"/{self.pattern}" if self.command and not self.pattern.startswith("/") else self.pattern

    def match(self, message: Message) -> PatternMatch:
        tokens = _message_tokens(message)
        if self.command:
            command_index = _find_command(tokens)
            if command_index is None:
                return PatternMatch(False, {}, command_matched=False)
            raw = tokens[command_index]
            assert isinstance(raw, str)
            command_name = raw.lstrip("/")
            allowed = {self.command_name.lower(), *(alias.lower().lstrip("/") for alias in self.aliases)}
            if command_name.lower() not in allowed:
                return PatternMatch(False, {}, command_matched=False)
            try:
                values = _match_elements(self.body, tokens[command_index + 1 :])
            except PatternMatchError as exc:
                return PatternMatch(False, {}, str(exc), command_matched=True)
            return PatternMatch(True, values, command_matched=True)

        if not self.body:
            return PatternMatch(True, {}, command_matched=False)
        try:
            values = _match_elements(self.body, tokens)
        except PatternMatchError as exc:
            return PatternMatch(False, {}, str(exc), command_matched=False)
        return PatternMatch(True, values, command_matched=False)


def _parse_pattern(pattern: str) -> list[PatternElement]:
    if not pattern:
        return []
    try:
        tokens = shlex.split(pattern, posix=True)
    except ValueError as exc:
        raise PatternError(str(exc)) from exc

    elements: list[PatternElement] = []
    for token in tokens:
        if token.startswith("<") and token.endswith(">"):
            elements.append(_parse_param(token[1:-1], optional=False))
        elif token.startswith("[") and token.endswith("]"):
            elements.append(_parse_param(token[1:-1], optional=True))
        else:
            elements.append(PatternElement(kind="literal", value=token))
    return elements


def _parse_param(raw: str, *, optional: bool) -> PatternElement:
    if ":" in raw:
        name, value_type = raw.split(":", 1)
    else:
        name, value_type = raw, "str"
    name = name.strip()
    value_type = value_type.strip()
    if not name:
        raise PatternError("parameter name cannot be empty")
    list_value = value_type.startswith("list[") and value_type.endswith("]")
    if list_value:
        value_type = value_type[5:-1].strip()
    if value_type not in {"str", "int", "float", "bool", "rest", "image"}:
        raise PatternError(f"unsupported parameter type: {value_type}")
    return PatternElement(
        kind="param",
        value=raw,
        name=name,
        value_type=value_type,
        optional=optional,
        list_value=list_value,
    )


def _message_tokens(message: Message) -> list[str | MessageSegment]:
    tokens: list[str | MessageSegment] = []
    for segment in message.segments:
        if segment.type == "text":
            tokens.extend(_split_text(segment.text))
        else:
            tokens.append(segment)
    return tokens


def _split_text(value: str) -> list[str]:
    try:
        return shlex.split(value, posix=True)
    except ValueError:
        return value.split()


def _find_command(tokens: list[str | MessageSegment]) -> int | None:
    for index, token in enumerate(tokens):
        if isinstance(token, str) and token.startswith("/") and len(token) > 1:
            return index
    return None


def _match_elements(elements: list[PatternElement], tokens: list[str | MessageSegment]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    index = 0
    for element in elements:
        if element.kind == "literal":
            index = _match_literal(element.value, tokens, index)
            continue
        assert element.name is not None
        value, index = _capture(element, tokens, index)
        values[element.name] = value
    return values


def _match_literal(literal: str, tokens: list[str | MessageSegment], start: int) -> int:
    for index in range(start, len(tokens)):
        token = tokens[index]
        if isinstance(token, str) and token.lower() == literal.lower():
            return index + 1
        if not isinstance(token, str):
            continue
        break
    raise PatternMatchError(f"expected {literal!r}")


def _capture(element: PatternElement, tokens: list[str | MessageSegment], start: int) -> tuple[Any, int]:
    if element.value_type == "image":
        return _capture_image(element, tokens, start)
    if element.value_type == "rest":
        rest = " ".join(token for token in tokens[start:] if isinstance(token, str))
        if not rest and not element.optional:
            raise PatternMatchError(f"missing required parameter {element.name}")
        return (rest or None if element.optional else rest), len(tokens)

    index = _next_text_token(tokens, start)
    if index is None:
        if element.optional:
            return None, start
        raise PatternMatchError(f"missing required parameter {element.name}")
    token = tokens[index]
    assert isinstance(token, str)
    return _coerce_text(token, element), index + 1


def _capture_image(element: PatternElement, tokens: list[str | MessageSegment], start: int) -> tuple[Any, int]:
    images: list[ImageSegment] = []
    first_index: int | None = None
    last_index = start
    for index in range(start, len(tokens)):
        token = tokens[index]
        if isinstance(token, ImageSegment):
            if first_index is None:
                first_index = index
            images.append(token)
            last_index = index + 1
            if not element.list_value:
                break
    if element.list_value:
        if not images and not element.optional:
            raise PatternMatchError(f"missing required image parameter {element.name}")
        return images, last_index if images else start
    if first_index is None:
        if element.optional:
            return None, start
        raise PatternMatchError(f"missing required image parameter {element.name}")
    return images[0], last_index


def _next_text_token(tokens: list[str | MessageSegment], start: int) -> int | None:
    for index in range(start, len(tokens)):
        if isinstance(tokens[index], str):
            return index
    return None


def _coerce_text(value: str, element: PatternElement) -> Any:
    try:
        if element.value_type == "str":
            return value
        if element.value_type == "int":
            return int(value)
        if element.value_type == "float":
            return float(value)
        if element.value_type == "bool":
            return _coerce_bool(value)
    except ValueError as exc:
        raise PatternMatchError(f"invalid value for {element.name}: {value!r}") from exc
    raise PatternMatchError(f"unsupported parameter type: {element.value_type}")


def _coerce_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(value)
