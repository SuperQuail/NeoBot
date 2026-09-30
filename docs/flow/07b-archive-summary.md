---
flow: 07b-archive-summary
covers:
  - app/src/neobot_app/runtime/archive_memory_summary.py
  - packages/memory/src/neobot_memory/archive_service.py
verified_against: 528fe18
verified_hash: ce64fcefcf35
---

# 07b 档案自动总结与压缩：计数触发 · 手写工具循环 · 溢出压缩 · 面板手动/批量入口

## 范围

本图钻 `app/src/neobot_app/runtime/archive_memory_summary.py`（2153 行）的内部，以及它依赖的
`packages/memory/src/neobot_memory/archive_service.py` 里**与容量治理相关的半边**：

* 计数：`record_message` 的读-改-写、30 秒解析缓存、`interval` 截断、单飞与失败退避；
* 总结：`_summarize_and_reset` -> `_run_summary` 的**手写工具轮次循环**（提示词装配、20 轮、
  300s 预算、单次调用超时、工具失败熔断、终止条件）；
* 收尾：`_commit_success` / `_defer_after_failure` 两条清账路径与指数退避；
* 溢出压缩：写路径判定、reject/summarize 两种动作、两层冷却与两层退避、压缩循环与回滚；
* 快照：`save_snapshot` 时机与保留策略、`set_if_version` 回滚为何不再触发容量治理；
* 面板入口：`start_manual_compression` / `start_batch_compression` / `get_manual_task` 与进程内
  任务状态表；关闭收尾 `flush_all`；用量统计与日志观测点。

**不画什么**（指向相邻图）：

* 触发者与入站链路：`EventPipeline._schedule_archive_summary` / `flush_pending_summaries` 的位置、
  入站消息解析 -> `02-inbound-message.md`、`02c-event-pipeline.md`（本图只标调用点）；
* 记忆与档案的整体契约、三种写入结果全貌、存储层事务与乐观锁仓库实现 -> `07-memory-archive.md`；
* 面板端点权限与快照历史页面 -> `09b-dashboard-api.md`；`archive_crud` / `favorability` 工具自身
  的实现 -> `06-tools-skills.md`。

**spec 与现实的差异**（先看这四条再读图）：

1. `agent.memory.archive.auto_compact_chars`（默认 200）是**死配置**：全仓只有定义处
   （`config/schemas/bot.py:1171`），容量治理只认 `max_total_chars` + `overflow_action`（W4）。
2. 自动总结**不走 `neobot_chat` 的 Agent 类**：本文件手写 `provider.chat` 轮次循环，轮次/预算/超时
   全是自己的常量与 `agent.memory.trigger.*` 配置（`:425`）。
3. `flush_all` 与 `record_message` 的判据不一致：关闭收尾不看待机、不看 provider、不看失败退避
   （W17；本图细节 9 补了「不看 provider」这一条）。
4. 两层冷却用**两个时钟**：档案服务侧用 `time.monotonic()`，触发方失败退避与计数器退避用
   `time.time()`（`epoch_seconds`）；只有计数器退避落在库里，另外两个随进程消失（细节 4）。

## 流程

```mermaid
flowchart TD
    A["EventPipeline 每条群/私聊消息派生后台任务｜event_pipeline.py:222"] --> B["record_message｜archive_memory_summary.py:218"]
    B --> C{"五道前置闸门｜:228-250<br/>kind · 待机 · interval · provider · 文本非空"}
    C -- 任一不满足 --> C1["return：不计数不落库，不留任何痕迹"]
    C -- 全通过 --> D["计数器锁内读改写｜:258<br/>_cached_counter TTL 30s；text 截 800 字；只留末 interval 条"]
    D --> E{"count+1 大于等于 interval？｜:260 群 500 私聊 200"}
    E -- 否 --> Z1["结束：计数器已落库，等下一条消息"]
    E -- 是 --> G{"已在 _active_summaries 或 冷却未过？｜:282-298<br/>触发路径会绕过缓存重读库内最新｜:263"}
    G -- 是 --> Z1
    G -- 否 --> H["_summarize_and_reset｜:312 单飞占位 finally 必释放"]
    H --> I["_run_summary 手写工具轮次循环｜:387 轮次 20 · 预算 300s · 单调用超时见 :341"]
    I -- 没有任何待总结消息 --> J["统一清账收口｜:540 _commit_success<br/>有部分失败补 WARNING；正常则 INFO 档案已更新"]
    I -- 至少写入过一次就中止 --> J
    I -- 一次都没写进去 / 异常 --> K["_defer_after_failure｜:766 保留 count 与 messages 并写冷却"]
    I --> L["逐条执行 tool_calls｜:496 失败计数大于等于 3 熔断｜:519"]
    L --> M["工具写档案：archive_crud 转调 set_with_outcome｜archive_service.py:277"]
    M -- 未超限 --> M1["正常落库 action=none"]
    M -- overflow_action=reject --> M2["不落库：ArchiveOverflowRejected｜:47 工具回 hint 指引"]
    M -- overflow_action=summarize --> N["先落库再同步回调｜:326 写入方不被模型调用拖住"]
    N --> O{"服务侧冷却中？｜archive_service.py:673 monotonic + 600s"}
    O -- 是 --> O1["scheduled=False：原文完整保留，下次写入再试"]
    O -- 否 --> P["触发方 _schedule_overflow_compression｜:878<br/>上限 0 · provider 空 · 失败退避 · 单飞 四道闸门"]
    P -- 调度成功 --> Q["create_task(_run_compression_job) 立即返回｜:912 不等结果"]
    P -- 任一闸门拦下 --> O1
    Q --> R["compress_archive｜:993 先存快照，再跑压缩工具循环"]
    R -- 写成功且 remaining 小于等于 target --> R1["保留快照，清空该键失败退避｜:1107"]
    R -- 未达标或没写进 --> R2["set_if_version 回滚原文｜:1155 回滚成功才删本次快照"]
```

