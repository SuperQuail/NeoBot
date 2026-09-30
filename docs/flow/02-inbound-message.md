---
flow: 02-inbound-message
covers:
  - packages/adapter/src/neobot_adapter/
  - app/src/neobot_app/message/queue.py
  - app/src/neobot_app/runtime/gateway.py
  - app/src/neobot_app/runtime/inbound_pipeline.py
verified_against: 96da9ef
verified_hash: 7b1ffda9aa1a
---

# 02 适配器入站：反向 WS -> 事件网关 -> 队列 -> 事件管道

## 范围

从「QQ 框架把一帧 JSON 推进反向 WebSocket」到「消息进入事件管道、准备做意愿判定」的全过程。
覆盖 `packages/adapter/src/neobot_adapter/`、`app/src/neobot_app/message/queue.py`、
`app/src/neobot_app/runtime/gateway.py`。回复怎么产生见 `03-reply-pipeline.md`，
概率怎么算见 `02b 细节` 与 `03-reply-pipeline.md` 的细节块。

## 流程

```mermaid
flowchart TD
    A["框架 connect 反向 WS"] --> B{"配置了 access_token?"}
    B -- 是 --> B1["_authorize_handshake<br/>hmac.compare_digest, 失败 401"]
    B -- 否 --> C["_handle_client 建立会话"]
    B1 -->|通过| C
    C --> D["active_connections.add + 置 _connection_established"]
    D --> E["async for message in websocket"]
    E --> F{"json.loads 成功?"}
    F -- 否 --> F1["告警 + continue（连接不死）"]
    F -- 是 --> G{"isinstance(data, dict)?"}
    G -- 否 --> G1["告警 + continue<br/>非对象帧不再打死分发循环"]
    G -- 是 --> H{"有 echo 字段?"}
    H -- 是 --> H1["_fulfill_echo 幂等兑现回执"]
    H -- 否 --> I["_handle_event 第二道 dict 守卫"]
    I --> J["message_queue.put_nowait<br/>满 -> 丢弃并打印"]
    J --> K["OneBotAdapter._dispatch_loop"]
    K --> L["EventDispatcher.publish 按 priority"]
    L --> M["EventGateway.handle 组装 EventContext"]
    M --> N["hook_bus.dispatch 插件钩子"]
    N --> O{"ctx.consumed?"}
    O -- 是 --> O1["插件已接管, 结束"]
    O -- 否 --> P{"post_type"}
    P -- message --> Q["EventPipeline.handle_*_message_event"]
    P -- notice --> R["NoticeHandler 撤回/表情回应/戳一戳"]
    P -- request --> S["OneBotRequestHandler"]
    P -- meta_event --> T["LifecycleHandler 心跳"]
    Q --> U["去重 -> 工具输入短路 -> 命令 -> 入队"]
    U --> V["意愿判定 -> 回复管线（见 03）"]
    K -.分发循环意外退出.-> W["_on_dispatch_task_done 告警（不再静默）"]
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant FW as QQ 框架
    participant CORE as AdapterCore(接收线程)
    participant ADP as OneBotAdapter
    participant GW as EventGateway
    participant EP as EventPipeline
    participant Q as MessageQueue

    FW->>CORE: 反向 WS 连接 + 鉴权
    CORE->>CORE: 置闩锁 _connection_established
    FW->>CORE: 推 JSON 帧
    CORE->>CORE: json.loads + dict 守卫
    CORE->>Q: put_nowait(event)
    ADP->>Q: get_message(block=True, 0.1s)
    ADP->>GW: dispatcher.publish(event)
    GW->>GW: hook_bus.dispatch + consumed 判定
    GW->>EP: handle_group/private_message_event
    EP->>Q: push 进会话队列
    Note over EP: 去重 / 命令 / 意愿判定在此之后
```

## 细节

> 默认折叠；按需展开。每一块都能单独截图给评审。

<details>
### 适配器工厂：mode 决定实例

```mermaid
flowchart LR
    A["AdapterSettings.mode"] --> B{"onebot?"}
    B -- 是 --> C["OneBotAdapter(host=reverse_ws_host,<br/>port=reverse_ws_port, access_token=…)"]
    B -- 否 --> D{"local?"}
    D -- 是 --> E["LocalAdapter 内嵌, 不需要连接等待"]
    D -- 否 --> F["raise ValueError"]
    C --> G["RuntimeAdapter 协议:<br/>start/stop/subscribe/call_api/send"]
    G --> H["requires_connection_wait=True -> 装配连接探针"]
    E --> I["requires_connection_wait=False -> 无探针"]
```

