---
flow: 07-memory-archive
covers:
  - app/src/neobot_app/runtime/archive_memory_summary.py
  - packages/memory/src/neobot_memory/
  - packages/contracts/src/neobot_contracts/models/memory.py
  - packages/contracts/src/neobot_contracts/ports/memory.py
  - packages/contracts/src/neobot_contracts/ports/archive_memory_access.py
  - packages/contracts/src/neobot_contracts/ports/unit_of_work.py
  - packages/storage/src/neobot_storage/uow.py
  - packages/storage/src/neobot_storage/engine.py
  - packages/storage/src/neobot_storage/_retry.py
  - packages/storage/src/neobot_storage/models.py
  - packages/storage/src/neobot_storage/repositories/archive.py
  - packages/storage/src/neobot_storage/repositories/archive_snapshot.py
verified_against: d37eae4
verified_hash: 4c2dcaf77a0c
---

# 07 档案记忆：自动总结触发 · 三种写入结果 · 溢出压缩与快照

## 范围

本图画「实时消息 → 档案」这条主干，以及它落在三个包里的契约与落库细节：

* 触发：`EventPipeline._schedule_archive_summary`（每条群/私聊消息）→
  `ArchiveMemoryAutoSummaryService.record_message` 的**计数与判据链**；
* 写入：`archive_crud` 工具 → `ArchiveMemoryService.set_with_outcome` 的**三种结果**
  （正常落库／超限先写后压缩／超限拒绝写入）；
* 溢出：`max_total_chars` 被突破后的**两层冷却 + 单飞 + 后台压缩 + 失败回滚**；
* 留痕：`archive_snapshots` 压缩前快照与保留策略；
* 存储：`SqlAlchemyUnitOfWork` 事务边界、SQLite WAL／busy_timeout、`retry_on_lock`、
  乐观锁 `set_if_version`；
* 读取：`ArchiveMemoryAccess` 契约、面板与工具的分页／预览口径。

**不画**（指向相邻图）：

* `archive_memory_summary.py` 的内部细节（提示词拼装、手写工具循环的逐轮判据、手动／批量压缩的
  面板入口与任务状态表、用量统计）→ `docs/flow/07b-archive-summary.md`（待补）；
* 入站消息解析与管道分发 → `02-inbound-message`；回复编排 → `03-reply-pipeline`；
  Agent 类工具循环 → `04-agent-loop`。

**spec 与现实的差异**（先看这三条再读图）：

1. `agent.memory.archive.auto_compact_chars`（默认 200，描述写「超过即触发一次 AI 自动精简」）
   在**全仓只有定义处**（`config/schemas/bot.py:1171`）出现过，没有任何读取点 —— 真正生效的
   只有 `max_total_chars` + `overflow_action` 这一组。
2. `max_chars`（500）与 `group_profile_max_chars`（1500）是**渲染／摘要长度上限**，不是存储上限；
   存储上限只有 `max_total_chars`（10000）。三者互不相干，见细节 4 与细节 9。
3. 自动总结的工具循环是**手写循环**（直接调 `provider.chat`），不走 `neobot_chat` 的 Agent 类；
   轮次、预算、单次调用超时都是这个服务自己的常量（细节见 07b 待补）。

## 流程