主干只有一条：**每条消息计数 -> 攒够 interval -> 手写循环更新档案 -> 写超限则后台压缩**。
三种失败语义要分清：写入被拒（reject，不落库）、压缩没调度（保留原文等下次写入）、
压缩未达标（回滚原文，留下快照）。

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant EP as EventPipeline
    participant AS as ArchiveMemoryAutoSummaryService
    participant PN as 总结模型 provider
    participant EX as skill_manager 工具执行器
    participant AMS as ArchiveMemoryService
    participant ST as 存储与档案快照
    participant DB as Dashboard 面板

    Note over EP,AS: 每条群/私聊消息（派生后台任务，失败只记 WARNING）
    EP->>AS: record_message(kind, id, text, sender)
    AS->>AMS: get(memory_counter, 会话键)：30s 缓存命中则不查库
    AS->>AMS: set 计数器 +1（每条消息都落库，不吃缓存）
    Note over AS: 未到 interval / 单飞 / 冷却中 → 立刻返回；<br/>已到 interval 时冷却与计数一起写库
    AS->>AS: _begin_summary 占位 → _run_summary 手写循环
    AS->>PN: chat(chat_messages, tools)（wait_for 单次调用超时，最多 20 轮）
    PN-->>AS: tool_calls 或纯文本收尾（超时不返回 usage，只能靠日志留痕）
    AS->>EX: 逐个 execute(工具名, 参数)（异常转 Tool error 文本，参与熔断计数）
    EX->>AMS: set_with_outcome(table, key, value, tags)
    AMS->>ST: uow.archive.set + commit（超限也先落库，不丢信息）
    AMS-->>AS: 同步回调 _schedule_overflow_compression(table, key) 返回 bool
    Note over AMS,AS: 服务侧冷却用 monotonic；触发方退避用 epoch；触发方返回 False 时不写冷却
    alt 通过全部闸门
        AS->>AS: create_task 后台压缩（不等结果）
        AS->>AMS: save_snapshot 留痕 → 压缩循环 → 未达标则 set_if_version 回滚
    else 冷却 / AI 不可用 / 退避 / 单飞
        AS-->>AMS: 返回 False，hint 说明原文已保留、下次写入再试
    end
    AS->>AMS: 收尾 _commit_success 或 _defer_after_failure（短锁读改写，绝不回写快照）
    Note over AS,AMS: 部分成功也清账：档案是增量 append，重跑会重复写事实
    DB->>AS: start_manual_compression / start_batch_compression（202 + task_id）
    DB->>AS: get_manual_task(task_id) 轮询（进程内状态表，重启即 404）
    DB->>AMS: list_over_limit / list_snapshots（只读，超限清单排除豁免表）
    Note over EP,AS: 关闭：flush_pending_summaries 取消后台任务后 flush_all；<br/>close() 只关 provider，在途压缩任务没有等待点
```

三条「不致命」的线：**单条消息记录失败**只由 EventPipeline 记 WARNING；**压缩失败**保留原文并退避，
绝不影响写入方；**用量统计失败**只 WARNING（但账单会缺，见细节 10）。

## 细节

<details>
### 计数与触发：五道前置闸门、30 秒解析缓存与两道并发闸门

```mermaid
flowchart TD
    A["record_message｜:218 由 EventPipeline 后台任务调用"] --> B{"kind 是 group/private？｜:228"}
    B -- 否 --> B1["return：notice/request 等一律不计数"]
    B -- 是 --> C{"is_standby()｜:230"}
    C -- 是 --> C1["return：待机期不计数（关闭收尾的 flush_all 不查这一条）"]
    C -- 否 --> D{"_interval_for(kind) 大于 0？｜:237 / :1846"}
    D -- 默认群 500 私聊 200 --> E{"provider 已装配？｜:240"}
    D -- 等于 0 --> D1["return：配置禁用"]
    E -- 否 --> E1["return：provider 不可用（这条消息完全不计数）"]
    E -- 是 --> F{"_normalize_message_text 后非空？｜:248"}
    F -- 否 --> F1["return：空白消息不计数"]
    F -- 是 --> G["_counter_lock(counter_key)｜:258 分片锁，释放后回收 key｜:615"]
    G --> H["_cached_counter：进程内解析缓存，TTL 30s｜:637"]
    H --> I{"count+1 大于等于 interval？｜:260"}
    I -- 否 --> J["append 本条 + count+1，只留末 interval 条｜:264-273"]
    I -- 是 --> K["绕过缓存 _load_counter 重读库内最新，防覆盖外部清零｜:263"]
    K --> J
    J --> L["_save_counter：写库 + 同步缓存｜:686"]
    L --> M{"count 小于 interval？｜:276"}
    M -- 是 --> M1["结束：计数器已落库"]
    M -- 否 --> N{"counter_key 在 _active_summaries？｜:282 只预检"}
    N -- 是 --> M1
    N -- 否 --> O{"_retry_ready：epoch 大于等于 retry_after？｜:290-298"}
    O -- 否 --> O1["debug 日志：保留待总结消息，等冷却结束"]
    O -- 是 --> P["_summarize_and_reset(messages, snapshot_count=count)｜:299"]
