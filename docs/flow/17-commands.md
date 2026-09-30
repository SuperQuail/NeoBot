---
flow: 17-commands
covers:
  - app/src/neobot_app/commands/
verified_against: 99836cd
verified_hash: cc3d84d9a43d
---

# 17 命令系统：注册 / 解析 / 权限 / 内置命令

## 范围

一条消息被判定成「命令」之后的全部流程：注册表匹配、别名与重名去重、权限判定、
执行（本体命令 / 插件命令 / 面板命令）、`consumed` 语义与 `sync_reply` 分叉。
不在这里：命令的**触发时机**（去重、@ 前置、待机跳过）见 `02c-event-pipeline.md`；
卡片渲染见 `13-render-cards.md`；插件命令的注册来源见 `08-plugins.md`。

## 流程

```mermaid
flowchart TD
    A["event_pipeline: command_service.handle_message(event)"] --> B{"消息文本可解析成命令?"}
    B -- 否 --> B1["返回未命中，继续走意愿判定"]
    B -- 是 --> C["registry 查找命令（含别名）"]
    C --> D{"命中?"}
    D -- 否 --> D1["未命中（可能走 AI 兜底）"]
    D -- 是 --> E["permissions 判定执行者级别"]
    E --> F{"有权限?"}
    F -- 否 --> F1["回固定文案（**仍标记 consumed**）"]
    F -- 是 --> G{"命令类型"}
    G -- 内置 --> H["builtin.py 的 handler"]
    G -- 插件 --> I["插件注册的 handler"]
    G -- 面板 --> J["面板命令 handler"]
    H --> K["handler 返回值"]
    I --> K
    J --> K
    K --> L{"返回 None?"}
    L -- 是 --> L1["表示已自行发图/回复，不再补文本"]
    L -- 否 --> M["sync_reply 立即回复文本"]
    F1 --> N["consumed = True"]
    L1 --> N
    M --> N
    N --> O["事件管道据此跳过后续意愿判定"]
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant EP as EventPipeline
    participant CS as CommandService
    participant RG as CommandRegistry
    participant PM as 权限判定
    participant HD as handler

    EP->>CS: handle_message(event)
    CS->>RG: 解析 + 查找（含别名）
    alt 未命中
        RG-->>CS: None
        CS-->>EP: 未命中（AI 可兜底）
    else 命中
        CS->>PM: 判定执行者级别
        alt 权限不足
            PM-->>CS: 拒绝
            CS-->>EP: 固定文案 + consumed
        else 通过
            CS->>HD: 执行（含参数）
            HD-->>CS: 文本 / 卡片 / None
            CS-->>EP: consumed（并可能 sync_reply）
        end
    end
```

## 细节

<details>
### 注册表：名称、别名与来源前缀

```mermaid
flowchart TD
    A["插件/本体启动时注册"] --> B["registry.register(name, aliases, usage, handler, source)"]
    B --> C{"名称已被占用?"}
    C -- 否 --> D["登记原名"]
    C -- 是 --> E["按来源加前缀（本体 / 插件名）"]
    E --> F["实际生效名 = 去重后的名字"]
    D --> G["激活/停用时增删登记"]
    F --> G
```

重名去重的产物是**实际生效名**：插件与本体命令同名时，插件侧会带上来源前缀（spec(4) R26），
面板会展示「原 X → 实际 Y」。排查「命令名对但没反应」时先确认实际生效名。
命令在插件**激活/停用**时会动态增删（`08-plugins.md`），所以「命令消失」多半是插件没加载。
</details>

<details>
### 解析：@ 触发与 / 前缀的差异

```mermaid
flowchart TD
    A["收到消息"] --> B{"群聊?"}
    B -- 是 --> C{"@ 了 bot?"}
    C -- 否 --> C1["命令不被消费（直接走意愿判定）"]
    C -- 是 --> D["剥离 @ 段后取正文"]
    B -- 否 --> D
    D --> E{"以 / 开头?"}
    E -- 否 --> F["按普通消息处理"]
    E -- 是 --> G["切出命令名与参数"]
    G --> H["查注册表（含别名）"]
```

**群聊里命令必须先 @bot**（`commands/service.py` 约 `:158`）：这是与私聊最大的行为差异。
私聊则直接识别 `/` 前缀。命令名与参数的分割在解析阶段完成，参数原样交给 handler。
</details>

<details>
### 权限判定与 consumed 语义