```mermaid
flowchart TD
    A["群/私聊消息｜event_pipeline.py:368 / :564<br/>_schedule_archive_summary 每条消息派发后台任务"] --> B["record_message｜archive_memory_summary.py:218<br/>把这条消息记进计数器"]
    B --> C{"前置判据｜:228-250<br/>kind 是 group/private · 非待机 · interval 大于 0 · provider 已装配 · 文本非空"}
    C -- 任一不满足 --> C1["直接 return：这条消息完全不进计数, 也不产生任何档案写入"]
    C -- 全部通过 --> D["锁内 _cached_counter（TTL 30s）+ append｜:256-274<br/>text 截到 800 字, messages 最多留 interval 条"]
    D --> E{"count+1 大于等于 interval ?<br/>群 500 / 私聊 200｜config/schemas/bot.py:1123"}
    E -- 否 --> Z1["本轮不触发总结：计数器已落库, 等下一条消息｜:276"]
    E -- 是 --> F["绕过缓存 _load_counter 重读库内最新｜:260-263"]
    F --> G{"该会话已在 _active_summaries ?｜:282"}
    G -- 是 --> Z1
    G -- 否 --> H{"_retry_ready：now 大于等于 retry_after ?｜:290-298"}
    H -- 否 --> Z1
    H -- 是 --> I["_summarize_and_reset｜:312<br/>_begin_summary 单飞占位, finally 必释放"]
    I --> J["_run_summary 手写工具循环｜:387<br/>20 轮 / 300s 预算 / 单调用超时（细节见 07b 待补）"]
    J -- 成功或部分成功 --> K["_commit_success｜:747<br/>按 count 差值清账, 保留总结期间新到的消息"]
    J -- 失败·预算耗尽·无任何工具成功 --> L["_defer_after_failure｜:766<br/>count 与 messages 原样保留, 写 failures/retry_after"]
    J --> M["工具写档案：archive_crud 转调 set_with_outcome｜archive_service.py:277"]
    M --> N{"超限判定｜:285-289<br/>表不在豁免名单 且 limit 大于 0 且 chars 大于 limit"}
    N -- 未超限 --> N1["ArchiveWriteOutcome：item 已落库, over_limit=False, action=none"]
    N -- overflow_action=reject --> N2["不落库：抛 ArchiveOverflowRejected｜:47<br/>工具回 over_limit + 压缩指引 hint"]
    N -- overflow_action=summarize --> O["先落库再调度｜:326<br/>_schedule_overflow_compression 同步回调, 立即返回"]
    O --> P{"服务侧冷却未过 ?｜:673<br/>_overflow_cooldown_until 用 monotonic + 600s"}
    P -- 冷却中 --> P1["scheduled=False：原文完整保留, 下次写入再试"]
    P -- 已解封 --> Q["后台任务 _run_compression_job → compress_archive<br/>压缩前先 save_snapshot 留痕, 同键最多 10 份（细节见 07b 待补）"]
    Q --> S{"压缩后 chars 小于等于 target ?"}
    S -- 是 --> S1["保留快照 + 清失败退避：面板与工具读到压缩结果"]
    S -- 否或异常 --> S2["set_if_version 回滚原文｜:1155<br/>回滚成功才删本次快照, 否则留痕等人工"]
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant EP as EventPipeline
    participant AS as ArchiveMemoryAutoSummaryService
    participant SK as archive_crud 工具
    participant AMS as ArchiveMemoryService
    participant UOW as SqlAlchemyUnitOfWork
    participant DB as SQLite WAL
    participant PN as Dashboard 面板

    EP->>EP: _schedule_archive_summary 派生后台任务（每条群/私聊消息）
    EP->>AS: record_message(kind, id, text)
    AS->>AMS: get(memory_counter, 会话键)：命中 30s 缓存则不查库
    AS->>AMS: set 计数器 +1（每条消息都落库, 写路径不吃缓存）
    Note over AS: 未到 interval / 冷却中 / 已单飞 → 立刻返回；<br/>这条路径失败只由 EP 记 WARNING, 不影响消息处理
    AS->>AS: _begin_summary 占位 → _run_summary 工具循环（最多 20 轮、300s）
    AS->>SK: 模型的 tool_calls → skill_manager.execute
    SK->>AMS: set_with_outcome(table, key, value, tags)
    AMS->>UOW: uow.archive.set + uow.commit
    UOW->>DB: INSERT ... ON CONFLICT DO UPDATE, version+1
    alt 未超限
        AMS-->>SK: ArchiveWriteOutcome(over_limit=False, action=none)
    else 超限且 summarize
        AMS-->>SK: item 已落库 + hint（先写后压缩, 写入方不被模型调用拖住）
        AMS->>AS: 同步回调 _schedule_overflow_compression(table, key)
        AS->>AS: 冷却 / provider 缺失 / 退避 / 单飞 任一命中 → scheduled=False
        AS->>AS: 否则 create_task 后台压缩, 不等结果
    else 超限且 reject
        AMS-->>SK: 抛 ArchiveOverflowRejected（不落库）
    end
    AS->>AMS: _commit_success 或 _defer_after_failure（短锁读改写, 绝不回写快照）
    AS->>AMS: 后台压缩：save_snapshot → 改写 → 未达标则 set_if_version 回滚
    PN->>AMS: list / list_over_limit / snapshots（只读, 超限清单排除豁免表）
```

## 细节

<details>
### 触发判据链：五个前置 return + 计数阈值 + 两道闸门