```

要点：**计数器是唯一事实来源**，`count` 的语义是「缓冲中尚未总结的消息条数」。缓存只服务读路径，
写路径每条消息都落库（崩溃丢失窗口与旧实现一致）；只有「将要触发总结」这一条路径强制绕过缓存，
因为写回缓存内容会撤消外部对该行的清零或冷却修改（`:261-263` 的注释写明）。
非触发路径仍以 30 秒前的缓存为读-改-写基底：外部进程在这 30 秒内对该行的修改可能被覆盖回去，
这是缓存换性能的已知代价。
`messages` 只保留最后 `interval` 条：冷却期足够长时，最早的待总结消息会被新消息挤出缓冲并**永久丢失**
（没有溢出到别处的暂存区）。
</details>

<details>
### _run_summary 手写循环：20 轮、300s 预算、三种 break 与三种收尾

```mermaid
flowchart TD
    A["_summarize_and_reset｜:312"] --> B["_begin_summary 占位｜:729 无 await，检查与占位原子；finally _end_summary｜:339"]
    B --> C{"messages 为空？｜:396"}
    C -- 是 --> C1["_commit_success 后 return True｜:397（没有 INFO 日志）"]
    C -- 否 --> D["_build_summary_prompt｜:400 / :1921 与 system 指令：增量 patch，不整条重写｜:407-415"]
    D --> E["tools = archive_crud + favorability 的定义｜:419 装配处 _services.py:371"]
    E --> F["deadline = monotonic + max_summary_seconds 默认 300s｜:423 轮次上限 20｜:425"]
    F --> G{"remaining 小于等于 1.0？｜:426"}
    G -- 是且已写入过 --> G1["_commit_partial_success(reason=budget_exhausted) return True｜:430"]
    G -- 是且没写过 --> O1
    G -- 否 --> H["call_timeout = min(显式配置 或 provider.timeout+15 或 60, remaining)｜:341-356"]
    H --> I["wait_for(provider.chat(chat_messages, tools), call_timeout)｜:451<br/>返回后 _record_usage 记用量，异常只 WARNING｜:482"]
    I -- TimeoutError 且已写入过 --> I1["_commit_partial_success(reason=model_call_timeout) return True｜:470"]
    I -- TimeoutError 且没写过 --> I2["raise：交给外层 except 记失败退避｜:481"]
    I -- 正常返回 --> J{"tool_calls 非空且 tool_executor 已装配？｜:489-494"}
    J -- 否 --> J1["break：模型交卷，或执行器未装配（0 成功 0 失败，照样清账）"]
    J -- 是 --> K["逐个执行：参数 JSON 解析失败按空参；异常转 Tool error 文本｜:496-505"]
    K --> M["_is_tool_failure 子串判定并计数；_trim_tool_history 收紧到 60k｜:506-517"]
    M --> N{"累计 tool_failures 大于等于 3？｜:519"}
    N -- 是 --> N1["break：熔断（是累计而非连续，日志措辞是连续失败）"]
    N -- 否 --> F
    J1 --> O{"tool_failures 大于 0 且 tool_successes 等于 0？｜:528"}
    N1 --> O
    O -- 是 --> O1["_defer_after_failure + WARNING return False｜:441-448 预算耗尽 / :530 工具全失败"]
    O -- 否 --> P["_commit_success；有部分失败补 WARNING；INFO 档案已更新 return True｜:540-559"]
    I2 -.-> Q["except Exception：_defer_after_failure + WARNING｜:561-569"]
    Q -.-> Q1["此处没有 return：注解是 bool，实际返回 None（W16），调用方按 falsy 处理"]
```

循环的三种正常出口都落到清账：**模型不再调工具**（break）、**轮次用满**（for 走完）、**工具熔断**（break）。
只有「一次工具都没成功 + 有失败」「预算耗尽且没写过」「抛异常」三种情况才走退避。
`asyncio.wait_for` 的超时不返回 `usage`，服务端却已经计费 —— 所以超时分支专门打一条 WARNING 说明
「本次调用不会计入用量统计」（`:459-468`）。
`_next_call_timeout` 的余量设计（`PROVIDER_TIMEOUT_MARGIN_SECONDS=15`）是让 httpx 先超时并返回可读错误，
而不是在模型仍正常推理时被外层掐断（`:341-347`）。
</details>

<details>
### 清账 vs 退避：count 差值清账、字段覆写顺带复位冷却、60 到 900 秒指数退避

```mermaid
flowchart TD
    A["成功路径 _commit_success｜:747"] --> B["_counter_lock 内回库读最新（刻意不用 30s 缓存）｜:754"]
    B --> C["arrivals = max(0, count - snapshot_count)｜:758"]
    C --> D["kept = messages[-arrivals:]：总结期间新到的消息｜:759"]
    D --> E["写回 {count: len(kept), messages: kept}｜:762"]
    E --> F["副作用：整个字典被替换，failures / retry_after 字段随之消失，冷却自动复位"]
    G["失败路径 _defer_after_failure｜:766"] --> H["_counter_lock 内回库读最新｜:775"]
    H --> I["failures = 旧值 + 1｜:777"]
    I --> J["retry_after = epoch_seconds() + _backoff_seconds(failures)｜:784 墙上钟"]
    J --> K["_counter_state 合并写回：count 与 messages 原样保留｜:780"]
    K --> L{"写库自身抛异常？｜:788"}
    L -- 是 --> L1["吞掉并 return 0：退避没写上，但消息不丢"]
    L -- 否 --> M["返回 failures 供日志 consecutive_failures｜:787"]
    N["_backoff_seconds(failures)｜:740"] --> O["doublings = min(failures-1, 4)｜:742"]
    O --> P["60 × 2^doublings，上限 900s｜:743-745"]
    P --> Q["序列：60 · 120 · 240 · 480 · 900 · 900 且 failures 从 1 起"]
    R["部分成功 _commit_partial_success｜:358"] --> S["先清账再 WARNING，不重跑整批｜:376-385"]
    S --> T["三个触发点：预算耗尽 · 模型调用超时 · 工具失败但至少成功过一次"]
    U["成功但有过工具失败｜:541"] --> V["照常清账 + WARNING 已按部分成功清账｜:545"]
