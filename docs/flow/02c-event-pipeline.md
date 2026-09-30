---
flow: 02c-event-pipeline
covers:
  - app/src/neobot_app/runtime/event_pipeline.py
  - app/src/neobot_app/message/queue.py
verified_against: 1de0bea
verified_hash: 40bb17c22f2a
---

# 02c 事件管道：去重 · 命令 · 入队 · 挂起 · 通知

## 范围

从 `EventGateway` 把 `raw_event` 交给 `EventPipeline.handle_group_message_event` /
`handle_private_message_event` 那一刻起，到「消息落进 `MessageQueue` 并决定要不要起回复
管线」为止的全部分派、去重、命令拦截、挂起排队与通知入队逻辑。

* **画**：17 步群聊分派顺序、私聊/群聊差异、`message_id` 去重窗口、
  `handle_agent_tool_input` 短路、命令 consumed 标记、`_replying_queues` /
  `_post_reply_willing` / `_pending_image_willing` 三条挂起状态、待机与睡眠拦截、
  凭据签发短路、三类通知入队、后台任务登记与停机 flush。
* **不画**：WS 收帧、鉴权、`EventDispatcher` 优先级、`EventGateway` 的插件钩子
  （见 `02-inbound-message.md`）；`WillingService` 的概率算术（见
  `02b-willing-probability.md`）；回复管线内部状态机、冷却、看门狗
  （见 `03-reply-pipeline.md`）；命令的解析与权限树（见 17-commands，待补）。
* **spec 与现实的差异**：本模块不自己订阅事件。旧实现的 `start()` 会再注册一套
  `message`/`notice`/`request` 订阅，同一事件会被投递两次，且它**从来没有被调用过** ——
  唯一入口是 `EventGateway`（`event_pipeline.py:130-139` 的注释即为此事留档）。

## 流程

主干 + 四条 `return` 闸；17 步的行号与逐步判据见 `## 细节` 第一块。

```mermaid
flowchart TD
    A["EventGateway.handle<br/>gateway.py:129"] --> B["群消息入口<br/>handle_group_message_event:502"]
    B --> C["safe_parse_model(event, GroupMessage)"]
    C --> D{"去重：message_id<br/>在最近 200 条内?"}
    D -- 是 --> D1["丢弃：不入队、不计总结<br/>id 已进窗口，不可回滚"]
    D -- 否 --> E["工具输入短路<br/>agent_tool_input:270<br/>命中则 push + 标记 + 终结"]
    E --> F["入站管线 + 抓被回复消息<br/>超时只 warning，不中断"]
    F --> G{"命令系统 handle_message<br/>群聊需被 @bot 且命令已注册<br/>否则 consumed=False"}
    G -- 未命中 --> G1["consumed=False"]
    G -- 命中 --> G2["consumed=True<br/>background 可选"]
    G1 --> H["agent_intent 兜底<br/>仅当未被命令消费"]
    G2 --> H
    H --> I{"待机中?"}
    I -- 是 --> I1["丢弃后续回复与记忆管线<br/>命令已在前面处理完"]
    I -- 否 --> J["queue.push + 命中则标记已消费<br/>资料 / 头像 / 图片解析 / 档案总结"]
    J --> K{"命令已消费?"}
    K -- 是 --> K1{"有 background<br/>或 preactivate?"}
    K1 -- 是 --> K2["命令同步回复<br/>manager_name=command"]
    K1 -- 否 --> K3["不回复：命令通道已自行发送"]
    K -- 否 --> L{"凭据文本且首次签发?"}
    L -- 命中 --> L1["发凭据提示<br/>+ 以签发结果为背景起回复"]
    L -- 未命中 --> M{"自己发的 或<br/>插件已阻止本条回复?"}
    M -- 是 --> M1["不触发回复"]
    M -- 否 --> N{"queue_key 在回复中集合?"}
    N -- 是且管线活跃 --> N1["进回复后积压<br/>本轮结束再处理"]
    N -- 是但标记过期 --> N2["warning 后清掉该标记"]
    N -- 否 --> O{"消息含图?"}
    N2 --> O
    O -- 是 --> O1["进图片待决队列<br/>后台任务等解析后按序处理"]
    O -- 否 --> P["意愿判定<br/>见 02b 图"]
    K2 --> Q["起回复管线 start_reply<br/>成功才登记回复中标记"]
    L1 --> Q
    P --> Q
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant GW as EventGateway
    participant EP as EventPipeline
    participant CS as CommandService
    participant RO as ReplyOrchestrator
    participant Q as MessageQueue
    participant BG as 后台任务

    GW->>EP: handle_group_message_event(event, agent_intent)
    EP->>EP: safe_parse_model + _is_duplicate_message
    Note over EP: 去重在第一步且不可回滚<br/>命中的 id 已经写进窗口
    EP->>RO: _handle_agent_tool_input(message, kind, queue_key)
    RO-->>EP: None 表示不是工具输入
    EP->>EP: _handle_inbound_raw_event 10s 超时只 warning
    EP->>Q: find_by_message_id 找被回复的消息
    EP->>EP: 未命中则 adapter.get_msg 10s 超时 continue
    EP->>CS: handle_message(message, kind, queue_key)
    CS-->>EP: consumed / background
    EP->>Q: push(message, replied_messages)
    EP->>Q: mark_command_consumed 仅当命令命中
    EP->>BG: _schedule_archive_summary 派生任务
    alt 命令已消费
        EP->>RO: _start_command_sync_reply 有 background 时
        Note over EP,RO: 管线被拒时**不** discard 回复中标记
    else 普通消息
        EP->>EP: 凭据 / bot 自查 / 插件阻断 / 回复中 / 含图
        EP->>EP: _handle_willing_decision（02b）
        EP->>RO: _start_reply_with_tracking
        RO-->>EP: 事件对象 或 None
        Note over EP: 仅非 None 才 add 进 _replying_queues
    end
    RO-->>EP: on_reply_done 回调
    EP->>Q: _process_post_reply_queue 60s 过期跳过
```

