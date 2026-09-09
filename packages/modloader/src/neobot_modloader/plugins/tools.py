"""插件 Tool 注册与执行。

`@plugin.tool(...)` 声明的处理器会被包装成 SkillModule 协议对象，
通过 `ctx.plugin_host.register_skill(...)` 注册进主应用的 SkillManager，
从而进入主聊天 Agent 的工具集。工具全局名为 ``{plugin_name}__{tool_name}``。
"""

from __future__ import annotations

import inspect
import json
import logging
import re
from copy import deepcopy
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from pydantic import BaseModel, TypeAdapter

from neobot_modloader.message import Message
from neobot_modloader.plugins.injection import (
    get_handler_type_hints,
    injected_parameter_kind,
    parameter_injection_kind,
    resolve_handler_kwargs,
    validate_config_injection,
)
from neobot_modloader.plugins.registration import (
    Handler,
    ToolRegistration,
    validate_qualified_tool_name,
)

_RESERVED_FINAL_TOOL_NAMES = frozenset(
    {"skills__read_manifest", "skills__read_resource"}
)
_AGENT_REQUEST_KINDS = frozenset({"agent_request", "task", "state", "messages"})
_MAX_SCHEMA_BYTES = 64 * 1024
_MAX_TOOL_RESULT_CHARS = 16 * 1024
_LOGGER = logging.getLogger("neobot_modloader")


def build_tool_schema(
    handler: Handler,
    *,
    context_type: type[Any] | None = None,
    config_model: type[Any] | None = None,
) -> dict[str, Any]:
    """根据函数签名生成 OpenAI function-calling 参数 schema。"""
    hints = get_handler_type_hints(handler)
    signature = inspect.signature(handler)
    properties: dict[str, Any] = {}
    required: list[str] = []
    # 嵌套 BaseModel 的 $defs 统一收集并上提到 parameters 根层：
    # $ref 形如 "#/$defs/<名称>"，锚定 JSON 文档根，属性层的 $defs 无法被解析，
    # 主流 function-calling API 因此会拒绝请求
    defs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
        annotation = hints.get(name, inspect.Parameter.empty)
        if (
            parameter_injection_kind(
                name,
                annotation,
                context_type=context_type,
                config_model=config_model,
            )
            is not None
        ):
            continue
        # prefix 用于同名 $defs 冲突时的唯一化命名空间（{参数名}__{def 名}）
        try:
            properties[name] = _type_to_schema(annotation, defs, prefix=name)
        except Exception as exc:
            raise TypeError(
                f"Cannot build a tool schema for parameter {name!r} of handler "
                f"{handler.__qualname__}: {type(exc).__name__}: {exc}"
            ) from exc
        if parameter.default is inspect.Parameter.empty:
            required.append(name)
        elif parameter.default is not None:
            properties[name]["default"] = _serialize_parameter_default(
                name, annotation, parameter.default
            )
    schema = {"type": "object", "properties": properties, "required": required}
    if defs:
        schema["$defs"] = defs
    return schema


def _type_to_schema(
    annotation: Any, defs: dict[str, Any] | None = None, prefix: str | None = None
) -> dict[str, Any]:
    if annotation is None or annotation is inspect.Parameter.empty:
        return {"type": "string"}
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is not None:
        if origin is Annotated or origin is tuple:
            return _type_adapter_schema(annotation, defs, prefix)
        if origin in {list, set}:
            items = (
                _type_to_schema(args[0], defs, prefix) if args else {"type": "string"}
            )
            return {"type": "array", "items": items}
        if origin is dict:
            return {"type": "object"}
        if origin is Union or origin is UnionType:
            inner = [arg for arg in args if arg is not type(None)]
            schemas = [_type_to_schema(arg, defs, prefix) for arg in inner]
            if not schemas:
                return {"type": "string"}
            if len(schemas) == 1:
                return schemas[0]
            # int | float 等纯数值联合收敛为 number
            if all(schema.get("type") in {"integer", "number"} for schema in schemas):
                return {"type": "number"}
            # 其余多类型联合（如 str | int）无法收敛，回退为 string
            if len({schema.get("type") for schema in schemas}) == 1:
                return schemas[0]
            return {"type": "string"}
        return {"type": "string"}
    if isinstance(annotation, type):
        if issubclass(annotation, bool):
            return {"type": "boolean"}
        if issubclass(annotation, int):
            return {"type": "integer"}
        if issubclass(annotation, float):
            return {"type": "number"}
        if issubclass(annotation, str):
            return {"type": "string"}
        if issubclass(annotation, dict):
            return {"type": "object"}
        if issubclass(annotation, list):
            return {"type": "array"}
        if issubclass(annotation, BaseModel):
            return _type_adapter_schema(annotation, defs, prefix)
        if issubclass(annotation, tuple):
            return {"type": "array"}
    return {"type": "string"}