`packages/adapter/src/neobot_adapter/factory.py:29 create_adapter`；
契约在 `interfaces.py:31 RuntimeAdapter`，热重载能力由 `AdapterReconfigurable``（`:79`）判定，
装配层用 `isinstance` 而不是 `hasattr`（`runtime/adapter_supervisor.py:87`）。
</details>

<details>
### 反向 WS 服务端：起在接收线程自己的事件循环里

```mermaid
flowchart TD
    A["AdapterCore.start()"] --> B{"旧接收线程还活着?"}
    B -- 是 --> B1["raise RuntimeError 拒绝重建（需重启进程）"]
    B -- 否 --> C["清 _stop_event / _abandoned / 闩锁"]
    C --> D["起守护线程 DaemonThread"]
    D --> E["线程内 asyncio 循环: _run_server"]
    E --> F["websockets.serve(_handle_client, host, port,<br/>max_size=10MiB, process_request=_authorize_handshake)"]
    F --> G["serve_forever 监听"]
    G -.收到 stop.-> H["close server -> 关活跃连接 -> wait_closed(2s)"]
    H --> I["_connection_established.clear()"]
```

这里是**反向** WS：bot 当服务端、QQ 框架主动连进来，所以「启动成功」只代表端口在听，
不代表框架已连上（见 `01-startup-shutdown.md` 的连接探针细节）。
</details>

<details>
### _handle_client：一帧数据要过几道闸

```mermaid
flowchart TD
    A["收到一帧文本"] --> B{"json.loads 抛异常?"}
    B -- 是 --> B1["warning + continue"]
    B -- 否 --> C{"dict?"}
    C -- 否 --> C1["warning『收到非对象 JSON 帧』+ continue"]
    C -- 是 --> D{"'echo' in data?"}
    D -- 是 --> E{"fut 还在等?"}
    E -- 否 --> E1["丢弃（迟到/重复回执）"]
    E -- 是 --> E2["set_result 兑现 API 回执"]
    D -- 否 --> F["_handle_event(event)"]
    F --> G{"再次 dict 守卫"}
    G -- 否 --> G1["丢弃"]
    G -- 是 --> H["put_nowait 入队"]
    H --> I{"队列满?"}
    I -- 是 --> I1["打印『队列满，丢弃事件』"]
    I -- 否 --> I2["交给分发循环"]
    F --> J["_handle_meta_event 心跳/生命周期"]
```

**两道 dict 守卫**（`core.py:546` 与 `:613`）是 `fix(13)` 的直接产物：
数组/字符串帧继续下传会在 `'"echo" in data'` 处抛 TypeError，把整条连接拆掉。
</details>

<details>
### 分发循环与「队列不是分发器」

```mermaid
flowchart TD
    A["OneBotAdapter.start()"] --> B["bind_core -> core.start()"]
    B --> C["create_task(_dispatch_loop) + done 回调"]
    C --> D{"_stopping 已置位?"}
    D -- 是 --> E["退出循环"]
    D -- 否 --> F["get_message(block=True, timeout=0.1)<br/>跑在 asyncio.to_thread 里"]
    F --> G{"拿到事件?"}
    G -- 否 --> D
    G -- 是 --> H["dispatcher.publish(event)"]
    H --> I{"单个 handler 抛异常?"}
    I -- 是 --> I1["记 ERROR『事件分发失败，已跳过该事件』"]
    I -- 否 --> D
    I1 --> D
    C -.任务结束.-> J["_on_dispatch_task_done:<br/>取消/异常/正常退出都要告警"]
```

`app/src/neobot_app/message/queue.py:115 MessageQueue` 只是**数据结构**（分桶 + 容量 + 权重 +
渲染成文本），**没有循环**。真正的分发循环在
`packages/adapter/src/neobot_adapter/onebot/adapter.py:384`。
`listener/manager.py:246` 里的线程版 `_dispatch_loop` 是遗留实现，现行适配器不引用。
</details>

<details>
### 消息队列：容量、权重与时间戳

```mermaid
flowchart TD
    A["push(key, message, occurred_at, replied_messages)"] --> B["_convert_message 归一化"]
    B --> C["_resolve_occurred_at 缺时间戳则补"]
    C --> D{"非时间戳条目 + 桶已满?"}
    D -- 是 --> E["_ensure_capacity_for_non_timestamp_entry<br/>按权重驱逐；丢不下就整条丢弃并 return"]
    D -- 否 --> F["append QueueEntry + 计数/统计"]
    F --> G["to_text / diff_to_text<br/>渲染给模型的聊天记录"]
    G --> H["事件管道取上下文时读取"]
```

队列类型是私有/群两套（`MessageQueueType`），条目类型见 `QueueEntryType`：
MESSAGE / NOTICE / REACTION / POKE / NOTIFICATION。
命令消费标记（`mark_command_consumed` / `is_command_consumed`）用来避免
「挂起管线增量收集」把已回复过的 `/help` 再回一遍。
</details>

<details>
### 事件网关：唯一的订阅入口

```mermaid
flowchart TD
    A["EventGateway.start()"] --> B["event_source.subscribe<br/>message / notice / request / meta_event"]
    B --> C["handle(raw_event)"]
    C --> D["读取 _neobot_skip_ai_reply / _local_conversation_name"]
    D --> E["构造 EventContext"]
    E --> F["hook_bus.dispatch(ctx)"]
    F --> G{"插件钩子抛异常?"}
    G -- 是 --> G1["只记日志，不中断"]
    G -- 否 --> H["take_agent_reply_intent()"]
    G1 --> H
    H --> I{"ctx.consumed?"}
    I -- 是 --> I1["插件已接管 -> return"]
    I -- 否 --> J["_route 按 post_type 分派"]
    J --> K["message -> EventPipeline"]
    J --> L["notice / request / meta_event -> 各自 handler"]
