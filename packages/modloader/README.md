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
message.ats
message.first_at
message.has_at
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

`at` 段同样可以捕获注入：

```python
from neobot_modloader import AtSegment, MessageChain, Plugin, Reply

plugin = Plugin("callout")


@plugin.command("点名 <user:at>")
async def callout(user: AtSegment, reply: Reply):
    await reply.send(MessageChain().text("请 ").at("123456"))
```

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
| `<name:at>` | 一个 @ 段 |
| `[name:at]` | 可选 @ 段 |
| `<names:list[at]>` | 一个或多个 @ 段 |

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

```python
await reply.send(
    MessageChain()
    .text("请 ")
    .at("123456")
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

主 Agent 通过 `agents__list` / `agents__delegate` 工具发现并委托插件子 Agent。

## 注册 Tool

插件可以声明可被主 Agent 直接调用的工具。处理器参数来自模型传入的 JSON 参数，
参数 schema 由函数签名自动生成（也可用 `parameters=` 显式覆盖）。

```python
from neobot_modloader import Plugin

plugin = Plugin("weather")


@plugin.tool("query", description="查询指定城市天气")
async def query(city: str, days: int = 1) -> str:
    return f"{city} 未来 {days} 天晴，22-28 度。"
```

全局工具名为 `{plugin_name}__{tool_name}`，例如 `weather__query`。

支持的类型注解：`str` / `int` / `float` / `bool` / `list[...]` / `dict` / Pydantic `BaseModel`。
带默认值的参数可选，无默认值的参数进入 `required`。

处理器同样支持 DI 注入，以下参数不会暴露给模型：

```python
@plugin.tool("save", description="保存笔记")
async def save(text: str, config: Config, ctx, logger) -> str:
    ...
```

支持：`config: Config`（插件配置）、`ctx` / `context`、`logger`、`data_dir: Path`、
`plugin_dir: Path`、`host`、`plugins`、`plugin_control`。

> 注：`Reply` 仅建议在命令/消息处理器中注入（此时携带当前事件上下文）。
> 工具处理器中的 `reply` 参数没有可用的回复事件，行为不可依赖；
> 工具如需发送消息，请使用自身能力或其他处理器完成。

## Markdown 技能（SKILL.md）

插件目录下的 `skills/**/SKILL.md` 会被自动发现并注册为 Markdown 技能：

```text
plugins/
  weather/
    __init__.py
    plugin.toml
    skills/
      weather-guide/
        SKILL.md
        references/
          cities.md
```

`SKILL.md` 使用 frontmatter 声明元数据：

```markdown
---
name: weather-guide
description: 查询天气及提供出行建议
keywords: 天气 气温 下雨 出行
allowed-tools: weather__query weather__alert
---

处理天气问题时：

1. 先调用 weather__query 查询天气。
2. 根据降雨概率提供携带雨具建议。
3. 不确定城市时先询问用户。
```

技能全局名为 `{plugin_name}:{local_name}`（例如 `weather:weather-guide`）。

### allowed-tools：技能激活时的工具白名单

`allowed-tools` 字段声明技能激活时允许主 Agent 使用的工具白名单。支持三种写法：
空格分隔字符串（如上面的示例）、逗号分隔字符串、或 YAML 列表（例如
`allowed-tools: [weather__query, weather__alert]`）。值按空白/逗号切分后去空去重；
空字符串/空列表等价于未声明。

限制的生效规则：

- **仅当本轮所有命中技能都声明了非空 `allowed-tools` 时限制才生效**，
  生效时限制集为各命中技能声明集的**并集**；
- 任一命中技能未声明（或声明为空）则不限制，避免未声明技能的工具被其他技能的声明误伤；
- 存在**不可被限制的基础白名单**：基础回复工具（cancel / split_reply / send_reply /
  send_emoji / send_long_reply / wait / speak）+ 技能读取工具
  （skills__read_manifest / skills__read_resource）+ 代理工具
  （agents__list / agents__delegate）+ 后台任务工具
  （check_background_tasks / cancel_task / check_last_drawing /
  mark_scheduled_task_complete）。技能作者无需、也无法把基础设施写进白名单。

### 读取授权边界

`skills__read_manifest` / `skills__read_resource` 可读取**任意已注册技能**的正文与
技能目录内资源，不限于本轮注入提示词的 3 个技能（技能 id 由主 Agent 自选）。
`skills__read_resource` 的路径严格限制在目标技能目录内：禁止绝对路径、
`..` 越界以及 symlink/junction 组件逃逸，单文件大小上限 1MB。

### data/skills：应用级技能

非插件自带的应用级 SKILL.md 放在 `data/skills` 目录（结构同插件侧：
`data/skills/<技能名>/SKILL.md`），启动时由主应用自动发现注册。要求与插件技能一致：
`name` 必须与目录名一致且为 kebab-case、`description` 必填。

主聊天在 Agent 模式下会按最新用户消息匹配关键词，把最多 3 个相关技能
以 `<可用技能>` 元数据注入提示词。模型通过 `skills__read_manifest` 读取技能正文，
通过 `skills__read_resource` 读取技能目录内的参考资料（相对路径，禁止越界）。

技能仅作为文档注入，不会自动执行脚本；文件读取限制在技能目录内。

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

## 插件管理 API

Dashboard 或其他管理型插件可以通过生命周期注入拿到受控管理门面：

```python
from neobot_modloader import Plugin, RuntimePluginContext

plugin = Plugin("manager")


@plugin.on_load
async def load(ctx: RuntimePluginContext):
    snapshots = ctx.plugin_control.snapshot()
```

`PluginControlFacade` 只暴露运行期管理能力，不暴露完整 `PluginRuntime`：

```python
await ctx.plugin_control.load_path(path, start=True)
await ctx.plugin_control.unload("ping")
await ctx.plugin_control.reload("ping")
await ctx.plugin_control.start("ping")
await ctx.plugin_control.stop("ping")
ctx.plugin_control.snapshot()
```

这些方法返回 `PluginOperationResult` 或 `PluginSnapshot`，用于展示结构化状态和错误，不需要访问 runtime/loader/manager 的私有成员。

## 公开 API

`neobot_modloader` 顶层只导出新的插件开发 API 和运行时基础设施：

```python
from neobot_modloader import (
    AgentRequest,
    AtSegment,
    Bot,
    DefaultPluginManager,
    DiscoveredPlugin,
    FilesystemPluginLoader,
    ImageSegment,
    Message,
    MessageChain,
    MessageSegment,
    Plugin,
    PluginControlFacade,
    PluginHookBus,
    PluginHostFacade,
    PluginOperationResult,
    PluginRuntime,
    PluginSnapshot,
    PythonDependencyInstaller,
    Reply,
    RuntimePluginContext,
    at,
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