def _type_adapter_schema(
    annotation: Any,
    defs: dict[str, Any] | None,
    prefix: str | None,
) -> dict[str, Any]:
    schema = TypeAdapter(annotation).json_schema()
    nested_defs = schema.pop("$defs", None)
    if nested_defs:
        if defs is None:
            schema["$defs"] = nested_defs
        else:
            _merge_defs(defs, nested_defs, schema, prefix)
    return schema


def _serialize_parameter_default(name: str, annotation: Any, value: Any) -> Any:
    try:
        if annotation is not inspect.Parameter.empty:
            adapter = TypeAdapter(annotation)
            value = adapter.dump_python(adapter.validate_python(value), mode="json")
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except Exception as exc:
        raise ValueError(
            f"Default for tool parameter {name!r} is invalid or not "
            f"JSON-serializable: {type(exc).__name__}: {exc}"
        ) from exc
    return value


def _merge_defs(
    defs: dict[str, Any],
    nested_defs: dict[str, Any],
    model_schema: dict[str, Any],
    prefix: str | None,
) -> None:
    """把单个参数 schema 的 $defs 合并上提到根层，同名冲突时唯一化并重写 $ref。

    同名且结构相同直接复用（先出现者为准）；同名但结构不同时按
    ``{参数名}__{def 名}`` 生成唯一 key，并重写该参数 schema 内所有指向该
    名称的 $ref（含 $defs 定义内部的交叉引用），避免第二个参数的定义被
    静默丢弃。
    """
    renames: dict[str, str] = {}
    for def_name, definition in nested_defs.items():
        existing = defs.get(def_name)
        if existing is not None and existing != definition:
            unique = (
                f"{prefix}__{def_name}" if prefix else f"def_{len(defs)}__{def_name}"
            )
            counter = 2
            while unique in defs:
                unique = f"{prefix or 'def'}__{def_name}_{counter}"
                counter += 1
            renames[def_name] = unique
    # A definition that was byte-for-byte identical can still depend on a
    # conflicting leaf. Once that leaf is renamed, the wrapper must be
    # namespaced as well or its reused copy keeps pointing at the old leaf.
    changed = True
    while changed:
        changed = False
        for def_name, definition in nested_defs.items():
            if def_name in renames or def_name not in defs:
                continue
            rewritten = deepcopy(definition)
            _rewrite_defs_refs(rewritten, renames)
            if rewritten != defs[def_name]:
                unique = (
                    f"{prefix}__{def_name}"
                    if prefix
                    else f"def_{len(defs)}__{def_name}"
                )
                counter = 2
                while unique in defs or unique in renames.values():
                    unique = f"{prefix or 'def'}__{def_name}_{counter}"
                    counter += 1
                renames[def_name] = unique
                changed = True
    if renames:
        _rewrite_defs_refs(model_schema, renames)
        for definition in nested_defs.values():
            _rewrite_defs_refs(definition, renames)
    for def_name, definition in nested_defs.items():
        defs.setdefault(renames.get(def_name, def_name), definition)


def _rewrite_defs_refs(node: Any, renames: dict[str, str]) -> None:
    """把 schema 内引用冲突定义名的 $ref（``#/$defs/<名称>``）改写为唯一名。"""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                for old, new in renames.items():
                    old_token = old.replace("~", "~0").replace("/", "~1")
                    new_token = new.replace("~", "~0").replace("/", "~1")
                    ref = f"#/$defs/{old_token}"
                    if value == ref or value.startswith(f"{ref}/"):
                        node[key] = f"#/$defs/{new_token}{value[len(ref) :]}"
                        break
            else:
                _rewrite_defs_refs(value, renames)
    elif isinstance(node, list):
        for item in node:
            _rewrite_defs_refs(item, renames)


