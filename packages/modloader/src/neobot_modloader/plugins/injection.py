from __future__ import annotations

import inspect
from pathlib import Path
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from neobot_contracts.ports.logging import Logger

from neobot_modloader.agent import AgentRequest
from neobot_modloader.bot import Bot
from neobot_modloader.management import PluginControlFacade
from neobot_modloader.message import Message
from neobot_modloader.plugins.registration import Handler
from neobot_modloader.reply import Reply


_NAME_INJECTION_KINDS = {
    "ctx": "context",
    "context": "context",
    "config": "config",
    "logger": "logger",
    "event": "event",
    "message": "message",
    "reply": "reply",
    "data_dir": "data_dir",
    "plugin_dir": "plugin_dir",
    "host": "host",
    "plugins": "plugins",
    "plugin_control": "plugin_control",
    "bot": "bot",
}
_AGENT_REQUEST_ALIASES = {
    "request": ("agent_request", AgentRequest),
    "agent_request": ("agent_request", AgentRequest),
    "task": ("task", str),
    "state": ("state", dict),
    "messages": ("messages", list),
}


def _handler_name(handler: Handler) -> str:
    module = getattr(handler, "__module__", "<unknown>")
    qualname = getattr(handler, "__qualname__", type(handler).__qualname__)
    return f"{module}.{qualname}"


def get_handler_type_hints(handler: Handler) -> dict[str, Any]:
    """Resolve parameter annotations with extras and parameter-specific errors."""
    signature = inspect.signature(handler)
    raw_hints = inspect.get_annotations(handler, eval_str=False)
    globalns = getattr(handler, "__globals__", {})
    localns: dict[str, Any] = {}
    try:
        closure = inspect.getclosurevars(handler)
    except (TypeError, ValueError):
        pass
    else:
        localns.update(closure.globals)
        localns.update(closure.nonlocals)

    resolved: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if parameter.annotation is inspect.Parameter.empty:
            continue
        raw_annotation = raw_hints.get(name, parameter.annotation)

        def annotated_value() -> None:
            return None

        annotated_value.__annotations__ = {"value": raw_annotation}
        try:
            resolved[name] = get_type_hints(
                annotated_value,
                globalns=globalns,
                localns=localns,
                include_extras=True,
            )["value"]
        except Exception as exc:
            raise TypeError(
                f"Cannot resolve annotation for parameter {name!r} of handler "
                f"{_handler_name(handler)}: {type(exc).__name__}: {exc}"
            ) from exc
    return resolved


def _annotation_candidates(annotation: Any) -> tuple[Any, ...]:
    if annotation is inspect.Parameter.empty:
        return ()
    origin = get_origin(annotation)
    if origin is Annotated:
        args = get_args(annotation)
        return _annotation_candidates(args[0]) if args else ()
    if origin is Union or origin is UnionType:
        candidates: list[Any] = []
        for candidate in get_args(annotation):
            if candidate is not type(None):
                candidates.extend(_annotation_candidates(candidate))
        return tuple(candidates)
    return (annotation,)


def _annotation_is_untyped(annotation: Any) -> bool:
    # Any carries no usable runtime type information and retains the legacy
    # convention behavior of an omitted annotation.
    return annotation is inspect.Parameter.empty or annotation is Any


def _safe_issubclass(candidate: Any, expected: Any) -> bool:
    try:
        return isinstance(candidate, type) and issubclass(candidate, expected)
    except TypeError:
        return False


def _classify_di_annotation(
    name: str,
    annotation: Any,
    *,
    context_type: type[Any] | None,
    config_model: type[BaseModel] | None,
) -> str | None:
    """Classify one concrete annotation against trusted runtime providers."""
    if not isinstance(annotation, type) or annotation is object:
        return None
    if context_type is not None and _safe_issubclass(context_type, annotation):
        return "context"
    if (
        config_model is not None
        and annotation is not BaseModel
        and (
            _safe_issubclass(config_model, annotation)
            or _safe_issubclass(annotation, config_model)
        )
    ):
        return "config"
    for provider_type, kind in (
        (Reply, "reply"),
        (Message, "message"),
        (AgentRequest, "agent_request"),
        (Bot, "bot"),
        (Logger, "logger"),
        (PluginControlFacade, "plugin_control"),
    ):
        if _safe_issubclass(provider_type, annotation) or _safe_issubclass(
            annotation, provider_type
        ):
            return kind
    if name in {"data_dir", "plugin_dir"} and (
        _safe_issubclass(Path, annotation) or _safe_issubclass(annotation, Path)
    ):
        return name
    return None


def injected_parameter_kind(
    name: str,
    annotation: Any,
    *,
    context_type: type[Any] | None = None,
    config_model: type[BaseModel] | None = None,
) -> str | None:
    """Return DI selected by an annotation, independent of parameter names."""
    if _annotation_is_untyped(annotation):
        return None
    for candidate in _annotation_candidates(annotation):
        kind = _classify_di_annotation(
            name,
            candidate,
            context_type=context_type,
            config_model=config_model,
        )
        if kind is not None:
            return kind
    return None


def _agent_request_parameter_kind(name: str, annotation: Any) -> str | None:
    alias = _AGENT_REQUEST_ALIASES.get(name)
    if alias is None:
        return None
    kind, provider_type = alias
    if _annotation_is_untyped(annotation):
        return kind
    for candidate in _annotation_candidates(annotation):
        candidate_type = get_origin(candidate) or candidate
        if candidate_type is object:
            continue
        if _safe_issubclass(provider_type, candidate_type):
            return kind
    return None


