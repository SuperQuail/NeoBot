from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import pytest
from pydantic import BaseModel, Field

from neobot_modloader.agent import AgentRequest
from neobot_modloader.bot import Bot
from neobot_modloader.command_dsl import MessagePattern, PatternError
from neobot_modloader.context import RuntimePluginContext
from neobot_modloader.hooks import PluginHookBus
from neobot_modloader.message import Message
from neobot_modloader.plugin import Plugin
from neobot_modloader.plugins.tools import (
    PluginToolModule,
    build_tool_schema,
)
from neobot_modloader.reply import Reply


class _BaseConfig(BaseModel):
    value: str = "base"


class _SubConfig(_BaseConfig):
    extra: str = "sub"


class _RecursivePayload(BaseModel):
    child: _RecursivePayload | None = None


class _ToolContext:
    def __init__(self, logger: Any = None) -> None:
        self.adapter = object()
        self.logger = logger
        self.data_dir = Path("data")
        self.plugin_dir = Path("plugin")
        self.plugin_control = object()
        self.plugins = object()
        self.plugin_host = object()


class _ExplodingLogger:
    def warning(self, *args: Any, **kwargs: Any) -> None:
        raise RuntimeError("logger failed")


class _DispatchContext:
    def __init__(self, raw_event: dict[str, Any]) -> None:
        self.raw_event = raw_event
        self.consumed = False
        self.skip_ai_reply = False

    def consume(self) -> None:
        self.consumed = True

    def block_ai_reply(self) -> None:
        self.skip_ai_reply = True


def _runtime_context(
    plugin: Plugin, hook_bus: PluginHookBus, tmp_path: Path
) -> RuntimePluginContext:
    return RuntimePluginContext(
        plugin_name=plugin.name,
        plugin_dir=tmp_path,
        data_dir=tmp_path / "data",
        config={},
        logger=None,
        adapter=object(),
        hook_bus=hook_bus,
        record_subscription=lambda _subscription: None,
    )


async def test_typed_convention_names_are_model_facing_end_to_end() -> None:
    plugin = Plugin("typed")
    seen: list[tuple[Any, ...]] = []

    @plugin.tool("names")
    async def names(
        message: str,
        config: dict[str, int],
        data_dir: str,
        ctx: str,
    ) -> str:
        seen.append((message, config, data_dir, ctx))
        return "ok"

    module = PluginToolModule(plugin, _ToolContext())
    schema = module.get_tools()[0]["function"]["parameters"]
    assert set(schema["properties"]) == {
        "message",
        "config",
        "data_dir",
        "ctx",
    }
    assert set(schema["required"]) == set(schema["properties"])

    result = await module.execute(
        "names",
        {
            "message": "model-message",
            "config": {"attempts": 2},
            "data_dir": "model-dir",
            "ctx": "model-context",
        },
    )
    assert result == "ok"
    assert seen == [("model-message", {"attempts": 2}, "model-dir", "model-context")]


async def test_explicit_schema_property_overrides_name_fallback() -> None:
    plugin = Plugin("explicit")

    @plugin.tool(
        "config_value",
        parameters={
            "properties": {"config": {"type": "string"}},
            "required": ["config"],
        },
    )
    async def config_value(config) -> str:
        return config

    module = PluginToolModule(plugin, _ToolContext())
    assert (
        await module.execute("config_value", {"config": "from-model"}) == "from-model"
    )


async def test_true_di_stays_hidden_and_cannot_be_forged() -> None:
    plugin = Plugin("secure")
    context = _ToolContext()
    seen: list[Any] = []

    @plugin.tool("context")
    async def context_tool(runtime: _ToolContext, value: str) -> str:
        seen.append(runtime)
        return value

    @plugin.tool("bot")
    async def bot_tool(bot, value: str) -> str:
        seen.append(bot)
        return value

    module = PluginToolModule(plugin, context)
    schemas = {
        tool["function"]["name"]: tool["function"]["parameters"]
        for tool in module.get_tools()
    }
    assert set(schemas["context"]["properties"]) == {"value"}
    assert set(schemas["bot"]["properties"]) == {"value"}

    assert (
        await module.execute("context", {"runtime": "forged", "value": "safe"})
        == "safe"
    )
    assert await module.execute("bot", {"bot": "forged", "value": "safe"}) == "safe"
    assert seen[0] is context
    assert isinstance(seen[1], Bot)


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: request,
        lambda task: task,
        lambda state: state,
        lambda messages: messages,
    ],
)
def test_required_unannotated_agent_request_aliases_fail_tool_binding(handler) -> None:
    plugin = Plugin("gated")
    plugin.tool("call")(handler)
    with pytest.raises(ValueError, match="depends on AgentRequest"):
        PluginToolModule(plugin, _ToolContext())