## 细节

<details>
### 群聊 17 步分派顺序：少一步或多一步都会改变短路范围

```mermaid
flowchart TD
    subgraph 入口三步
      A1["safe_parse_model(event, GroupMessage)"] --> A2{"_is_duplicate_message"}
      A2 --> A3{"_handle_agent_tool_input"}
    end
    subgraph 上下文两步
      B1["_handle_inbound_raw_event"] --> B2["_fetch_replied_messages"]
    end
    subgraph 命令与意图
      C1{"command_service.handle_message"} --> C2{"agent_intent 且未被消费"}
    end
    subgraph 落库与副作用
      D1{"_skip_while_standby"} --> D2["queue.push"] --> D3["mark_command_consumed"] --> D4["profile / avatar / image_parse"] --> D5["_schedule_archive_summary"]
    end
    subgraph 回复决策四道闸
      E1{"command_consumed"} --> E2{"_try_issue_credential"} --> E3{"_is_bot_self"} --> E4{"skip_ai_reply / _consume_ai_reply_block"}
    end
    subgraph 队列与意愿
      F1{"_replying_queues"} --> F2{"_message_has_images"} --> F3["_handle_willing_decision"]
    end
    A3 --> B1
    B2 --> C1
    C2 --> D1
    D5 --> E1
    E4 --> F1
```

行号逐条对应（`event_pipeline.py`）：510 解析 → 511 去重 → 519 工具输入 → 521 入站管线 →
522 被回复消息 → 530 命令 → 542 agent_intent → 546 待机 → 553 入队 → 554 命令标记 →
559 资料 → 560 头像 → 561 图片解析 → 564 档案总结 → 575 命令闸 → 585 凭据 →
592 bot 自查 → 595 插件阻断 → 603 回复中 → 615 含图 → 625 意愿。

三条**副作用早于回复决策**的步骤必须记住：`push`、`mark_command_consumed` 与
`_schedule_archive_summary` 都在「是否回复」之前执行 —— 后面任何一步 `return` 都不会
撤销这三件事（消息已经进队列、已经进总结计数）。
</details>

<details>
### 私聊与群聊的 7 处差异：不是「同一函数换个 queue」

```mermaid
flowchart TD
    subgraph 相同["两条路都走的步骤"]
      S1["safe_parse_model -> 去重 -> 工具输入短路"]
      S2["入站管线 -> 被回复消息 -> 命令系统"]
      S3["agent_intent -> 待机熔断 -> push -> 标记已消费"]
      S4["资料 / 头像 / 图片解析 / 档案总结"]
      S5["命令闸 -> 凭据签发 -> bot 自查 -> 插件阻断"]
    end
    subgraph 不同["分叉点"]
      D1["queue_key：user_id vs group_id"]
      D2["命令触发：私聊直接匹配 vs 群聊需被 @bot"]
      D3["回复入口：private_reply:408 vs willing_decision:625"]
      D4["延迟配置：private_chat_reply_delay_seconds vs at_mention_reply_delay_seconds 都是 5.0s"]
      D5["决策：private_direct 恒 1.0 vs Quail 算术"]
      D6["私聊不走睡眠拦截、不进两条挂起队列"]
    end
    S5 --> D1
    D6 --> D3
```

