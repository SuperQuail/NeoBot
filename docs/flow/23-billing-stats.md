---
flow: 23-billing-stats
covers:
  - app/src/neobot_app/statistics/
  - app/src/neobot_app/observability/
  - app/src/neobot_app/cache/
verified_against: 08faa3f
verified_hash: 7a5528dcba88
---

# 23 计费、用量统计与可观测性

## 范围

一次模型调用结束后「钱怎么算、量怎么记、日志怎么留」的完整链路：
`UsageTracker.record`（唯一落点） -> 计费脚本/内置计价 -> `ModelUsageRecord` 落库 -> 报表；
以及日志四类 sink、脱敏、DebugRecorder 事件录制、ContextRecorder 提示词历史、缓存命中计算。
不在这里：模型路由与 provider 契约见 `05-llm-routing.md` / `05b-provider-native-vision.md`；
面板的用量接口见 `09b-dashboard-api.md`。

## 流程

```mermaid
flowchart TD
    A["provider 返回 usage"] --> B["调用方: UsageTracker.record(...)"]
    B --> C{"module 在 _VALID_MODULES 闭集里?"}
    C -- 否 --> C1["debug 日志后直接丢弃"]
    C -- 是 --> D["_ensure_model_cache 重建注册表快照"]
    D --> E["_lookup(registered_key, model_name)"]
    E --> F{"命中 ModelEntry?"}
    F -- 否 --> F1["debug 日志后丢弃（不落库）"]
    F -- 是 --> G{"模型配了 billing_script?"}
    G -- 是 --> H["run_in_executor 到专用线程池<br/>wait_for(timeout=200ms 默认)"]
    H --> I{"脚本结果"}
    I -- 超时 --> I1["SOURCE_TIMEOUT"]
    I -- 抛错 --> I2["SOURCE_ERROR"]
    I -- 无脚本 --> I3["SOURCE_MISSING"]
    I -- 正常 --> I4["SOURCE_BUILTIN + cost_detail"]
    G -- 否 --> J["builtin_cost 按 pricing 算"]
    I1 --> K["写 ModelUsageRecord 一行"]
    I2 --> K
    I3 --> K
    I4 --> K
    J --> K
    K --> L["reporter.generate_all_reports 汇总 5 张表"]
    L --> M["面板用量接口（见 09b）"]
    K -.落库异常.-> N["只记日志，绝不反噬回复"]
    B -.观察.-> O["DebugRecorder 事件 + ContextRecorder 提示词快照"]
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant R as ReplyOrchestrator
    participant T as UsageTracker
    participant B as BillingService
    participant E as 计价线程池
    participant DB as SQLite
    participant P as 面板报表

    R->>T: record(module, model_name, tokens, registered_key)
    T->>T: 白名单校验 + 注册表快照 + _lookup
    alt 配了 billing_script
        T->>B: compute_cost(context)
        B->>E: run_in_executor(脚本)
        E-->>B: cost 或异常或超时
    else 内置计价
        T->>T: builtin_cost(pricing)
    end
    T->>DB: insert ModelUsageRecord（含 source 与 cost_detail）
    DB-->>T: ok 或异常（仅日志）
    P->>DB: 聚合 5 张报表
```

## 细节

<details>
### record 的入参与两道丢弃闸门

```mermaid
flowchart TD
    A["record(module, model_name, input_tokens, output_tokens,<br/>cache_hit_tokens, cache_miss_tokens,<br/>conversation_kind, conversation_id, registered_key)"] --> B{"module ∈ _VALID_MODULES ?"}
    B -- 否 --> B1["debug 跳过"]
    B -- 是 --> C["_ensure_model_cache()"]
    C --> D{"注册表条目集合/id 变化?"}
    D -- 否 --> E["沿用缓存"]
    D -- 是 --> F["重建 _model_info 与 _model_info_by_name<br/>并持强引用防 id() 复用"]
    E --> G["_lookup(registered_key, model_name)"]
    F --> G
    G --> H{"registered_key 命中?"}
    H -- 是 --> I["用该条目"]
    H -- 否 --> J{"model_name 命中 by_name ?"}
    J -- 否 --> K["丢弃（debug）"]
    J -- 是 --> L["用同名最后注册者（兼容历史）"]
```

`_VALID_MODULES`（`tracker.py:24`）是**闭集**：`reply_agent` / `reply_common` / `agent:memory` /
`agent:chat_interaction` / `agent:image_parse` / `agent:willingness` / `agent:scheduled_task` /
`agent:problem_solver` / `agent:self_heal` / `memory_compaction`。
其中 5 个模块（`agent:image_parse` / `agent:chat_interaction` / `agent:willingness` /
`agent:scheduled_task` / `memory_compaction`）全仓**没有任何写入点** —— 只有白名单本身在引用它们，
所以这些能力即使被调用也不会进账（见 FINDINGS 15-2）。
</details>

