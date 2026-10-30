"""按 SDK 的字段语义保护配置值，读取与保存共用一份模型声明。"""

from __future__ import annotations

from typing import Any, Literal

from neobot_modloader.sdk.schema import export_model_schema, is_sensitive_field, sanitize_schema, schema_child_nodes

from ..security import SECRET_PLACEHOLDER

_ABSENT = object()
_Operation = Literal["contains", "mask", "restore"]


def _secret_value(value: Any, operation: _Operation, original: Any) -> Any:
    present = value is not None and value != ""
    if operation == "contains":
        return present
    if operation == "mask":
        return SECRET_PLACEHOLDER if present else ""
    if isinstance(value, str) and (not value.strip() or value == SECRET_PLACEHOLDER):
        return original
    return value


class PluginSecretPolicy:
    def __init__(self, model: Any = None, *, schema: dict[str, Any] | None = None) -> None:
        self.schema = export_model_schema(model, by_alias=False) if model is not None else sanitize_schema(schema or {})

    def _nodes(self, node: dict[str, Any], seen: frozenset[str] = frozenset()):
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/") and reference not in seen:
            target = self.schema
            for segment in reference[2:].split("/"):
                target = target.get(segment.replace("~1", "/").replace("~0", "~"), {})
            yield from self._nodes(target, seen | {reference})
        yield node
        for keyword in ("anyOf", "oneOf", "allOf"):
            for variant in node.get(keyword, []):
                yield from self._nodes(variant, seen)

    def _children(
        self, nodes: list[dict[str, Any]], key: str | int, *, length: int | None = None
    ) -> list[dict[str, Any]]:
        children = []
        for parent in nodes:
            for child in schema_child_nodes(parent, key, self.schema, length=length):
                children.extend(self._nodes(child))
        return children or [{}]

    @staticmethod
    def _sensitive(name: str, value: Any, nodes: list[dict[str, Any]]) -> bool:
        return any(
            is_sensitive_field(name, node) and (isinstance(value, str) or node.get("writeOnly")) for node in nodes
        )

    def sensitive(self, path: tuple[str | int, ...], value: Any) -> bool:
        nodes = list(self._nodes(self.schema))
        for part in path:
            nodes = self._children(nodes, part)
        return self._sensitive(str(path[-1]) if path else "", value, nodes)

    def _mapping(self, values: dict, nodes: list[dict[str, Any]], operation: _Operation, original: Any) -> Any:
        previous = original if isinstance(original, dict) else {}
        result = {}
        for key, value in values.items():
            children = self._children(nodes, str(key))
            result[key] = self._visit(value, children, str(key), operation, previous.get(key, _ABSENT))
        if operation == "contains":
            return any(result.values())
        return {key: value for key, value in result.items() if value is not _ABSENT}

    def _sequence(self, values: list | tuple, nodes: list[dict[str, Any]], operation: _Operation, original: Any) -> Any:
        previous = original if isinstance(original, (list, tuple)) else []
        result = []
        for index, value in enumerate(values):
            children = self._children(nodes, index, length=len(values))
            original_value = previous[index] if index < len(previous) else _ABSENT
            result.append(self._visit(value, children, "", operation, original_value))
        if operation == "contains":
            return any(result)
        return [None if value is _ABSENT else value for value in result]

    def _visit(
        self, value: Any, nodes: list[dict[str, Any]], name: str, operation: _Operation, original: Any = _ABSENT
    ) -> Any:
        if self._sensitive(name, value, nodes):
            return _secret_value(value, operation, original)
        if isinstance(value, dict):
            return self._mapping(value, nodes, operation, original)
        if isinstance(value, (list, tuple)):
            return self._sequence(value, nodes, operation, original)
        if operation == "contains":
            return False
        return value

    def mask(self, value: Any) -> Any:
        return self._visit(value, list(self._nodes(self.schema)), "", "mask")

    def contains(self, value: Any) -> bool:
        return bool(self._visit(value, list(self._nodes(self.schema)), "", "contains"))

    def restore(self, value: Any, original: Any) -> Any:
        return self._visit(value, list(self._nodes(self.schema)), "", "restore", original)