* 私聊在 `event_pipeline.py:408` 直接调 `_handle_private_reply`，看不到
  `_replying_queues` / `_pending_image_willing` 两段 —— 这两段只在群聊分支
  （`:603`/`:615`）里。私聊消息**永远**会触发一次回复（`skip_ai_reply`、插件阻断、
  bot 自查、凭据、命令五种情况除外）。
* 私聊延迟用的是 `chat.private_chat_reply_delay_seconds`（`config/schemas/bot.py:1875`，
  默认 5.0），**不是** `at_mention_reply_delay_seconds`；两处默认值相同，改错配置项
  时表现为「私聊没延迟」。
* 私聊的 `WillingDecision` 在函数内部现场构造（`:484`，`manager_name="private_direct"`），
  概率恒 1.0，`reasons=("私聊直接回复（跳过意愿管理器）",)` —— 面板里看到这个 manager
  名就说明走的是私聊直通。
</details>

<details>
### 去重窗口：`_recent_message_ids` 是 200 条不可回滚的滑动窗口

```mermaid
flowchart TD
    A["_is_duplicate_message(message)<br/>:257"] --> B{"message_id 为 None?"}
    B -- 是 --> B1["返回 False：不参与去重"]
    B -- 否 --> C["async with _recent_message_ids_lock"]
    C --> D{"message_id in _recent_message_ids?"}
    D -- 是 --> D1["返回 True<br/>调用方 debug 日志后 return"]
    D -- 否 --> E["append 进 deque(maxlen=200)"]
    E --> F["返回 False：继续管线"]
    F --> G{"_handle_agent_tool_input<br/>:270"}
    G -- "bot 自己 or 无挂起人类请求" --> G1["False：继续"]
    G -- "orchestrator 无该方法" --> G1
    G -- "orchestrator 返回 None" --> G1
    G -- "返回了 background 文本" --> G2["queue.push + mark_command_consumed<br/>+ _start_command_sync_reply"]
    G2 --> G3["返回 True：后续 15 步全部短路"]
```

* 窗口是**硬编码 200**（`:124`），与 `max_group_chat_observations` 无关；队列配置成 2000
  也是 200。窗口只按条数淘汰，没有时间维度。
* `append` 发生在**判定之后、后续任何步骤之前**：如果 519~625 任一步抛异常，这条
  `message_id` 已经留在窗口里，同一消息重投会被当重复丢弃（重试不回来）。
* `_handle_agent_tool_input` 排在去重之后，是 17 步里最靠前的「整条事件终结者」：
  它自己会 `push` 并 `mark_command_consumed`（`:279-280`），所以消息不会丢上下文，
  但 `_handle_inbound_raw_event`、命令系统、档案总结都不会执行。
* 工具输入的三道门（`orchestrator.py:550-567`）：`CURRENT_HUMAN_MESSAGE` 必为真
  （只有 `@human_message_entry` 装饰的真实消息入口才置位）、`queue_key` 必须是纯数字、
  必须拿到 `agent_tools` 技能包；任一不满足返回 `None` 即正常管线。
</details>

<details>
### 命令优先级与 consumed 标记：谁置位、谁必须不清理

```mermaid
flowchart TD
    A["CommandService.handle_message"] --> B{"kind == group?"}
    B -- 是 --> B1{"bot_account 在消息的 at 段里?"}
    B1 -- 否 --> B2["consumed=False 移交管线"]
    B1 -- 是 --> C["_registry.match(text)"]
    B -- 否 --> C
    C --> D{"match 到已注册命令?"}
    D -- 否 --> D1["consumed=False<br/>含 /开头但未注册"]
    D -- 是 --> E{"permissions.can(user_id, permission)?"}
    E -- 否 --> E1["发「你没有权限使用 X」<br/>consumed=True"]
    E -- 是 --> F["await command.handler(context)"]
    F --> G{"抛异常?"}
    G -- 是 --> G1["result_text = 命令执行失败: …<br/>仍算 consumed"]
    G -- 否 --> H{"command.sync_reply 或 context.sync_reply?"}
    H -- 是 --> H1["consumed=True<br/>background=命令执行结果"]
    H -- 否 --> I{"result_text 不是 None?"}
    I -- 是 --> I1["_send_text 直接回复"]
    I -- 否 --> I2["handler 自己发过了（如图片）"]
    H1 --> J["事件管道：push + mark_command_consumed"]
    J --> K{"有 background 或 preactivate?"}
    K -- 是 --> K1["_start_command_sync_reply"]
    K -- 否 --> K2["只标记，不回复"]
```