def test_required_annotated_agent_request_alias_fails_tool_binding() -> None:
    plugin = Plugin("gated")

    @plugin.tool("call")
    async def call(agent_request: AgentRequest) -> str:
        return agent_request.task

    with pytest.raises(ValueError, match="depends on AgentRequest"):
        PluginToolModule(plugin, _ToolContext())


async def test_optional_agent_request_alias_uses_handler_default() -> None:
    plugin = Plugin("optional")

    @plugin.tool("call")
    async def call(task: str = "fallback") -> str:
        return task

    module = PluginToolModule(plugin, _ToolContext())
    assert module.get_tools()[0]["function"]["parameters"]["properties"] == {}
    assert await module.execute("call", {}) == "fallback"


def test_tool_reply_di_is_rejected_but_message_di_is_explicitly_empty() -> None:
    plugin = Plugin("reply")

    @plugin.tool("bad")
    async def bad(reply: Reply) -> str:
        return str(reply.event)

    with pytest.raises(ValueError, match="Reply DI.*no inbound event"):
        PluginToolModule(plugin, _ToolContext())


async def test_tool_message_di_receives_empty_synthetic_message() -> None:
    plugin = Plugin("message")
    seen: list[Message] = []

    @plugin.tool("inspect")
    async def inspect_message(incoming: Message) -> str:
        seen.append(incoming)
        return incoming.text

    module = PluginToolModule(plugin, _ToolContext())
    assert await module.execute("inspect", {}) == ""
    assert seen[0].raw_event == {}


def test_required_config_fallback_without_model_fails_binding() -> None:
    plugin = Plugin("configless")

    @plugin.tool("read")
    async def read_config(config) -> str:
        return str(config)

    with pytest.raises(ValueError, match="config DI.*no config model"):
        PluginToolModule(plugin, _ToolContext())


def test_bare_base_model_annotation_remains_model_facing() -> None:
    async def handler(config: BaseModel) -> str:
        return str(config)

    schema = build_tool_schema(handler, context_type=_ToolContext)
    assert schema["properties"]["config"]["type"] == "object"
    assert schema["required"] == ["config"]


async def test_config_subclass_is_rejected_or_injected_with_matching_instance() -> None:
    plugin = Plugin("config", config=_BaseConfig)
    plugin._config = _BaseConfig()

    @plugin.tool("read")
    async def read_config(settings: _SubConfig) -> str:
        return settings.extra

    with pytest.raises(TypeError, match="expected _SubConfig, got _BaseConfig"):
        PluginToolModule(plugin, _ToolContext())

    plugin._config = _SubConfig()
    module = PluginToolModule(plugin, _ToolContext())
    assert await module.execute("read", {"settings": {"extra": "forged"}}) == "sub"


@pytest.mark.parametrize("logger", [None, object(), _ExplodingLogger()])
async def test_tool_exception_contract_survives_malformed_logger(logger: Any) -> None:
    plugin = Plugin("failure")

    @plugin.tool("explode")
    async def explode() -> str:
        raise RuntimeError("secret detail")

    module = PluginToolModule(plugin, _ToolContext(logger))
    assert await module.execute("explode", {}) == "工具执行失败 [explode]"


async def test_annotated_metadata_schema_and_coercion_are_preserved() -> None:
    plugin = Plugin("annotated")
    seen: list[int] = []

    @plugin.tool("positive")
    async def positive(
        value: Annotated[
            int,
            Field(gt=0, description="Must be positive", title="Positive value"),
        ] = 2,
    ) -> str:
        seen.append(value)
        return str(value)

    module = PluginToolModule(plugin, _ToolContext())
    value_schema = module.get_tools()[0]["function"]["parameters"]["properties"][
        "value"
    ]
    assert value_schema["description"] == "Must be positive"
    assert value_schema["title"] == "Positive value"
    assert value_schema["exclusiveMinimum"] == 0
    assert value_schema["default"] == 2
    assert await module.execute("positive", {"value": "3"}) == "3"
    assert seen == [3]
    assert "参数 value 校验失败" in await module.execute("positive", {"value": 0})