```mermaid
flowchart TD
    A["record_message｜archive_memory_summary.py:218"] --> B{"conversation_kind 是 group/private ?｜:228"}
    B -- 否 --> B1["return：其它类型永不计数"]
    B -- 是 --> C{"is_standby 为真 ?｜:230"}
    C -- 是 --> C1["return：待机期不记也不总结"]
    C -- 否 --> D{"_interval_for 取到的 interval 大于 0 ?｜:237, :1846"}
    D -- 否, 0 即禁用 --> D1["return：该会话类型永久不总结"]
    D -- 是 --> E{"self._provider 已装配 ?｜:240"}
    E -- 否 --> E1["return：provider 不可用时连计数都不做"]
    E -- 是 --> F{"_normalize_message_text 后非空 ?｜:248"}
    F -- 否 --> F1["return：纯空白消息丢弃"]
    F -- 是 --> G["锁内读计数器并 append 一条<br/>text 截到 MAX_STORED_MESSAGE_CHARS=800｜:256"]
    G --> H{"count 加 1 大于等于 interval ?｜:260"}
    H -- 是 --> H1["绕过 30s 缓存, _load_counter 重读库内最新｜:263"]
    H -- 否 --> I["_save_counter 落库, messages 只留最后 interval 条"]
    H1 --> I
    I --> J{"count 大于等于 interval ?｜:276"}
    J -- 否 --> J1["本轮结束：等下一条消息再判"]
    J -- 是 --> K{"counter_key 已在 _active_summaries ?｜:282"}
    K -- 是 --> K1["跳过调度：消息保留, 不为每条消息排一个必然超时的任务"]
    K -- 否 --> L{"_retry_ready｜:290：epoch_seconds 大于等于 retry_after"}
    L -- 否 --> L1["失败冷却中：保留待总结消息, 等下一条消息再判"]
    L -- 是 --> M["_summarize_and_reset 入口｜:299"]
```

阈值来自 `config/schemas/bot.py:1123` 的 `AgentMemoryTrigger`：`group_interval=500`、
`private_interval=200`，`0` 表示禁用（`_interval_for` 直接返回 0，与「未配置」同义）。
两道闸门顺序不能换：**先判单飞（K）再判冷却（L）**，因为冷却中的计数器每来一条消息都会
越过 interval，若先判冷却就会在每条消息上多读一次库。
注意 `H` 的「绕过缓存重读」只在**将要触发**时才做：把外部对 counter 行的清零／改冷却
覆盖掉的代价，比每条消息多一次 DB 读大得多。
</details>

<details>
### memory_counter 行的形态与读写时机（为什么它是豁免表）

```mermaid
flowchart TD
    A["memory_counter 一行一个会话<br/>key = group:群号 或 private:QQ号｜:1860"] --> B["value 是 JSON blob｜_save_counter :686"]
    B --> C["count：缓冲中尚未总结的消息条数"]
    B --> D["messages：最多 interval 条, 每条 text 最多 800 字"]
    B --> E["failures / retry_after：只在失败后写入, 缺省不落盘｜:696"]
    A --> F{"读路径｜_cached_counter :637"}
    F -- 命中且未超 30s --> F1["直接返回缓存：把每条消息一次 DB 读加 json.loads 降到 30 秒一次"]
    F -- 过期或未命中 --> F2["_load_counter → archive.get 读库; JSON 解析失败回落 count=0, messages=[]"]
    A --> G{"写路径"}
    G -- 每条消息 --> G1["_save_counter：archive.set 落库并同步刷新缓存"]
    G -- 将要触发总结 --> G2["先 _load_counter 重读, 防止把外部清零整块写回｜:263"]
    G -- 总结成功 --> G3["_commit_success 短锁内按 count 差值清账｜:754"]
    G -- 总结失败 --> G4["_defer_after_failure 只合并冷却字段, 不改 count 与 messages｜:775"]
    A --> H{"容量治理｜archive_service.py:285-289"}
    H -- memory_counter 在 exempt_tables --> H1["永不做长度上限拦截：reject 会让计数写不进去, summarize 会吃掉待总结消息"]
    H -- 其它表 --> H2["参与 max_total_chars 判定, 见细节 4"]
```

