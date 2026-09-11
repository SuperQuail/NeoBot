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

插件可通过 `Plugin(command_prefix="#")` 为全部命令设置固定前缀。若插件配置模型包含
`command_prefix` 字段，加载时经过校验的配置值会自动覆盖该默认值：

```python
class Config(BaseModel):
    command_prefix: str = "/"


plugin = Plugin("ping", config=Config)
```

单个命令仍可用 `@plugin.command("ping", prefix="!")` 覆盖插件全局前缀。
空字符串表示无前缀；前缀不能包含空白字符。

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

## 正则模式

`@plugin.regex(pattern, ...)` 对消息纯文本（`message.text`，text 段拼接）做正则 `search`，
把命名分组 `(?P<名字>...)` 按名注入处理器参数。适合实现无斜杠的中文指令：

```python
from neobot_modloader import Plugin, Reply

plugin = Plugin("weather")


@plugin.regex(r"^天气 (?P<city>\S+)")
async def weather(city: str | None, reply: Reply):
    await reply.send(f"{city} 今天晴，22-28 度。")
```

用户发送「天气 上海」即可触发，`city` 参数会得到 `"上海"`。命名分组注入到同名参数，
可选分组未命中时为 `None`；`reply`、`config`、`logger` 等 DI 参数照常可用，
命名分组名不能与 DI 参数名冲突。与 `@plugin.message(...)` 一样是消息级注册
（不是 slash 命令，无前缀概念），其余参数（`group` / `private` / `priority` /
`block` / `parse_error` 等）行为一致。

## 用户资料

`ctx.users`（`UserDirectory`）统一查询用户与群成员资料，屏蔽 OneBot 适配器的字段差异。
当前发言人直接用 `from_event`（零 API 请求），查其他用户用 `get`，
排行榜这类批量查询用 `get_many`：

```python
from neobot_modloader import Plugin, Reply, UserProfile

plugin = Plugin("coin")


@plugin.message("金币")
async def balance(event, ctx, reply: Reply):
    sender = ctx.users.from_event(event)          # 当前发言人：直接读事件，零 API 请求
    await reply.send(f"{sender.display_name} 当前拥有 100 金币")


@plugin.message("排行榜")
async def leaderboard(message, ctx, reply: Reply):
    user_ids = ["111", "222", "333"]
    profiles = await ctx.users.get_many(user_ids, group_id=message.raw_event.get("group_id"))
    await reply.send("\n".join(p.display_name for p in profiles.values()))
```

`UserProfile` 是不可变（frozen）dataclass，常用字段：

- `user_id: str`
- `nickname: str | None`、`avatar_url: str | None`、`group_id: str | None`
- `card: str | None`（群名片）、`role: str | None`（owner / admin / member）、
  `title: str | None`（群头衔）
- `raw: Mapping`：只读原始数据逃生口，业务代码不应依赖
- `display_name` 属性 = `card or nickname or user_id`

方法一览：

- `await ctx.users.get(user_id, *, group_id=None, refresh=False) -> UserProfile`
- `ctx.users.from_event(event) -> UserProfile`（同步，读事件 sender，零请求）
- `await ctx.users.display_name(user_id, *, group_id=None, refresh=False) -> str`
- `await ctx.users.get_many(user_ids, *, group_id=None) -> dict[str, UserProfile]`
  （自动去重；带 `group_id` 时批量拉取一次群成员列表，避免 N+1 查询）

查询规则：带 `group_id` 时先查群成员资料、优先群名片 `card`；失败回退全局用户昵称；
全部失败返回只有 `user_id` 的占位资料，不让昵称查询拖垮指令。
结果缓存：成功 5 分钟、失败 30 秒，`refresh=True` 可强制刷新。

`users` 也可以作为 DI 参数注入（`async def h(users: UserDirectory, reply: Reply)`，
与 `config`、`logger` 等用法一致），但 `ctx.users` 是主入口。

> 注意：`profile.role == "admin"` 只是 QQ 群管理员，并不等同于 NeoBot 的全局管理员，
> 插件不要拿它做权限判断（权限体系另行设计）。

不建议直接调用 `ctx.adapter.get_group_member_info(...)` 等原始 API：返回字段绑定 OneBot
实现、各适配器字段不一致，且回退规则、缓存与批量查询无法统一；用 `ctx.users` 即可。

## 独立数据库

插件可以声明自己的 SQLite 数据库（SQLAlchemy Async + aiosqlite），数据文件按插件隔离。宿主负责数据库的初始化、迁移、关闭与路径校验，插件只关心模型定义和查询。

