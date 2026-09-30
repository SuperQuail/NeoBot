---
flow: 03-reply-pipeline
covers:
  - app/src/neobot_app/reply/orchestrator.py
  - app/src/neobot_app/reply/event.py
  - app/src/neobot_app/reply/sender.py
  - app/src/neobot_app/reply/postprocess.py
  - app/src/neobot_app/reply/output_guard.py
  - app/src/neobot_app/reply/vision_context.py
  - app/src/neobot_app/reply/flow_registry.py
verified_against: 08faa3f
verified_hash: 013bea14911e
---

# 03 回复管线：状态机 / 冷却 / 静默看门狗 / 发送与后处理

## 范围

从事件管道喊 `start_reply` 到消息真正发出去（并把自身发言写回队列）的全部环节：
状态机、同会话去重、冷却、两种模式（common / agent）、静默看门狗、后处理与输出兜底、发送。
意愿判定本身见 `02-inbound-message.md` 的细节块与 `willing` 小节；工具迭代见 `04-agent-loop.md`。

## 流程

```mermaid
flowchart TD
    A["事件管道 _start_reply_with_tracking"] --> B["orchestrator.start_reply"]
    B --> C{"_closed?"}
    C -- 是 --> C1["拒绝：管线已关闭"]
    C -- 否 --> D["_resolve_mode: common / agent"]
    D --> E{"同会话已有在跑管线?"}
    E -- 是 --> E1["skipped_pipeline_overlap 直接返回"]
    E -- 否 --> F{"距上次回复 < reply_cooldown_seconds?"}
    F -- 是 --> F1["skipped_cooldown 返回 None<br/>（skip_cooldown=True 可绕）"]
    F -- 否 --> G["create_task(_run)"]
    G --> H["PENDING -> BUILDING_PROMPT"]
    H --> I{"reply.decide.before/after 被消费?"}
    I -- 是 --> I1["CANCELLED + 发 reply.cancel"]
    I -- 否 --> J{"mode"}
    J -- common --> K["_run_common_mode"]
    J -- agent --> L["_run_agent_mode + 静默看门狗"]
    K --> M["GENERATING -> _generate_reply"]
    L --> M
    M --> N["SENDING -> _send_reply"]
    N --> O["后处理 + 输出兜底 + 逐句发送"]
    O --> P["COMPLETED + 记 _last_reply_time"]
    P --> Q["on_reply_done: 处理回复期间积压的消息"]
    N -.取消.-> R["CANCELLED（无出边）"]
    N -.异常.-> S["FAILED（无出边）+ _handle_runtime_failure"]
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant EP as EventPipeline
    participant OR as ReplyOrchestrator
    participant AG as Agent/provider
    participant PP as postprocess
    participant SD as ReplySender
    participant Q as MessageQueue

    EP->>OR: start_reply(event, queue, queue_key)
    OR->>OR: 去重 / 冷却 / 建任务
    OR->>AG: _build_prompt + 生成
    AG-->>OR: 文本或工具调用
    OR->>SD: send_reply(text)
    SD->>PP: process_reply_text 切句
    PP-->>SD: segments + fallback_used
    SD->>Q: 逐句发送
    SD->>Q: _emit_self_sent 自身发言入队 + 落盘
    OR->>OR: COMPLETED + 记冷却基准
```

## 细节

<details>
### 状态机：七个状态与合法迁移

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> BUILDING_PROMPT
    BUILDING_PROMPT --> GENERATING
    GENERATING --> SENDING
    SENDING --> GENERATING
    SENDING --> COMPLETED
    PENDING --> CANCELLED
    BUILDING_PROMPT --> CANCELLED
    GENERATING --> CANCELLED
    SENDING --> CANCELLED
    PENDING --> FAILED
    BUILDING_PROMPT --> FAILED
    GENERATING --> FAILED
    SENDING --> FAILED
    COMPLETED --> [*]
    CANCELLED --> [*]
    FAILED --> [*]