```

用 `count` 差值而不是消息下标：总结期间消息会因 `interval` 截断把最早的挤掉，下标会错位，
而 `count` 每条消息恰好 +1（`:750-752`）。退避整体在计数器锁内完成，失败路径只允许合并冷却字段，
不得改写 `count` / `messages`（`:771-772`）—— 否则会把总结期间新到的消息用旧快照覆盖掉。
**部分成功清账是刻意的**：档案是增量 append，重跑会把同一批事实再写一遍，还会再烧一遍 token，
大概率以同样方式再次中止；代价是「模型没处理完就被销账」只留一条 WARNING（`:370-374`）。
</details>

<details>
### 溢出判定与两层冷却：服务侧 monotonic 600s + 触发方 epoch 退避

```mermaid
flowchart TD
    A["archive_crud.save_archive → set_with_outcome｜archive_service.py:277"] --> B{"表不在豁免名单 且 limit 大于 0 且 chars 大于 limit？｜:285-288"}
    B -- 否 --> B1["正常落库：ArchiveWriteOutcome(action=none)｜:323"]
    B -- reject --> C["不落库：hint 指引先分页读再压，抛 ArchiveOverflowRejected｜:289-311"]
    B -- summarize --> D["先写库并 commit｜:313-315；随后才判是否已超限"]
    D --> E["_schedule_overflow_compression｜:677"]
    E --> F{"_in_overflow_cooldown？｜:673 冷却用 time.monotonic + 600s"}
    F -- 是 --> F1["返回 False：hint 说后台压缩暂未调度，下次写入自动重试｜:333"]
    F -- 否 --> G{"trigger 已注入？｜:694"}
    G -- 否 --> G1["WARNING 没有可用入口，仅保留原内容｜:696"]
    G -- 是 --> H["调用 trigger(table,key)；异常吞成 WARNING 并返回 False｜:704-713"]
    H --> I["触发方 _schedule_overflow_compression｜:878 先查 max_total_chars 大于 0"]
    I --> K{"provider 已装配？｜:888"}
    K -- 否 --> K1["WARNING 保留原内容，等下次写入重试（不截断、不丢弃）"]
    K -- 是 --> L{"_overflow_retry_ready？｜:896 比较 epoch_seconds"}
    L -- 是 --> M{"_begin_summary(overflow:table:key)？｜:904 与总结共用占位集合"}
    M -- 否 --> LM["debug：失败退避中或同一键已有压缩在跑，跳过本次触发"]
    L -- 否 --> LM
    M -- 是 --> N["create_task(_run_compression_job) 立刻返回 True｜:912 写入方不被模型调用拖住"]
    N --> O["服务侧这时才写冷却：monotonic + cooldown_seconds｜archive_service.py:714-717"]
    P["压缩失败收尾｜:1071 / :1815"] --> Q["_record_overflow_failure：epoch + 同一套 60/120/240/480/900 退避（进程内 dict）"]
    P --> R["_clear_overflow_cooldown：清掉服务侧冷却｜:1833 避免 600 秒静默掩盖失败"]
    Q --> S["两层时钟不同步：服务侧看单调钟，触发方看墙上钟；只有计数器退避落库"]
```

**同一套退避算法用在三处**：会话总结（落库）、溢出压缩（进程内 dict）、以及面板手动压缩失败
（也写进溢出压缩这张表，因此一次失败的手动压缩会推迟自动重试）。
服务侧冷却只在 `trigger` 返回 True 时写入；触发方因为 AI 不可用 / 退避 / 单飞而返回 False 时
**不写冷却**，这样「下次写入再试」不会被一次失败锁死 600 秒（`:684-685`）。
`_prune_overflow_backoff` 只在条目数超过 512 时才清理已过期项（`:1823-1831`）。
</details>

<details>
### 压缩循环：target 三种 no-op、与总结同源的预算与熔断、未达标必须回滚

```mermaid
flowchart TD
    A["compress_archive(table,key,target,source)｜:993"] --> B{"limit = _positive_int_or_zero(target) 大于 0？｜:1013"}
    B -- 否 --> B1["return True：等于没压，调用方按成功记账"]
    B -- 是 --> C["get 档案；value 为空 → return False｜:1016-1019"]
    C --> D{"chars_before 小于等于 limit？｜:1023"}
    D -- 是 --> D1["return True：已被别的路径压过，不跑模型也不留快照"]
    D -- 否 --> E["_save_compression_snapshot：写失败只 WARNING，不阻断本次压缩｜:1030 / :1121"]
    E --> F["_build_overflow_compression_prompt：manual 才加硬性目标说明｜:1041 / :1748"]
    F --> G["_run_overflow_tool_loop｜:1650 与总结同一套轮次 20 / 预算 300s / 单次调用超时"]
    G --> H{"循环抛异常？｜:1056"}
    H -- 是 --> H1["先回滚原文；还原成功才删快照；再原样 raise｜:1057-1063"]
    H -- 否 --> I["回读档案，remaining = 当前长度｜:1065"]
    I --> J{"tool_successes 小于等于 0 或 remaining 大于 limit？｜:1070"}
    J -- 否 --> K["成功：清空该键 failures / retry_after，保留快照，INFO 记前后字数｜:1107-1118"]
    J -- 是 --> L["_record_overflow_failure + _clear_overflow_cooldown｜:1071-1074"]
    L --> M["error 文案分两种：未达到目标 / 没有产生有效写入｜:1075-1079"]
    M --> N["_restore_compression_original：库内内容已等于原文也算还原成功｜:1155-1177"]
    N --> O{"还原成功？｜:1083"}
    O -- 是 --> O1["删除本次快照，state.chars_after 回填 chars_before"]
    O -- 否 --> O2["保留快照当唯一副本，state.snapshot_id 保留"]
    O1 --> P["WARNING 未压到上限内，return False｜:1092"]
    O2 --> P
    R["循环内部判据｜:1679-1745"] --> S["预算耗尽 / 模型超时 / 无 tool_calls 都 break；工具失败累计 3 次也 break；返回 (成功数, 失败数)"]