def _coerce_tool_value(annotation: Any, value: Any) -> Any:
    """按类型注解把模型传入的 JSON 值转换为目标类型（失败抛异常）。

    BaseModel 子类用 ``model_validate`` 实例化；容器与 Union/Optional
    交给 ``TypeAdapter``；自定义类等无法转换的注解原样透传。
    """
    if annotation is None or annotation is inspect.Parameter.empty:
        return value
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.model_validate(value)
    if get_origin(annotation) is None:
        if annotation in {str, int, float, bool, tuple}:
            return TypeAdapter(annotation).validate_python(value)
        return value
    return TypeAdapter(annotation).validate_python(value)


def _summarize_validation_error(exc: Exception) -> str:
    """把 pydantic 校验异常压缩为单行摘要（≤200 字符）。

    pydantic 的 ``str(exc)`` 是多行 + 错误详情 + 文档 URL，对模型消费过重；
    这里取首行（含模型名），再补第一个错误项的 loc 与 msg。
    """
    message = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    errors_fn = getattr(exc, "errors", None)
    if callable(errors_fn):
        try:
            errors = errors_fn()
        except Exception:
            errors = []
        if errors:
            first = errors[0]
            loc = ".".join(str(part) for part in first.get("loc", ()))
            msg = first.get("msg", "")
            detail = f"{loc}: {msg}" if loc else msg
            message = f"{message}; {detail}"
    return message[:200]


def coerce_tool_args(
    handler: Handler,
    args: dict[str, Any],
    *,
    context_type: type[Any] | None = None,
    config_model: type[Any] | None = None,
    model_parameters: frozenset[str] = frozenset(),
) -> dict[str, Any] | str:
    """按 handler 的类型注解转换捕获参数（如 dict → BaseModel 实例）。

    成功返回转换后的参数字典；失败返回友好错误文本（不抛异常）。
    DI 参数（含 Optional/Union 伪装）由 resolve_handler_kwargs 注入，
    永远不会进入捕获转换。
    """
    hints = get_handler_type_hints(handler)
    coerced: dict[str, Any] = {}
    for name, value in args.items():
        # DI 参数由 resolve_handler_kwargs 注入，不参与捕获转换
        if (
            parameter_injection_kind(
                name,
                hints.get(name, inspect.Parameter.empty),
                context_type=context_type,
                config_model=config_model,
                explicit_model_parameter=name in model_parameters,
            )
            is not None
        ):
            coerced[name] = value
            continue
        annotation = hints.get(name, inspect.Parameter.empty)
        if annotation is None or annotation is inspect.Parameter.empty:
            coerced[name] = value
            continue
        try:
            coerced[name] = _coerce_tool_value(annotation, value)
        except Exception as exc:
            return f"参数 {name} 校验失败: {_summarize_validation_error(exc)}"[:200]
    return coerced


def _validate_tool_handler(
    registration: ToolRegistration,
    *,
    context: Any,
    config: BaseModel | None,
    config_model: type[BaseModel] | None,
    model_parameters: frozenset[str],
) -> None:
    hints = get_handler_type_hints(registration.handler)
    signature = inspect.signature(registration.handler)
    for name, parameter in signature.parameters.items():
        if parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue
        annotation = hints.get(name, inspect.Parameter.empty)
        annotated_kind = injected_parameter_kind(
            name,
            annotation,
            context_type=context.__class__,
            config_model=config_model,
        )
        if annotated_kind is not None and name in model_parameters:
            raise ValueError(
                f"tool {registration.name!r} parameter {name!r} is supplied by "
                f"annotation-based DI and cannot be declared model-facing"
            )
        kind = parameter_injection_kind(
            name,
            annotation,
            context_type=context.__class__,
            config_model=config_model,
            explicit_model_parameter=name in model_parameters,
        )
        if kind is None:
            continue
        if kind == "reply":
            raise ValueError(
                f"tool {registration.name!r} parameter {name!r} requests Reply DI, "
                "but tools have no inbound event to reply to"
            )
        required = parameter.default is inspect.Parameter.empty
        if kind in _AGENT_REQUEST_KINDS and required:
            raise ValueError(
                f"tool {registration.name!r} required parameter {name!r} depends "
                "on AgentRequest, which is unavailable to tools"
            )
        if kind == "config":
            if config is not None and annotated_kind == "config":
                validate_config_injection(
                    registration.handler,
                    name,
                    annotation,
                    config,
                    config_model,
                )
            elif required and (config_model is None or config is None):
                reason = (
                    "the plugin has no config model"
                    if config_model is None
                    else "no validated config instance is available"
                )
                raise ValueError(
                    f"tool {registration.name!r} required parameter {name!r} "
                    f"requests config DI, but {reason}"
                )