```

`reply/event.py:19 ReplyState`、`:29 _VALID_TRANSITIONS`；`:58 transition` 对非法迁移直接
`raise RuntimeError`（「非法状态转换: A -> B」），三个终态没有出边。
群聊有个特例：`sender.py:167 _leave_sending` 允许 COMPLETED 之后再次进入 SENDING，
这样模型连续多次 `send_reply` 不会被状态机吞掉；私聊则回到 GENERATING。
</details>

<details>
### start_reply 的四道拒绝（顺序不能换）

```mermaid
flowchart TD
    A["start_reply"] --> B{"_closed?"}
    B -- 是 --> B1["拒绝: 已关闭"]
    B -- 否 --> C["_resolve_mode 先定 common/agent"]
    C --> D{"pipeline_key 已有在跑?"}
    D -- 是 --> D1["skipped_pipeline_overlap:<br/>同会话并发回复会串轮次"]
    D -- 否 --> E{"冷却窗口内?"}
    E -- 是 --> E1["skipped_cooldown 返回 None"]
    E -- 否 --> F["建 ReplyEvent + create_task(_run)"]
    F --> G["_cleanup: 释放 executor / finish_turn / on_reply_done"]
```

`pipeline_key = f"{conversation_ref.kind}:{queue_key}"`（`orchestrator.py:600`）；
冷却基准是**上一次成功的 `_run` 完成时刻**（`:1805`），不是「上次收到消息的时刻」。
后台通知走 `start_background_reply`（`:761`），它带 `skip_cooldown=True`，不占用冷却额度。
</details>

<details>
### common 模式：提示词 -> 生成 -> 发送

```mermaid
flowchart TD
    A["_run_common_mode"] --> B["表情包随机触发（按概率决定是否带图）"]
    B --> C["_build_role_messages 组装角色消息"]
    C --> D["_build_prompt + _record_flow_prompt 登记聊天流"]
    D --> E["_apply_pre_reply_hooks 插件可短路"]
    E --> F{"被短路?"}
    F -- 是 --> F1["直接返回，不调模型"]
    F -- 否 --> G["_generate_reply 调 provider"]
    G --> H["_send_reply(self_sent=...)"]
    H --> I["sender.send_reply -> 后处理 -> 发送"]
```

AI 回复检查分流（`:3014`）：`full_check` 直接查；否则先用
`process_reply_text(...).fallback_used` 预演判断是否「需要复核」，需要则追加一条 user 消息
等模型再次 `send_reply`。这样避免「超长必炸」还要多花一次调用。
</details>

<details>
### agent 模式：静默看门狗（内联闭包，不是独立任务）

```mermaid
flowchart TD
    A["_run_agent_mode"] --> B["silent_timeout = group_agent_silent_timeout_seconds<br/>默认 120s"]
    B --> C["silent_deadline = now + timeout"]
    C --> D["reset_silent_deadline(extra) 由活动点调用"]
    D --> E["工具/模型活动:<br/>SILENT_HEARTBEAT ContextVar 下发"]
    E --> F{"一轮结束, silent_remaining() 内?"}
    F -- 是 --> G["继续下一轮"]
    F -- 否 --> H["cancel_for_silence(phase)"]
    H --> I["error=『群聊 agent 管线静默超过 N 秒, 已强制关闭（阶段: x）』"]
    I --> J["非终态 -> CANCELLED, 记 group_agent_silent_timeout"]
    G --> K{"模型调 send_reply?"}
    K -- 是 --> L["send_reply_handler; 返回 False 提示重生成"]
    K -- 否 --> M{"iterations 用尽?"}
    M -- 是 --> N["按失败语义结束"]
```

看门狗是 `_run_agent_mode` 里的闭包 + `SILENT_HEARTBEAT` ContextVar（`orchestrator.py:2031-2095`），
**没有独立任务** —— 调试时不要去找 `watchdog_task` 之类的东西。
</details>

<details>
### 后处理：去壳 -> 控 token 判定 -> 切句 -> 兜底

```mermaid
flowchart TD
    A["process_reply_text(text, bot_name, fallback_template, max_length, max_sentence_count)"] --> B["去标注壳（角色前缀/think 标记）"]
    B --> C["保护颜文字, 避免被切句切碎"]
    C --> D{"控制 token 处理后为空?"}
    D -- 是 --> D1["走 fallback 模板 + fallback_used=True"]
    D -- 否 --> E{"超长?"}
    E -- 是 --> E1["fallback + build_over_limit_guidance"]
    E -- 否 --> F["split_into_sentences_w_remove_punctuation<br/>_stable_seed 保证同文本同切分"]
    F --> G{"句数超限?"}
    G -- 是 --> G1["fallback"]
    G -- 否 --> H["返回 ReplyPostProcessResult"]
    H --> I["ReplySplitPreview.matches 判定『可信切分』"]
