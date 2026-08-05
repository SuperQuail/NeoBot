from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from neobot_contracts.ports.logging import Logger
from neobot_modloader.bot import Bot
from neobot_modloader.command_dsl import PatternError
from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.management import PluginControlFacade
from neobot_modloader.message import Message
from neobot_modloader.plugin import Plugin
from neobot_modloader.plugins.injection import (
    injected_parameter_kind,
    resolve_handler_kwargs,
)
from neobot_modloader.plugins.tools import (
    _rewrite_defs_refs,
    _validate_tool_schema,
    bind_tools,
    build_tool_schema,
)
from neobot_modloader.reply import Reply


class _Config(BaseModel):
    enabled: bool = True


class _SubConfig(_Config):
    extra: str = "x"


class _Context:
    adapter = object()
    logger = object()
    data_dir = Path("data")
    plugin_dir = Path("plugin")
    plugin_control = object()
    plugins = object()
    plugin_host = object()


class _BaseContext:
    pass


class _SubContext(_BaseContext):
    adapter = object()
    logger = object()
    data_dir = Path("data")
    plugin_dir = Path("plugin")
    plugin_control = object()
    plugins = object()
    plugin_host = object()


class _DispatchCtx:
    def __init__(self, raw_event: dict) -> None:
        self.raw_event = raw_event
        self.consumed = False
        self.skip_ai_reply = False

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True


def _runtime_context(
    plugin: Plugin, hook_bus: PluginHookBus, tmp_path: Path, logger: Any = None
) -> RuntimePluginContext:
    return RuntimePluginContext(
        plugin_name=plugin.name,
        plugin_dir=Path(tmp_path),
        data_dir=Path(tmp_path) / "data",
        config={},
        logger=logger,
        adapter=object(),
        hook_bus=hook_bus,
        record_subscription=lambda _subscription: None,
        agent_registry=None,
        plugin_registry=None,
        host=None,
        plugin_control=None,
        markdown_skill_registry=None,
        record_skill_cleanup=None,
    )


async def _dispatch_command(
    plugin: Plugin, hook_bus: PluginHookBus, context: RuntimePluginContext, text: str
) -> None:
    await plugin.on_load(context)
    await hook_bus.dispatch(
        _DispatchCtx(
            {
                "post_type": "message",
                "message_type": "private",
                "user_id": 1,
                "message": [{"type": "text", "data": {"text": text}}],
            }
        )
    )


async def test_annotation_di_uses_nonstandard_names_and_is_hidden_from_schema() -> None:
    async def handler(
        runtime: _Context,
        log_sink: Logger,
        response: Reply,
        incoming: Message,
        client: Bot,
        controls: PluginControlFacade,
        settings: _Config,
        data_dir: Path,
        plugin_dir: Path,
        query: str,
    ) -> None:
        pass

    schema = build_tool_schema(handler, context_type=_Context, config_model=_Config)
    assert set(schema["properties"]) == {"query"}

    context = _Context()
    config = _Config()
    kwargs = await resolve_handler_kwargs(
        handler,
        context=context,
        event={},
        message=Message({}),
        captures={
            "runtime": "forged",
            "log_sink": "forged",
            "response": "forged",
            "query": "safe",
        },
        config=config,
        config_model=_Config,
        agent_request=None,
    )
    assert kwargs["runtime"] is context
    assert kwargs["log_sink"] is context.logger
    assert isinstance(kwargs["response"], Reply)
    assert isinstance(kwargs["incoming"], Message)
    assert isinstance(kwargs["client"], Bot)
    assert kwargs["controls"] is context.plugin_control
    assert kwargs["settings"] is config
    assert kwargs["data_dir"] == context.data_dir
    assert kwargs["plugin_dir"] == context.plugin_dir
    assert kwargs["query"] == "safe"


async def test_optional_union_and_base_class_annotations_classified_as_di() -> None:
    async def handler(
        settings: _Config | None,
        runtime: _BaseContext,
        response: Reply | str,
        data_dir: Path | None,
        client: Bot | None,
        query: str,
    ) -> None:
        pass

    schema = build_tool_schema(handler, context_type=_SubContext, config_model=_Config)
    assert set(schema["properties"]) == {"query"}

    context = _SubContext()
    config = _Config()
    kwargs = await resolve_handler_kwargs(
        handler,
        context=context,
        event={},
        message=Message({}),
        captures={
            "settings": "forged",
            "runtime": "forged",
            "response": "forged",
            "data_dir": "forged",
            "client": "forged",
            "query": "safe",
        },
        config=config,
        config_model=_Config,
        agent_request=None,
    )
    assert kwargs["settings"] is config
    assert kwargs["runtime"] is context
    assert isinstance(kwargs["response"], Reply)
    assert kwargs["data_dir"] == context.data_dir
    assert isinstance(kwargs["client"], Bot)
    assert kwargs["query"] == "safe"


