---
flow: 02b-willing-probability
covers:
  - app/src/neobot_app/willing/
  - app/src/neobot_app/runtime/event_pipeline.py
verified_against: 99836cd
verified_hash: 3052a05cbd82
---

# 02b 回复意愿：概率到底怎么算出来的（逐步精确）

## 范围

`WillingService.evaluate` 组装 `WillingContext`，`QuailWillingManager.evaluate` 出
`WillingDecision(probability, should_reply, reasons)` 的**完整算术**，以及事件管道在调用前后
做了什么（睡眠拦截、屏蔽优先、@ 必回的等待与关键词短路、回复中队列、回复后积压处理）。
配置项默认值以 `config/schemas/bot.py` 当前实现为准；本图逐字对齐
`willing/builtin.py:15` 的求值顺序。

## 流程

```mermaid
flowchart TD
    A["event_pipeline._handle_willing_decision"] --> B{"睡眠中?"}
    B -- 是 --> B1["_handle_sleeping_message<br/>仅被@可唤醒, 屏蔽优先于唤醒"]
    B -- 否 --> C{"is_at_mentioned（配置 at_mention_guaranteed_reply）"}
    C -- 是 --> C1["block_reason_for_message 先判屏蔽"]
    C1 --> C2{"被屏蔽?"}
    C2 -- 是 --> C3["不回复: 屏蔽优先于@"]
    C2 -- 否 --> C4["等 at_mention_reply_delay_seconds（默认 5.0s）"]
    C4 --> C5{"命中 _at_mention_instant_keyword?"}
    C5 -- 是 --> C6["跳过等待, 立即回复"]
    C5 -- 否 --> C7["等待结束"]
    C6 --> D["WillingDecision(manager=Quail, probability=1.0)"]
    C7 --> D
    C -- 否 --> E["willing_service.evaluate(message, queue, queue_key)"]
    E --> F["QuailWillingManager.evaluate"]
    F --> G["is_allowed? 否则 0.0"]
    G --> H["运行时黑名单? 否则 0.0"]
    H --> I{"私聊?"}
    I -- 是 --> I1["1.0 直接回复（不受任何系数影响）"]
    I -- 否 --> J["@必回? 是则 1.0"]
    J -- 否 --> K["基础 0.5 +（问句 +0.15）"]
    K --> L["依次乘 8 个系数（见细节）"]
    L --> M["clamp 到 0..1"]
    M --> N["random.random() < probability ?"]
    N -- 是 --> O["should_reply=True -> _start_reply_with_tracking"]
    N -- 否 --> P["静默丢弃（记 reasons 供排查）"]
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant EP as EventPipeline
    participant WS as WillingService
    participant QM as QuailWillingManager
    participant OR as ReplyOrchestrator

    EP->>EP: 睡眠/屏蔽/@ 判定
    EP->>WS: evaluate(message, queue, queue_key)
    WS->>WS: _build_context 采齐 20+ 个字段
    WS->>QM: manager.evaluate(context)
    QM->>QM: 三段短路 -> 加法加成 -> 8 次乘法 -> clamp
    QM-->>WS: WillingDecision(probability, should_reply, reasons)
    WS-->>EP: 同上
    alt should_reply
        EP->>OR: start_reply(...)
    else 不回复
        EP->>EP: 丢弃（注意：不写任何状态）
    end
```

## 细节

<details>
### 三段短路：返回 0.0 / 1.0 的六种情况

```mermaid
flowchart TD
    A["evaluate(context)"] --> B{"context.is_allowed?"}
    B -- 否 --> B1["probability=0.0, should_reply=False<br/>reasons: blocked: &lt;block_reason&gt;"]
    B -- 是 --> C{"conversation_id 在运行时黑名单?"}
    C -- 是 --> C1["0.0 / False<br/>reasons: runtime_blacklist: blocked"]
    C -- 否 --> D{"is_direct_message?"}
    D -- 是 --> D1["1.0 / True<br/>reasons: private_chat_guaranteed"]
    D -- 否 --> E{"at_guaranteed_reply 且 mentioned_bot?"}
    E -- 是 --> E1["1.0 / True<br/>reasons: at_guaranteed_reply: mentioned_bot"]
    E -- 否 --> F["进入算术段（下一个小节）"]
```

`is_allowed` 由 `service.py:350 _is_conversation_allowed` 算出，取值来源：
群聊 `message.enable_group=False` -> `group_disabled`；否则
`chat.group_use_black_list` + `chat.group_list` -> `group_blacklisted` / `group_not_in_whitelist`。
私聊同理（`enable_private` / `friend_list`）。
**列表为空时一律放行**（`_check_list_rule` 第一行就 return True）。
</details>

<details>
### 算术段：加一次、乘八次，顺序不能换