```

判定只看两个量：**至少成功写过一次** 且 **最终长度不超过 target**。因此「模型把档案改写短了但丢了事实」
不会被拦（没有事实保真校验）；反过来「模型只写了一部分、长度已达标」会被当成功保留。
与总结循环的差别：这里预算耗尽 / 超时**不写失败退避**（不算异常），由外层按「未达标」统一收口，
所以不会重复记两次失败。
自动路径的 target 恒为 `max_total_chars`，手动路径是面板传入并经 `normalize_manual_target` 校验的值。
</details>

<details>
### 快照与回滚：压缩前留痕、每键 10 份、回滚走 set_if_version 因此不再触发治理

```mermaid
flowchart TD
    A["压缩开始前 save_snapshot｜archive_service.py:534"] --> B{"uow.archive_snapshots 存在？｜:529"}
    B -- 否 --> B1["WARNING 本次压缩不留痕，返回 None（旧实现 / 测试替身降级）"]
    B -- 是 --> C["access.add 全文 + total_chars + version + reason + operator_ip｜:561<br/>同一事务内 access.prune 每键 10 份、全局 2000｜:570"]
    C --> E["commit 后 INFO 记 snapshot_id 与 pruned｜:576 返回 id"]
    F["未达标 / 循环异常回滚 _restore_compression_original｜:1155"] --> G["get 当前内容｜:1165 读失败只 WARNING 并 return False"]
    G --> H{"条目已被并发删除？｜:1174"}
    H -- 是 --> H1["return False：不凭空重建，保留快照等人工恢复"]
    H -- 否 --> I{"库内内容已等于原文？｜:1177"}
    I -- 是 --> I1["return True：模型根本没写，算还原成功，可以删快照"]
    I -- 否 --> J["set_if_version(table,key,原文,当前 tags,当前 version)｜:1183"]
    J --> K{"抛异常（含乐观锁冲突）？｜:1190"}
    K -- 是 --> K1["WARNING 保留快照供人工恢复；return False"]
    K -- 否 --> L["INFO 已回滚为压缩前原文；return True"]
    M["set_if_version 的治理口径｜archive_service.py:365"] --> N{"超过 limit 且不在豁免表？｜:380"}
    N -- 是 --> N1["只 WARNING，不拦截也不调度压缩（W15）"]
    N -- 否 --> N2["直接写库（带乐观锁，冲突抛 ArchiveVersionConflictError，面板 409）"]
    N1 --> O["因此回滚不会再触发一次自动压缩，避免 回滚 到 超限 到 再压 的循环｜:1160-1161"]
    N2 --> O
    P["快照只在三种情况被删除"] --> Q["① 未达标且回滚成功 ② 循环异常且回滚成功 ③ 面板 delete_snapshot；没有自动过期清理任务"]
    R["成功路径保留快照"] --> S["面板 list_snapshots / get_snapshot 只读；不提供一键恢复接口（A47）"]
```

快照的写入时机由调用方保证：**压缩开始前、拿到 chars_before 之后**（`:547-548`）。写失败只告警，
不阻断压缩本身。删除是保守的：只有确认「库内内容已等于原文」才删，否则快照就是这次失败压缩的唯一副本。
`_set_if_version_fallback` 用于没有原生乐观锁的内存实现（先查后写，有 TOCTOU 窗口，仅开发路径，
`archive_service.py:420-444`）。
</details>

<details>
### 面板手动压缩：目标边界、零 token no-op、与自动压缩抢单飞键

```mermaid
flowchart TD
    A["面板 POST 触发压缩｜dashboard/api.py:2377 先过 _require_manage 并拦内部表"] --> B["start_manual_compression｜:1251"]
    B --> C{"table / key 非空？｜:1265-1268"}
    C -- 是 --> D["normalize_manual_target｜:1235 边界 200 到 max_total_chars 或兜底 100000"]
    C -- 否 --> ERR1
    D -- 越界或非整数 --> ERR1
    D -- 合法 --> F{"同键已有 running 的手动任务？｜:1271 只扫手动任务表"}
    F -- 是 --> F1["直接回「该档案正在压缩中，请稍后查看结果」"]
    F -- 否 --> G{"档案存在？｜:1275"}
    G -- 否 --> ERR1
    G -- 是 --> H{"当前字数小于等于目标？｜:1279"}
    H -- 是 --> H1["A32 零 token no-op：ok=True status=noop task_id=None，绝不调模型｜:1281"]
    H -- 否 --> I{"provider 已装配？｜:1299"}
    I -- 否 --> ERR2
    I -- 是 --> J["_new_manual_task：task_id = 秒级时间戳-自增序号，status=running｜:1519-1531"]
    J --> K{"_begin_summary(overflow:table:key)？｜:1305"}
    K -- 否 --> K1["撤回任务，如实回 status=running task_id=None（自动压缩刚好抢跑）｜:1306-1322"]
    K -- 是 --> L["create_task(_run_compression_job(source=manual))｜:1324"]
    L --> M{"没有运行中的事件循环？｜:1335"}
    M -- 是 --> ERR2
    M -- 否 --> N["登记进 _overflow_tasks；INFO 记 operator_ip 与 task_id｜:1339-1349"]
    N --> O["返回 _task_payload 投影，面板回 202 + task_id｜:1350"]
    P["收尾 _finalize_manual_task｜:1587"] --> Q["status done/failed + finished_at + message（前后字数）"]
    Q --> R["状态表：进程内 dict；已结束记录 TTL 1800s，FIFO 上限 50，running 永不淘汰｜:1566-1585"]
    ERR1["面板 400：ValueError（缺 table/key · 目标越界 · 没有该档案）"] --> Z1["停在：没有任何模型调用，档案未改动"]
    ERR2["面板 503：RuntimeError（provider 未装配 · 无事件循环）"] --> Z1
