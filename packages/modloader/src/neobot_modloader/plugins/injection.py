from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, get_type_hints

from pydantic import BaseModel

from neobot_contracts.ports.logging import Logger

from neobot_modloader.agent import AgentRequest
from neobot_modloader.bot import Bot
from neobot_modloader.management import PluginControlFacade
from neobot_modloader.message import Message
from neobot_modloader.reply import Reply
from neobot_modloader.plugins.registration import Handler


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
) -> dict[str, Any]:
    try:
        hints = get_type_hints(handler, include_extras=False)
    except Exception:
        hints = {}
    signature = inspect.signature(handler)
    kwargs: dict[str, Any] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind in {inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL}:
            continue
        annotation = hints.get(name)
        # 这里保持轻量注入：优先 DSL 捕获，再按类型注解和少量约定参数名解析。
        if name in captures:
            kwargs[name] = captures[name]
        elif name in {"ctx", "context"} or annotation is context.__class__:
            kwargs[name] = context
        elif annotation is Reply:
            kwargs[name] = Reply(context, event)
        elif annotation is Message:
            kwargs[name] = message
        elif agent_request is not None and (annotation is AgentRequest or name == "request"):
            kwargs[name] = agent_request
        elif agent_request is not None and name == "task":
            kwargs[name] = agent_request.task
        elif agent_request is not None and name == "state":
            kwargs[name] = agent_request.state
        elif agent_request is not None and name == "messages":
            kwargs[name] = agent_request.messages
        elif annotation is Bot:
            kwargs[name] = Bot(context.adapter)
        elif annotation is Logger or name == "logger":
            kwargs[name] = context.logger
        elif annotation is Path and name == "data_dir":
            kwargs[name] = context.data_dir
        elif annotation is Path and name == "plugin_dir":
            kwargs[name] = context.plugin_dir
        elif name == "event":
            kwargs[name] = event
        elif name == "plugins":
            kwargs[name] = context.plugins
        elif name == "host":
            kwargs[name] = context.plugin_host
        elif annotation is PluginControlFacade or name == "plugin_control":
            kwargs[name] = context.plugin_control
        elif config_model is not None and annotation is config_model:
            kwargs[name] = config
        elif parameter.default is inspect.Parameter.empty:
            raise TypeError(f"Cannot resolve parameter {name!r} for handler {handler.__qualname__}")
    return kwargs