def parameter_injection_kind(
    name: str,
    annotation: Any,
    *,
    context_type: type[Any] | None = None,
    config_model: type[BaseModel] | None = None,
    explicit_model_parameter: bool = False,
) -> str | None:
    """Classify annotation DI and annotation-aware convention DI.

    An explicit tool schema property may override a name convention, but never
    a true annotation-based dependency.
    """
    annotated = injected_parameter_kind(
        name,
        annotation,
        context_type=context_type,
        config_model=config_model,
    )
    if annotated is not None:
        return annotated
    if explicit_model_parameter:
        return None
    agent_alias = _agent_request_parameter_kind(name, annotation)
    if agent_alias is not None:
        return agent_alias
    if _annotation_is_untyped(annotation):
        return _NAME_INJECTION_KINDS.get(name)
    return None


def validate_config_injection(
    handler: Handler,
    name: str,
    annotation: Any,
    config: BaseModel | None,
    config_model: type[BaseModel] | None,
) -> None:
    """Ensure a configured instance satisfies the handler's config annotation."""
    if config_model is None or config is None:
        raise TypeError(
            f"Cannot inject config into required parameter {name!r} of handler "
            f"{_handler_name(handler)}: the plugin has no matching config instance"
        )
    expected = tuple(
        candidate
        for candidate in _annotation_candidates(annotation)
        if isinstance(candidate, type)
        and candidate is not BaseModel
        and (
            _safe_issubclass(config_model, candidate)
            or _safe_issubclass(candidate, config_model)
        )
    )
    if expected and not any(isinstance(config, candidate) for candidate in expected):
        expected_names = " | ".join(candidate.__qualname__ for candidate in expected)
        raise TypeError(
            f"Cannot inject config into parameter {name!r} of handler "
            f"{_handler_name(handler)}: expected {expected_names}, got "
            f"{type(config).__qualname__}"
        )


def _injected_value(
    kind: str,
    *,
    context: Any,
    event: dict[str, Any],
    message: Message,
    config: BaseModel | None,
    config_model: type[BaseModel] | None,
    agent_request: AgentRequest | None,
) -> tuple[bool, Any]:
    if kind == "context":
        return True, context
    if kind == "reply":
        return True, Reply(context, event)
    if kind == "message":
        return True, message
    if kind == "agent_request":
        return agent_request is not None, agent_request
    if kind == "task":
        return agent_request is not None, agent_request.task if agent_request else None
    if kind == "state":
        return agent_request is not None, agent_request.state if agent_request else None
    if kind == "messages":
        return (
            agent_request is not None,
            agent_request.messages if agent_request else None,
        )
    if kind == "bot":
        return True, Bot(context.adapter)
    if kind == "logger":
        return True, context.logger
    if kind == "event":
        return True, event
    if kind == "data_dir":
        return True, context.data_dir
    if kind == "plugin_dir":
        return True, context.plugin_dir
    if kind == "host":
        return True, context.plugin_host
    if kind == "plugins":
        return True, context.plugins
    if kind == "plugin_control":
        return True, context.plugin_control
    if kind == "config":
        return config_model is not None and config is not None, config
    return False, None


async def resolve_handler_kwargs(
    handler: Handler,
    *,
    context: Any,
    event: dict[str, Any],
    message: Message,
    captures: dict[str, Any],
    config: BaseModel | None,
    config_model: type[BaseModel] | None,
    agent_request: AgentRequest | None,
    model_parameters: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    hints = get_handler_type_hints(handler)
    signature = inspect.signature(handler)
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in {
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        }:
            continue
        annotation = hints.get(name, inspect.Parameter.empty)
        annotated_kind = injected_parameter_kind(
            name,
            annotation,
            context_type=context.__class__,
            config_model=config_model,
        )
        if annotated_kind is not None:
            if annotated_kind == "config" and config is not None:
                validate_config_injection(
                    handler, name, annotation, config, config_model
                )
            available, value = _injected_value(
                annotated_kind,
                context=context,
                event=event,
                message=message,
                config=config,
                config_model=config_model,
                agent_request=agent_request,
            )
            if available:
                kwargs[name] = value
            elif parameter.default is inspect.Parameter.empty:
                raise TypeError(
                    f"Dependency {annotated_kind!r} is unavailable for required "
                    f"parameter {name!r} of handler {_handler_name(handler)}"
                )
            continue

        if name in captures:
            kwargs[name] = captures[name]
            continue

        conventional_kind = parameter_injection_kind(
            name,
            annotation,
            context_type=context.__class__,
            config_model=config_model,
            explicit_model_parameter=name in model_parameters,
        )
        if conventional_kind is not None:
            available, value = _injected_value(
                conventional_kind,
                context=context,
                event=event,
                message=message,
                config=config,
                config_model=config_model,
                agent_request=agent_request,
            )
            if available:
                kwargs[name] = value
            elif parameter.default is inspect.Parameter.empty:
                raise TypeError(
                    f"Dependency {conventional_kind!r} is unavailable for required "
                    f"parameter {name!r} of handler {_handler_name(handler)}"
                )
            continue

        if parameter.default is inspect.Parameter.empty:
            raise TypeError(
                f"Cannot resolve parameter {name!r} for handler {_handler_name(handler)}"
            )
    return kwargs