`DEFAULT_EXEMPT_TABLES = {memory_counter}`（`archive_service.py:40`）不是优化而是**安全阀**：
500 条 × 800 字 ≈ 400KB 的计数器天然超过任何 `max_total_chars` 上限。装配期由自动总结服务
显式传入 `exempt_tables=(COUNTER_TABLE,)`（`archive_memory_summary.py:207`），以 `COUNTER_TABLE`
为唯一事实来源。缓存 TTL 30 秒的代价是：外部改动最多 30 秒后才可见 —— 因此成功／失败两条
清账路径都必须回库读最新值。
</details>

<details>
### 成功清账 vs 失败退避：count 差值算法与 60→900 秒指数退避

```mermaid
flowchart TD
    A["_run_summary 返回 True｜:560"] --> B["_commit_success｜:747"]
    B --> C["锁内 _load_counter 重读最新：缓存可能已经陈旧 30s"]
    C --> D["arrivals = max（0, count 减 snapshot_count）<br/>用差值而不是下标：总结期间 interval 截断会把最早的挤掉, 下标会错位"]
    D --> E["kept = messages 的尾部 arrivals 条"]
    E --> F["写回 count=len（kept）, messages=kept<br/>新 state 不再带 failures/retry_after, 冷却被清掉"]
    F --> G["下次再攒满 interval 才总结"]
    A2["_run_summary 返回 False 或抛异常｜:561"] --> H["_defer_after_failure｜:766"]
    H --> I["failures = 库里已有值 + 1"]
    I --> J["_backoff_seconds：60 乘 2 的 n 次方, n = min（failures-1, 4）｜:740<br/>60 / 120 / 240 / 480 / 900, 封顶 RETRY_BACKOFF_MAX_SECONDS=900"]
    J --> K["retry_after = epoch_seconds 加 backoff, 与 count/messages 一起落盘"]
    K --> L["下一条越过 interval 的消息由 _retry_ready 放行"]
    H --> M["退避写入自身异常被吞掉, 返回 0：冷却写不进去, 但绝不向上抛"]
    A3["无任何工具成功 / 预算耗尽 / 模型超时且没写入｜:427-448, :528-538"] --> H
    A4["已写入过内容才中止｜_commit_partial_success :358"] --> N["按部分成功清账并 WARNING：档案是增量 append, 重跑会重复写事实"]
```

`count` 的语义是「**缓冲中尚未总结**的消息条数」（`:760-761`），不是累计计数器：
成功后被重置为总结期间新到的条数，所以总量与旧行为一致，但总结期间到达的那几条不会被丢掉。
失败退避是**唯一持久化在数据行里的冷却**（`failures`/`retry_after` 与计数器同一个 JSON），
进程重启后依然生效；而压缩路径的退避与冷却都是纯内存的（见细节 5）。
</details>

<details>
### 一次写入的三种结果：ArchiveWriteOutcome / ArchiveOverflowRejected / ArchiveVersionConflictError

```mermaid
flowchart TD
    A["archive_crud 写入｜_write_archive_entry｜skills/archive_crud.py:333"] --> B["ArchiveMemoryService.set_with_outcome｜archive_service.py:277"]
    B --> C["chars = len（value）<br/>governed = 表名不在 exempt_tables｜:285-287"]
    C --> D{"governed 且 limit 大于 0 且 chars 大于 limit ?"}
    D -- 否 --> E["落库：uow.archive.set + commit<br/>返回 ArchiveWriteOutcome（item, over_limit=False, action=none）｜:322"]
    D -- 是, overflow_action=reject --> F["不落库：返回 item=None 的 outcome｜:303<br/>set 再抛 ArchiveOverflowRejected（NeoBotError + ValueError）｜:47"]
    F --> F1["工具回模型 over_limit / total_chars / max_total_chars / hint<br/>指引先 outline 分页读、再 patch 压缩后重试"]
    D -- 是, overflow_action=summarize --> G["先落库：原文完整保留, 不丢信息｜:326"]
    G --> H["同步调用 _schedule_overflow_compression, 立即返回：写入方不被模型调用拖住"]
    H --> I{"服务侧冷却期内 ?｜:673"}
    I -- 是 --> I1["scheduled=False, hint = 暂未调度, 原文已保留, 下次写入自动重试"]
    I -- 否 --> J{"trigger 回调返回 True ?｜:705"}
    J -- 否, AI 不可用或退避中或已单飞 --> I1
    J -- 是 --> K["写冷却 until = monotonic 加 600s, hint = 已触发后台自动压缩｜:715"]
    B --> L["面板路径 set_if_version 是例外：不判超限, 只记 WARNING｜:365<br/>管理员必须能写入并看见超限, 真正的回收靠压缩"]
```

