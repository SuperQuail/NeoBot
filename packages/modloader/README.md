# NeoBot Modloader

NeoBot Modloader provides a lightweight plugin runtime for loading Python plugins from a filesystem directory. Plugins can listen to OneBot events, register agents, expose capabilities, and integrate with host-level commands, queries, lifecycle hooks, output, and runtime interception.

> Security note: plugins are imported and executed as normal Python code in the NeoBot process. This is not a sandbox. Only install plugins you trust.

## Plugin layout

A plugin can be either a single Python file:

```text
plugins/
  ping.py
```

or a package directory:

```text
plugins/
  hello/
    plugin.toml
    __init__.py
    helper.py
```

Entries whose name starts with `_` are ignored.

## Entrypoints

The loader supports three entry styles.

### `setup(ctx)` function

```python
# plugins/ping.py

def setup(ctx):
    @ctx.on.message(contains="ping")
    async def ping(event):
        await ctx.reply(event, "pong")
```

A `setup(ctx)` plugin is wrapped as a function plugin. `setup` runs during `on_load`.

### `plugin` object

```python
class HelloPlugin:
    name = "hello"
    version = "0.1.0"

    async def on_load(self, ctx):
        self.ctx = ctx

    async def on_start(self):
        self.ctx.logger.info("hello started")

    async def on_stop(self):
        self.ctx.logger.info("hello stopped")

plugin = HelloPlugin()
```

### `create_plugin()` factory

```python
class HelloPlugin:
    name = "hello"
    version = "0.1.0"

    async def on_load(self, ctx): ...
    async def on_start(self): ...
    async def on_stop(self): ...


def create_plugin():
    return HelloPlugin()
```

## Manifest

Package plugins can include `plugin.toml`:

```toml
name = "hello"
version = "0.2.0"
description = "Example hello plugin"
author = "NeoBot Team"
enabled = true
priority = 10
min_neobot_version = "1.0.0-alpha.7"
dependencies = ["base_plugin"]

[config]
reply = "pong"
```

Supported fields:

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | string | directory name | Plugin name. Must match `[A-Za-z0-9_.-]{1,64}`. |
| `version` | string | `0.1.0` | Plugin version. |
| `description` | string | empty | Human-readable description. |
| `author` | string | empty | Plugin author. |
| `enabled` | bool | `true` | Disabled plugins are skipped. |
| `priority` | int | `0` | Higher priority plugins are considered earlier when ordering independent plugins. |
| `min_neobot_version` | string | unset | Minimum compatible NeoBot version, currently recorded for metadata. |
| `dependencies` | string list | `[]` | Required plugin names. Missing or cyclic dependencies produce load errors. |
| `[config]` | table | `{}` | Plugin-specific configuration exposed as `ctx.config`. |

Dependency order always takes precedence over priority.

## Plugin context

Common context properties:

```python
ctx.plugin_name      # current plugin name
ctx.plugin_dir       # source plugin directory
ctx.data_dir         # writable per-plugin data directory
ctx.config           # manifest [config]
ctx.logger           # plugin logger
ctx.on               # event decorators
ctx.intercept        # runtime interception registry
ctx.agents           # plugin-scoped agent registrar
ctx.plugins          # restricted plugin registry view
ctx.output           # output port
ctx.plugin_host      # host facade, if provided
```

Messaging helpers:

```python
await ctx.send_private(user_id, "hello")
await ctx.send_group(group_id, "hello")
await ctx.send(conversation, "hello")
await ctx.reply(event, "hello")
text = ctx.message_text(event)
conversation = ctx.conversation_from_event(event)
value = ctx.require_config("reply")
```

## Event subscriptions

```python
def setup(ctx):
    @ctx.on.message(group=True, contains="菜单", priority=10, block_ai_reply=True)
    async def menu(event):
        await ctx.reply(event, "菜单内容")

    @ctx.on.notice("group_increase")
    async def welcome(event):
        await ctx.send_group(event["group_id"], "欢迎")

    @ctx.on.request("friend")
    async def friend_request(event):
        ctx.logger.info(f"friend request: {event}")
```

`ctx.on.message` supports:

- `group=True` or `private=True`
- `sub_type`
- `priority`
- `timeout`
- `block`
- `block_ai_reply`
- `regex`
- `keywords`
- `contains`
- `not_contains`
- custom `rule(event)` callable

Handlers are executed by priority from high to low. Exceptions and timeouts are logged and swallowed.

## Runtime interception

```python
from neobot_contracts.ports.runtime_event import RuntimeEnvelope


def setup(ctx):
    @ctx.on.runtime(kind="inbound_event", stage="message", priority=100)
    async def intercept(envelope: RuntimeEnvelope):
        event = envelope.payload.get("event", {})
        if event.get("raw_message") == "stop":
            envelope.consume({"reason": "blocked by plugin"})
```

You can also use `ctx.intercept.subscribe(...)` directly.

## Host facade

If the application provides a host facade, plugins can access it through `ctx.plugin_host`.

### Commands

Commands represent write operations:

```python
def setup(ctx):
    ctx.plugin_host.commands.register(
        "tts.speak",
        "Speak text via TTS",
        lambda text: {"spoken": text},
        schema={"type": "object", "properties": {"text": {"type": "string"}}},
    )
```

Call commands from host/application code:

```python
result = await host.commands.call("tts.speak", text="hello")
```

### Queries

Queries represent read-only operations:

```python
def setup(ctx):
    ctx.plugin_host.queries.register("memory.get", "Get memory", lambda key: {"key": key})
```

### Capabilities

Capabilities are general callable features:

```python
def setup(ctx):
    ctx.plugin_host.capabilities.register("echo", "Echo text", lambda text: text)
```

### Duplicate names and overrides

Command, query, and capability registries reject duplicate names by default:

```python
ctx.plugin_host.commands.register("demo", "first", lambda: 1)
ctx.plugin_host.commands.register("demo", "second", lambda: 2)  # raises ValueError
```

Use `override=True` only when replacing an existing registration is intentional:

```python
ctx.plugin_host.commands.register("demo", "replace", lambda: 2, override=True)
```

### Lifecycle hooks

```python
def setup(ctx):
    ctx.plugin_host.lifecycle.subscribe(
        "config.changed",
        lambda stage, config: ctx.logger.info(f"config changed: {config}"),
        priority=10,
    )
```

Plugins registered through the tracked host facade are cleaned up automatically when the plugin stops or fails during load/start.

## Plugin registry and capabilities

Plugins can expose capabilities through a `capabilities` mapping or iterable. Other plugins see restricted handles through `ctx.plugins`, not raw plugin instances.

```python
class EchoPlugin:
    name = "echo"
    version = "0.1.0"
    capabilities = {"echo": lambda payload: payload.get("text", "")}

    async def on_load(self, ctx):
        self.ctx = ctx

    async def on_start(self): pass
    async def on_stop(self): pass
```

Consumer:

```python
async def on_start(self):
    echo = self.ctx.plugins.get("echo")
    if echo is not None:
        result = await echo.call("echo", {"text": "hello"})
```

## Lifecycle state model

The manager exposes these states:

- `UNLOADED`
- `LOADING`
- `LOADED`
- `STARTING`
- `RUNNING`
- `STOPPING`
- `STOPPED`
- `ERROR`

`STOPPED` plugins are loaded again before restart. Plugin manager operations are protected by async locks to avoid concurrent lifecycle races.