* **被拒也 consumed=True**：权限不足（`commands/service.py:175-182`）与 handler 抛异常
  （`:197-199`）都返回 `consumed=True`。设计意图是「命令消息不再交给 AI 自由发挥」，
  后果是**用户发错命令时 AI 不会兜底解释**，只会收到固定文案或报错文本。
* 命令消息**照常入队**（`:553`，注释：作为上下文保留），另加 `mark_command_consumed`。
  挂起中的回复管线收集新条目时会跳过它但仍写进快照
  （`reply/orchestrator.py:3774-3789`），避免反复拾取。
* 标记桶是 `deque(maxlen=max_size * 2)`（`queue.py:169`，默认配置 = 400），
  `is_command_consumed` 只查 membership；桶满会静默挤掉最旧的 id。
* **易错的坑：管线被拒时不能 `discard` 标记**（`:1406-1414`、`:949-952` 两处同款注释）。
  `start_reply` 返回 `None`（编排器已关闭／同会话管线在跑／冷却中）时，标记可能属于
  另一条**正在运行**的管线；删掉它会让后续消息走意愿路径，破坏分流守卫。现在的写法是
  「启动成功后才 `add`」，失败路径什么都不做。
</details>

<details>
### 三条挂起状态：回复中、含图、回复后积压

```mermaid
flowchart TD
    A["群消息到达且未被前面任何闸拦下"] --> B{"queue_key in _replying_queues?"}
    B -- "是 且 is_pipeline_active" --> B1["_post_reply_willing[queue_key].append"]
    B -- "是 但管线不活跃" --> B2["warning 已清理过期的回复中队列状态<br/>discard 标记后继续"]
    B -- 否 --> C{"_message_has_images?"}
    B2 --> C
    C -- 是 --> C1["_pending_image_willing[queue_key].append"]
    C1 --> C2["create_task _process_pending_image_willing<br/>+ _track_background_task"]
    C2 --> C3["wait_for_queue 超时 = group_agent_silent_timeout_seconds 默认 120"]
    C3 --> C4{"等待抛异常?"}
    C4 -- 是 --> C5["warning 后继续：不能让 pending 永久滞留"]
    C4 -- 否 --> D
    C5 --> D["加 _image_willing_lock 弹出整批 pending"]
    D --> E{"逐条 _handle_willing_decision"}
    E -- "触发回复" --> E1["break：剩余消息留给管线内挂起循环"]
    E -- "未触发" --> E2["处理下一条"]
    E -- "期间进入 _replying_queues" --> E3["剩余 pending 整批转进 _post_reply_willing"]
    C -- 否 --> F["_handle_willing_decision"]
    F --> G["_start_reply_with_tracking"]
    G --> H{"group_chat_reply_lifespan > 0?"}
    H -- 是 --> H1["on_reply_done 直接 pop 掉 _post_reply_willing<br/>消息已在管线挂起循环里处理"]
    H -- 否 --> H2["on_reply_done -> _process_post_reply_queue"]
    H2 --> I["逐条：新消息 return 回填 / 超 60s 跳过 / 含图转 pending"]
```

* 三条状态的**归属**：`_replying_queues` 由 `_start_reply_with_tracking`（`:953`）与
  `_start_command_sync_reply`（`:1415`）**成功启动后**才 add；由 `on_reply_done` 回调
  discard。`_post_reply_willing` 与 `_pending_image_willing` 都是 `dict[str, list]`，
  按 queue_key 分桶，弹出即删（`pop`）。
* **60s 过期判定**：`_process_post_reply_queue` 读 `chat.post_reply_message_timeout_seconds`
  （`config/schemas/bot.py:1879`，默认 60.0），`_is_message_stale` 用
  `epoch_seconds() - message.time > timeout`；`message.time` 为 `None` 时**永不判定过期**
  （`:1530-1535`）。过期消息 `continue` 跳过 —— 不补回复、不重排，直接丢。