三种结果对应三条不同出路，别混：

| 结果 | 触发条件 | 是否落库 | 谁消费 |
|---|---|---|---|
| `ArchiveWriteOutcome`（success） | 未超限 | 是 | 工具层直接回 ok |
| `ArchiveWriteOutcome`（over_limit + summarize） | 超限且 action=summarize | **是**（先写后压缩） | 工具回 hint, 后台压缩 |
| `ArchiveOverflowRejected` | 超限且 action=reject | 否 | 工具／上层捕获, 回错误与指引 |
| `ArchiveVersionConflictError` | `set_if_version` 版本不一致 | 否 | 面板 409；压缩回滚失败时保留快照 |

`ArchiveWriteOutcome.ok` 的定义就是 `item is not None`（`:107-110`），它只回答「是否真的落库」，
不回答「是否超限」—— `over_limit=True` 与 `ok=True` 可以同时成立。
</details>

<details>
### 溢出压缩的两层冷却：服务侧 600s 与触发方 60→900s 退避

```mermaid
flowchart TD
    A["写路径超限 → _schedule_overflow_compression｜archive_service.py:677"] --> B{"_in_overflow_cooldown ?｜:673"}
    B -- 是 --> B1["return False：同一键 600s 内不重复触发（overflow_summary_cooldown_seconds）"]
    B -- 否 --> C{"_overflow_trigger 已注入 ?｜:694"}
    C -- 否 --> C1["WARNING 后 return False：只有原内容保留"]
    C -- 是 --> D["调用触发方回调｜archive_memory_summary.py:878"]
    D --> E{"_overflow_max_total_chars 大于 0 ?｜:885"}
    E -- 否 --> E1["return False：容量治理关闭, 压缩入口完全不介入"]
    E -- 是 --> F{"provider 已装配 ?｜:888"}
    F -- 否 --> F1["WARNING 保留原内容等待下次写入重试：不截断, 不写冷却"]
    F -- 是 --> G{"_overflow_retry_ready：epoch 大于等于 retry_after ?｜:896"}
    G -- 否 --> G1["失败退避中：60→120→240→480→900 秒｜:740"]
    G -- 是 --> H{"_begin_summary 拿到 overflow:table:key 单飞位 ?｜:904"}
    H -- 否 --> H1["已有压缩在跑：跳过而不排队"]
    H -- 是 --> I["asyncio.create_task 跑 _run_compression_job｜:912<br/>没有运行中的事件循环时释放占位并 WARNING"]
    I --> J["结束后 add_done_callback 从 _overflow_tasks 移除｜:930"]
    A --> K["冷却只在 trigger 返回 True 时写入｜:714<br/>压缩失败时触发方 clear_overflow_cooldown 立即解封, 重试节奏交给退避｜:970"]
```

**两个时钟不同**，这是排查「为什么压不动」的关键：

* 服务侧冷却用 `time.monotonic()`（`archive_service.py:163, 675, 716`）—— 墙钟跳变不影响，
  但**进程重启即清空**；
* 触发方退避用 `epoch_seconds()`（`archive_memory_summary.py:1819`）—— 同样只在内存里，
  重启后 `_overflow_failures` / `_overflow_retry_after` 归零，压缩会立刻被再试一次。

「失败时不写服务侧冷却」是刻意的（`:684-686` 注释）：若一次失败写 600 秒冷却，
真正的重试节奏就再也由不了退避控制。另外 `MAX_OVERFLOW_BACKOFF_ENTRIES=512` 只做**容量保护**：
超过 512 条且已过期时才清理（`:1823-1831`），长期运行不会无界增长。
</details>

<details>
### 压缩留痕与回滚：快照什么时候留、什么时候删