```

手动路径**不查服务侧冷却、也不查失败退避**，只与自动压缩共用单飞键 `overflow:{table}:{key}`（D16）：
同一键正在跑时如实回「进行中」，不排第二个模型循环。
`manual_target_bounds` 的兜底上限 100000 在 `max_total_chars=0`（容量治理关闭）时生效，
所以单条手动压缩在关闭治理后仍可用（A44）。
任务状态表只当「最近一次操作结果」，历史在 `archive_snapshots`；进程重启即清空，面板查询返回 404
（`dashboard/api.py:2432-2436`）。
</details>

<details>
### 批量压缩：20 条上限、truncated 口径与逐条串行

```mermaid
flowchart TD
    A["面板批量入口｜dashboard/api.py:2439"] --> B["start_batch_compression｜:1355"]
    B --> C["normalize_manual_target：整批一个目标｜:1367"]
    C --> D{"provider 已装配？｜:1368"}
    D -- 否 --> D1["RuntimeError，面板 503"]
    D -- 是 --> E["list_over_limit(scope, limit=20)｜:1371 / archive_service.py:482"]
    E --> F["count_over_limit(scope)｜:1374 上限禁用时恒 0"]
    F --> G["truncated = max(0, 超限总数 - 本次返回条数)｜:1375"]
    G --> H["逐行建档：chars 小于等于 target 标 skipped 并记原因，否则累计 selected_chars｜:1394-1399"]
    H --> I{"还有 pending 条目？｜:1405"}
    I -- 否 --> I1["status=done 直接返回，不起任务（消息说明全部不大于目标）｜:1406-1412"]
    I -- 是 --> J["_new_manual_task(kind=batch)｜:1377 带头 items / skipped / truncated"]
    J --> K["create_task(_run_batch_compression)｜:1415 一并登记进 _overflow_tasks"]
    K --> L["_run_batch_compression｜:1436 逐条串行：任意时刻至多 1 条在跑（A45）"]
    L --> M{"_begin_summary(该条 overflow 键)？｜:1449"}
    M -- 否 --> M1["标 skipped + 原因「该档案正在压缩中」，不排队｜:1451"]
    M -- 是 --> N["status=running → compress_archive(source=manual) → finally _end_summary｜:1461-1482"]
    N --> O{"单条抛异常？｜:1469"}
    O -- 是 --> O1["记失败退避 + 清服务侧冷却，保留原内容｜:1473-1480"]
    O -- 否 --> P["回填 chars_before/after/snapshot_id/error，status=done 或 failed｜:1483-1490"]
    O1 --> P
    P --> Q["finally 汇总：chars_after 只累加 done 条目；status=failed 当且仅当存在 failed｜:1496-1509"]
    R["注意：候选来自 list_over_limit（按全局 max_total_chars 判定）"] --> S["max_total_chars=0 时 list_over_limit 恒空，批量永远 0 条；A44 的兜底只对单条路径成立"]
```

`truncated` 是「超限总数 - 返回条数」，面板据此提示还有多少条没被这次请求覆盖（要分多次点）。
`skipped` 有两个来源：**自身不大于目标**（本次统一目标）与**同键正在被压缩**（自动或其它手动任务），
两者都进同一个 `skipped` 列表，面板如需区分只能看 reason 文本。
批量任务自身的异常被最外层 `except` 兜住，已完成的条目结果不受影响（`:1493-1495`）。
</details>

<details>
### 关闭收尾 flush_all：只刷部分计数、与 record_message 的三处判据差异

```mermaid
flowchart TD
    A["关闭收尾 EventPipeline.flush_pending_summaries｜event_pipeline.py:130"] --> B["先置 _stopping=True 并取消管道后台任务｜:140-141"]
    B --> C["flush_all()｜:791"]
    C --> D["list(COUNTER_TABLE, tags=[auto_summary_counter], limit=10000)｜:798"]
    D --> E{"列举抛异常？｜:801"}
    E -- 是 --> E1["WARNING 后直接 return：本次不刷新任何会话"]
    E -- 否 --> F["Semaphore(50) 并发处理每个计数器｜:808"]
    F --> G["_flush_one：key 需能按冒号拆成 kind/id，且 kind 是 group/private｜:811-819"]
    G --> H{"count 大于 0 且 count 小于 interval？｜:824"}
    H -- 否 --> H1["跳过：空计数与已达标计数都不刷（已达标的早被 record_message 触发）"]
    H -- 是 --> I{"messages 非空？｜:827"}
    I -- 否 --> H1
    I -- 是 --> J["在计数器锁内重新读库复查同样条件｜:835-842 锁内只读不跑模型"]
    J --> K{"复查仍满足？｜:838"}
    K -- 否 --> H1
    K -- 是 --> L["_summarize_and_reset(messages=current, snapshot_count=current_count)｜:843"]
    L --> M{"_begin_summary 占位成功？｜:328"}
    M -- 否 --> M1["return False：并发调用 flush_all 或与正常触发撞车时放弃本次"]
    M -- 是 --> N["照常跑 _run_summary：成功清账，失败写退避并返回 False"]
    N --> O["汇总 flushed = 结果严格为 True 的条数，非 0 才 INFO｜:862-868"]
    P["与 record_message 判据的三处不一致"] --> Q["① 不看 is_standby：待机中关闭也会总结"]
    Q --> R["② 不看 provider 是否为 None：无 provider 时属性错误被 _run_summary 吞成一次失败退避｜:561"]
    R --> S["③ 不看 _retry_ready：退避中的会话被强行总结一次（W17）｜与 :290 对比"]