* `_process_post_reply_queue` 的「已在回复中」分支用的是 `pending.index(msg)`（`:1056`）——
  同一条消息对象出现两次时会取到第一个下标，回填范围可能偏大（等价消息对象不常见，
  但这是线性 `index` 而非 `enumerate` 的代价）。
* 图片批处理锁 `_image_willing_lock`（`:956-973`）只保护「取列表 + 清理」这段；
  逐条意愿判定在锁外执行，所以同会话可能有并发判定。
</details>

<details>
### 待机与睡眠：两种「不回复」的语义完全不同

```mermaid
flowchart TD
    A["消息完成 命令 / agent_intent 判定"] --> B{"is_standby()?"}
    B -- 是 --> B1["_skip_while_standby 返回 True<br/>日志：Bot 已进入待机，消息不进入回复与记忆管线"]
    B1 --> B2["return：连队列都不 push<br/>命令判定在这之前已执行完"]
    B -- 否 --> C["queue.push + mark_command_consumed"]
    C --> D{"_handle_willing_decision"}
    D --> E{"_sleep_service.is_sleeping()?"}
    E -- 是 --> F["_handle_sleeping_message"]
    F --> G{"is_at_mentioned?"}
    G -- 否 --> G1["日志：睡眠中，消息仅入队不触发回复<br/>（消息已经 push 过了）"]
    G -- 是 --> H{"block_reason_for_message?"}
    H -- 是 --> H1["屏蔽优先于唤醒：不唤醒、不回复"]
    H -- 否 --> I["sleep_service.wake(reason=at_mention_event)"]
    I --> J{"_at_mention_instant_keyword 命中?"}
    J -- 是 --> J1["跳过 at_mention_reply_delay_seconds"]
    J -- 否 --> J2["sleep delay 默认 5.0s"]
    J1 --> K["WillingDecision(wake_up, 1.0)<br/>background_content = wake_prompt()"]
    J2 --> K
    K --> L["_start_reply_with_tracking"]
```

* 待机是**在 push 之前**熔断（`:350-353`/`:546-549`，注释明确要求「必须在 push/档案总结
  之前返回，否则待机期间仍会积压记忆总结任务」）；睡眠是**在 push 之后**只掐回复。
  两者都「不回复」，但待机期间该会话的队列长度不增长，睡眠期间照常增长。
* 唤醒响应（`wake_prompt()`）通过 `background_content` 注入 —— 与命令 sync_reply、
  凭据签发共用同一个参数，这是「非概率触发的三种 1.0 回复」的统一实现方式。
* 凭据签发（`:1417-1472`）：`issuer_id == bot_account` 直接放过（防自我签发）；
  匹配用的是 `_credential_message_text`（纯 text 段拼接，**不含** `event_message__to_text`
  的「发送者: 」前缀，`:1570-1575` 有专门注释）；只有 `permission_denied` 才当「已处理」
  并回绝，`not_found`/`expired` 一律交回正常管线；只有 `newly_issued`（pending → active）
  才发提示并触发回复，重复发送静默但返回 True。
</details>

<details>
### 三类通知怎么进队列：撤回 / 表情回应 / 戳一戳（外加后台通知）

```mermaid
flowchart TD
    A["_handle_notice(event) :1131"] --> B{"notice_type"}
    B -- "private_message_delete / friend_recall" --> B1["safe_parse_model PrivateMessageDelete"]
    B1 --> B2{"user_id 非空?"}
    B2 -- 是 --> B3["_friend_queue.push_notice"]
    B -- "group_message_delete / group_recall" --> C1["safe_parse_model GroupMessageDelete"]
    C1 --> C2{"group_id 非空?"}
    C2 -- 是 --> C3["_group_queue.push_notice"]
    B -- "message_reaction" --> D1["_handle_reaction_notice"]
    D1 --> D2{"message_id 与 emoji_id 都在?"}
    D2 -- 否 --> D3["return：连日志都不记这条"]
    D2 -- 是 --> D4["按 group_id 优先选 _group_queue，否则 user_id 选 _friend_queue"]
    D4 --> D5["_resolve_name 查昵称，超时/异常回退 QQ:id"]
    D5 --> D6["queue.push_reaction(ReactionEntry)"]
    B -- "notify + poke" --> E1["_handle_poke_notice"]
    E1 --> E2{"event.group_id 有值?"}
    E2 -- 是 --> E3["GroupPoke + 群成员名解析 + _build_poke_action_text"]
    E2 -- 否 --> E4["PrivatePoke + 陌生人名解析"]
    E3 --> E5["queue.push_poke(PokeEntry)"]
    E4 --> E5
    B -- 其它 --> F1["只记日志：收到通知[label] 字段串"]
    E5 --> G["_logger.info 收到通知[label] …"]
    D6 --> G
```

