---
flow: 16-scheduled-tasks
covers:
  - app/src/neobot_app/runtime/scheduled_tasks.py
  - app/src/neobot_app/runtime/sleep_service.py
  - app/src/neobot_app/runtime/notifications.py
  - app/src/neobot_app/runtime/temp_cleaner.py
verified_against: 96da9ef
verified_hash: 151b959b4f0b
---

# 16 定时任务 · 睡眠 · 后台通知 · 临时清理

## 范围

四条与「时间」相关的链路：

* `ScheduledTaskManager`（888 行）：定时任务的扫描、到点判定、错过窗口、提醒投递与完成标记；
* `SleepService`（307 行）：`/sleep` `/awake` 的睡眠状态机与 ticker；
* `BackgroundNotificationHub`（344 行）：后台任务（绘画/解题等）完成后如何回到会话；
* `temp_cleaner`（191 行）：临时文件清理周期。

不在这里：/sleep、/awake 命令的解析与权限见 `17-commands.md`；睡眠期「仅被@可唤醒」的意愿判定
见 `02b-willing-probability.md`；面板的定时任务接口见 `09b-dashboard-api.md`。

## 流程

```mermaid
flowchart TD
    A["application.start: scheduled_task_manager.start()"] --> B["_run_loop"]
    B --> C["每 tick: scan_due_tasks(now)"]
    C --> D["_list_active_tasks 拉未完成任务"]
    D --> E["_plan_task_scan 计算本次要处理谁"]
    E --> F{"窗口内?"}
    F -- 否 --> F1["_is_missed_window 判错过"]
    F1 --> F2["_log_missed_window 只记日志"]
    F -- 是 --> G["_remind_if_due 判定是否该提醒"]
    G --> H{"_was_notified 已通知过?"}
    H -- 是 --> H1["跳过，避免重复打扰"]
    H -- 否 --> I["_build_reminder_prompt 拼提醒文案"]
    I --> J["_remind_bindings 投递给各绑定会话"]
    J --> K["orchestrator.start_background_reply"]
    K --> L["BackgroundNotificationHub.publish"]
    L --> M["poll(pipeline_key) 由管线取走"]
    M --> N["_consume 回灌到会话"]
    N --> O["mark_completed 标记完成"]
    B -.停机.-> P["shutdown 取消循环"]
    Q["SleepService.ticker"] --> R["_ticker_loop 到期自动唤醒"]
    S["temp_cleaner"] --> T["按周期删过期临时文件"]
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant APP as application
    participant STM as ScheduledTaskManager
    participant OR as ReplyOrchestrator
    participant HUB as NotificationHub
    participant EP as EventPipeline

    APP->>STM: start()
    loop 每个 tick
        STM->>STM: scan_due_tasks(now)
        STM->>STM: _plan_task_scan + _remind_if_due
        alt 需要提醒
            STM->>OR: start_background_reply(提醒文案)
            OR->>HUB: publish(notification)
            EP->>HUB: poll(pipeline_key)
            HUB-->>EP: 文案或 None
            EP->>STM: mark_completed(task_uuid)
        else 窗口已过
            STM->>STM: _log_missed_window（只记日志）
        end
    end
```

## 细节

<details>
### 扫描循环与到点判定

```mermaid
flowchart TD
    A["_run_loop"] --> B["等待下一个 tick"]
    B --> C["scan_due_tasks(now)"]
    C --> D["_list_active_tasks"]
    D --> E["_plan_task_scan(tasks, now)"]
    E --> F["ScheduledTaskWindow.contains(now)"]
    F --> G{"在窗口内?"}
    G -- 是 --> H["进入提醒判定"]
    G -- 否 --> I{"_is_missed_window?"}
    I -- 是 --> J["_log_missed_window"]
    I -- 否 --> K["还没到，跳过"]
    H --> L["_current_window 取当前窗口"]
```

到点判定是**窗口**而不是精确时刻（`ScheduledTaskWindow`，`scheduled_tasks.py:79`）：
窗口内的第一次扫描就会提醒，所以 tick 间隔直接决定提醒的及时性。
错过的任务**只记日志**（`_log_missed_window`，`:500`）不会补发 —— 进程停机期间错过的提醒不会补。
</details>

<details>
### 提醒判定：三重条件与去重

```mermaid
flowchart TD
    A["_remind_if_due(task)"] --> B{"任务已完成?"}
    B -- 是 --> B1["跳过"]
    B -- 否 --> C{"_was_notified 已有通知记录?"}
    C -- 是 --> C1["跳过（去重）"]
    C -- 否 --> D{"_is_one_shot_notification?"}
    D -- 是 --> E["_with_default_notification_policy 套默认策略"]
    D -- 否 --> F["用任务自带策略"]
    E --> G["_build_reminder_prompt"]
    F --> G
    G --> H["_remind_bindings 投递"]
```

去重依据是任务记录里的通知字段（`_was_notified`，`:515`），不是内存标记 —— 进程重启后
仍不会重复提醒同一次。
不主动重试：投递失败只记日志，下一次扫描会重新判定（因为 `_was_notified` 尚未置位）。
</details>