def _log_tool_failure(context: Any, tool_name: str, exc: Exception) -> None:
    try:
        logger = getattr(context, "logger", None)
        warning = getattr(logger, "warning", None)
        if callable(warning):
            warning(
                "插件工具执行失败",
                tool=tool_name,
                error_type=type(exc).__name__,
            )
            return
    except Exception:
        pass
    try:
        _LOGGER.warning(
            "插件工具执行失败：tool=%s error_type=%s",
            tool_name,
            type(exc).__name__,
        )
    except Exception:
        pass


class PluginToolModule:
    """把插件的 `@plugin.tool` 处理器适配成 SkillModule 协议。"""

    def __init__(self, plugin: Any, context: Any) -> None:
        self._plugin = plugin
        self._context = context
        self._tools: dict[str, ToolRegistration] = {}
        self._schemas: dict[str, dict[str, Any]] = {}
        self._model_parameters: dict[str, frozenset[str]] = {}
        for registration in plugin._tool_registrations:
            if registration.name in self._tools:
                raise ValueError(f"工具已注册: {registration.name}")
            self._tools[registration.name] = registration
            if registration.parameters is not None:
                parameters = {"type": "object", **registration.parameters}
            else:
                parameters = build_tool_schema(
                    registration.handler,
                    context_type=context.__class__,
                    config_model=getattr(plugin, "config_model", None),
                )
            _validate_tool_schema(parameters, registration.name)
            model_parameters = (
                frozenset(parameters.get("properties", {}))
                if registration.parameters is not None
                else frozenset()
            )
            _validate_tool_handler(
                registration,
                context=context,
                config=getattr(plugin, "_config", None),
                config_model=getattr(plugin, "config_model", None),
                model_parameters=model_parameters,
            )
            self._schemas[registration.name] = parameters
            self._model_parameters[registration.name] = model_parameters

    @property
    def name(self) -> str:
        return self._plugin.name

    @property
    def description(self) -> str:
        return self._plugin.description

    @property
    def instructions(self) -> str:
        return ""

    @property
    def session_tools(self) -> set[str]:
        return set()

    def get_tools(self) -> list[dict]:
        tools: list[dict] = []
        for name, registration in self._tools.items():
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": registration.description
                        or f"{self._plugin.name} tool",
                        "parameters": deepcopy(self._schemas[name]),
                    },
                }
            )
        return tools

    async def execute(self, tool_name: str, args: dict[str, Any]) -> str:
        registration = self._tools.get(tool_name)
        if registration is None:
            available = ", ".join(self._tools)
            return f"未知工具: {tool_name}（可用: {available or '无'}）"
        try:
            # Tool arguments are untrusted model output. DI values are supplied
            # only by resolve_handler_kwargs and can never be forged here.
            hints = get_handler_type_hints(registration.handler)
            model_parameters = self._model_parameters[tool_name]
            captures = coerce_tool_args(
                registration.handler,
                {
                    key: value
                    for key, value in dict(args).items()
                    if parameter_injection_kind(
                        key,
                        hints.get(key, inspect.Parameter.empty),
                        context_type=self._context.__class__,
                        config_model=getattr(self._plugin, "config_model", None),
                        explicit_model_parameter=key in model_parameters,
                    )
                    is None
                },
                context_type=self._context.__class__,
                config_model=getattr(self._plugin, "config_model", None),
                model_parameters=model_parameters,
            )
            if isinstance(captures, str):
                return captures
            kwargs = await resolve_handler_kwargs(
                registration.handler,
                context=self._context,
                event={},
                message=Message({}),
                captures=captures,
                config=getattr(self._plugin, "_config", None),
                config_model=getattr(self._plugin, "config_model", None),
                agent_request=None,
                model_parameters=model_parameters,
            )
            result = registration.handler(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            return _render_result(result)
        except Exception as exc:
            _log_tool_failure(self._context, tool_name, exc)
            return f"工具执行失败 [{tool_name}]"

    def reset(self) -> None:
        return None


def _render_result(result: Any) -> str:
    if result is None:
        return "ok"
    if isinstance(result, str):
        rendered = result
    elif isinstance(result, (list, dict)):
        rendered = json.dumps(result, ensure_ascii=False, default=str)
    else:
        rendered = str(result)
    if len(rendered) > _MAX_TOOL_RESULT_CHARS:
        return rendered[:_MAX_TOOL_RESULT_CHARS] + "\n...[truncated]"
    return rendered


def _validate_tool_schema(schema: dict[str, Any], tool_name: str) -> None:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError(f"tool {tool_name!r} parameters must have an object root")
    try:
        encoded = json.dumps(schema, ensure_ascii=False, allow_nan=False).encode(
            "utf-8"
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError(
            f"tool {tool_name!r} parameters must be JSON-serializable"
        ) from exc
    if len(encoded) > _MAX_SCHEMA_BYTES:
        raise ValueError(
            f"tool {tool_name!r} parameters exceed {_MAX_SCHEMA_BYTES} bytes"
        )
    _validate_schema_node(schema, tool_name)
    for ref in _collect_local_refs(schema):
        if not _resolves_json_pointer(schema, ref[1:]):
            raise ValueError(
                f"tool {tool_name!r} parameters contain dangling local ref {ref!r}"
            )
    _reject_recursive_refs(schema, tool_name)


def _validate_schema_node(node: Any, tool_name: str) -> None:
    if isinstance(node, bool):
        return
    if not isinstance(node, dict):
        raise ValueError(f"tool {tool_name!r} parameters contain a non-object schema")
    schema_types = {"object", "array", "string", "number", "integer", "boolean", "null"}
    value = node.get("type")
    if value is not None and not (
        isinstance(value, str)
        and value in schema_types
        or isinstance(value, list)
        and value
        and all(isinstance(v, str) and v in schema_types for v in value)
    ):
        raise ValueError(f"tool {tool_name!r} parameters contain malformed type")
    ref = node.get("$ref")
    if "$ref" in node and (not isinstance(ref, str) or not ref.startswith("#/")):
        raise ValueError(
            f"tool {tool_name!r} parameters contain an invalid or external ref"
        )
    for keyword in ("properties", "$defs", "patternProperties"):
        children = node.get(keyword)
        if children is not None:
            if not isinstance(children, dict) or not all(
                isinstance(k, str) for k in children
            ):
                raise ValueError(
                    f"tool {tool_name!r} parameters contain malformed {keyword}"
                )
            for child in children.values():
                _validate_schema_node(child, tool_name)
    pattern_properties = node.get("patternProperties")
    if isinstance(pattern_properties, dict):
        for pattern in pattern_properties:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(
                    f"tool {tool_name!r} parameters contain malformed "
                    "patternProperties regex"
                ) from exc
    required = node.get("required")
    if required is not None and (
        not isinstance(required, list)
        or not all(isinstance(item, str) for item in required)
    ):
        raise ValueError(f"tool {tool_name!r} parameters contain malformed required")
    properties = node.get("properties")
    if (
        required is not None
        and isinstance(required, list)
        and isinstance(properties, dict)
    ):
        missing = [item for item in required if item not in properties]
        if missing:
            raise ValueError(
                f"tool {tool_name!r} parameters required references missing "
                f"property: {missing[0]!r}"
            )
    items = node.get("items")
    if isinstance(items, list):
        raise ValueError(
            f"tool {tool_name!r} parameters use legacy tuple items; "
            "use prefixItems instead"
        )
    if items is not None:
        _validate_schema_node(items, tool_name)
    prefix_items = node.get("prefixItems")
    if prefix_items is not None:
        if not isinstance(prefix_items, list) or not prefix_items:
            raise ValueError(
                f"tool {tool_name!r} parameters contain malformed prefixItems"
            )
        for item in prefix_items:
            _validate_schema_node(item, tool_name)
    additional = node.get("additionalProperties")
    if additional is not None:
        _validate_schema_node(additional, tool_name)
    for keyword in ("allOf", "anyOf", "oneOf"):
        alternatives = node.get(keyword)
        if alternatives is not None:
            if not isinstance(alternatives, list) or not alternatives:
                raise ValueError(
                    f"tool {tool_name!r} parameters contain malformed {keyword}"
                )
            for alternative in alternatives:
                _validate_schema_node(alternative, tool_name)
    if "not" in node:
        _validate_schema_node(node["not"], tool_name)
    if "enum" in node and (not isinstance(node["enum"], list) or not node["enum"]):
        raise ValueError(f"tool {tool_name!r} parameters contain malformed enum")
    for keyword in (
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    ):
        number = node.get(keyword)
        if number is not None and (
            not isinstance(number, (int, float)) or isinstance(number, bool)
        ):
            raise ValueError(
                f"tool {tool_name!r} parameters contain malformed {keyword}"
            )
    for keyword in (
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "minProperties",
        "maxProperties",
    ):
        count = node.get(keyword)
        if count is not None and (
            not isinstance(count, int) or isinstance(count, bool) or count < 0
        ):
            raise ValueError(
                f"tool {tool_name!r} parameters contain malformed {keyword}"
            )
    if "pattern" in node:
        pattern = node.get("pattern")
        if not isinstance(pattern, str):
            raise ValueError(f"tool {tool_name!r} parameters contain malformed pattern")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueError(
                f"tool {tool_name!r} parameters contain malformed pattern"
            ) from exc
    if "uniqueItems" in node and not isinstance(node["uniqueItems"], bool):
        raise ValueError(f"tool {tool_name!r} parameters contain malformed uniqueItems")


def _collect_local_refs(node: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref":
                if isinstance(value, str) and value.startswith("#"):
                    refs.append(value)
            else:
                refs.extend(_collect_local_refs(value))
    elif isinstance(node, list):
        for item in node:
            refs.extend(_collect_local_refs(item))
    return refs


def _resolves_json_pointer(document: Any, pointer: str) -> bool:
    resolved, _ = _resolve_json_pointer(document, pointer)
    return resolved


def _resolve_json_pointer(document: Any, pointer: str) -> tuple[bool, Any]:
    if pointer == "":
        return True, document
    if not pointer.startswith("/"):
        return False, None
    current = document
    for raw_part in pointer[1:].split("/"):
        if "~" in raw_part and any(
            index + 1 >= len(raw_part) or raw_part[index + 1] not in "01"
            for index, char in enumerate(raw_part)
            if char == "~"
        ):
            return False, None
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False, None
    return True, current


def _reject_recursive_refs(schema: dict[str, Any], tool_name: str) -> None:
    refs = set(_collect_local_refs(schema))
    graph: dict[str, set[str]] = {}
    for ref in refs:
        resolved, target = _resolve_json_pointer(schema, ref[1:])
        if resolved:
            graph[ref] = set(_collect_local_refs(target)) & refs

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(ref: str) -> None:
        if ref in visiting:
            raise ValueError(
                f"tool {tool_name!r} parameters contain recursive local ref {ref!r}; "
                "recursive schemas are not supported by tool providers"
            )
        if ref in visited:
            return
        visiting.add(ref)
        for dependency in graph.get(ref, set()):
            visit(dependency)
        visiting.remove(ref)
        visited.add(ref)

    for ref in graph:
        visit(ref)


async def bind_tools(
    plugin: Any,
    registrations: list[ToolRegistration],
    context: Any,
) -> None:
    """将插件的 Tool 注册进宿主（SkillManager）。"""
    if not registrations:
        return
    for registration in registrations:
        # 最终全局名 {plugin}__{tool} 必须无点且不超过 64 字符，否则模型请求会被拒绝
        qualified = validate_qualified_tool_name(plugin.name, registration.name)
        if qualified in _RESERVED_FINAL_TOOL_NAMES:
            raise ValueError(f"reserved qualified tool name: {qualified!r}")
    # Validate every tool even when this host cannot register it. Invalid
    # declarations must fail during plugin binding, not surface much later.
    module = PluginToolModule(plugin, context)
    host = getattr(context, "plugin_host", None)
    if host is None or not hasattr(host, "register_skill"):
        logger = getattr(context, "logger", None)
        message = (
            f"plugin {plugin.name!r} registers tools but the plugin host has no "
            "register_skill; tools are skipped"
        )
        if logger is not None and callable(getattr(logger, "warning", None)):
            logger.warning(message)
        else:
            _LOGGER.warning(message)
        return
    host.register_skill(module)