async def test_tool_execute_cannot_forge_optional_or_base_class_di() -> None:
    from neobot_modloader.plugins.tools import PluginToolModule

    plugin = Plugin("opt", config=_Config)
    plugin._config = _Config()
    seen: list[tuple[Any, Any]] = []

    @plugin.tool("q")
    async def q(runtime: _BaseContext, settings: _Config | None, query: str) -> str:
        seen.append((runtime, settings))
        return query

    context = _SubContext()
    module = PluginToolModule(plugin, context)
    result = await module.execute(
        "q",
        {
            "runtime": "forged",
            "settings": {"enabled": "forged"},
            "query": "ok",
        },
    )

    assert result == "ok"
    assert seen == [(context, plugin._config)]


async def test_event_dsl_captures_cannot_shadow_annotated_di_params(tmp_path) -> None:
    """Annotation DI and DSL captures cannot silently target the same name."""

    class _FakeLogger:
        name = "framework-logger"

    plugin = Plugin("dsl")
    hook_bus = PluginHookBus()
    seen: list[tuple[Any, Any, str]] = []

    @plugin.command("run <logger> <ctx> <payload>")
    async def run(logger: Logger, ctx: RuntimePluginContext, payload: str) -> None:
        seen.append((logger, ctx, payload))

    context = _runtime_context(plugin, hook_bus, tmp_path, logger=_FakeLogger())
    with pytest.raises(PatternError, match="capture 'logger'.*logger DI"):
        await _dispatch_command(plugin, hook_bus, context, "/run hello world value")
    assert seen == []


async def test_command_dsl_unannotated_names_receive_captures(tmp_path) -> None:
    """未注解的 DSL 捕获名（host/plugins/event/ctx/logger/plugin_control）
    必须拿到解析后的字符串，而不是框架名称回退对象。"""
    plugin = Plugin("ban")
    hook_bus = PluginHookBus()
    seen: list[tuple[Any, ...]] = []

    @plugin.command("ban <host> <plugins> <event> <ctx> <logger> <plugin_control>")
    async def ban(host, plugins, event, ctx, logger, plugin_control) -> None:
        seen.append((host, plugins, event, ctx, logger, plugin_control))

    context = _runtime_context(plugin, hook_bus, tmp_path)
    await _dispatch_command(plugin, hook_bus, context, "/ban h p e c l pc")

    assert seen == [("h", "p", "e", "c", "l", "pc")]


async def test_unannotated_di_named_tool_params_receive_runtime_values() -> None:
    """无注解但名为 config/data_dir/message/bot 的工具参数必须由运行时注入，
    模型伪造值被过滤，执行不得失败。"""
    from neobot_modloader.plugins.tools import PluginToolModule

    plugin = Plugin("unn", config=_Config)
    plugin._config = _Config()
    seen: list[tuple[Any, Any, Any, Any]] = []

    @plugin.tool("q")
    async def q(config, data_dir, message, bot, query) -> str:
        seen.append((config, data_dir, message, bot))
        return query

    context = _SubContext()
    module = PluginToolModule(plugin, context)
    result = await module.execute(
        "q",
        {
            "config": "forged",
            "data_dir": "forged",
            "message": "forged",
            "bot": "forged",
            "query": "ok",
        },
    )

    assert result == "ok"
    assert seen[0][0] is plugin._config
    assert seen[0][1] == Path("data")
    assert isinstance(seen[0][2], Message)
    assert isinstance(seen[0][3], Bot)


def test_base_model_annotation_is_not_config_di() -> None:
    """裸 BaseModel 注解不得被当作 config DI（否则会被 schema 隐藏）。"""
    assert (
        injected_parameter_kind(
            "payload", BaseModel, context_type=_SubContext, config_model=_Config
        )
        is None
    )
    assert (
        injected_parameter_kind(
            "settings", _Config, context_type=_SubContext, config_model=_Config
        )
        == "config"
    )