```mermaid
flowchart TD
    A["probability = 0.5（硬编码起点）"] --> B{"has_question? 文本含 ? 或 ？"}
    B -- 是 --> B1["probability += 0.15"]
    B -- 否 --> C["不变"]
    B1 --> C
    C --> D["× config_global_coefficient<br/>agent 模式用 willing_agent_global_coefficient<br/>common 模式用 willing_global_coefficient"]
    D --> E["× conversation_coefficient<br/>群聊 chat.group_response_coefficient[群号], 缺省 1.0；私聊恒 1.0"]
    E --> F["× runtime.global_coefficient<br/>（AI 工具改的运行时系数, 默认 1.0）"]
    F --> G["× runtime.conversation_coefficients[conversation_id]（默认 1.0）"]
    G --> H["× runtime.user_global_coefficients[sender_id]（默认 1.0）"]
    H --> I["× runtime.conversation_user_coefficients[会话][用户]（默认 1.0）"]
    I --> J{"is_official_bot?"}
    J -- 是 --> J1["× official_bot_coefficient<br/>chat.official_bot_reply_coefficient 默认 0.05"]
    J -- 否 --> K["不变"]
    J1 --> L["× base_probability<br/>chat.group_chat_chance（_base_probability 读它）"]
    K --> L
    L --> M["clamp_probability: max(0, min(1, p))"]
    M --> N["should_reply = random.random() < p"]
```

**乘法顺序不影响数值**（都是乘法），但**起点是 0.5 且没有单独的基础概率加法**：
`chat.group_chat_chance` 是被当作**乘法系数**乘进去的，不是「基础概率」。
这个命名容易误导：它是最终乘数之一，默认值直接决定量级。
</details>

<details>
### 每个系数的来源与默认值

```mermaid
flowchart LR
    subgraph 配置层
      A1["chat.willing_global_coefficient"]
      A2["chat.willing_agent_global_coefficient"]
      A3["chat.group_response_coefficient: {群号: 系数}"]
      A4["chat.group_chat_chance"]
      A5["chat.official_bot_reply_coefficient 默认 0.05"]
      A6["chat.at_mention_guaranteed_reply 默认 True"]
      A7["chat.group_use_black_list / group_list<br/>friend_use_black_list / friend_list"]
    end
    subgraph 运行时层
      B1["runtime.global_coefficient"]
      B2["runtime.conversation_coefficients"]
      B3["runtime.user_global_coefficients"]
      B4["runtime.conversation_user_coefficients"]
      B5["runtime.blacklisted_conversations"]
    end
    subgraph 观测层
      C1["observe_window 决定 observed_messages_text 条数"]
      C2["matched_keywords 来自 chat.key_word 规则"]
      C3["called_bot_name / replied_to_message / queue_size / queue_text"]
    end
```

运行时层由 AI 工具/面板调用 setter 修改（`service.py:92-172`）：
`set_runtime_global_coefficient`、`set_runtime_conversation_coefficient`、
`set_runtime_user_global_coefficient`、`set_runtime_conversation_user_coefficient`、
`add_runtime_blacklist` 等，全部 `clamp_probability` 到 0..1 且**不落盘**（重启即回默认）。
`get_runtime_config_summary`（`:174`）是给模型看的当前值摘要。
</details>

<details>
### 算一遍：三种典型输入

```mermaid
flowchart TD
    subgraph 例1["例1｜群里普通一句（无问号）"]
      P1["0.5"] --> P2["×1.0 全局 ×1.0 会话"] --> P3["×1.0 运行时四项"] --> P4["×group_chat_chance"]
    end
    subgraph 例2["例2｜群里问句"]
      Q1["0.5 + 0.15 = 0.65"] --> Q2["×group_chat_chance"]
    end
    subgraph 例3["例3｜官方 Bot 发言的问句"]
      R1["0.5 + 0.15 = 0.65"] --> R2["×0.05 官方 Bot 系数"] --> R3["×group_chat_chance"]
    end
```

以 `group_chat_chance = 0.5` 为例（实际值看当前配置）：

| 输入 | 计算 | 最终概率 |
|---|---|---|
| 群聊普通句 | 0.5 × 0.5 | 0.25 |
| 群聊问句 | (0.5+0.15) × 0.5 | 0.325 |
| 官方 Bot 问句 | (0.5+0.15) × 0.05 × 0.5 | 0.01625 |
| 群里 @ 了 bot | 短路 | 1.0 |
| 私聊任意消息 | 短路 | 1.0 |
| 会话在临时黑名单 | 短路 | 0.0 |

`reasons` 会把这些步骤逐条记下来（`起始概率=0.500`、`问句加成=+0.150`、`加成后=0.650`、
`全局系数=…`、`最终概率=…`），排查「为什么这条没回」时先看它。
</details>

<details>
### 事件管道侧的加减项（不属于概率）