```mermaid
flowchart TD
    A["compress_archive（table, key, target_chars, source）｜:993"] --> B{"target 不大于 0 ?｜:1013"}
    B -- 是 --> B1["return True：什么都不做（手动路径已被 normalize 拦住）"]
    B -- 否 --> C{"读到的 value 为空 ?"}
    C -- 是 --> C1["return False：条目不存在或空档案"]
    C -- 否 --> D{"chars_before 小于等于 target ?｜:1023"}
    D -- 是 --> D1["return True：已被别的路径压过, 不再调模型"]
    D -- 否 --> E["_save_compression_snapshot 写下压缩前原文｜:1030<br/>快照写失败只 WARNING, 不阻断压缩"]
    E --> F["_build_overflow_compression_prompt + _run_overflow_tool_loop（细节见 07b 待补）"]
    F --> G{"工具循环抛异常 ?｜:1056"}
    G -- 是 --> G1["回滚原文 → 回滚成功才删快照 → 异常上抛, 由任务入口记退避"]
    G -- 否 --> H["重读 value 得到 chars_after｜:1065"]
    H --> I{"tool_successes 不大于 0 或 remaining 大于 limit ?｜:1070"}
    I -- 是 --> I1["记失败退避 + clear_overflow_cooldown｜:1071-1074"]
    I1 --> I2["回滚原文：走 set_if_version（面板路径）——不触发容量治理, 带乐观锁"]
    I2 --> I3{"回滚成功 ?"}
    I3 -- 是 --> I4["删除本次快照：库内已等于原文, 不留无意义的痕｜:1085"]
    I3 -- 否 --> I5["保留快照供人工恢复｜:1174-1176<br/>条目被并发删除时不敢凭空重建"]
    I -- 否 --> J["清退避, INFO 档案超限压缩完成, 保留快照｜:1107"]
```

「宁可不压，不静默丢数据」（R19）全靠这两条：

* **未达标即失败**：压缩后仍大于目标，即使模型确实写了内容，也回滚原文（`:1070-1085`）；
* **回滚走 `set_if_version`**：一是绕过容量治理 —— 否则会形成「回滚 → 再次超限 → 再压缩」的
  死循环；二是带乐观锁，不覆盖并发的人工编辑（冲突时保留快照）。
  回滚的前提是「库内内容确实等于原文」或「成功改回原文」；条目已被删除时返回 False，
  快照保留（`:1174-1176`）。
</details>

<details>
### 快照保留策略与「压缩后可回看」

```mermaid
flowchart TD
    A["压缩开始前 save_snapshot｜archive_service.py:534"] --> B["写 archive_snapshots 一行：value 原文全量<br/>total_chars / version / reason=manual|auto / operator_ip｜models.py:108"]
    B --> C["同一事务内 prune：单键保留最近 MAX_ARCHIVE_SNAPSHOTS_PER_KEY=10 份｜:570"]
    C --> D["全局兜底保留最近 MAX_ARCHIVE_SNAPSHOTS=2000 份｜archive_snapshot.py:121"]
    D --> E["排序 created_at 与 id 倒序, 越旧越先删｜:125-130"]
    E --> F["list_snapshots 默认不含全文, limit 上限也是 10｜:589"]
    F --> G["get_snapshot 读单份全文：面板『查看某份快照』｜:608"]
    G --> H["delete_snapshot：压缩失败且回滚成功时删掉本次｜:621"]
    H --> I["面板 archives/snapshots 只读：不提供一键恢复（A47）"]
    A --> J["存储实现没有 archive_snapshots 时 save_snapshot 返回 None｜:531<br/>压缩照常进行, 只是不留痕"]
```

快照是**压缩前**写的：只有在「模型已经改写过档案」这个不可逆动作之前留一份原文才有意义。
`reason` 区分 `manual`（面板／批量）与 `auto`（写超限自动压缩），`operator_ip` 自动压缩时为
NULL —— 排查「谁把档案压小了」先看这两列。面板没有任何写接口，恢复属于独立工作项
（`models.py:111-113`）。
</details>

<details>
### 存储层：UoW 事务边界 / WAL / retry_on_lock / 乐观锁单语句 UPDATE