数据库在插件模块加载时声明，随插件加载初始化、随卸载关闭；卸载不会删除数据文件。

```python
from neobot_modloader import Migration, Plugin

from .models import Base
from .migrations import create_initial_schema, add_user_index

plugin = Plugin("example", version="1.0.0", description="数据库示例插件")

database = plugin.sqlite_database(
    "main",
    filename="example.db",
    metadata=Base.metadata,
    migrations=[
        Migration(version=1, name="initial-schema", upgrade=create_initial_schema),
        Migration(version=2, name="add-user-index", upgrade=add_user_index),
    ],
)
```

- `Migration(version, name, upgrade)`：`version` 必须为正整数且同一数据库内不能重复；迁移按 `version` 升序执行；首版没有 downgrade
- `plugin.sqlite_database(name="main", *, filename=None, metadata=None, migrations=(), pragmas=None) -> PluginDatabase`：同一插件内 `name` 不能重复；`filename` 缺省为 `<name>.sqlite3`；`metadata=` 传入 SQLAlchemy `DeclarativeBase.metadata` 用于建表

### 使用

写操作放进事务，成功自动 commit，异常自动 rollback：

```python
async with database.transaction() as session:
    session.add(ExampleUser(name=name))
```

只读查询用普通会话，不自动提交：

```python
async with database.session() as session:
    users = list(await session.scalars(select(ExampleUser).order_by(ExampleUser.id)))
```

`PluginDatabase` 的属性与方法：`name` / `path` / `url` / `engine`；`session()`（AsyncSession，不自动提交）、`transaction()`（commit/rollback）、`migrate()`、`close()`（幂等，可重试）。

### 迁移

迁移函数签名：

```python
async def upgrade(connection):
    ...
```

每个迁移在独立事务中执行，失败自动回滚并阻止插件启动（插件进入 ERROR）。迁移声明后不会重复执行：已执行的迁移记录在 `_neobot_plugin_migrations` 表中，并做 checksum 校验，修改已执行迁移的代码会报 `PluginMigrationConflictError`。

### 存储路径与路径安全

数据文件位于 `<插件数据目录>/databases/<filename>`，例如插件 `example` 的数据文件在 `data/plugins_data/example/databases/example.db`（数据根目录由部署配置决定）。

路径安全规则：禁止绝对路径、`..`、盘符、UNC 与 symlink 逃逸；文件必须位于本插件自己的 databases 目录内；`filename` 只能是文件名，不能包含目录分隔符；不允许指向 `neobot.db`。

### 强制 PRAGMA

每连接强制设置以下 PRAGMA，插件无法覆盖：`journal_mode=WAL`、`foreign_keys=ON`、`busy_timeout=5000`、`synchronous=NORMAL`。`pragmas=` 参数可追加其他 PRAGMA。

### 生命周期与错误

数据库在 `on_load` 之前初始化，migration 全部完成后才绑定命令/Tool/Agent；初始化失败插件进入 ERROR。停止时在 `on_shutdown` 之后关闭数据库，关闭失败记录进插件错误状态；热重载不会重复迁移；卸载不删除数据文件。

错误类型：

- `PluginDatabaseError`：数据库通用错误
- `PluginDatabaseNotReadyError`：数据库尚未绑定完成就查询
- `PluginDatabaseClosedError`：数据库已关闭后使用
- `PluginMigrationError`：迁移执行失败
- `PluginMigrationConflictError`：已执行迁移的 checksum 冲突

完整的声明、迁移与使用示例见 `example_plugins/database_example/`（插件名 `example`，包含 models / migrations / plugin.toml，`plugin.toml` 中声明 `python_dependencies = ["sqlalchemy>=2.0", "aiosqlite>=0.20.0"]`）。

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

包插件可以使用 `plugin.toml` 声明默认配置、优先级与依赖：

```toml
enabled = true                # 打包默认的启用状态（真正的启停记录在 plugin_state.json）
priority = 10
dependencies = []
python_dependencies = ["httpx"]

[config]                      # 打包默认配置（安装/更新会被覆盖）
api_key = "secret"
default_city = "Shanghai"
```

运行期配置不写在这里，而是插件数据目录的 `plugins_data/<插件名>/config.toml`：
读取时以 `[config]` 的打包默认值打底、插件数据目录里已保存的值覆盖，
插件收到的 `ctx.config` 就是合并后的结果，插件更新不会覆盖用户配置。