入队前的**容量口径**（`message/queue.py`）：

| 方法 | 条目 kind | 权重 | 额外判定 |
|---|---|---|---|
| `push`/`push_history` | MESSAGE | `self_sent_weight` 0.1（自己）/ `forward_weight` 2（合并转发）/ 1.0 | 无 |
| `push_notice` | RECALL | 1.0 | 先 `find_by_message_id` 深拷贝原消息，找不到也入队 |
| `push_reaction` | REACTION | `reaction_weight` 默认 0.2 | **目标消息不在队列里直接 return，静默丢弃**（`queue.py:410-412`） |
| `push_poke` | POKE | `poke_weight` 默认 0.2 | 无 |
| `push_notification` | NOTIFICATION | `self_sent_weight` 0.1 | 永不抛异常 |

还有第六个入口不经过 `_handle_notice`：后台通知由
`ReplyOrchestrator.record_notification`（`reply/orchestrator.py:4712-4738`）写入
`NotificationEntry(source, content)`，**投递与入队是两件事** —— 投递仍归
`BackgroundNotificationHub`，入队只为让 agent 下一轮 transcript 里能看到。
</details>

<details>
### 队列容量与驱逐：权重账本必须与入队用同一个值

```mermaid
flowchart TD
    A["push(key, message, replied_messages)"] --> B["_convert_message<br/>GetSignalMsg* 转成 Group/PrivateMessage"]
    B --> C["_resolve_occurred_at：显式值 > message.time > now"]
    C --> D["_compute_message_weight<br/>自己 0.1 / forward 2 / 其它 1.0"]
    D --> E["_ensure_capacity_for_non_timestamp_entry(entry_weight)"]
    E --> F{"queue 非空 且 weighted + w > max_size?"}
    F -- 是 --> F1["popleft 最旧条目<br/>TIMESTAMP 只弹出不计账"]
    F1 --> F
    F -- 否 --> G{"weighted + w > max_size?"}
    G -- 是 --> G1["返回 False：新条目丢弃<br/>stats.dropped_messages += 1"]
    G -- 否 --> H["_append_timestamp_if_needed<br/>间隔 > 300s 才插时间戳"]
    H --> I["append QueueEntry(weight=w)"]
    I --> J["_message_counts += 1, _weighted_counts += w"]
    J --> K{"oldest_message_id 为 None?"}
    K -- 是 --> K1["置为这条 message_id"]
```

* 容量是**按权重而非按条数**：默认 `max_group_chat_observations` 与
  `max_friend_chat_observations` 都是 200（`config/schemas/bot.py:57/81`），
  `weighted_counts + entry_weight > max_size` 才驱逐（`queue.py:279`），
  时间戳条目权重 0 且不占账。
* `QueueEntry.weight` 是**入队时固化**的（`queue.py:108-112` 的注释记录了一个真实 bug）：
  旧实现驱逐时按 kind 重算（MESSAGE 恒 1.0），入队按内容算（合并转发 2.0），
  于是权重账本单调虚高、队列提前丢弃真实消息。**驱逐与「按权重取最近消息」
  （`iterate_entries_from_newest_weighted`）必须读同一个字段。**
* 单条权重本身超过 `max_size` 时（例如 `forward_weight` 被配成大于观测上限），
  `_ensure_capacity` 返回 False，调用方**放弃插入**并计入 `dropped_messages` →
  `push` 静默无操作，消息在队列里完全不存在。
* `to_text`（`:673`）把 `last_reply_message_id` 当作分隔点，找不到分隔点时补
  `<当前均为新消息，没有上次回复过的内容>`；最后一条消息 @ 了 bot 时追加
  `<最新消息为@你的内容，请回复这句话>`（`:687-688`，判据 `_should_request_reply` 只看
  **最后一条**、且发送者在 `reply_blacklist` 时直接返回 False）。
</details>

<details>
### 后台任务登记与停机 flush：`_stopping` 之后不再派生新任务