```mermaid
flowchart TD
    A["命中命令"] --> B["permissions 取执行者级别"]
    B --> C{"级别满足?"}
    C -- 是 --> D["执行"]
    C -- 否 --> E["回固定文案"]
    D --> F["consumed = True"]
    E --> F
    F --> G["事件管道跳过后续 AI 回复"]
    H["handler 内部抛异常"] --> I["回错误文本（仍 consumed）"]
```

两条容易误判的行为：

1. **权限被拒也 `consumed=True`**：发错命令时 AI **不会**兜底解释，用户只会收到固定拒绝文案；
2. **handler 抛异常也算已消费**（`commands/service.py` 约 `:197-199`）——
   异常被转成一条错误文本回给用户，同样不再走 AI。

这是刻意的：命令一旦被识别，就不该再让模型自由发挥（否则 `/help` 可能被解释成闲聊）。
</details>

<details>
### sync_reply 与「返回 None 表示我自己发了」

```mermaid
flowchart TD
    A["handler 返回"] --> B{"是 None?"}
    B -- 是 --> B1["约定：命令已自行发图/发消息"]
    B -- 否 --> C["走 sync_reply 立即回复文本"]
    B1 --> D["不再补文本"]
    C --> E{"群聊?"}
    E -- 是 --> F["用回复管线（携带命令上下文）"]
    E -- 否 --> G["同样走回复管线"]
    F --> H["被拒时**不**丢弃回复中标记"]
    G --> H
```

`返回 None` 是**命令与管线之间的契约**：`/mg`、`/help` 这类自带卡片渲染的命令用它表示
「图我自己发了」。事件管道里对应的分支是 `_start_command_sync_reply`，
注释明确写了「被拒（None）时**不** discard 回复中标记」—— 丢掉标记会把同会话另一条
正在跑的管线一起解锁（见 `02c-event-pipeline.md` 的同类坑）。
</details>

<details>
### 内置命令总表

```mermaid
flowchart LR
    A["/help"] --> A1["自包含卡片 + 30 条/页翻页（13）"]
    B["/sleep  /awake"] --> B1["睡眠状态机（16）"]
    C["/standby  /reboot"] --> C1["待机与软重启（01）"]
    D["/status"] --> D1["控制台看板图（次级管理员）"]
    E["/mg …"] --> E1["小游戏插件命令（11）"]
    F["其它内置"] --> F1["见 commands/builtin.py 注册表"]
```

内置命令的完整清单以 `commands/builtin.py` 的注册代码为准（本图不复制全表，避免漂移）。
注意 `/status` 出自面板插件（spec(4)）而不是本体 —— 排查「命令不见了」要同时看
本体注册表与插件注册表。
</details>

<details>
### 面板与命令的两条入口

```mermaid
flowchart TD
    A["面板 HTTP 端点"] --> B["dashboard/api.py 直接调服务"]
    C["QQ 命令"] --> D["CommandService -> handler"]
    D --> E["与面板调的是同一批服务对象"]
    B --> E
```

同一动作（如待机、重载插件）在面板与命令里走的是**同一个服务对象**，但：
面板路径受 `_require_manage` 与 loopback 限制（见 `09b`），命令路径受权限树限制。
两条路的错误文案与副作用范围不同 —— 排查「面板能点但命令不行」时按这条线查。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| 命令注册项 | 本体/插件注册 | 插件停用时移除 | 名字冲突时改为带来源前缀的实际名 |
| `consumed` 标记 | 命令命中（含权限拒绝、handler 异常） | 每条事件独立 | 已消费即不再走 AI 兜底 |
| 执行者级别 | 每次判定时现取 | 不缓存 | 级别不足回固定文案，不进 AI |
| 回复中标记 | `sync_reply` 成功启动管线 | `on_reply_done` | 管线被拒时**不**丢弃（否则会解锁别的管线） |

## 易错点

* **群聊命令必须先 @bot**：不 @ 的命令会被当普通消息，直接进意愿判定。
* **权限拒绝也消费命令**：用户看到的是固定文案，AI 不会补救 —— 这是设计不是 bug。
* **`返回 None` 有特殊含义**：写成 `return`（隐式 None）会让命令静默不回复。
* **重名命令的实际名字可能带前缀**：面板会显示映射关系，别按注册名断言。
* **插件停用会连带命令消失**：命令与插件生命周期绑定，不是永久注册。
* **`sync_reply` 被拒时不要丢标记**：这是 `02c` 里同一类坑的命令侧版本。