**是否启用不是配置项**：启停状态保存在数据目录的 `plugin_state.json`
（`PluginStateStore`），与 `plugin.toml` 的顶层 `enabled` 默认值解耦：

```json
{"version": 1, "plugins": {"weather": {"enabled": false}}}
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

子 Agent 默认不直接发消息，而是把结果返回给主 Agent。

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
`plugin_dir: Path`、`host`、`plugins`、`plugin_control`、`users: UserDirectory`。

约定名注入遵循「类型注解优先」：参数带注解时按类型匹配 DI（例如 `ctx: str` 是模型参数，
不会被注入上下文）。唯一例外是 `event`——它注入的是原始事件字典，没有对应的运行时类型，
因此 `event`、`event: dict`、`event: dict[str, Any]`、`event: Mapping[str, Any]`
都会被注入当前事件：

```python
@plugin.message(priority=-100)
async def count_message(event: dict[str, Any]) -> None:
    print(event["user_id"])
```

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

## 插件依赖

插件可以在 `plugin.toml` 或 `Plugin(...)` 里声明前置插件，声明支持版本约束：

```toml
# plugin.toml
name = "starship"
version = "1.0.0"
dependencies = ["dashboard>=1.0.0"]
priority = -1
```

```python
plugin = Plugin(
    "starship",
    version="1.0.0",
    # 支持 >= <= == != > < ~= ，逗号分隔表示「与」
    dependencies=("dashboard>=1.0.0",),
)
```

### 加载顺序与自动禁用

- **拓扑排序**：有前置插件的插件一定在前置插件之后加载（同级按 `priority` 降序）；
- **自动禁用**：前置插件缺失、版本不满足、被停用或依赖成环时，该插件会被
  **自动禁用**，程序照常启动、其他插件不受影响；
- **自动恢复**：前置插件被重新启用 / 恢复运行后，运行时会自动把它拉起来；
- **反向联动**：停用 / 卸载 / 重载前置插件时，依赖它的插件会被联动停用，
  前置插件恢复后自动重新加载。

自动禁用的原因会在面板「插件」页展示（`disabled_reason` / `dependency_issues` /
`dependents`），日志里也有对应告警：

```text
插件依赖未满足，已自动禁用 (starship): 前置插件不可用: dashboard>=1.0.0（插件已停用）
```

版本号只比较数字段（`1.0.0-alpha.1` 按 `1.0.0` 处理）；无法比较时按「满足」处理
并记录告警，不会因为版本号写法把插件拦死。

### 调用前置插件的功能

前置插件用 `@plugin.capability(...)` 暴露能力，依赖方用
`ctx.require_plugin(...).call(...)` 调用：

```python
# 前置插件：dashboard
@plugin.capability("web.register_extension")
async def _register_extension(payload):
    return server.register_extension(payload["name"], payload["extension"])


# 依赖方：starship
@plugin.on_load
async def _load(ctx):
    handle = ctx.require_plugin("dashboard", ">=1.0.0")   # 未就绪/版本不符会抛 PluginDependencyError
    prefix = await handle.call(
        "web.register_extension",
        {"name": "starship", "extension": extension},
    )
    ctx.logger.info(f"已挂载到面板: {prefix}/")
```

- `ctx.require_plugin(name, specifier="")`：前置插件不存在 / 未就绪 / 版本不满足时抛
  `PluginDependencyError`，错误文本可直接展示；
- `ctx.plugins.get(name)` / `optional(name)`：拿句柄但不抛异常的宽松版本；
- `ctx.plugins.dependents_of(name)` / `dependency_issues(name)`：反向依赖与依赖体检；
- `PluginHandle.call(capability, payload)`：调用能力，同步/异步处理器都支持；
- `PluginControlFacade.dependencies(name)`：面板侧的依赖报告
  （声明、未满足项、反向依赖、自动禁用原因）。

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
    Migration,
    Plugin,
    PluginControlFacade,
    PluginDatabase,
    PluginDatabaseClosedError,
    PluginDatabaseError,
    PluginDatabaseNotReadyError,
    PluginHookBus,
    PluginHostFacade,
    PluginMigrationConflictError,
    PluginMigrationError,
    PluginOperationResult,
    PluginRuntime,
    PluginSnapshot,
    PythonDependencyInstaller,
    Reply,
    RuntimePluginContext,
    UserDirectory,
    UserProfile,
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
- `get_plugin_config()`（配置改为 `ctx.config` + 插件数据目录 `config.toml`）
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