```mermaid
flowchart TD
    A["_schedule_archive_summary / 图片挂起 / 其它"] --> B["asyncio.create_task(_run())"]
    B --> C["_track_background_task(task, label, context)"]
    C --> D{"_stopping?"}
    D -- 是 --> D1["task.cancel()：仍然 add 进集合等回调清理"]
    D -- 否 --> E["add 进 _background_tasks"]
    D1 --> E
    E --> F["add_done_callback(_done)"]
    F --> G{"任务结束"}
    G -- 取消 --> G1["CancelledError 静默吞掉"]
    G -- 异常 --> G2["logger.warning label + context"]
    G -- 正常 --> G3["result() 取值（异常同样被上面捕获）"]
    G1 --> H["discard 出 _background_tasks"]
    G2 --> H
    G3 --> H
    I["flush_pending_summaries 停机收尾"] --> J["_stopping = True"]
    J --> K["_cancel_background_tasks：cancel 全部 + gather(return_exceptions)"]
    K --> L["_archive_summary_service.flush_all()"]
    L --> M["未达阈值的摘要被冲刷落盘"]
```

* `_schedule_archive_summary` 的三条前置短路（`:231-236`）：`_stopping` 为真、
  服务未注入、`conversation_id` 为空 —— 任一命中直接 return，**不创建任务**。
* `flush_pending_summaries` 只在关闭流程调用一次，所以 `_stopping` 是一次性置位
  （`:137-139` 注释）；它**不重新订阅事件**（旧 `start()` 的重复订阅已删除）。
* 后台任务异常只 warning，不影响消息路径 —— 档案总结失败不会让用户收不到回复。
  这是刻意的：整个 `_schedule_archive_summary` 与 `_record_archive_summary` 都吞异常
  （`:648-654`）。
* 关停顺序上，`EventGateway.stop()`（退订全部 subscription）由上游负责；
  `EventPipeline.flush_pending_summaries` 只负责「停止派生 + 取消在途 + 冲刷摘要」。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `_recent_message_ids`（deque maxlen=200） | `_is_duplicate_message` 判定为「新」时 append | 只按条数淘汰（自己滚出窗口），无显式清理 | 判定与 append 都成功后才继续；后续步骤抛异常**不回滚**，重投被当重复丢弃 |
| `_replying_queues`（set） | `_start_reply_with_tracking:953`、`_start_command_sync_reply:1415`，**仅当 `start_reply` 返回非 None** | `on_reply_done` 回调 discard；分派时发现标记在但 `is_pipeline_active` 为假则 warning + discard | 管线被拒（返回 None）时**什么都不做**；误 discard 会破坏同会话另一条运行中管线的分流守卫 |
| `_post_reply_willing`（dict） | 回复中收到的新消息（`:605`）、图片挂起批处理中途转存（`:1014`）、回复后队列自回填（`:1055`） | `_process_post_reply_queue` 开头 `pop`；寿命机制下 `on_reply_done` 直接 `pop` 丢弃 | 弹出后逐条处理；早于 `pop` 的异常会让这批消息滞留到下一次回复结束 |
| `_pending_image_willing`（dict） | 含图消息（`:616`）、回复后队列里的含图消息（`:1069`） | `_process_pending_image_willing` 在 `_image_willing_lock` 内 `pop` | `wait_for_queue` 超时/异常只 warning 后继续处理（旧实现直接抛出会让列表永久滞留） |
| `_image_willing_locks`（dict[str, Lock]） | `_image_willing_lock` 首次进入时创建 | `finally` 里 `del`（仍持有同一把锁才删） | 只保护弹出阶段；逐条意愿判定在锁外，同会话可并发 |
| `_command_consumed`（queue.py，deque maxlen=max_size*2） | `mark_command_consumed`：命令命中、工具输入命中 | `clear(key)` / `clear()`；桶满自动挤掉最旧 id | 只做 membership 查询；桶满后旧标记失效 → 老命令消息可能被挂起管线再次拾取 |
| `_background_tasks`（set） | `_track_background_task`；`_stopping` 为真时先 cancel 再 add | `_done` 回调 discard；`_cancel_background_tasks` 整体清空 | 任务异常只 warning（label + context），不影响消息路径 |
| `_stopping`（bool） | `flush_pending_summaries` 一次性置 True | 无（进程生命周期内不再复位） | 置位后 `_schedule_archive_summary` 直接 return，不再派生新任务 |
| `_warmed_up_friends`（set） | `_maybe_warmup_friend_chat` 成功灌完历史后 add | 无（进程内存，重启清空） | 预热超时/失败 return 且**不加入集合** → 下一条私聊会再试一次 |
| 睡眠状态 | `SleepService`（`/sleep`、定时） | `sleep_service.wake(at_mention_event)` 或 `/awake` | 睡眠中消息照常入队，只是不触发回复；唤醒后回复带 `wake_prompt()` 背景 |