```mermaid
flowchart TD
    A["uow_factory 一次调用 = 一个 SqlAlchemyUnitOfWork｜uow.py:21"] --> B["__aenter__ 建 AsyncSession 并挂上 archive / archive_snapshots / messages 等访问层｜:27"]
    B --> C["__aexit__：有异常先 rollback 再 close session｜:40"]
    C --> D["commit 遇 SQLite 锁冲突 → rollback 后抛 RuntimeError『重试整个事务』｜:45"]
    D --> E["retry_on_lock 的正确用法是重放整个事务体, 不是重试 commit｜_retry.py:42"]
    E --> F["判据 _is_locked_error：沿 __cause__ 与 __context__ 链找 4 种文案｜:12"]
    F --> G["退避 0.1s 起翻倍, 上限 2s, 加 0 到 25% 抖动, 默认最多重试 3 次｜:42-49"]
    A --> H["create_engine：SQLite 自动 PRAGMA journal_mode=WAL 与 busy_timeout=5000｜engine.py:25"]
    H --> I["WAL 让读不阻塞写；busy_timeout 的 5 秒内自动等锁, 超时才报 locked"]
    A --> J["archive.set：INSERT ... ON CONFLICT DO UPDATE, version+1｜archive.py:63<br/>单语句 upsert, 不需要先读再写"]
    J --> K["set_if_version：UPDATE ... WHERE version = expected｜:242"]
    K --> L{"rowcount 为 0 ?"}
    L -- 行存在 --> L1["ArchiveVersionConflictError, 带 expected 与 actual：面板 409"]
    L -- 行不存在且 expected=0 --> L2["INSERT ... ON CONFLICT DO NOTHING：并发新建谁先插入谁生效"]
    L -- 行不存在且 expected 非 0 --> L1
    A --> M["tags 以 JSON 字符串存储, 读取兼容旧的逗号分隔格式｜:390-413"]
```

为什么 `commit()` 不允许「rollback 后重试 commit」：仓库层大量使用
`session.execute(insert(...).on_conflict_do_update())`，这类 Core DML 不体现在 ORM 的
new/dirty/deleted 状态里，rollback 之后重试 `commit()` 可能提交成功却**静默丢掉写入**
（`uow.py:46-55`）。正确姿势是调用方用 `retry_on_lock` 包住整个事务体并在 `on_retry` 里
`session.rollback()`。
</details>

<details>
### 读取路径：契约、面板与工具的分页／预览口径

```mermaid
flowchart TD
    A["契约 ArchiveMemoryAccess｜ports/archive_memory_access.py:36<br/>get / set / delete / exists / list"] --> B["ArchiveMemoryAccessWrapper 自动把 int 等键转 str｜:152"]
    B --> C["ArchiveMemoryService 转调 uow.archive｜archive_service.py:218"]
    C --> D["模型侧工具：read_archive / list_archive / archive_stats｜skills/archive_crud.py"]
    D --> E["list_archive 每条只给开头 500 字预览加总字数"]
    D --> F["read_archive 分页：每页 500 字; offset=0 头部, 正数向后, 负数从尾部（-1 为最新页）"]
    D --> G["read_pending_messages：按会话键与下标读 memory_counter 里待总结消息的全文"]
    C --> H["面板 list_items 只回 200 字预览, 详情接口才给全文｜dashboard/archives.py:75"]
    C --> I["list_over_limit：按 value 长度比较 max_chars, updated_at 倒序｜archive.py:217<br/>排除豁免表, 单页上限 500"]
    C --> J["count_over_limit 给批量压缩算 truncated｜:466"]
    I --> K["面板档案页：表清单加每表条目数／最长字数／超限数｜archives.py:117"]
    L["端口分解：ArchiveStorage 只管写, ArchiveQuery 只管读｜ports/memory.py:12, :27"] --> A
```

读取路径的**三层口径**要分清：存储上限 `max_total_chars`（判定与压缩）、渲染上限
`max_chars` / `group_profile_max_chars`（塞进提示词的展示长度）、工具预览
（`list_archive` 500 字、面板 200 字）。三者互相独立：把渲染上限调小不会触发压缩，
把存储上限调小也不会改变提示词里的展示长度。
面板与工具读的是同一条 `ArchiveMemoryService`，不新建数据层（`dashboard/archives.py:5`）。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `memory_counter` 行的 count／messages | `_save_counter`（每条消息都写） | `_commit_success` 按 count 差值清账 | 失败时原样保留：消息不丢, 等下一条消息再判 |
| `memory_counter` 的 failures／retry_after | `_defer_after_failure` | 成功清账时整行覆盖写（新 state 不带这两个键） | 退避写入自身异常被吞, 退化为下一条消息立即重试 |
| `_active_summaries` 单飞位 | `_begin_summary` | `_summarize_and_reset` 的 finally | 无论成功失败都释放；进程崩溃则随进程消失 |
| 服务侧压缩冷却 `_overflow_cooldown_until` | 调度成功时写 monotonic 加 cooldown | 到期自然失效或 `clear_overflow_cooldown` | 压缩失败时触发方主动清除, 避免 600 秒静默 |
| 触发方退避 `_overflow_failures`／`_overflow_retry_after` | `_record_overflow_failure` | 压缩成功时 pop；超 512 条时清已过期项 | 纯内存：进程重启归零, 会立刻再试一次 |
| `archive_snapshots` 行 | `save_snapshot`（压缩前） | 失败且回滚成功时删除；prune 单键 10／全局 2000 | 快照写失败只 WARNING：压缩照跑, 失去留痕 |
| `archive_memories.version` | 每次 `set`／`set_if_version` 加 1 | 不清理（无上限） | 版本冲突抛 `ArchiveVersionConflictError`；压缩回滚失败则保留快照 |
| 手动／批量压缩任务表 `_manual_tasks` | `_new_manual_task` | `_prune_manual_tasks`：结束 1800s 后清, FIFO 50 条, running 永不淘汰 | 进程重启即清空, 面板只当「最近一次操作结果」 |
| 后台压缩任务集合 `_overflow_tasks` | 调度时 `create_task` 并 add | 完成回调 `add_done_callback` 移除 | `wait_pending_overflow_tasks` 只在测试与关闭路径等待 |