```

订阅只此一处（`runtime/gateway.py:51`）。`EventPipeline` 不再自订阅：
历史上两处都订阅会让同一条消息被处理两次（`event_pipeline.py:130` 有明确注释）。
</details>

<details>
### 群聊分派的判据顺序（代码顺序即优先级）

```mermaid
flowchart TD
    A["handle_group_message_event"] --> B["safe_parse_model"]
    B --> C{"_is_duplicate_message 命中 200 条窗口?"}
    C -- 是 --> C1["丢弃重复"]
    C -- 否 --> D{"_handle_agent_tool_input 命中?"}
    D -- 是 --> D1["工具输入短路, 不走向上回复"]
    D -- 否 --> E["_handle_inbound_raw_event 10s 超时, 只警告"]
    E --> F["_fetch_replied_messages 拉被引用消息"]
    F --> G{"command_service.handle_message 命中?"}
    G -- 是 --> G1["标记 consumed, 命令优先"]
    G -- 否 --> H["agent_intent 插件交付主管线"]
    H --> I["_skip_while_standby 待机期不入队"]
    I --> J["queue.push + mark_command_consumed"]
    J --> K["画像 / 头像 / 图片解析 / 摘要调度"]
    K --> L{"命令已消费?"}
    L -- 是 --> L1["_start_command_sync_reply 后 return"]
    L -- 否 --> M["凭据发放 / 自我消息判定 / 屏蔽判定"]
    M --> N{"该会话正在回复中?"}
    N -- 是 --> N1["进 _post_reply_willing 等回复结束"]
    N -- 否 --> O{"消息含图?"}
    O -- 是 --> O1["进 _pending_image_willing"]
    O -- 否 --> P["_handle_willing_decision 意愿判定"]
```

私聊同序，但没有「@ 要求」与「回复中队列」两段（`event_pipeline.py:306` vs `:502`）。
</details>

<details>
### InboundPipeline 目前是 NO-OP

```mermaid
flowchart LR
    A["_handle_inbound_raw_event(event)"] --> B["InboundPipeline.handle_raw_event"]
    B --> C["map_to_incoming_message 规范化"]
    C --> D["handle(message)"]
    D --> E["只打一条『收到入站消息』日志"]
    E --> F["短期记忆 remember 整段被注释<br/>（未完成功能, 不要画成有效步骤）"]
```

判定要看代码注释：`runtime/inbound_pipeline.py:39-51` 明确写了
「短期记忆为未完成功能，recall 无使用者，暂不启用」。改这块代码时同步更新本小节。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| 连接闩锁 `_connection_established` | 首个客户端连入 `_handle_client` | 服务端收尾 `_run_server` | 只看闩锁会误报「已连接」，判定必须带 `active_connections` |
| 活跃连接集合 `active_connections` | 连接建立 | `_remove_connection` | 连接断开时挂起的 echo 以 `ConnectionClosed` 结束 |
| 分发任务 `_dispatch_task` | `OneBotAdapter.start()` | `stop()`（先等 2s 再 cancel） | 退出必告警：取消/异常/正常三种都要能看见 |
| 适配器入站队列 `message_queue` | 接收线程入队 | 分发循环取走 | 满则丢弃并打印，不阻塞收帧 |
| 命令消费标记 | `event_pipeline` 命中命令时 | 条目出队时 | 已消费的命令不再触发二次回复 |
| 事件钩子 `ctx.consumed` | 插件 `hook_bus.dispatch` | 每个事件新建 `EventContext` | 插件接管后主链路直接结束（不算失败） |

## 易错点

* **非 dict 帧是历史事故现场**：数组/字符串帧必须在入站处丢弃（两道守卫都在
  `receiver/core.py`），否则 `'"echo" in data'` 抛 TypeError 把连接拆了（`fix(13)`）。
* **别把 MessageQueue 当分发器**：`queue.py` 没有循环、没有异常保护，入队失败直接向上抛；
  分发与异常保护在 `adapter.py:384 _dispatch_loop`。
* **分发任务退出必须可观测**：`_on_dispatch_task_done` 是「事件入口静默死亡」的补丁，
  改动 `start()/stop()` 时要保留它。
* **订阅只能有一处**：`EventGateway`。任何在 `EventPipeline` 里重新 subscribe 的改动
  都会让事件被处理两遍。
* **入站处理有 10s 依赖超时**：`_handle_inbound_raw_event` 超时只 warning，不阻断主链路。
* **遗留实现别当现行链路**：`listener/manager.py` 的线程版分发循环已不被引用。