async def test_fixed_tuple_schema_matches_runtime_coercion() -> None:
    plugin = Plugin("tuple")
    seen: list[tuple[int, str]] = []

    @plugin.tool("pair")
    async def pair(value: tuple[int, str]) -> str:
        seen.append(value)
        return f"{value[0]}:{value[1]}"

    module = PluginToolModule(plugin, _ToolContext())
    value_schema = module.get_tools()[0]["function"]["parameters"]["properties"][
        "value"
    ]
    assert value_schema["prefixItems"] == [
        {"type": "integer"},
        {"type": "string"},
    ]
    assert value_schema["minItems"] == value_schema["maxItems"] == 2
    assert await module.execute("pair", {"value": ["2", "items"]}) == "2:items"
    assert seen == [(2, "items")]


async def test_bare_tuple_annotation_also_coerces_to_tuple() -> None:
    plugin = Plugin("baretuple")
    seen: list[tuple[Any, ...]] = []

    @plugin.tool("items")
    async def items(value: tuple) -> str:
        seen.append(value)
        return str(len(value))

    module = PluginToolModule(plugin, _ToolContext())
    assert await module.execute("items", {"value": [1, 2]}) == "2"
    assert seen == [(1, 2)]


def test_recursive_model_schema_is_rejected_before_registration() -> None:
    plugin = Plugin("recursive")

    @plugin.tool("walk")
    async def walk(payload: _RecursivePayload) -> str:
        return str(payload)

    with pytest.raises(ValueError, match="recursive local ref"):
        PluginToolModule(plugin, _ToolContext())


def test_type_hint_and_default_failures_name_the_parameter() -> None:
    async def unresolved(value) -> str:
        return str(value)

    unresolved.__annotations__["value"] = "MissingPluginType"
    with pytest.raises(TypeError, match="parameter 'value'.*unresolved.*NameError"):
        build_tool_schema(unresolved)

    sentinel = object()

    async def invalid_default(value: object = sentinel) -> str:
        return str(value)

    with pytest.raises(ValueError, match="tool parameter 'value'"):
        build_tool_schema(invalid_default)


def test_duplicate_dsl_capture_names_are_rejected_during_parse() -> None:
    with pytest.raises(PatternError, match="duplicate parameter name: value"):
        MessagePattern("run <value> [value]", command=True)


async def test_lifecycle_documents_empty_message_and_reply_event(
    tmp_path: Path,
) -> None:
    plugin = Plugin("lifecycle")
    hook_bus = PluginHookBus()
    seen: list[tuple[dict[str, Any], dict[str, Any]]] = []

    @plugin.on_load
    async def loaded(message: Message, reply: Reply) -> None:
        seen.append((message.raw_event, reply.event))

    await plugin.on_load(_runtime_context(plugin, hook_bus, tmp_path))
    assert seen == [({}, {})]
    assert "no inbound event" in (Plugin.on_load.__doc__ or "")


async def test_command_parse_ignore_does_not_consume_or_block(tmp_path: Path) -> None:
    plugin = Plugin("ignore")
    hook_bus = PluginHookBus()
    called: list[str] = []

    @plugin.command("number <value:int>", parse_error="ignore")
    async def number(value: int) -> None:
        called.append(str(value))

    context = _runtime_context(plugin, hook_bus, tmp_path)
    await plugin.on_load(context)

    async def downstream(_event: dict[str, Any]) -> None:
        called.append("downstream")

    hook_bus.subscribe(downstream, post_type="message", priority=0)
    dispatch_context = _DispatchContext(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 1,
            "raw_message": "/number not-an-int",
        }
    )
    await hook_bus.dispatch(dispatch_context)

    assert called == ["downstream"]
    assert dispatch_context.consumed is False
    assert dispatch_context.skip_ai_reply is False