<details>
### 两级索引：注册 key 优先，同名回落最后注册者

```mermaid
flowchart LR
    A["_model_info: key -> ModelEntry"] --> C["_lookup"]
    B["_model_info_by_name: model_name -> key"] --> C
    C --> D{"registered_key 非空且命中?"}
    D -- 是 --> E["返回该条目"]
    D -- 否 --> F["by_name 回落到 key 再取条目"]
    F --> G["同名条目以**最后注册者**为准"]
```

这段是 spec(4) D19 的产物：默认模型库 4 个 chat 条目的 `model_name` 都是 `deepseek-flash`，
按名字建索引会互相覆盖，所以改成按**注册 key** 建索引（`tracker.py:38-101`）。
但回落仍然存在 —— 而 `NativeVisionFallbackProvider` 不代理 `registered_key`（见 FINDINGS W21），
开原生视觉后这条回落会被真实命中，**计价脚本可能串到别的注册条目**。
</details>

<details>
### 计价三态：脚本 / 内置 / 回落，以及 source 的四个取值

```mermaid
flowchart TD
    A["compute_cost(context)"] --> B{"settings.enabled 且模型配了脚本?"}
    B -- 否 --> C["builtin_cost(pricing, usage)"]
    B -- 是 --> D["_resolve_script_path 单段文件名校验"]
    D --> E{"脚本可加载?"}
    E -- 否 --> E1["SOURCE_MISSING = fallback:missing"]
    E -- 是 --> F["_acquire_slot（BILLING_MAX_INFLIGHT=2）"]
    F --> G{"拿到槽位?"}
    G -- 否 --> G1["按回落处理（不排队堵住调用方）"]
    G -- 是 --> H["executor.submit(脚本, ctx)<br/>线程池 BILLING_MAX_WORKERS=2"]
    H --> I{"wait_for(timeout_seconds 默认 0.2s)"}
    I -- 超时 --> I1["SOURCE_TIMEOUT = fallback:timeout"]
    I -- 抛异常 --> I2["SOURCE_ERROR = fallback:error"]
    I -- 成功 --> I3["SOURCE_BUILTIN = builtin"]
```

**默认 200ms**（`billing.py:47-48 DEFAULT_TIMEOUT_MS`）是硬事实：计价脚本一旦超过 200ms
就静默变成 `fallback:timeout`，报表上的「计费来源分布」里 `fallback:*` 占比高就说明这个。
线程池只有 2 个 worker、同时在跑或排队的上限也是 2（`billing.py:50-52`），
并发高时脚本计价会大量落进回落分支。
</details>

<details>
### cost_detail 与落库字段

```mermaid
flowchart LR
    A["脚本/内置的返回"] --> B["_interpret 归一化"]
    B --> C["BillingOutcome(is_script, to_payload)"]
    C --> D["cost_detail 序列化<br/>上限 MAX_COST_DETAIL_CHARS=8192"]
    D --> E["截断后写 ModelUsageRecord"]
    E --> F["13 列 + 双索引（按时间 / 按模型）"]
```

`cost_detail` 上限是为了「永不因分项过大导致落库失败」（`billing.py:44`）。
落库走 `retry_on_lock`（SQLite 锁重试必须重放整个事务体，见 `22-storage-migrations.md`）。
</details>

<details>
### 报表与聚合口径

```mermaid
flowchart TD
    A["reporter.generate_all_reports"] --> B["UsageReportService（session_factory）"]
    B --> C["按 since 窗口聚合"]
    C --> D["5 张报表：总量 / 按模型 / 按模块 / 计费来源分布 / 时间序列"]
    D --> E["面板 /api/stats/*（见 09b）"]
```

「计费来源分布」是排查计价问题的第一手材料：`builtin` 占比突然升高 = 脚本没生效；
`fallback:*` 升高 = 脚本超时/抛错/找不到。默认模型库 `pricing` 全为 0（见 FINDINGS W27），
所以**不配脚本时 `builtin_cost` 恒为 0**。
</details>

<details>
### 缓存命中计算：字符级近似

```mermaid
flowchart TD
    A["CacheCalculator"] --> B["retention_seconds 默认 1800"]
    A --> C["price_difference 默认 120"]
    B --> D["同一前缀在窗口内重复出现 -> 视为命中"]
    C --> E["命中 token 按价差折算成本节省"]
    D --> F["cache_hit_tokens / cache_miss_tokens"]
    E --> F
    F --> G["写进 record 的 usage 字段"]
```

这是**字符级估算**，不是供应商返回的真实缓存命中数：它按文本前缀在保留窗口内的重复度推断。
报表里的缓存命中率因此是近似值，不要与供应商账单逐字对齐。
</details>

<details>
### 日志：四类 sink 与脱敏