```

关停顺序（`application.py:467-477`）：先 `flush_pending_summaries`，再 `archive summary service` 的
`close()`；而 `close()` 只关 provider（`:1842-1844`），**不等在途的溢出压缩任务** ——
`wait_pending_overflow_tasks` 在全仓只有测试调用（`app/tests/modules/runtime/*`），生产关闭路径没有等待点。
`flush_all` 的并发语义：`asyncio.gather(..., return_exceptions=True)`，单个计数器异常只 WARNING，
不影响其它会话（`:850-861`）。
</details>

<details>
### 观测点：日志字段、用量统计的两个 kind、面板可见状态

```mermaid
flowchart TD
    A["INFO 档案已更新｜:553"] --> A1["字段 conversation_kind/id · message_count · tool_calls_succeeded"]
    B["WARNING 部分成功清账｜:377 / :545"] --> B1["字段 round · tool_calls_succeeded · reason 或 tool_failures"]
    C["WARNING 失败进入冷却｜:563 字段 error 与 consecutive_failures（写库失败时为 0）"]
    D["WARNING 模型调用超时｜:459"] --> D1["字段 timeout_seconds · request_chars · messages_count · round；说明本次不计用量"]
    E["WARNING 用量记录失败｜:606 字段 input/output_tokens 与 error，这是账单缺口的唯一线索"]
    F["INFO 档案超限压缩完成｜:1109"] --> F1["字段 chars_before/after · target_chars · snapshot_id · source"]
    G["WARNING 压缩未达标｜:1092"] --> G1["字段 chars_before/after · tool_calls_succeeded · tool_failures · consecutive_failures"]
    H["用量统计 _record_usage｜:592"] --> H1["module=agent:memory；model_name 与 registered_key 取自 provider"]
    H1 --> H2["conversation_kind：group/private · archive_manual · archive_overflow｜:86-87"]
    H2 --> H3["conversation_id：总结是会话号；压缩是 table:key｜:1710"]
    I["面板可见状态"] --> I1["_task_payload｜:1616：status · chars_before/after · snapshot_id · operator_ip · message"]
    I1 --> I2["批量另带 items / skipped / truncated / succeeded / failed｜:1638-1647"]
    I --> I3["超限清单与快照来自档案服务：list_over_limit｜:482 · list_snapshots｜:589 · get_snapshot｜:608"]
    I3 --> I4["排查失败压缩的第一现场：archive_snapshots 里留下的那份快照就是唯一完整副本"]
    J["关闭时 INFO 关闭时已刷新档案自动总结｜:865 字段 flushed_count；只在 flushed 非 0 时打印"]
    K["状态第一现场：计数器行 memory_counter:group:xxx｜:697"] --> K1["count · messages · failures · retry_after 四个字段即全部状态"]
```

`agent_prompt_parts()`（`:1904`）把群聊模板与工具定义交给分析页展示，是「模型看到什么」的只读入口；
提示词拼装细节见细节 11。日志字段名即排查时的检索键，例如用 `consecutive_failures` 判断某个会话
是否已经连续失败多轮。
</details>

<details>
### 提示词装配：档案表与长度上限、好感度软约束、截断补救与容量说明

```mermaid
flowchart TD
    A["_build_summary_prompt｜:1921"] --> B["头部：当前时间 + 群聊(群号) 或 私聊(QQ号) + conversation_key｜:1928-1934"]
    B --> C["_render_recent_messages：每条截到 prompt_snippet_chars（默认 120）｜:1881-1897"]
    C --> D{"有消息被截断？｜:1893"}
    D -- 是 --> D1["truncation_note 列出前 20 个序号，要求用 read_pending_messages 按需读全文｜:2001-2010"]
    D -- 否 --> E["不加截断说明"]
    F["_summary_limits｜:1863"] --> G["私聊默认 500（max_chars）· 群聊默认 1500（group_profile_max_chars）"]
    G --> H["群聊写 group_profile + group_summary；私聊写 user_profile + user_summary｜:1938-1953"]
    H --> I["profile 段：全量档只允许 patch append，不读不重写；只有 summary 表允许 save_archive 重写｜:1955"]
    I --> J["favorability 段：群聊逐个活跃发言者，私聊锁定 user_id；单次变化 ±max_change_per_summary（默认 5）｜:1976"]
    J --> K{"item_archive.enabled？｜:1993"}
    K -- 是 --> K1["item 段：关键词键名 + patch append，默认表 item_archive｜:1994"]
    K -- 否 --> L["不写 item 段"]
    M{"max_total_chars 大于 0？｜:2012"} -- 是 --> M1["overflow_note：写明单条上限，并声明超限会被后台自动压缩，不要自己整条重写｜:2014"]
    M -- 否 --> N["不加容量说明"]
    O["压缩提示词 _build_overflow_compression_prompt｜:1748"] --> P["注入 trigger / table_name / key / current_chars / target_chars / hard_limit｜:1776"]
    P --> Q["要求基于 FULL 记录重写；命中省略标记时先用 read_archive 分页读完再写｜:1788-1793"]
    Q --> R["保留事实不许编造；目标约 target 的一半；保存后用 total_chars 自证不超过目标｜:1794-1802"]
    R --> S["_bounded_archive_text：超过 60000 字只保留首尾各半，中间插省略标记｜:2059-2065"]
```

`max_chars` / `group_profile_max_chars` 是**渲染与摘要长度上限**，与存储上限 `max_total_chars` 无关
（三者互不相干，见 07 的说明）。favorability 的 ±N 只是写进提示词的软约束，真正的钳制在工具侧；
但工具侧读的配置键名与 schema 不一致（见易错点）。
压缩提示词的目标与硬上限是两个字段：手动路径下 `target` 是本次要求，`hard_limit` 始终是全局
`max_total_chars`（`:1782-1783`）。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `memory_counter:{kind}:{id}` 行（count / messages / failures / retry_after） | `record_message` 每条消息写库；`_defer_after_failure` 追加冷却字段 | `_commit_success` 整字典覆写，顺带抹掉 failures / retry_after | 计数器写库失败由 EventPipeline 捕获记 WARNING，这条消息不计数 |
| `_counter_cache[key]`（TTL 30s） | `_cached_counter` 读库后 / `_save_counter` 写后 | TTL 到期；下一次写入覆盖 | 缓存永远不是事实来源：触发路径强制回库重读 |
| `_active_summaries`（会话键与 `overflow:table:key` 共用） | `_begin_summary`（无 await，原子） | `_end_summary`：总结 finally、压缩任务 finally、批量每条 finally | 调度失败（无事件循环）时显式 `_end_summary` 释放，不留幽灵占位 |
| `_overflow_failures` / `_overflow_retry_after`（进程内） | `_record_overflow_failure` | 压缩成功时 pop；条目过期且超 512 时 `_prune_overflow_backoff` | 只在内存，重启即重置退避（与计数器退避不同） |
| `_overflow_cooldown_until[(table,key)]`（服务侧，monotonic） | 档案服务在 trigger 返回 True 时写 | `clear_overflow_cooldown`（触发方在压缩失败时调用） | 触发方返回 False 时不写冷却，下次写入可立即重试 |
| `_overflow_tasks` | `create_task` 后 add | 任务完成回调自动 discard | 关闭路径没有等待点：`wait_pending_overflow_tasks` 只有测试调用 |
| `_manual_tasks`（进程内，含 batch 的 items/skipped） | `_new_manual_task` | `_prune_manual_tasks`：已结束且超 1800s，或 FIFO 超 50；running 永不淘汰 | 进程重启即清空，面板按 task_id 查询 404 |
| `archive_snapshots` 行 | 压缩前 `save_snapshot`（同事务内 prune） | 未达标且回滚成功 / 异常且回滚成功 / 面板 `delete_snapshot` | 回滚失败时保留快照，作为这次压缩的唯一副本 |
| 面板 payload 的 status / chars_before/after / snapshot_id / error | `_finalize_manual_task`（单条）与批量 finally 汇总 | 只读投影，无清理 | 轮询不到即进程重启或超出 TTL |
| `provider` 引用 | `install_provider` 换引用（不关旧实例，由调用方清理） | 只有 `close()` 关当前实例 | provider 为 None 时：record_message 早退不计数，触发方拒绝调度，手动入口回 503 |

## 易错点

* **`_run_summary` 异常分支没有 `return False`**（`:561-569`，W16）：注解写 `-> bool`，实际返回 `None`。
  调用方按 falsy 处理所以行为正确，但把返回值直接参与 `is False` 判断会踩坑。
* **`flush_all` 与 `record_message` 判据不一致**（`:791`，W17）：关停收尾不看 `_retry_ready`，退避中的会话
  会被强行总结一次；而且它**也不看 `is_standby`、不看 `provider is None`** —— 没装 provider 时
  `self._provider.chat` 的 `AttributeError` 会被 `_run_summary` 的 `except Exception` 吞成一次失败退避，
  于是每次关闭都给退避中的会话再叠一次 `failures`。
* **两层冷却用两个时钟，且都不落盘**：服务侧 `_overflow_cooldown_until` 用 `time.monotonic()`，
  触发方 `_overflow_retry_after` 用 `time.time()`（改系统时间会影响后者）；只有计数器行的 `retry_after`
  是持久的。重启后溢出退避清零，但服务侧冷却同样清零 —— 「重启后立刻又压一次」是预期行为。
* **回滚不再触发容量治理**（W15）：`set_if_version` 对超限只 WARNING（`archive_service.py:380-389`），
  所以「压缩未达标 -> 回滚 -> 又超限」不会形成压缩循环；代价是面板可以写入超限档案，只能靠
  `list_over_limit` 暴露。
* **`auto_compact_chars` 是死配置**（W4）：`config/schemas/bot.py:1171` 定义，全仓无读取点；改它没有任何效果。
* **清账会顺带清掉失败计数**：`_commit_success` 写回的字典只有 `count` / `messages`（`:762`），
  所以一次成功就把 `failures` / `retry_after` 抹掉 —— 这是冷却复位的实现方式，不是 bug；
  但也意味着「连续失败 3 次后成功一次」无法从计数器行看出历史。
* **预算耗尽/超时都优先「部分成功清账」**：只要成功写过一次就清账、不重试；只有一次都没写进才退避。
  代价是「档案只更新了一半」完全静默，只有一条 WARNING（`:377`）。
* **工具失败是子串匹配**：`_is_tool_failure` 用 `未知工具` / `工具执行失败` / `Tool error` 三个标记
  在**返回值文本**里搜索（`:2122-2125`）。工具正常返回的正文一旦包含这些词就会被计成失败，
  累计 3 次即熔断本轮总结。
* **`tool_executor` 为 None 时循环直接 break**（`:493-494`）：0 成功 0 失败，于是走 `_commit_success` 清账并
  打印「档案已更新」，但档案一个字都没动。装配正常时不会发生（`bootstrap/_services.py:375` 必传），
  测试替身或手工构造实例时要小心。
* **`messages` 缓冲只有 `interval` 条**：长冷却 + 消息洪水会把最早的待总结消息挤出并被覆盖（`:270`），
  那批消息永远不会被总结。`flush_all` 读的也是这同一份缓冲。
* **批量压缩的候选来自 `list_over_limit`（按 `max_total_chars` 判定），不是按本次目标**：
  所以出现「超限 10 条、全部 skipped」是正常的（目标比它们的当前字数还大）；更隐蔽的是
  `max_total_chars=0` 时 `list_over_limit` 恒空 —— 容量治理关闭后**批量入口永远 0 条**，
  而单条手动压缩仍可用（A44 的兜底只覆盖了单条路径，`:1230-1233`）。
* **手动/批量压缩不查服务侧冷却与失败退避**，只抢单飞键：面板可以立刻重压一条刚失败过的档案；
  但手动失败会写进自动压缩的退避表，反过来推迟后台自动重试。
* **快照只在「确认回滚成功」时才删**（`:1084`，`1157-1204`）：回滚失败或条目被并发删除时快照保留，
  面板没有一键恢复接口（A47），恢复要靠人工把快照内容写回。
* **`_favorability_min` / `_favorability_max` 读了从不用**（`:127-128`）；而 `skills/__init__.py:186-188`
  读的键名是 `favorability_max_change` / `favorability_min` / `favorability_max`，schema 里却是
  `favorability.max_change_per_summary` / `min_value` / `max_value`（`bot.py:1201-1212`）。
  结果：提示词里的 ±N 用配置值，工具侧钳制恒为默认 ±5、范围 ±1000 —— 改配置会让两边口径分叉。
* **`_format_counter_message` 是死函数**（`:2151`）：全仓只有定义处；渲染走的是
  `_normalize_counter_message` + `_format_sender`（`:2132`、`:2142`）。
* **关停不等在途压缩**：`close()` 只关 provider（`:1842`），`wait_pending_overflow_tasks` 只有测试调用；
  进程退出时在途的压缩任务可能被丢弃（原文已在库，快照可能残留）。

