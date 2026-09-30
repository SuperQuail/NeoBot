---
flow: 04-agent-loop
covers:
  - packages/chat/src/neobot_chat/runtime/agent.py
  - packages/chat/src/neobot_chat/schema/exceptions.py
  - app/src/neobot_app/agents/
  - app/src/neobot_app/agent_tools/invocation.py
verified_against: 528fe18
verified_hash: c906ef4d946c
---

# 04 Agent 循环：工具迭代 / 轮次上限 / 失败语义 / 自修复

## 范围

模型与工具之间的往返循环本体（`packages/chat/src/neobot_chat/runtime/agent.py` `Agent` 类），
以及 app 侧怎么用它：解题 Agent（`ProblemSolverManager`）、自修复 Agent（`SelfHealManager`）。
工具清单与技能注册见 `06-tools-skills.md`；模型路由见 `05-llm-routing.md`。

## 流程

```mermaid
flowchart TD
    A["调用方: agent.invoke(state)"] --> B["i = 0"]
    B --> C{"i < max_iterations?"}
    C -- 否 --> C1["达到轮次上限: 退出循环"]
    C -- 是 --> D["provider.chat(messages, tools)"]
    D --> E{"provider 抛异常?"}
    E -- "ProviderError" --> E1["原样上抛（原类型保留）"]
    E -- "其它 Exception" --> E2["包装成 ProviderError 后上抛"]
    E -- 否 --> F["把 assistant 消息写进历史"]
    F --> G{"有 tool_calls?"}
    G -- 否 --> H["break：模型给了最终答复"]
    G -- 是 --> I["_decide_tool_action: allow / ask / deny"]
    I --> J{"deny?"}
    J -- 是 --> J1["写回 tool 消息说明被拒, 不执行"]
    J -- 否 --> K["_run_tools 执行本批工具"]
    K --> L["工具结果作为 tool 消息回灌历史"]
    L --> M["i += 1"]
    M --> C
    H --> N["返回最终文本"]
    E1 --> O["编排层处理: 不入历史、不降级成 assistant 文本"]
    E2 --> O
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant P as 调用方(orchestrator/manager)
    participant AG as Agent.invoke
    participant PR as provider
    participant TL as toolset(AgentToolRuntime)

    P->>AG: invoke(state)
    loop 每轮 i < max_iterations
        AG->>PR: chat(messages, tools)
        PR-->>AG: assistant 消息(可能带 tool_calls)
        alt 有 tool_calls
            AG->>AG: _decide_tool_action 判定 allow/ask/deny
            AG->>TL: execute(工具名, 参数)
            TL-->>AG: 结果文本
            AG->>AG: 结果作为 tool 消息回灌
        else 无 tool_calls
            AG-->>P: 最终文本
        end
    end
    Note over AG,PR: ProviderError 原样上抛，绝不写进历史
```

## 细节

<details>
### 迭代上限：三处不同的数字

```mermaid
flowchart LR
    A["Agent.__init__(max_iterations=10)"] --> B{"谁在用"}
    B -- "聊天管线 agent 模式" --> C["app 侧显式覆盖"]
    B -- "解题 Agent" --> D["problem_solver.py:51<br/>_MAX_AGENT_ITERATIONS = 20"]
    B -- "自修复 Agent" --> E["self_heal.py:1730<br/>max_iterations=30"]
    B -- "沙箱维护 Agent" --> F["bootstrap/__init__.py:470<br/>max_iterations=30, command_timeout=120"]
    B -- "子 Agent(工具)" --> G["agent_tools/runtime.py:341<br/>config.max_agent_iterations 默认 20"]
```

`packages/chat/src/neobot_chat/runtime/agent.py:53` 的默认值是 10，**实际生效值看调用点**：
改上限时容易只改一处，导致「聊天够用、解题不够」这类不对称问题。
`stream_invoke`（`:150`）用同一个上限，流式与非流式的轮次语义必须一致。
</details>

<details>
### 失败语义：ProviderError 的类型契约

```mermaid
flowchart TD
    A["provider.chat 抛异常"] --> B{"是 ProviderError?"}
    B -- 是 --> C["_emit error(provider=True)<br/>然后 raise 原异常"]
    B -- 否 --> D["包装: ProviderError(error_text,<br/>provider=…, original=exc, iteration=i)"]
    C --> E["上抛到调用方"]
    D --> E
    E --> F{"调用方"}
    F -- "聊天管线" --> G["编排层失败处理: 事件 FAILED<br/>历史里不出现 Error: 文本"]
    F -- "解题 Agent" --> H["任务标记失败, 回执说明原因"]
    F -- "自修复" --> I["记日志, 不递归触发自身"]
```

类型定义在 `packages/chat/src/neobot_chat/schema/exceptions.py:8 ProviderError`。
`fix(12) §4.2` 的教训：**绝不能**把 provider 异常吞成一条 assistant 文本 —— 那会污染历史，
让模型以为「刚才那句 Error: … 是自己说的」。
</details>

<details>
### 工具裁决：allow / ask / deny 三分支

```mermaid
flowchart TD
    A["模型请求的 tool_calls"] --> B["逐个 _decide_tool_action"]
    B --> C{"策略判定"}
    C -- allow --> D["直接执行"]
    C -- ask --> E["需要人工确认:<br/>ToolPermissions.require(context, action)"]
    E --> F{"凭据就绪?"}
    F -- 是 --> D
    F -- 否 --> G["抛 CREDENTIAL_REQUIRED, 由上游发凭据"]
    C -- deny --> H["不执行, 写回 tool 消息说明被拒"]
    D --> I["结果文本回灌历史"]
    H --> I
```