```mermaid
flowchart TD
    A["configure_loguru(data/logs, runtime_events=True)"] --> B["控制台 sink"]
    A --> C["文件 sink neobot.log"]
    A --> D["运行时事件 sink（面板日志页）"]
    A --> E["自修复 sink：ERROR 级 -> SelfHealManager.record"]
    E --> F{"来自 app.self_heal 自己?"}
    F -- 是 --> F1["丢弃，防自激"]
    F -- 否 --> F2["进环形缓冲，按三重门槛触发"]
    B --> G["脱敏：密钥类字段掩码"]
    C --> G
    D --> G
```

自修复的完整触发链见 `04-agent-loop.md`。脱敏在写入前做（面板只读会话另有裁剪，见 `09b`）。
</details>

<details>
### DebugRecorder：事件录制与保留期

```mermaid
flowchart TD
    A["record_packet(packet)"] --> B["按事件类型写 JSONL"]
    C["record_reply_event(event)"] --> D["_serialize_reply_event"]
    D --> E["写单事件 markdown + json"]
    B --> F["prune_expired(force)"]
    E --> F
    F --> G{"超过保留期?"}
    G -- 是 --> H["删除过期文件"]
    G -- 否 --> I["保留"]
```

保留期与开关来自 `debug` 配置；`prune_expired` 是**被动触发**（写入时顺带清理），
没有独立定时器 —— 长时间不产生事件就不会清理。
</details>

<details>
### ContextRecorder：提示词历史为什么「看起来在盘上」其实不在

```mermaid
flowchart TD
    A["每次模型调用前"] --> B["ContextRecorder.record(messages, meta)"]
    B --> C{"第 1 份?"}
    C -- 是 --> D["存完整快照作为基准"]
    C -- 否 --> E["只存相对上一份的 diff（prompt_diff）"]
    E --> F["图片正文换 sha256 哈希（sanitize_images）"]
    D --> F
    F --> G{"超过 limit（默认 100 份）?"}
    G -- 是 --> H["淘汰最旧一份并重新定基"]
    G -- 否 --> I["留在内存"]
    H --> I
    I --> J["面板按 seq 重建：apply_patch 逐份累加"]
```

三条容易记错的性质（`context_recorder.py` 模块 docstring 写明）：

1. **纯内存**：重启即清空，没有 `ctx_*.json` 残留；`legacy_dir` 只用于「清空历史」时删旧文件；
2. **逐份 diff**：回复管线的 messages 逐轮追加，所以补丁极小，100 份常驻约 1–2 MB；
3. **图片只留哈希**：`data:image/...;base64` 换成 sha256（与图库去重同口径），面板不搬 MB 级 base64。

读写异常一律只记 debug，**绝不反噬回复管线** —— 这与聊天流登记的三处 try/except 是同一设计取向。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| 注册表快照缓存 `_cache_stamp` | `_ensure_model_cache`（条目或 id 变化） | 下次重建覆盖 | 持强引用防 `id()` 复用，缓存永不过期式失效 |
| 计费来源 `source` | `compute_cost` 的四条出口 | 不清理（每行独立） | `fallback:missing/error/timeout` 都算「记了账但没算出准确价」 |
| 线程池槽位 | `_acquire_slot` | `_release_slot`（finally） | 拿不到槽位即按回落处理，不阻塞调用方 |
| 自修复环形缓冲 | loguru ERROR sink | 触发后不清空（按窗口计数） | 来自 `app.self_heal` 自身的事件直接丢弃 |
| 提示词历史 | `ContextRecorder.record` | 超限淘汰最旧 + 重启清空 | 读写异常只记 debug |
| DebugRecorder 文件 | `record_*` 写入 | `prune_expired`（写入时被动触发） | 无定时器，长期无事件则不清理 |

## 易错点

* **`_VALID_MODULES` 是闭集且 5 个模块无写入点**：新增能力要记账，必须同时加白名单**和**调用点，
  否则 `record` 静默丢弃（只 debug 日志）。
* **计价超时默认 200ms**：脚本里做网络请求或复杂计算必然落 `fallback:timeout`，
  表现为「费用突然变 0 / 变小」。先看报表的计费来源分布，别先怀疑模型价格。
* **`registered_key` 恒空会让计价串条目**（原生视觉包装器不代理该字段，W21）——
  这是「按模型绑定计价脚本」目前唯一的漏网路径。
* **默认 pricing 全 0**：不配脚本时 `builtin_cost` 恒为 0，「费用为 0」多半是配置缺省而不是 bug。
* **提示词历史不落盘**：面板看到的完整提示词重启即失；想长期留存必须另接（当前不提供）。
* **DebugRecorder 清理是被动的**：保留期到了但进程没写入新事件就不会删文件。
* **缓存命中是字符级估算**：不要用它去核对供应商账单。