async def test_config_subclass_annotation_requires_matching_instance() -> None:
    """A narrower config annotation must never receive the configured base type."""

    async def handler(settings: _SubConfig, query: str) -> None:
        pass

    schema = build_tool_schema(handler, context_type=_SubContext, config_model=_Config)
    assert set(schema["properties"]) == {"query"}

    with pytest.raises(TypeError, match="expected _SubConfig, got _Config"):
        await resolve_handler_kwargs(
            handler,
            context=_SubContext(),
            event={},
            message=Message({}),
            captures={"settings": "forged", "query": "safe"},
            config=_Config(),
            config_model=_Config,
            agent_request=None,
        )

    config = _SubConfig()
    kwargs = await resolve_handler_kwargs(
        handler,
        context=_SubContext(),
        event={},
        message=Message({}),
        captures={"settings": "forged", "query": "safe"},
        config=config,
        config_model=_Config,
        agent_request=None,
    )
    assert kwargs["settings"] is config
    assert kwargs["query"] == "safe"


def test_bind_tools_logs_clearly_without_register_skill() -> None:
    class _NoHost:
        def __init__(self) -> None:
            self.warnings: list[tuple] = []

        @property
        def logger(self):
            return self

        def warning(self, *args, **kwargs) -> None:
            self.warnings.append((args, kwargs))

    plugin = Plugin("nohost")

    @plugin.tool("t")
    async def t() -> str:
        return "ok"

    context = _NoHost()
    asyncio.run(bind_tools(plugin, plugin._tool_registrations, context))
    assert context.warnings
    assert "no register_skill" in context.warnings[0][0][0]


def test_defs_ref_rewrite_preserves_suffix_and_escaped_name() -> None:
    node = {"$ref": "#/$defs/a~1b~0c/properties/value"}
    _rewrite_defs_refs(node, {"a/b~c": "renamed/x~y"})
    assert node["$ref"] == "#/$defs/renamed~1x~0y/properties/value"


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "properties": []},
        {"type": "object", "required": "x"},
        {"type": "object", "items": []},
        {"type": "object", "$ref": 3},
        {"type": "object", "$ref": "https://example.invalid/schema"},
        {"type": "object", "anyOf": {}},
        {"type": "object", "minProperties": "one"},
        {"type": "object", "uniqueItems": 1},
        {"type": "object", "enum": []},
        {
            "type": "object",
            "properties": {"a": {"type": "string"}},
            "required": ["a", "missing"],
        },
        {"type": "object", "patternProperties": {1: {"type": "string"}}},
    ],
)
def test_explicit_schema_rejects_malformed_supported_keywords(schema: dict) -> None:
    with pytest.raises(ValueError):
        _validate_tool_schema(schema, "bad")


def test_explicit_schema_accepts_boolean_schema_forms() -> None:
    _validate_tool_schema(
        {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": True},
                "meta": {"type": "object", "additionalProperties": False},
            },
            "required": [],
        },
        "ok",
    )


def test_explicit_schema_rejects_invalid_regex_pattern() -> None:
    with pytest.raises(ValueError, match="pattern"):
        _validate_tool_schema(
            {
                "type": "object",
                "properties": {"x": {"type": "string", "pattern": "["}},
            },
            "bad",
        )


def test_explicit_schema_rejects_invalid_pattern_properties_regex() -> None:
    with pytest.raises(ValueError, match="patternProperties regex"):
        _validate_tool_schema(
            {
                "type": "object",
                "patternProperties": {"[": {"type": "string"}},
            },
            "bad",
        )


def test_explicit_schema_accepts_prefix_items_and_rejects_recursion() -> None:
    _validate_tool_schema(
        {
            "type": "object",
            "properties": {
                "pair": {
                    "type": "array",
                    "prefixItems": [
                        {"type": "integer"},
                        {"type": "string"},
                    ],
                    "minItems": 2,
                    "maxItems": 2,
                }
            },
        },
        "tuple",
    )
    with pytest.raises(ValueError, match="recursive local ref"):
        _validate_tool_schema(
            {
                "type": "object",
                "$defs": {
                    "Node": {
                        "type": "object",
                        "properties": {"child": {"$ref": "#/$defs/Node"}},
                    }
                },
                "properties": {"root": {"$ref": "#/$defs/Node"}},
            },
            "recursive",
        )