`agent.py:327 _decide_tool_action`、`:370` deny 分支；
敏感操作凭据在 `agent_tools/permissions.py:13`。
「被拒」也是一次有效轮次（要有 tool 消息），否则模型会反复重试同一个被拒调用。
</details>

<details>
### 解题 Agent：提交 -> 后台任务 -> 超时

```mermaid
flowchart TD
    A["ProblemSolverManager.submit"] --> B["建任务 + 占位回复"]
    B --> C["asyncio 后台任务<br/>timeout=config.timeout_seconds 默认 600s"]
    C --> D["_invoke_direct -> agent.invoke(state)"]
    D --> E{"超时?"}
    E -- 是 --> F["取消任务 + 回执说明超时"]
    E -- 否 --> G{"ProviderError?"}
    G -- 是 --> H["失败回执: 模型侧不可用"]
    G -- 否 --> I["产出结果"]
    I --> J["回执发送（可能走 send_reply）"]
    J --> K["note_session_closed 等会话窗口收尾"]
```

解题 Agent 与聊天管线**共用同一个 `Agent` 类**：`problem_solver.py:21` 直接
`from neobot_chat import Agent`，本文件只负责配置、委托与提示词。查工具循环问题请去
`packages/chat/src/neobot_chat/runtime/agent.py`，不要只看 app 侧。
</details>

<details>
### 自修复：三重门槛 + 每日上限

```mermaid
flowchart TD
    A["loguru ERROR sink"] --> B["SelfHealManager.record(error_payload)"]
    B --> C{"来自 app.self_heal 自己?"}
    C -- 是 --> D["丢弃, 防自激"]
    C -- 否 --> E["入环形缓冲 buffer_size=200"]
    E --> F["_maybe_trigger"]
    F --> G{"已有修复任务在跑?"}
    G -- 是 --> H["跳过（单飞）"]
    G -- 否 --> I{"距上次 < min_interval_seconds=300s?"}
    I -- 是 --> J["节流, 跳过"]
    I -- 否 --> K{"traceback 数 >= 3 或<br/>60s 内错误数 >= 10?"}
    K -- 否 --> L["不触发"]
    K -- 是 --> M{"今日次数 < daily_limit=5?"}
    M -- 否 --> N["拒绝: 达到每日上限"]
    M -- 是 --> O{"admin_account 配置了?"}
    O -- 否 --> P["拒绝: 没有回执对象"]
    O -- 是 --> Q["派发修复 Agent(main_iterations=30)"]
```

阈值来自 `agents/self_heal.py:101 SelfHealAgentConfig`（traceback_threshold=3、
rate_threshold=10、rate_window_seconds=60、min_interval_seconds=300、daily_limit=5）。
`trigger_now`（`:349`）是手动入口，注释写明**暂未接入技能** —— 想手工触发要自己接线。
</details>

<details>
### 工具执行期间的取消与心跳

```mermaid
flowchart TD
    A["工具开始执行"] --> B["注册 cancel_handler(reason)"]
    B --> C["长时间任务定期 reset_silent_deadline"]
    C --> D{"收到取消?"}
    D -- 是 --> E["cancelled=True, event.error=reason"]
    E --> F["非终态 -> CANCELLED"]
    D -- 否 --> G["正常返回结果"]
    G --> H["结果回灌 -> 下一轮"]
    F --> I["循环终止, 不再调模型"]
```

取消是「工具层可见」的：`orchestrator.py:2259 cancel_handler` 注入 toolset，
这样进程命令、子 Agent 之类长任务能被静默看门狗或用户命令打断，
而不是等 `max_iterations` 耗完。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| 轮次计数 `i` | `invoke` 循环 | 循环结束即弃 | 到 `max_iterations` 直接退出（不是异常） |
| 历史 messages | 每轮追加 assistant / tool | 循环结束交回调用方 | ProviderError 时**不追加**，历史保持干净 |
| 工具裁决结果 | `_decide_tool_action` | 单次调用 | deny 也写 tool 消息，避免重复请求 |
| 自修复单飞任务 | `_dispatch` | 任务 done 回调 | 单飞/节流/阈值/每日上限任一不满足即不触发 |
| 取消标记 | `cancel_handler(reason)` | 每个回复事件独立 | 非终态转 CANCELLED，工具尽快退出 |

## 易错点

* **主循环不在 `agents/problem_solver.py`**：那是配置与委托；循环本体在
  `packages/chat/src/neobot_chat/runtime/agent.py`。改循环语义要同时看 `invoke` 与 `stream_invoke`。
* **providers 异常必须原样上抛**：包装只对「非 ProviderError」做；把 `ProviderError`
  也包一层会让原生视觉降级判定失效（`05-llm-routing.md` 依赖这个类型）。
* **轮次上限有三个数字**：默认 10、解题 20、自修复/沙箱维护 30、子 Agent 取
  `agent_tools.max_agent_iterations`。改一个要知道影响谁。
* **deny 不写历史是 bug**：模型会无限重试被拒的工具，必须在历史里留下 tool 消息。
* **自修复要防自激**：`record` 里跳过 `app.self_heal` 自己的日志，否则一次失败会滚成风暴。
