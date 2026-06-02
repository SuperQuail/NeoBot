# NeoBot Modloader

NeoBot Modloader 用于从文件系统目录加载 Python 插件。

当前版本是一次破坏性插件 API 更新。插件入口只保留一种写法：显式导出 `plugin = Plugin(...)`，不再支持旧的 `setup(ctx)`、`ctx.on.*`、`Matcher`、`on_command()` 等兼容 API。

## 插件结构

插件可以是单个 Python 文件：

```text
plugins/
  ping.py
```

也可以是一个包：

```text
plugins/
  weather/
    plugin.toml
    __init__.py
```

插件模块必须导出一个 `Plugin` 实例：

```python
from neobot_modloader import Plugin

plugin = Plugin("ping")
```

## 快速开始

```python
from neobot_modloader import Plugin, Reply

plugin = Plugin("ping")


@plugin.command("ping [args:rest]")
async def ping(args: str | None, reply: Reply):
    await reply.send(f"pong: {args or ''}")
```

用户发送 `/ping hello` 时，`args` 会得到 `"hello"`。

## 消息链

处理器可以注入标准化后的 `Message` 对象。它会优先从 `event["message"]` 读取 OneBot 消息链；如果没有消息链，才使用 `raw_message` 作为纯文本兜底。

```python
from neobot_modloader import Message, Plugin, Reply

plugin = Plugin("echo")


@plugin.message()
async def echo(message: Message, reply: Reply):
    await reply.send(message)
```

常用属性：

```python
message.raw_event
message.raw_message
message.segments
message.text
message.images
message.first_image
message.has_image
message.of_type("at")
```

`reply.send(message)` 会直接发送原始消息链，适合做复读、转发式响应或调试。

## 消息链 DSL

`@plugin.command(...)` 和 `@plugin.message(...)` 的模式匹配基于消息链 token stream，而不是只看 `raw_message`。

```python
from neobot_modloader import ImageSegment, Plugin, Reply

plugin = Plugin("vision")


@plugin.command("识图 <img:image>")
async def vision(img: ImageSegment, reply: Reply):
    await reply.send(img)
```

这段代码可以匹配类似 `/识图 + 图片` 的消息链，并把图片段注入到 `img` 参数。

支持的捕获写法：

| 模式 | 注入结果 |
| --- | --- |
| `<name>` | 必填字符串 token |
| `[name]` | 可选字符串 token |
| `<name:int>` | `int` |
| `<name:float>` | `float` |
| `<name:bool>` | `bool` |
| `<name:rest>` | 剩余文本 token |
| `<img:image>` | 一个图片段 |
| `[img:image]` | 可选图片段 |
| `<imgs:list[image]>` | 一个或多个图片段 |

如果不想要求 slash 命令，可以用 message 模式：

```python
@plugin.message("识图 <img:image>")
async def vision_message(img: ImageSegment, reply: Reply):
    await reply.send(img)
```

## Reply

`Reply.send()` 是主要发送入口。

```python
await reply.send("text")
await reply.send(message)
await reply.send(message.segments)
await reply.send(img)
await reply.send([
    {"type": "text", "data": {"text": "result:"}},
    {"type": "image", "data": {"url": image_url}},
])
```

也提供一些糖方法：

```python
await reply.text("hello")
await reply.image(url=image_url)
await reply.private(user_id, "hello")
await reply.group(group_id, "hello")
```

`reply.send(...)` 支持：

- `str`
- `list[dict]`
- `Message`
- `MessageChain`
- `MessageSegment`
- `ImageSegment`
- `list[MessageSegment]`

## 组合消息链

可以用 `MessageChain` 组合多个消息段：

```python
from neobot_modloader import MessageChain

await reply.send(
    MessageChain()
    .text("收到图片: ")
    .image(url=img.url, file=img.file)
)
```

## 配置

包插件可以使用 `plugin.toml` 配置启用状态、优先级、依赖和默认配置：

```toml
enabled = true
priority = 10
dependencies = []
python_dependencies = ["httpx"]

[config]
api_key = "secret"
default_city = "Shanghai"
```

插件名、版本、描述、作者以 `Plugin(...)` 为准：

```python
from pydantic import BaseModel
from neobot_modloader import Plugin, Reply


class Config(BaseModel):
    api_key: str
    default_city: str = "Shanghai"


plugin = Plugin(
    "weather",
    version="1.0.0",
    description="Weather query plugin",
    config=Config,
)


@plugin.command("weather [city]")
async def weather(city: str | None, config: Config, reply: Reply):
    await reply.send(city or config.default_city)
```