<details>
### 后台通知中枢：publish / poll / consume

```mermaid
flowchart TD
    A["publish(notification)"] --> B["入队 + _mirror_to_message_queue"]
    B --> C{"回调超时?"}
    C -- 是 --> D["_get_callback_timeout_seconds 作为上限"]
    C -- 否 --> E["等待管线 poll"]
    E --> F["poll(pipeline_key)"]
    F --> G{"队列里有匹配项?"}
    G -- 是 --> H["_pop_first_matching 取出"]
    G -- 否 --> I["_sweep_idle_queues 清理空闲队列"]
    H --> J["_try_start_background_reply 尝试直接起回复"]
    J --> K{"能起?"}
    K -- 是 --> L["直接回复"]
    K -- 否 --> M["_requeue 放回队列，等下一轮 poll"]
    L --> N["_consume 收尾"]
```

`_mirror_to_message_queue`（`:131`）是关键设计：通知同时镜像进会话消息队列，
这样**即使 poll 没被调用**，通知也不会凭空消失（下一次构建上下文时它已在队列里）。
`_sweep_idle_queues`（`:196`）按空闲时间清理，避免长期无人取的队列常驻内存。
</details>

<details>
### 睡眠状态机与 ticker

```mermaid
flowchart TD
    A["/sleep 或命令触发"] --> B["parse_sleep_duration 解析时长"]
    B --> C{"解析成功?"}
    C -- 否 --> C1["返回 (None, 错误文案)"]
    C -- 是 --> D["sleep(seconds)"]
    D --> E{"已在睡眠?"}
    E -- 是 --> E1["拒绝（或按实现续期）"]
    E -- 否 --> F["置睡眠状态 + wake_up_at"]
    F --> G["ticker() 起 _ticker_loop"]
    G --> H{"到 wake_up_at?"}
    H -- 否 --> I["_log_remaining 周期性记录剩余"]
    H -- 是 --> J["wake(reason='timer')"]
    K["事件管道被@"] --> L["wake(reason='at_mention_event')"]
    L --> M["wake_prompt() 生成唤醒提示词"]
    J --> M
```

`is_sleeping` / `remaining_seconds` / `wake_up_at` / `wake_up_time_text`（`:148-184`）是只读观测面，
面板与意愿判定都靠它们。`wake_prompt` / `sleep_prompt` / `awake_prompt` 三个提示词方法
（`:260-293`）决定「睡眠/唤醒」时给模型什么上下文。
**睡眠不阻断命令**：命令解析在事件管道里早于意愿判定（见 `02c-event-pipeline.md`）。
</details>

<details>
### 临时清理：阈值与竞态

```mermaid
flowchart TD
    A["temp_cleaner 周期触发"] --> B["枚举临时目录"]
    B --> C{"文件超过 TTL?"}
    C -- 否 --> D["保留"]
    C -- 是 --> E{"被在途任务占用?"}
    E -- 是 --> F["跳过（防删正在写的文件）"]
    E -- 否 --> G["删除"]
```

临时清理与 13 的 `image_pool`（300s TTL，只删引用不删磁盘文件）、14 的图片缓存是**三套独立阈值**：
清理临时文件不会清图片暂存池引用的文件，反之亦然。排查「文件莫名消失」时先确认是哪一套删的。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| 任务通知标记 | `_remind_if_due` 投递成功 | `mark_completed` | 投递失败不置位，下一轮重试 |
| 任务完成状态 | `mark_completed(task_uuid)` | 不清理（终态） | 完成后再扫描直接跳过 |
| 扫描循环 | `start()` -> `_run_loop` | `shutdown()` 取消 | 异常退出会让任务不再被扫描（无自愈） |
| 睡眠状态 | `sleep(seconds)` | `wake(reason)` 或 ticker 到期 | 到点自动唤醒，不依赖外部调用 |
| 通知队列 | `publish` | `poll` 取走 / `_sweep_idle_queues` 清理 | 无消费者时镜像进消息队列兜底 |
| 临时文件 | 各子系统写入 | `temp_cleaner` 按 TTL | 被占用时跳过 |

## 易错点

* **错过的窗口不补发**：`_is_missed_window` 只记日志；停机期间到点的提醒永久消失，需要补发得改这里。
* **任务扫描循环没有自愈**：`_run_loop` 异常退出后不会自动重启 —— 表现为「定时任务全部不再触发」，
  排查时先看循环任务是否还活着。
* **通知有两条路**：`poll` 正常取走 + 镜像进消息队列兜底。改其中一条要同时想另一条，
  否则会出现「重复回复」或「通知丢失」。
* **睡眠不阻断命令**：别把「睡眠 = 全静默」当成事实，命令解析在它之前。
* **三套临时清理阈值**（temp_cleaner / image_pool / 图片缓存）互不影响，排查文件消失要看来源。
* **`ticker` 是协程**：由 `application.background_coros` 拉起，停机时随应用一起取消；
  手工调用 `sleep()` 而不启动 ticker 会导致永不到点自动唤醒。