## 易错点

* **`auto_compact_chars` 是死配置**：默认 200、描述写着「超过即触发 AI 自动精简」，但全仓
  除 `config/schemas/bot.py:1171` 的定义处外没有任何读取点。改它不会有任何效果 —— 真正生效的
  是 `max_total_chars` + `overflow_action` + `overflow_summary_cooldown_seconds`。
* **两个「上限」不是一回事**：`max_chars`（500）／`group_profile_max_chars`（1500）只决定
  渲染与摘要长度（`_summary_limits` 把它们当作 `user_summary`／`group_summary` 的硬限制），
  与存储上限 `max_total_chars`（10000）无关。
* **`memory_counter` 必须无条件豁免容量治理**：若对它 reject，自动总结连计数都写不进去；
  若对它 summarize，压缩器会去「压缩」待总结消息队列，把尚未总结的消息吃掉。
  误伤的表现是「档案自动总结整体失效」，比超限严重得多。
* **provider 不可用时 `record_message` 提前返回**（`:240`），这条消息**不计入**计数器；
  而失败冷却中仍会每条消息计数落库。前者丢计数，后者只是攒着 —— 排查「消息数对不上」时
  先确认这段时间 provider 是否可用。
* **`flush_all` 不看冷却**（`:791-849`）：关闭收尾时对所有 `0 < count < interval` 的会话
  立即总结，处在失败退避中的会话也会被强行尝试一次；`record_message` 才会判 `_retry_ready`。
  关闭顺序是 `flush_pending_summaries` 先于 `archive_summary_service.close`（`application.py:471, :476`），
  所以刷新时 provider 还活着 —— 但可能拖慢关机（每条最多 300 秒预算）。
* **`_run_summary` 的异常分支没有显式 `return False`**（`:561-569`，函数注解是 `bool`）：
  走到这里会落下返回 `None`。调用方按 falsy 处理，行为正确，但别依赖「返回布尔」这一契约。
* **压缩未达标 = 失败并回滚**，不是「尽力而为」：回滚走 `set_if_version`（面板路径）因此
  **不会**再次触发自动压缩；反过来说，任何绕过 `set` 的写入路径都不参与容量治理。
* **服务侧冷却看 monotonic，触发方退避看 epoch**：两者都是进程内的，重启后冷却全清；
  但 `memory_counter` 里的失败退避是**持久化**的，重启后仍然拦着自动总结。
* **`uow.commit` 不允许「rollback 后重试 commit」**：Core DML 的写入不在 ORM 状态里，
  重试 commit 可能「提交成功但静默丢写入」；正确做法是 `retry_on_lock` 重放整个事务体。
* **面板路径故意不做容量上限拦截**（`set_if_version`，`archive_service.py:365`）：管理员写入
  超限档案只会得到 WARNING，超限条目靠 `list_over_limit` 暴露、由压缩回收；不要把它
  当成「服务端已经拦住」。
* **压缩期间不要整条重写档案**：hint 里明确要求（`archive_service.py:329-331`）—— 模型若在
  后台压缩进行中整条 `save_archive`，会与压缩结果互相覆盖，而 `version` 冲突只在
  `set_if_version` 路径上才报错。