```

`postprocess.py:50` 是唯一入口；`:36 ReplySplitPreview.matches` 只有 text 与 segments
**逐字一致**才认为可信，不可信时发送侧不会抑制控制 token。
</details>

<details>
### 输出兜底与发送：两次清洗 + 自身发言入队

```mermaid
flowchart TD
    A["sender.send_reply"] --> B["reply.postprocess.before 钩子"]
    B --> C["_sanitize_outgoing 第一次清洗"]
    C --> D["reply.send.before 钩子（插件可改写）"]
    D --> E["再清洗一次（改写后必须重清）"]
    E --> F{"清洗后为空?"}
    F -- 是 --> F1["丢弃 + warning, 返回 False"]
    F -- 否 --> G["_build_reply_messages"]
    G --> H["reply.postprocess.after 钩子"]
    H --> I["clean_segments（trusted_split 才关控制 token 抑制）"]
    I --> J["逐条发送: 句子冷却 -> send_with_timeout"]
    J --> K["_emit_self_sent_text 自身发言入队 + 快照"]
    K --> L["_schedule_self_sent_persist 后台落盘（永不抛）"]
```

自身发言的合成 message_id 是**严格递减的负数**（`sender.py:561`），与后端真实 id 天然不撞号；
落盘 `event_id` 是 `self:<id>`，软重启后据此补齐 assistant 块。
入队失败只 warning：「宁可少一条上下文，也不能让回复发不出去」。
</details>

<details>
### 超时封装与聊天流登记（失败都不影响回复）

```mermaid
flowchart LR
    subgraph 出站 IO
      A["_send_with_timeout"] --> B["adapter 发送"]
      C["_call_api_with_timeout"] --> D["OneBot API"]
    end
    subgraph 只读登记
      E["record_prompt"] --> F["ChatFlowRegistry"]
      G["record_request"] --> F
      H["set_active"] --> F
      F --> I["面板『聊天流』页只读展示"]
    end
    F -.登记失败.-> J["try/except 降级: 不影响本次回复"]
```

三处登记（`orchestrator.py:1337 / 1357 / 1382`）全部 try/except；
面板按 `pipeline_key` 取快照与后台任务（`flow_registry.py:147`）。
视觉上下文 `ReplyVisionContext`：每轮 `refresh_defaults` 在预算内加载图片，
`request_messages` 在请求边界追加图片附录，加载失败**可见可重试**。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `ReplyState` 七态 | `ReplyEvent.transition` | 终态无出边 | 非法迁移直接 RuntimeError；终态补 `completed_at` |
| 同会话在跑标记 `_replying_queues` | `_start_reply_with_tracking` 成功后 | `on_reply_done` | start_reply 返回 None 时不置位（否则会话会被永久锁住） |
| 冷却基准 `_last_reply_time` | `_run` 成功完成时 | 不清理（只被新值覆盖） | 取消/失败都不刷新基准 |
| 静默看门狗 `silent_deadline` | `_run_agent_mode` 建闭包 | 每轮 `reset_silent_deadline` | 超时 -> CANCELLED + 记 phase，不抛异常上浮 |
| 发送中标记 | `sender._enter_sending` | `_leave_sending` | 群聊允许 COMPLETED -> SENDING 再入 |
| 自身发言落盘任务 | `_emit_self_sent` | 后台任务自行结束 | 永不抛异常，失败只记日志 |

## 易错点

* **冷却不是意愿的事**：`willing/service.py` 里没有 cooldown；回复冷却在
  `orchestrator.py:619`，逐句打字冷却在 `sender.py:456`，静默超时在 `orchestrator.py:2041`。
  改「不回复」的直觉时先确认是哪一层。
* **同会话去重与冷却都会让 `start_reply` 返回 None**：调用方（事件管道）必须把 None 当作
  「本次不回复」，而不是错误 —— 命令同步回复被拒时**不能**丢弃回复中标记。
* **插件改写后必须重新清洗**：`reply.send.before` 之后还有一次 `_sanitize_outgoing`，
  去掉它会让插件注入的标注壳直接发给用户。
* **状态机终态无出边**：想「失败后再发一条」要新建 ReplyEvent，不能把 FAILED 改回 SENDING。
* **自身发言必须入队且允许失败**：入队/落盘失败只 warning（`fix(2)` 的教训是「不入队会丢上下文」，
  但绝不能因为落盘失败把已发出的回复判为失败）。
* **看门狗是闭包不是任务**：关机路径不会去 cancel 它，靠 deadline 自愈；改 `_run_agent_mode`
  时要保证每个可能长时间阻塞的 await 前后都有 `reset_silent_deadline`。