```mermaid
flowchart TD
    A["_handle_willing_decision 入口"] --> B{"睡眠服务在睡眠?"}
    B -- 是 --> C["_handle_sleeping_message"]
    C --> D{"被@?"}
    D -- 否 --> D1["主体不回复（可被关键词类逻辑另行处理）"]
    D -- 是 --> E{"block_reason_for_message 命中?"}
    E -- 是 --> E1["屏蔽优先, 不唤醒"]
    E -- 否 --> F["sleep_service.wake(at_mention_event)"]
    F --> G["WillingDecision(manager_name='wake_up', probability=1.0)"]
    G --> H["_start_reply_with_tracking(background_content=wake_prompt())"]
    B -- 否 --> I{"正在回复中?"}
    I -- 是 --> J["进 _post_reply_willing 队列, 等本轮结束"]
    I -- 否 --> K{"消息含图?"}
    K -- 是 --> L["进 _pending_image_willing"]
    K -- 否 --> M["正常 evaluate"]
    J --> N["回复结束后 _process_post_reply_queue"]
    N --> O["超时默认 60s, 过期消息跳过"]
    O --> P["含图走 _process_pending_image_willing, 否则再进本函数"]
```

这些是**排队与唤醒**，不改概率：`probability=1.0` 的三处短路（@必回、私聊、唤醒）
都是显式构造的 `WillingDecision(manager_name=...)`，与 `QuailWillingManager` 的算术无关。
`fix` 记录里的坑：屏蔽判定必须在唤醒与@之前，否则拉黑的人还能靠 @ 把 bot 叫醒。
</details>

<details>
### 自定义 manager：换了实现就换了算术

```mermaid
flowchart TD
    A["config.willing.manager_name"] --> B["WillingService._load_manager"]
    B --> C{"内置名?"}
    C -- "Quail" --> D["QuailWillingManager（本图描述的算术）"]
    C -- 其它 --> E["_resolve_custom_manager_path<br/>查 data/Willing/ 下的自定义实现"]
    E --> F{"找到?"}
    F -- 否 --> G["回落到 Quail + 告警"]
    F -- 是 --> H["_instantiate_manager 动态加载"]
    H --> I{"实现 BaseWillingManager?"}
    I -- 否 --> G
    I -- 是 --> J["用自定义 evaluate"]
    B --> K["_sync_runtime_documents<br/>把 templates/README.md 同步到 data/Willing/"]
```

自定义 manager 也可以返回任意 `WillingDecision`：`BaseWillingManager` 只要求
`evaluate(context) -> WillingDecision`（`models.py:69`）。换 manager 时，
`probability` 与 `should_reply` 的语义（谁决定要不要回复）由实现方负责，
事件管道只看 `should_reply`。
</details>

<details>
### WillingContext 全字段（_build_context 采什么、谁用）

```mermaid
flowchart LR
    subgraph 身份["身份与标量"]
      F1["manager_name / conversation_type / conversation_id"]
      F2["sender_id / message_id / text / raw_message"]
      F3["bot_account / bot_name / bot_aliases"]
    end
    subgraph 布尔判定["布尔判定"]
      G1["mentioned_bot / called_bot_name / replied_to_message"]
      G2["has_question / is_direct_message / is_allowed"]
      G3["at_guaranteed_reply / is_official_bot"]
    end
    subgraph 数值["数值系数"]
      H1["base_probability <- group_chat_chance"]
      H2["conversation_coefficient <- group_response_coefficient"]
      H3["config_global_coefficient <- 按 reply_mode 选"]
      H4["official_bot_coefficient 默认 0.05"]
    end
    subgraph 观测["观测数据（当前 Quail 不用）"]
      I1["queue / queue_size / queue_text"]
      I2["observe_window / observed_messages_text"]
      I3["matched_keywords"]
    end
```

`queue_text` 是**整段聊天记录渲染**，`observed_messages_text` 是最近 `observe_window` 条：
这两个字段是给「上下文感知型 manager」预留的，Quail 读了但没参与计算 ——
自研 manager 可以直接用它们做语义判定，不用再自己取队列。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| 运行时系数（四项） | AI 工具/面板 setter | 进程重启（纯内存） | `clamp_probability` 到 0..1，非法值不会越界 |
| 运行时黑名单 | `add_runtime_blacklist` | `remove_runtime_blacklist` 或重启 | 命中即 0.0，不进入算术 |
| 睡眠状态 | `SleepService` / `/sleep` | 被@唤醒或 `/awake` | 睡眠期只有屏蔽优先的 @ 能唤醒 |
| 回复中标记 | `_start_reply_with_tracking` 成功后 | `on_reply_done` | 期间消息进 `_post_reply_willing`，不丢 |
| 图片待决 | 含图消息进 `_pending_image_willing` | 图片解析完成或超时 60s | 过期消息直接跳过，不补回复 |

## 易错点

* **起点是 0.5 不是 0**，`group_chat_chance` 是乘数不是「基础概率」；调参时先确认目标量级。
* **加项只有问句 +0.15**：被叫昵称（`called_bot_name`）、关键词、被回复等字段被算出来了但
  **当前 Quail 没用**。想看「叫了名字也不回」的原因，答案在算术里，不在字段里。
* **乘法顺序会体现在 reasons 顺序上**，但数值与顺序无关；改顺序只影响日志可读性。
* **三处 1.0 短路绕过所有系数**：@ 必回、私聊、睡眠唤醒。用户抱怨「系数调了没用」时先看是否是这三种。
* **屏蔽优先于一切**：`block_reason_for_message` 必须排在 @ 判定与唤醒之前。
* **运行时系数不落盘**：重启回默认值，别把它当成持久配置。