## 易错点

* **命令消息在队列里没丢**：`push` 与 `mark_command_consumed` 都执行（`:553-557`），
  标记只影响挂起管线的增量收集（`orchestrator.py:3774-3789` 跳过但写快照）。
  排查「命令之后 AI 又答了一遍」要看挂起收集，而不是看入队。
* **`discard(_replying_queues)` 必须只在启动成功后**：`:949-952` 与 `:1406-1414` 两处
  同款注释说明这是被踩过的坑 —— 管线被拒时删标记会连带删掉同会话另一条运行中管线的
  标记，让后续消息走意愿路径并在同样被拒时丢失。
* **`post_reply_message_timeout_seconds` 只对「回复后队列」生效**：默认 60.0s，
  `message.time` 为 `None` 时永不判过期；超时消息 `continue`，不补回复也不重排。
  改小它等于主动丢消息，改大它会让陈旧消息挤进下一轮上下文。
* **`group_chat_reply_lifespan > 0` 时回复后队列被整批丢弃**（`:934-937`）：
  默认配置 `group_chat_reply_lifespan = 5`（`config/schemas/bot.py:1899`），
  所以**默认路径下 `_process_post_reply_queue` 不会被 `on_reply_done` 调用** ——
  消息由回复管线内部的挂起循环处理。要验证回复后队列逻辑必须先关掉寿命机制。
* **待机与睡眠是两种语义**：待机在 `push` 之前熔断（队列不增长、记忆总结不积压），
  睡眠在 `push` 之后只掐回复（队列照常增长）。两者都「不回复」但排查入口不同。
* **去重窗口硬编码 200**，与 `max_*_chat_observations` 无关；窗口内只看 `message_id`，
  没有时间维度与来源维度 —— 不同会话里出现同一个 `message_id` 会被误判为重复。
* **`_fetch_replied_messages` 是阻塞式的**：队列里找不到被回复消息就同步等 `get_msg`，
  单条 10s 超时（`_get_dependency_timeout_seconds` 硬编码，`:196-197`），
  超时 `continue` 下一条；这会直接拖慢整个事件的入队时间。
* **`reply_blacklist` 命中会让「@ 提醒」整段失效**：`_should_request_reply` 先看发送者
  是否在黑名单，命中直接返回 False，`to_text` 不会追加「最新消息为@你的内容」。
* **`_maybe_cleanup_credentials` 用 `getattr(self, "_last_credential_cleanup", 0.0)`**：
  属性不在 `__init__` 里初始化，靠 `getattr` 默认值兜底；清理间隔 60s，异常静默。
* **图片解析等待超时用的是 `group_agent_silent_timeout_seconds`**（默认 120.0，
  `config/schemas/bot.py:1736`）而不是 `_get_dependency_timeout_seconds()` 的 10s ——
  改「依赖超时」时不要以为图片等待也跟着变。
* **旧 `start()` 的双重订阅已删除**（`:130-139` 注释）：不要再往 `EventPipeline` 加
  事件订阅，唯一入口是 `EventGateway`；否则同一条事件会被投递两次。
* **整条事件链是串行的，`await asyncio.sleep(delay)` 会占住分发循环**：
  `OneBotAdapter._dispatch_loop`（`packages/adapter/src/neobot_adapter/onebot/adapter.py:384-399`）
  与 `EventDispatcher.publish`（`eventing.py:83-122`）都是逐事件 `await`，
  `handle_*_message_event` 返回前下一条事件不会开始处理。私聊 `delay`、@ 提及
  `delay`（都默认 5.0s）因此是**全局**的 5 秒停顿，不是「每个会话各自等 5 秒」；
  事件量大时表现为整体延迟。要改这个语义必须动分发层，不是在管道里加 task。
* **自身发言的过滤在管道里太靠后**（`fix(6)` 的结论）：`_is_bot_self` 在
  `:592`/`:398`，而插件钩子总线在 `gateway.py:89-96` 更早执行 —— 插件一定能看到 bot
  自己发的消息，自我触发只能靠插件侧 `ignore_self=True` 兜。当前 HEAD 的
  `_is_bot_self` 仍在**命令处理之后**：bot 自己发的文本命中命令（如 `/help`）时会真的
  执行命令（`fix(6)` 只修了插件侧，宿主这一半是设计如此，别当 bug 去「修」）。