如果 `plugin.toml` 声明了和 `Plugin(...)` 冲突的 `name` 或 `version`，插件加载会失败。

## 注册子 Agent

插件可以声明可被主 Agent 委托的子 Agent。默认写法是 handler：接收自然语言 `task`，返回文本结果。

```python
from neobot_modloader import AgentRequest, Plugin

plugin = Plugin("weather")


@plugin.agent("forecast", description="查询天气、解释天气状况")
async def forecast(task: str, request: AgentRequest, config: Config) -> str:
    city = task.strip() or config.default_city
    return f"{city} 今天晴，22-28 度。"
```

子 Agent 会以 `<plugin>.<agent>` 的名字暴露给主 Agent，例如 `weather.forecast`。

如果要使用 `neobot_chat` 的 `Workflow`、`StateGraph`、`CompiledGraph`，使用 `factory=True` 返回一个有 `invoke(state)` 的对象：

```python
from neobot_chat import State, Workflow
from neobot_modloader import Plugin

plugin = Plugin("planner")


async def parse(state: State) -> State:
    messages = list(state.get("messages", []))
    task = str(messages[-1].get("content", "")) if messages else ""
    return {**state, "_task": task}


async def answer(state: State) -> State:
    messages = list(state.get("messages", []))
    messages.append({"role": "assistant", "content": f"完成: {state.get('_task', '')}"})
    return {**state, "messages": messages}


@plugin.agent("worker", description="使用 Workflow 处理委托任务", factory=True)
def build_worker() -> Workflow:
    return Workflow().add_step(parse).add_step(answer)
```

子 Agent 默认不直接发消息，而是把结果返回给主 Agent。需要直接回复用户时，仍使用 `@plugin.command` 或 `@plugin.message`。

## 生命周期

```python
from neobot_modloader import Plugin

plugin = Plugin("lifecycle")


@plugin.on_load
async def loaded(logger):
    logger.info("loaded")


@plugin.on_startup
async def started(logger):
    logger.info("started")


@plugin.on_shutdown
async def stopped(logger):
    logger.info("stopped")
```

## 运行时

应用侧仍然使用运行时设施加载和管理插件：

```python
runtime.load_all()
await runtime.load_registered()
await runtime.start_all()
await runtime.stop_all()
await runtime.reload_plugin("ping")
```

重载插件时，运行时会停止旧插件、清理已跟踪的订阅、Host 注册和 Agent 注册，清除模块缓存，然后重新导入插件并按需启动。

## 公开 API

`neobot_modloader` 顶层只导出新的插件开发 API 和运行时基础设施：

```python
from neobot_modloader import (
    AgentRequest,
    Bot,
    DefaultPluginManager,
    DiscoveredPlugin,
    FilesystemPluginLoader,
    ImageSegment,
    Message,
    MessageChain,
    MessageSegment,
    Plugin,
    PluginHookBus,
    PluginHostFacade,
    PluginRuntime,
    PythonDependencyInstaller,
    Reply,
    image,
    text,
)
```

## 破坏性迁移

已移除的旧 API：

- `setup(ctx)`
- 对象式旧 `plugin`
- `create_plugin()`
- `ctx.on.*`
- `on_command()` / `Matcher`
- `PluginMetadata`
- `get_plugin_config()`
- `CommandArg` 等旧 DI sentinel
- 旧兼容层模块

旧写法：

```python
def setup(ctx):
    @ctx.on.message(contains="ping")
    async def ping(event):
        await ctx.reply(event, "pong")
```

新写法：

```python
from neobot_modloader import Plugin, Reply

plugin = Plugin("ping")


@plugin.message(contains="ping")
async def ping(reply: Reply):
    await reply.send("pong")
```

旧写法：

```python
ping = on_command("ping")


@ping.handle()
async def ping_handler(args: CommandArg):
    await ping.finish(f"pong: {args}")
```

新写法：

```python
from neobot_modloader import Plugin, Reply

plugin = Plugin("ping")


@plugin.command("ping [args:rest]")
async def ping(args: str | None, reply: Reply):
    await reply.send(f"pong: {args or ''}")
```

旧写法：

```python
segments = event.get("message", [])
await ctx.reply(event, segments)
```

新写法：

```python
from neobot_modloader import Message, Plugin, Reply

plugin = Plugin("echo")


@plugin.message()
async def echo(message: Message, reply: Reply):
    await reply.send(message)
```
