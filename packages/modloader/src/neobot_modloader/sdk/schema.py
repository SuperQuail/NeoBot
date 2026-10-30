"""导出可以随包公开的配置契约，不实例化模型或运行默认工厂。"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
import re
from typing import Any, Literal, get_args, get_origin

_AUTH_KEY = re.compile(r"api[_-]?key|access[_-]?key|token|password|secret|credential|authorization|cookie", re.I)
_DROP = object()
_SCHEMA_MAPS = ("properties", "$defs", "definitions", "patternProperties")
_SCHEMA_LISTS = ("anyOf", "oneOf", "allOf", "prefixItems")
_SCHEMA_CHILDREN = ("items", "additionalProperties", "not", "if", "then", "else")
_ALIAS_ROUTE = "_neobot_input_alias_route"


def _check_schema_patterns(patterns: dict[str, Any], location: str, errors: list[str]) -> None:
    for index, pattern in enumerate(patterns):
        if not isinstance(pattern, str):
            continue
        try:
            re.compile(pattern)
        except (re.PatternError, OverflowError, RecursionError):
            errors.append(f"{location}[{index}] 正则表达式无效")


def _schema_map_locations(
    node: dict[str, Any], keyword: str, location: str, errors: list[str]
) -> Iterable[tuple[Any, str]]:
    if keyword not in node:
        return
    location = f"{location}.{keyword}"
    children = node[keyword]
    if not isinstance(children, dict):
        errors.append(f"{location} 必须是对象")
        return
    if keyword == "patternProperties":
        _check_schema_patterns(children, location, errors)
    for name, child in children.items():
        if not isinstance(name, str):
            errors.append(f"{location} 的字段名必须是字符串")
            continue
        yield child, f"{location}.{name}"


def _schema_list_locations(
    node: dict[str, Any], keyword: str, location: str, errors: list[str]
) -> Iterable[tuple[Any, str]]:
    if keyword not in node:
        return
    location = f"{location}.{keyword}"
    children = node[keyword]
    if not isinstance(children, list):
        errors.append(f"{location} 必须是列表")
        return
    for index, child in enumerate(children):
        yield child, f"{location}[{index}]"


def _schema_child_locations(node: dict[str, Any], location: str, errors: list[str]) -> Iterable[tuple[Any, str]]:
    for keyword in _SCHEMA_MAPS:
        yield from _schema_map_locations(node, keyword, location, errors)
    for keyword in _SCHEMA_LISTS:
        yield from _schema_list_locations(node, keyword, location, errors)
    for keyword in _SCHEMA_CHILDREN:
        yield node.get(keyword), f"{location}.{keyword}"
    hints = node.get("x-neobot")
    if isinstance(hints, dict) and not isinstance(hints.get("input_aliases", []), list):
        errors.append(f"{location}.x-neobot.input_aliases 必须是列表")


def _schema_reference_location(root: dict[str, Any], reference: Any, location: str) -> tuple[Any, str] | None:
    if not isinstance(reference, str) or not reference.startswith("#/"):
        return None
    target: Any = root
    for segment in reference[2:].split("/"):
        if not isinstance(target, dict):
            return None
        name = segment.replace("~1", "/").replace("~0", "~")
        target = target.get(name)
        location = f"{location}.{name}"
    return target, location


def schema_structure_errors(schema: dict[str, Any], location: str) -> list[str]:
    """仅校验现有遍历依赖的容器与正则；布尔叶子及其他关键字保留原有解释。"""
    errors: list[str] = []
    pending = [(schema, location)]
    seen: set[int] = set()
    while pending:
        node, current_location = pending.pop()
        if not isinstance(node, dict) or id(node) in seen:
            continue
        seen.add(id(node))
        pending.extend(_schema_child_locations(node, current_location, errors))
        referenced = _schema_reference_location(schema, node.get("$ref"), location)
        if referenced is not None:
            pending.append(referenced)
    return errors


def is_sensitive_field(name: str, schema: dict[str, Any]) -> bool:
    """显式语义优先，旧配置的认证字段名作为兼容兜底。"""
    hints = schema.get("x-neobot")
    explicit = schema.get("writeOnly") or schema.get("sensitive")
    if isinstance(hints, dict):
        explicit = explicit or hints.get("secret")
    if explicit:
        return True
    kind = schema.get("type")
    # token_limit 等数值配置不属于凭据，不能因兼容规则丢失默认值。
    scalar = isinstance(kind, str) and kind in {"integer", "number", "boolean", "null"}
    return bool(_AUTH_KEY.search(name)) and not scalar


def _schema_nodes(schema: Any):
    if not isinstance(schema, dict):
        return
    yield schema
    for keyword in _SCHEMA_MAPS:
        children = schema.get(keyword)
        if not isinstance(children, dict):
            continue
        for child in children.values():
            yield from _schema_nodes(child)
    for keyword in _SCHEMA_LISTS:
        children = schema.get(keyword)
        if not isinstance(children, list):
            continue
        for child in children:
            yield from _schema_nodes(child)
    for keyword in _SCHEMA_CHILDREN:
        yield from _schema_nodes(schema.get(keyword))


def _resolve(schema: Any, root: dict[str, Any], seen: frozenset[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    reference = schema.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/") or reference in seen:
        return schema
    target: Any = root
    for segment in reference[2:].split("/"):
        if not isinstance(target, dict):
            return schema
        target = target.get(segment.replace("~1", "/").replace("~0", "~"))
    resolved = _resolve(target, root, seen | {reference})
    return {**resolved, **{key: value for key, value in schema.items() if key != "$ref"}}


def _alias_paths(alias: Any) -> list[list[str | int]]:
    if isinstance(alias, str):
        return [[alias]]
    choices = getattr(alias, "choices", None)
    if isinstance(choices, (list, tuple)):
        paths = []
        for choice in choices:
            paths.extend(_alias_paths(choice))
        return paths
    path = getattr(alias, "path", None)
    if isinstance(path, (list, tuple)) and path and all(isinstance(part, (str, int)) for part in path):
        return [[int(part) if isinstance(part, int) else str(part) for part in path]]
    return []


def model_field_input_paths(name: str, field: Any) -> list[list[str | int]]:
    """按验证优先级列出别名路径，并保留字段名供配置保护与回填使用。"""
    alias = getattr(field, "validation_alias", None)
    paths = _alias_paths(getattr(field, "alias", None) if alias is None else alias)
    result = []
    for path in [*paths, [name]]:
        if path not in result:
            result.append(path)
    return result


def _add_field_alias_hints(name: str, field: Any, node: dict[str, Any]) -> None:
    paths = [path for path in model_field_input_paths(name, field) if path != [name]]
    if not paths:
        return
    hints = node.get("x-neobot")
    hints = dict(hints) if isinstance(hints, dict) else {}
    aliases = list(hints.get("input_aliases", []))
    hints["input_aliases"] = aliases + [path for path in paths if path not in aliases]
    node["x-neobot"] = hints


def _add_model_aliases(
    fields: Mapping[str, Any],
    node: dict[str, Any],
    definition: dict[str, Any],
    root: dict[str, Any],
    seen: set[tuple[int, int]],
) -> None:
    properties = definition.get("properties", {})
    for name, field in fields.items():
        child = properties.get(name)
        # RootModel 没有 properties，内部类型直接对应当前节点。
        if name == "root" and not properties:
            _add_input_aliases(getattr(field, "annotation", None), node, root, seen)
            continue
        if not isinstance(child, dict):
            continue
        _add_field_alias_hints(name, field, child)
        _add_input_aliases(getattr(field, "annotation", None), child, root, seen)


def _add_container_aliases(
    annotation: Any,
    node: dict[str, Any],
    definition: dict[str, Any],
    root: dict[str, Any],
    seen: set[tuple[int, int]],
) -> None:
    args = get_args(annotation)
    origin = get_origin(annotation)
    if origin is tuple and args:
        for child_annotation, child in zip(args, definition.get("prefixItems", [])):
            _add_input_aliases(child_annotation, child, root, seen)
        _add_input_aliases(args[0], definition.get("items"), root, seen)
        return
    if isinstance(origin, type) and issubclass(origin, Mapping) and len(args) == 2:
        _add_input_aliases(args[1], definition.get("additionalProperties"), root, seen)
        return
    if isinstance(origin, type) and issubclass(origin, Iterable) and args:
        _add_input_aliases(args[0], definition.get("items"), root, seen)
        return
    for arg in args:
        _add_input_aliases(arg, node, root, seen)


def _add_input_aliases(annotation: Any, node: Any, root: dict[str, Any], seen: set[tuple[int, int]]) -> None:
    """按注解与节点配对去重，允许共享定义被不同字段类型补充，同时终止递归模型。"""
    if not isinstance(node, dict) or (id(annotation), id(node)) in seen:
        return
    seen.add((id(annotation), id(node)))
    definition = _resolve(node, root)
    for keyword in ("anyOf", "oneOf", "allOf"):
        for variant in definition.get(keyword, []):
            _add_input_aliases(annotation, variant, root, seen)
    fields = getattr(annotation, "model_fields", None)
    if isinstance(fields, Mapping):
        _add_model_aliases(fields, node, definition, root, seen)
        return
    _add_container_aliases(annotation, node, definition, root, seen)


def _alias_child(path: list[str | int], child: dict[str, Any], key: str | int, length: int | None) -> dict | None:
    expected = path[0]
    if isinstance(expected, int) and expected < 0 and isinstance(key, int):
        matches = length is None or key == length + expected
    else:
        matches = expected == key
    if not matches:
        return None
    # 中间节点只用于遍历输入，绝不写回公开 JSON Schema 或改变配置验证规则。
    return child if len(path) == 1 else {_ALIAS_ROUTE: (path[1:], child)}


def _matching_alias_paths(
    paths: Iterable[Any],
    child: dict[str, Any],
    key: str | int,
    length: int | None,
) -> Iterable[dict[str, Any]]:
    for path in paths:
        if not isinstance(path, list) or not path:
            continue
        if any(type(part) not in (str, int) for part in path):
            continue
        match = _alias_child(path, child, key, length)
        if match is not None:
            yield match


def _matching_alias_children(
    properties: dict[str, Any],
    key: str | int,
    length: int | None,
) -> Iterable[dict[str, Any]]:
    for child in properties.values():
        if not isinstance(child, dict):
            continue
        hints = child.get("x-neobot", {})
        if not isinstance(hints, dict):
            continue
        yield from _matching_alias_paths(hints.get("input_aliases", []), child, key, length)


def schema_child_nodes(
    node: dict[str, Any], key: str | int, root: dict[str, Any], *, length: int | None = None
) -> list[dict[str, Any]]:
    """按字段名或输入别名寻找子契约，供公开值过滤与运行时脱敏共用。"""
    definition = _resolve(node, root)
    route = definition.get(_ALIAS_ROUTE)
    if route is not None:
        child = _alias_child(*route, key, length)
        return [child] if child is not None else []
    if isinstance(key, int):
        prefix = definition.get("prefixItems", [])
        child = prefix[key] if 0 <= key < len(prefix) else definition.get("items", {})
        return [child] if isinstance(child, dict) else []
    properties = definition.get("properties", {})
    matches = [properties[key]] if key in properties else []
    # 同一输入可能命中多个字段或别名，必须保留全部匹配供 allOf 脱敏使用。
    matches.extend(_matching_alias_children(properties, key, length))
    for pattern, child in definition.get("patternProperties", {}).items():
        if re.search(pattern, key):
            matches.append(child)
    if not matches:
        matches = [definition.get("additionalProperties", {})]
    return [child for child in matches if isinstance(child, dict)]


def _schema_variants(definition: dict[str, Any]) -> Iterable[Any]:
    for keyword in ("anyOf", "oneOf", "allOf"):
        variants = definition.get(keyword)
        if not isinstance(variants, list):
            continue
        yield from variants


def _public_mapping(value: dict[str, Any], definition: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    public = {}
    for name, item in value.items():
        matches = schema_child_nodes(definition, str(name), root)
        if len(matches) == 1:
            child = matches[0]
        elif matches:
            child = {"allOf": matches}
        else:
            child = {}
        child = _resolve(child, root)
        if is_sensitive_field(str(name), child):
            continue
        cleaned = _public_value(item, child, root)
        if cleaned is not _DROP:
            public[name] = cleaned
    return public


def _public_sequence(value: list[Any], definition: dict[str, Any], root: dict[str, Any]) -> Any:
    public = []
    for index, item in enumerate(value):
        matches = schema_child_nodes(definition, index, root, length=len(value))
        child = matches[0] if len(matches) == 1 else {"allOf": matches}
        cleaned = _public_value(item, child, root)
        # 数组删去一个位置会改变元组含义，此时省略整份默认值。
        if cleaned is _DROP:
            return _DROP
        public.append(cleaned)
    return public


def _public_value(value: Any, schema: Any, root: dict[str, Any]) -> Any:
    definition = _resolve(schema, root)
    if definition.get("writeOnly"):
        return _DROP
    for variant in _schema_variants(definition):
        value = _public_value(value, variant, root)
        if value is _DROP:
            return _DROP
    if isinstance(value, dict):
        return _public_mapping(value, definition, root)
    if isinstance(value, list):
        return _public_sequence(value, definition, root)
    return value


def _mark_sensitive_fields(node: dict[str, Any], root: dict[str, Any]) -> None:
    if is_sensitive_field("", _resolve(node, root)):
        node["writeOnly"] = True
    properties = node.get("properties")
    if not isinstance(properties, dict):
        return
    for name, child in properties.items():
        if isinstance(child, dict) and is_sensitive_field(name, _resolve(child, root)):
            child["writeOnly"] = True


def _sanitize_public_keyword(node: dict[str, Any], keyword: str, root: dict[str, Any]) -> None:
    if keyword not in node:
        return
    value = node[keyword]
    if keyword in {"examples", "enum"} and isinstance(value, list):
        cleaned = [_public_value(item, node, root) for item in value]
        cleaned = [item for item in cleaned if item is not _DROP]
        if cleaned:
            node[keyword] = cleaned
        else:
            node.pop(keyword)
        return
    cleaned = _public_value(value, node, root)
    if cleaned is _DROP:
        node.pop(keyword)
        return
    node[keyword] = cleaned


def sanitize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """复制契约并移除敏感默认值，连同父对象中的嵌套默认值一起处理。"""
    result = deepcopy(schema)
    nodes = list(_schema_nodes(result))
    # 先标记全部敏感节点，再过滤父级默认值，避免结果依赖定义的遍历顺序。
    for node in nodes:
        _mark_sensitive_fields(node, result)
    for node in nodes:
        for keyword in ("default", "examples", "const", "enum"):
            _sanitize_public_keyword(node, keyword, result)
    return result


def export_model_schema(
    model: Any, *, mode: Literal["validation", "serialization"] = "validation", by_alias: bool = True
) -> dict[str, Any] | None:
    """通过模型的公开导出协议生成契约，不额外依赖 Pydantic 实现类型。"""
    if model is None:
        return None
    exporter = getattr(model, "model_json_schema", None)
    if not callable(exporter):
        raise TypeError("配置或动作模型必须提供 model_json_schema()")
    schema = exporter(mode=mode) if by_alias else exporter(mode=mode, by_alias=False)
    if not isinstance(schema, dict):
        raise TypeError("模型导出的 JSON Schema 必须是对象")
    if not by_alias and mode == "validation":
        schema = deepcopy(schema)
        _add_input_aliases(model, schema, schema, set())
    return sanitize_schema(schema)


def schema_field_paths(schema: dict[str, Any] | None) -> set[str]:
    """收集可定位的字段路径；递归模型在重复引用处停止展开。"""
    if not isinstance(schema, dict):
        return set()
    paths: set[str] = set()

    def visit(node: Any, prefix: str, seen: frozenset[str]) -> None:
        if not isinstance(node, dict):
            return
        reference = node.get("$ref")
        if isinstance(reference, str) and reference in seen:
            return
        if isinstance(reference, str):
            seen = seen | {reference}
        definition = _resolve(node, schema)
        properties = definition.get("properties", {})
        if isinstance(properties, dict):
            for name, child in properties.items():
                path = f"{prefix}.{name}" if prefix else name
                paths.add(path)
                visit(child, path, seen)
        for variant in _schema_variants(definition):
            visit(variant, prefix, seen)

    visit(schema, "", frozenset())
    return paths
