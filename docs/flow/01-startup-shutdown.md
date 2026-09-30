---
flow: 01-startup-shutdown
covers:
  - app/src/neobot_app/cli.py
  - app/src/neobot_app/bootstrap/__init__.py
  - app/src/neobot_app/bootstrap/_pipeline.py
  - app/src/neobot_app/bootstrap/_standby_runtime.py
  - app/src/neobot_app/bootstrap/_services.py
  - app/src/neobot_app/runtime/application.py
  - app/src/neobot_app/runtime/standby_service.py
  - app/src/neobot_app/runtime/adapter_supervisor.py
  - app/src/neobot_app/runtime/process_restart.py
  - app/src/neobot_app/runtime/connection_readiness.py
verified_against: 99836cd
verified_hash: bb33a50cf947
---

# 01 启动装配 / 停机 / 软重启 / 待机

## 范围

这张图回答四个问题：**进程怎么起来**（CLI 入口 + 装配顺序）、**每一步失败停在哪**
（启动 13 步 + 回滚清单）、**怎么在不换进程的前提换一代运行时**（待机 + 软重启），
**怎么停才算停**（停机顺序与「超时只是报告」）。

覆盖：`cli.py` 的入口/信号/入口循环、`bootstrap.create_application` 的装配顺序与
核心对象复用、`app/src/neobot_app/bootstrap/_pipeline.py` 的管线与应用组装、
`NeoBotApplication.start/stop`、`ConnectionReadinessProbe`、
`StandbyService` 状态机、`StandbyController` 代际编排、`ProcessRestartSignal`、
`AdapterSupervisor` 监听热重载。

**不画**（各自成图，避免重复）：

* 配置加载/校验/热重载分类本身 → `01b-config-system.md`（待补）
* 入站收帧与队列 → `02-inbound-message.md`；事件网关之后的分派 → `02c-event-pipeline.md`（待补）
* 插件运行时的 `load_registered/start_all` 内部 → `08b-plugin-runtime.md`（待补）
* 面板路由与鉴权 → `09-dashboard.md`（待补）；QQ 命令表 → `17-commands.md`（待补）

**核对时发现的、与直觉或历史记录不符的事实（先读这条再看图）**：

1. **待机期 QQ 命令不可达**。待机的唯一动作是 `NeoBotApplication.stop()`，而
   `_stop_components` **无条件**执行 `event_ingress.stop`
   （`runtime/application.py:457`）；`EventGateway.stop` 会把四个订阅全部退订
   （`runtime/gateway.py:63`）。订阅没了，框架连得再稳也到不了命令服务。于是
   `standby_service.py:274` 的「面板与命令仍可用，/reboot 可软重启运行」与
   `bugfixes/README.md` 里 fix(3) 的「已修复，待真机验证」在 `dfe5416` 上**都不成立**：
   保留入站通道的实现（`retain_ingress`）只在分支 `feat/wip-followups`
   （commit 921cb5b，2026-09-16）上，**不是 HEAD 的祖先**。当前待机只能从面板
   `POST /api/admin/reboot` 恢复。
2. `StandbyController.request_process_restart`（`_standby_runtime.py:285`）除测试外
   **没有任何生产调用方** —— 它不是进程重启入口，真正的入口是宿主服务 `process_restart`
   （面板 `/api/admin/restart` 直接拿它）。
3. `ConnectionTimeoutError`（`runtime/application.py:27`）**已不再被抛出**，
   只保留类型兼容旧 `except` 分支；`cmd_run` 里那个 `except` 是死分支。
4. 「启动 13 步」是 `NeoBotApplication.start` 的阶段计数口径（与 `00-overview.md` 一致）。
   源码没有编号注释：`started.append` 只有 11 个标记，另有 4 个不带标记的阶段
   （连接探针、bot_detector、plugin.start_all、chat_stream）。
5. Windows 上 `signal.SIGTERM` **不会被处理**：`add_signal_handler` 抛
   `NotImplementedError` 时只对 `SIGINT` 回退（`cli.py:51`）。

## 流程

```mermaid
flowchart TD
    A["cli.main｜cli.py:985<br/>先 sanitize_no_proxy_environment"] --> A1{"argv 含 --neobot-python-lsp-worker ?"}
    A1 -- 是 --> A2["run_python_lsp_worker 后 SystemExit<br/>隐藏入口, 不是 Bot 服务"]
    A1 -- 否 --> B["子命令分派｜cli.py:1053"]
    B -- 无子命令 --> C["cmd_run｜cli.py:297<br/>asyncio.run(run())"]
    B -- "init / open_web / firewall-open / sandbox_CP" --> B1["各自子命令, 不起运行时"]
    C --> D["run｜cli.py:37<br/>注册 SIGINT/SIGTERM -> request_stop"]
    D --> E["enable_core_reuse + create_application｜cli.py:61<br/>owns_plugins=False"]
    E --> F{"get_cached_core('standby_service') 为空?"}
    F -- 是 --> F1["遗留单机装配: 直接 run_forever<br/>无待机/软重启"]
    F -- 否 --> G["StandbyController｜cli.py:75<br/>runtime_factory=create_application"]
    G --> H["standby_service.set_hooks｜cli.py:84<br/>on_enter/on_resume/on_onebot_change"]
    H --> I["startup 任务｜cli.py:91<br/>plugin load/start -> controller.start"]
    I --> J["run_entry_loop｜cli.py:144<br/>poll_interval=0.5s"]
    J --> K{"state 的 stopping 或 restart_signal.requested ?"}
    K -- 是 --> L["controller.request_shutdown<br/>-> shutdown 观察窗口 20s"]
    L --> M{"shutdown 确认完成?"}
    M -- 是 --> N["返回 restart -> cmd_run: os.execv｜cli.py:310"]
    M -- 否 --> J
    K -- 否 --> O{"runtime_task 刚结束?"}
    O -- "是, 且 controller.application 空, 且非待机" --> P["state 的 stopping=True<br/>下一轮走停机, 不重启"]
    O -- 否 --> Q["controller.application 非空<br/>-> run_forever 新代际"]
    P --> J
    Q --> J
```

主干只有三个分叉：**要不要停机**（`stopping` / 重启信号）、**停机算不算完成**
（`controller.shutdown()` 的返回值）、**运行时是正常退休还是异常退出**
（`standby_service.is_standby()` 是唯一判据）。

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant CLI as cli.run
    participant SC as StandbyController
    participant APP as NeoBotApplication
    participant SB as StandbyService
    participant AD as OneBotAdapter
    participant PR as 核心插件运行时
    participant PB as ConnectionReadinessProbe

    CLI->>CLI: sanitize_no_proxy_environment + 解析子命令
    CLI->>CLI: enable_core_reuse + create_application(owns_plugins=False)
    CLI->>SB: set_hooks(on_enter/on_resume/on_onebot_change)
    CLI->>PR: load_registered + start_all（core 自持, 不在 app.start 内）
    CLI->>SC: start()
    SC->>APP: start()（初始代际 _initial 直接复用）
    APP->>AD: adapter.start 起反向 WS 监听
    APP->>PB: observe() 最多 30s
    PB-->>APP: ConnectionState（连不上不致命, 绝不抛）
    APP-->>SC: 正常返回 / 抛异常则 _rollback_start 反向释放
    SC-->>CLI: phase=running, application 可运行
    CLI->>APP: run_forever() 阻塞等 _shutdown_event
    Note over CLI,AD: 待机: SB.enter -> on_enter=SC.enter -> _stop_runtime + _sync_adapter
    SC->>APP: request_stop + stop（20s 只报告, 继续 shield 等完）
    APP->>AD: adapter.stop（12s 报告 + 适配器自身 16s 宽限）
    CLI->>CLI: runtime_task 结束但 is_standby 为真 -> 不退出进程
    CLI->>SC: resume -> 新代际 -> controller.application -> run_forever
    Note over CLI,APP: 进程重启: restart_signal.request -> request_shutdown -> 收敛后 os.execv
```

谁等谁：CLI 等 `controller` 的代际切换，`controller` 等 `app.stop()`（20s 后只是
报告，仍继续等），`StandbyService` 等 hook（20s / 120s）。**没有一处把超时当成功**。

## 细节

<details>
### 启动 13 步：每一步失败会怎样

```mermaid
flowchart TD
    S1["S1 file_server.start｜application.py:148"] --> S2["S2 tts_service.initialize（可选）"]
    S2 --> S3["S3 plugin_runtime.load_registered<br/>仅 owns_plugins=True"]
    S3 --> S4["S4 adapter.start 起反向 WS 监听"]
    S4 --> S5["S5 connection_probe.observe 最多 30s"]
    S5 --> S6["S6 bot_detector.refresh（可选）"]
    S6 --> S7["S7 plugin_runtime.start_all<br/>仅 owns_plugins=True"]
    S7 --> S8["S8 chat_stream.initialize"]
    S8 --> S9["S9 emoji_service.start（可选）"]
    S9 --> S10["S10 background_coros 起后台任务"]
    S10 --> S11["S11 browser_lifecycle_manager.start（可选）"]
    S11 --> S12["S12 event_ingress.start 事件入口开通"]
    S12 --> S13["S13 scheduled_task / markdown_image / report 循环"]
    S13 --> OK["_started=True, 启动完成"]
    S1 -.->|任一步抛 BaseException| RB["_rollback_start(started)｜application.py:217"]
    RB -.-> ERR["_cleanup_complete=True + 关未启动协程<br/>再抛出第一个 deferred 异常"]
```

每一步的失败语义（`started` 列表是回滚依据，`application.py:145`）：

| 步 | 阶段 | 失败后果 |
|---|---|---|
| S1 | file_server.start | OSError 直接抛；file_server 已在 started（append 在 await 之前），回滚 stop 幂等 |
| S2 | tts.initialize | 抛；tts 在 started 内，回滚 close |
| S3 | plugin.load_registered | 抛；回滚 stop_all（**仅** standalone 路径；CLI 传 owns_plugins=False，此步与 S7 都被跳过，插件由 cli.py:94 启动） |
| S4 | adapter.start | 端口占用/接收器拒绝重建时抛；OneBotAdapter.start 失败会先 unbind_core + _stopping.set 再抛（adapter.py:154），不会留半启动状态 |
| S5 | connection_probe.observe | **不会失败**：内部 except 转 warning 后按未连接继续（connection_readiness.py:102） |
| S6 | bot_detector.refresh | 抛；无 started 标记，靠回滚里的无条件项（无）——refresh 不持有资源 |
| S7 | plugin.start_all | 抛；回滚 stop_all |
| S8 | chat_stream.initialize | 抛；无显式释放步骤（依赖引擎与存储层清理） |
| S9 | emoji_service.start | 抛；emoji 在 started 内，回滚 stop |
| S10 | background_coros | create_task 本身不抛；异常发生在新任务内，只进日志 |
| S11 | browser_lifecycle.start | 抛；browser 在 started 内，且 browser_instance 与截图/录屏产物是无条件清理项 |
| S12 | event_ingress.start | 同步函数、只做订阅，无 IO 不抛 |
| S13 | scheduled_task_manager / markdown_image_converter / report 循环 | 抛；回滚顺序里 report_task 排第 1，markdown_image 排第 3 |
| OK | _started=True | 之后 stop 才有意义；`dispose` 靠 _started 与 _cleanup_complete 两个标志决定走 stop 还是空回滚 |

失败最终落到哪：`start()` 重新抛出 → `controller._start_runtime` 的
`_wait_stage` 记 `phase=failed` → CLI `startup` 任务捕获异常 →
`standby_service.record_failure` 置 STANDBY（面板仍可用，可修配置后软重启）。
</details>

<details>
### 装配顺序即生效顺序：create_application 的对象顺序表

```mermaid
flowchart TD
    A["_run_once loguru｜bootstrap/__init__.py:656"] --> B["_reuse_or logger_factory"]
    B --> C["_load_config_for_reuse<br/>失败不回写缓存"]
    C --> D["prompt_store / chat_flow_registry / sleep_service / standby_service"]
    D --> E["debug_recorder / storage: 备份 -> 迁移 -> 引擎"]
    E --> F["usage / billing / avatar_store"]
    F --> G["group_queue / friend_queue（每代新建）"]
    G --> H["adapter <- _reuse_or, 核心复用"]
    H --> I["hot_reload_registry + 注册 AdapterSupervisor"]
    I --> J["plugin host: hook_bus / host_facade / 服务注册表"]
    J --> K["memory_svcs / vision_provider / provider"]
    K --> L["emoji / file_server / 运行时 manager / sandbox"]
    L --> M["command_service / skill / plugin_runtime"]
    M --> N["ReplyOrchestrator + 各 manager.set_orchestrator"]
    N --> O["_provider_reload 先 unregister 再 register<br/>排到消费者末尾"]
    O --> P["build_pipelines_and_app<br/>Inbound -> EventPipeline -> Gateway -> NeoBotApplication"]
    P --> Q["_REUSE_ENABLED 时建 ProcessRestartSignal 并注册为宿主服务"]
    Q --> R["command_service.set_restart_callback<br/>绑 application.request_restart"]
```

为什么顺序不能改：**存储先于业务**（usage/avatar 要用引擎）、**适配器先于管线**
（事件一流动，下游必须就绪）、**编排器先于 provider 热重载消费者**（挂载点要齐）。

`_reuse_or` 键（软重启代际之间**复用**，`bootstrap/__init__.py:588`）：
`logger_factory`、`config`、`prompt_store`、`chat_flow_registry`、
`sleep_service`、`standby_service`、`debug_recorder`、`storage`、
`usage`、`avatar_store`、`adapter`、`hot_reload_registry`、
`plugin`、`file_server`、`command_service`、`plugin_runtime`、
`process_restart`；`loguru` 走 `_run_once`（只配置一次）。
复用清单之外的一切（队列、memory_svcs、provider、emoji、编排器、管线、应用本身）**每代重建** ——
这就是「软重启能生效」与「面板不断线」同时成立的原因。

热重载消费者按**注册顺序**生效（`runtime/hot_reload_registry.py:113` 注释「先注册先生效」）：
`AdapterSupervisor` 在 :784 先注册，`_provider_reload` 在 :1182 先 unregister 再
register，所以顺序永远是「适配器先重连 → provider 再重建」。
</details>

<details>
### 连接探针：只观察、不致命，闩锁还要再验活跃连接

```mermaid
flowchart TD
    A["build_pipelines_and_app｜_pipeline.py:381"] --> B{"adapter.requires_connection_wait ?"}
    B -- 否, 内嵌 local 适配器 --> B1["probe=None<br/>只打印 http_url / ws_url"]
    B -- 是, OneBot 反向 WS --> C["ConnectionReadinessProbe<br/>wait_seconds=30.0｜_pipeline.py:36"]
    C --> D["start 第 5 步调用 observe"]
    D --> E{"snapshot 已经 connected ?"}
    E -- 是 --> E1["立即返回, waited_seconds=0"]
    E -- 否 --> F["asyncio.to_thread(adapter.wait_for_connection, 30)"]
    F --> G["AdapterCore.wait_for_connection｜receiver/core.py:155"]
    G --> H{"_connection_established 闩锁置位 ?"}
    H -- 否, 30s 用尽 --> H1["connected=False, wait_timed_out=True"]
    H -- 是 --> I{"active_connections 非空 ?"}
    I -- 否, 刚断开 --> H1
    I -- 是 --> I1["connected=True"]
    F -.->|适配器实现抛异常| J["记 warning, 按未连接继续"]
    H1 --> K["ConnectionState 交给 app._connection_state"]
    I1 --> K
    J --> K
    K --> L["startup_log 措辞: 暂未连接也会说<br/>框架连上后自动开始工作, 无需重启"]
```

三个反直觉点：

1. **超时不是失败**。`observe` 永不抛（`connection_readiness.py:91`）；`wait_seconds`
   被 `max(0.0, ...)` 夹住，传 0 表示「无限等」（`:96` 把 0 转成 `None`）。
   启动流程与已启动组件（面板等）**绝不因为框架还没连上而回滚**（`application.py:159-164`）。
2. **闩锁 + 活跃连接是两条判据**。只看 `_connection_established` 会在「刚断开」或
   「接收器已被放弃」时误报已连接，于是探针会打印「事件管线就绪」而实际收不到事件
   （`receiver/core.py:164-171` 注释）。
3. **状态会清**：`stop()` 把 `_connection_state` 置 `None`
   （`application.py:440`）；`connection_state` 属性在未启动时返回 `None`。
   `describe_requirements`（`:117`）是给面板/日志的诊断出口：address + wait_seconds。
</details>

<details>
### 待机状态机：enter / resume / reboot / set_connect_onebot 与 hook 超时

```mermaid
flowchart TD
    START["StandbyService.__init__｜standby_service.py:46"] --> S0{"start_in_standby 或 _CONFIG_ERROR ?"}
    S0 -- 是 --> SB["_state=STANDBY, reason='启动即待机', operator='config'"]
    S0 -- 否 --> RUN["_state=RUNNING"]
    RUN --> E["enter(reason, operator)"]
    E --> EB{"_transition 为真 ?"}
    EB -- 是 --> EB1["返回 False + _busy_message, 不排队"]
    EB -- 否 --> E2["加锁; 已 STANDBY 则只更新原因并 _persist"]
    E2 --> E3["先落 _state=STANDBY, 再调 on_enter<br/>(装配层注入的 controller.enter)"]
    E3 --> E4["_call_hook 观察窗口 20s<br/>DEFAULT_ENTER_TIMEOUT_SECONDS"]
    E4 -- 超时或失败 --> E5["abort_transition(task) + cancel<br/>已接线时保留 STANDBY, 记 '进入待机未完成：…'"]
    E4 -- 成功 --> E6["_persist 写 data/standby.json"]
    SB --> R["resume(reason, operator)"]
    E6 --> R
    R --> R1["先落 STANDBY + '软重启运行中'<br/>再调 on_resume, 窗口 120s"]
    R1 -- 失败 --> R2["停在 STANDBY, reason='软重启运行失败：…'"]
    R1 -- 成功 --> R3["_state=RUNNING, reason 清空, _persist"]
    R3 --> RB["reboot 只是 resume(reason='软重启') 的别名｜standby_service.py:329"]
```

* `_transition`（`:92`）是「本服务忙 + hook 任务未结束 + 控制器 pending」三者取或：
  任一为真就拒绝新迁移，返回 `_busy_message`，**不排队**（排队会连续重建运行时代际）。
* `_call_hook`（`:107`）超时时做三件事：通知 `abort_transition`（撤销一个
  即将被提交的结果）、`task.cancel()`、返回失败文案；`finished` 回调只负责消费异常，
  **绝不把超时的操作提升成 running**，也不会让旧完成清掉新代际。
* 谁置位谁清理：`_transition_active` 在 `try/finally` 里清；`_state` 只有
  `resume` 成功、`record_failure` 才改写；`_persist` 每次状态变更都落盘，
  `_restore`（`:359`）只恢复 `connect_onebot` —— **待机状态不跨进程恢复**。
* `set_connect_onebot`（`:333`）只有当值与现值不同（或上次失败）才调 hook，
  hook 成功后才提交 `_connect_onebot` 并落盘；hook 用时是 `enter_timeout`（20s）。
</details>

<details>
### StandbyController._perform：谁拥有「正在切换的那一代」

```mermaid
flowchart TD
    A["公开动作 start / enter / resume / shutdown / set_onebot<br/>_standby_runtime.py:205-283"] --> B{"_operation 尚未完成 ?"}
    B -- 是 --> B1["返回 False + _pending_message<br/>'运行时正在切换中, 尚未确认清理完成'"]
    B -- 否 --> C{"exiting 且不是 shutdown ?"}
    C -- 是 --> C1["拒绝启动: '进程正在关闭或等待重启'"]
    C -- 否 --> D["清 _aborted/_failure, _attention.clear<br/>记住 _caller_task"]
    D --> E["create_task 执行 owned_action -> _operation"]
    E --> F{"任务先完成, 还是 _attention 先置位 ?"}
    F -- 任务完成 --> G["finished: 异常 -> phase=failed<br/>正常 -> running 或 idle"]
    F -- 超时/中止先到 --> H["_report_pending: _aborted=True + 写 failure + _attention.set"]
    H --> I["返回 False + pending 文案<br/>任务仍归 _operation, 由 shield 继续等完"]
    G --> J["owned_action 的 finally: 若 _aborted 则 compensate"]
    J --> K["取消路径: cancel_transition -> _abort_operation<br/>补偿任务接管 _operation"]
```

* 观察窗口只有两个数：停机类 `STOP_TIMEOUT_SECONDS=20.0`，启动类
  `START_TIMEOUT_SECONDS=120.0`（`_standby_runtime.py:17-18`）。
  `_wait_stage`（`:195`）超时后调 `_report_pending` 再
  `await asyncio.shield(task)` —— 注释原话：这个无界等待归 `_operation` 所有，
  调用方已经拿到有界失败，取消不能丢弃资源。
* `application` 属性（`:53`）是**唯一**的代际发布口：只有
  `phase == "running"` 且未 `exiting`、未 `_aborted` 才把 app 交给 CLI；
  `_start_runtime` 成功后才写 `_app`，`_stop_runtime` 抛异常时**保留**
  `_app` 以便显式重试，不发布第二个运行时。
* `abort_transition`（`:102`）用「调用方任务同一性」防止旧完成/旧取消去撤销新迁移：
  仅当 `_caller_task is caller` 才生效。
* `request_shutdown` 是同步投递、总是解析当前代际（`:97`）；`_abort_operation`
  对 `_app` 与 `_starting_app` 都发 `request_stop` 并取消启动任务。
</details>

<details>
### 软重启两条路：重建运行时代际 与 换进程（os.execv）

```mermaid
flowchart TD
    subgraph P1["路径 A: 软重启运行, 进程不动"]
      A1["面板 POST /api/admin/reboot｜dashboard/api.py:2628<br/>或 QQ /reboot｜commands/builtin.py:456"] --> A2["StandbyService.reboot -> resume"]
      A2 --> A3["controller.resume｜_standby_runtime.py:230"]
      A3 --> A4["_stop_runtime: request_stop + app.stop<br/>观察窗口 20s"]
      A4 --> A5["_start_runtime: runtime_factory 新建 application<br/>核心对象仍复用"]
      A5 --> A6["app.start 观察窗口 120s<br/>-> _app 发布, phase=running"]
      A6 --> A7["CLI 入口循环发现 controller.application<br/>-> run_forever 新代际"]
    end
    subgraph P2["路径 B: 进程重启, 换进程"]
      B1["面板 POST /api/admin/restart｜api.py:2667"] --> B2["ProcessRestartSignal.request<br/>幂等置位, 广播 waiter"]
      B2 --> B3["watch_restart 的 await wait 返回｜cli.py:159"]
      B3 --> B4["controller.request_shutdown<br/>_shutdown_requested=True"]
      B4 --> B5["入口循环停机路径: 全部收敛后 return True"]
      B5 --> B6["cmd_run: os.execv 原地替换｜cli.py:310"]
      B6 --> B7["frozen 时置 PYINSTALLER_RESET_ENVIRONMENT<br/>win32 参数逐个 list2cmdline 引用"]
    end
    B5 -.->|清理未确认| B8["打印 failure, 进程保持存活<br/>绝不提前 execv"]
```

| 维度 | 路径 A 软重启 | 路径 B 进程重启 |
|---|---|---|
| 触发 | `StandbyService.reboot/resume` | `ProcessRestartSignal.request`（面板；`request_process_restart` 无生产调用方） |
| 面板 | 不断线（面板属核心插件运行时） | 断线，进程换掉后重连 |
| 重建范围 | 每代重建 bot 侧对象；15 个核心对象复用 | 全部重来（含日志、数据库引擎、插件） |
| 收敛判据 | `controller.resume` 返回 True 且 `application` 非空 | `controller.shutdown` 返回 True 且 `runtime_task` 已结束 |
| 失败停在哪 | 停在 STANDBY，reason='软重启运行失败：…' | 停在原进程，打印 failure 并 0.5s 后重试；不 execv |
| 出口 | 无（继续跑） | `os.execv`（`cli.py:325`），解释器 flags 经 `sys.orig_argv` 保留 |

`ProcessRestartSignal` 的三个语义（`runtime/process_restart.py`）：请求**先于** waiter
也保留（`:44` 先查 `_requested`）、重复请求合并（`:26` 已置位直接返回）、
取消 waiter 不清除意图（`:53` 只从集合移除）。所以「先点重启、再等 0.5s 的延迟回调」
不会漏，也不会重。
</details>

<details>
### 入口循环 run_entry_loop：判据、0.5s 心跳 与 finally 兜底

```mermaid
flowchart TD
    A["run_entry_loop｜cli.py:144<br/>poll_interval=0.5s"] --> B["watch_restart: await restart_signal.wait<br/>返回即 controller.request_shutdown"]
    B --> C{"stopping 或 restart 为真 ?"}
    C -- 是 --> D["controller.request_shutdown, 幂等可重复调"]
    D --> E{"startup_task 已完成 ?"}
    E -- 否 --> E1["cancel 但保留任务<br/>'startup 清理仍在进行…'"]
    E -- 是 --> F["await controller.shutdown, 内部窗口 20s"]
    F --> G{"ok 且 runtime_task 已收敛 ?"}
    G -- 否 --> G1["打印 failure, 去重后下一轮重试"]
    G -- 是 --> H["shutdown_confirmed=True<br/>return 非 stopping 且 restart"]
    G1 --> C
    C -- 否 --> I{"runtime_task 刚结束 ?"}
    I -- 是 --> I1["await 它, application 归零"]
    I1 --> I2{"controller.application 空且非待机 ?"}
    I2 -- 是 --> I3["state 的 stopping=True<br/>异常退出也走停机, 不重启"]
    I2 -- 否 --> J
    I -- 否 --> J["runtime_task 为空则取 controller.application<br/>起 run_forever 任务"]
    J --> K["wait 运行中任务, 超时 0.5s; 都没有就 sleep"]
    K --> C
    I3 --> C
    K -.->|循环退出或异常| FA["finally: watcher.cancel + gather"]
    FA --> FB["startup_task 未完成则 cancel 后 drain, 窗口 20s"]
    FB --> FC["runtime_task 未完成: request_shutdown + drain"]
    FC --> FD{"shutdown_confirmed ?"}
    FD -- 是 --> FE["结束"]
    FD -- 否 --> FF["wait_for_idle + controller.shutdown 重试"]
    FF --> FG{"ok ?"}
    FG -- 是 --> FE
    FG -- 否 --> FH{"lifecycle 仍 pending ?"}
    FH -- 否 --> FI["raise RuntimeError(detail)<br/>拒绝假装已停机"]
    FH -- 是 --> FF
```

* `engine 退出的三个判据` 是分开的：`legacy_restart`（无重启信号时的
  `application.restart_requested`）、`restart_signal.requested`、`state 的 stopping`。
  前两者都收敛到 `controller.request_shutdown`，**正常停止永远优先**（`cli.py:42` 注释）。
* 待机之所以不会被误判成退出：运行时退休后 `controller.application` 为空，但
  `standby_service.is_standby()` 为真，于是 `state 的 stopping` 不被置位，
  循环继续等下一代的 `run_forever`（`cli.py:201`）。**这是「软重启不掉进程」的全部机制**。
* `finally` 的 `while True` 只在拿不到 `shutdown_confirmed` 时进入；若
  `controller.shutdown` 失败且 `lifecycle_status()["pending"]` 为假，说明**没有在途清理
  却仍失败**，此时 `raise RuntimeError` 比「安静退出」正确。
</details>

<details>
### 停机顺序：超时只是报告，不是停止的许可

```mermaid
flowchart TD
    A["触发: SIGINT/SIGTERM / 重启信号 / 待机 enter-resume / 运行时异常退出"] --> B["controller.shutdown｜_standby_runtime.py:247"]
    B --> C["request_shutdown: _shutdown_requested=True + _abort_operation"]
    C --> D["_stop_runtime: request_stop 后 app.stop<br/>观察窗口 20s"]
    D --> E{"20s 内完成 ?"}
    E -- 否 --> E1["_report_pending: 报错 + _attention.set<br/>_app 不置空, 仍 shield 等完"]
    E -- 是 --> E2["_app=None, _stopping_task=None<br/>_adapter_running=False"]
    E1 --> E2
    E2 --> F["_starting_app 存在则 dispose, 窗口 20s<br/>phase=startup_cleanup"]
    F --> G["_discard_initial: 释放从未启动的初始代际"]
    G --> H["_sync_adapter(desired=False) 断待机连接"]
    H --> I["返回 True: 运行时与适配器已确认停止"]
    D --> J["app.stop: _stop_lock 串行, 防双跑清理链"]
    J --> K["_stop_components 逐项 shield<br/>self_heal/problem_solver -> report -> event_ingress"]
    K --> L["orchestrator.shutdown -> flush_pending_summaries<br/>-> plugin.stop_all -> creator_image -> markdown -> emoji -> background"]
    L --> M["agent_registry -> browser -> vision_provider<br/>-> adapter(12s 报告) -> tts -> file_server -> engine.dispose"]
    M --> N{"清理抛 KeyboardInterrupt/SystemExit ?"}
    N -- 是 --> N1["记日志后 deferred 上抛, 其余步骤继续跑完"]
    N -- 否 --> N2["普通异常只 warning, 不打断后续步骤"]
    K -.->|CLI 侧 _drain_shutdown_task｜cli.py:131| O["20s 只打印 '优雅关闭仍在等待'<br/>随后 shield 继续等, 绝不启动新进程"]
```

三层超时全部同构（**先报错、再无限期等**）：

| 位置 | 阈值 | 超时后的行为 |
|---|---|---|
| `cli._drain_shutdown_task` | `STOP_TIMEOUT_SECONDS=20.0` | 往 stderr 打印「不会启动新进程」，然后 `shield` 继续等 |
| `StandbyController._wait_stage` | 20s / 120s | `_report_pending` 置 `_aborted` 并写 failure，调用方拿到有界失败；任务仍被拥有 |
| `NeoBotApplication._stop_adapter_with_timeout` | `_ADAPTER_STOP_TIMEOUT_SECONDS=12.0` | 记 ERROR，然后 `shield` 等同一个 task；`_adapter_stop_task` 复用，避免重复 stop |

适配器自身还有限：`OneBotAdapter.stop` 先 `wait_for(task, 2.0)` 停止分发循环
（从分发循环内部调用时直接跳过等待，`adapter.py:170`），再以
`_STOP_TOTAL_GRACE_SECONDS=16.0` 为宽限反复 `_core.stop(8.0)`，用尽即放弃等待并
报告「接收器未停止」，端口已由 `server.close()` 释放。**12s + 4s 的搭配**就是让上层
最多再等约 4s 就能拿到结果，不会永久卡住（`application.py:36-39` 注释）。
</details>

<details>
### 启动失败的回滚：_rollback_start 的 started 列表与顺序偏差

```mermaid
flowchart TD
    A["start 抛 BaseException｜application.py:208"] --> B["_rollback_start(started)"]
    B --> C{"started 含 report_task ?"}
    C -- 是 --> C1["_cancel_report_task: cancel + gather"]
    C -- 否 --> D
    C1 --> D{"started 含 event_ingress ?"}
    D -- 是 --> D1["event_ingress.stop 先关入口"]
    D -- 否 --> E
    D1 --> E{"started 含 markdown_image_converter ?"}
    E -- 是 --> E1["markdown_image_converter.stop"]
    E -- 否 --> F["无条件项: self_heal / problem_solver<br/>reply_orchestrator 或 scheduled+drawing"]
    E1 --> F
    F --> G["creator_image / browser lifecycle<br/>browser instance + 截图录屏产物清理"]
    G --> H["background tasks -> emoji -> plugin.stop_all<br/>plugin 仅 owns_plugins=True"]
    H --> I["agent registry -> adapter, 仅 started 含 adapter"]
    I --> J["tts -> archive_summary -> vision_provider<br/>-> file_server -> engine.dispose"]
    J --> K["_close_unstarted_coros 关闭未 await 的协程对象"]
    K --> L["_started=False, _cleanup_complete=True"]
    L --> M{"有 deferred 异常 ?"}
    M -- 是 --> M1["优先 KeyboardInterrupt/SystemExit<br/>否则首个异常重新抛出"]
    M -- 否 --> M2["原异常继续向上抛"]
```

**回滚顺序不是 `started` 的严格逆序**（`00-overview.md` 的「逆序」说法只是近似）。
两处刻意提前/推后：

* `event_ingress.stop` 排第 2（在 `markdown_image_converter` 之前）—— 先关入口，
  再拆下游，避免拆除期间还有新事件进来。
* `plugin.stop_all` 排在 `adapter` 之前 —— 插件退出时可能还要用适配器发消息；
  而且 `plugin` 只在 `owns_plugins=True` 时才回滚（CLI 路径由 cli.py 自己管）。

另外三件容易漏的事：

1. **无 started 标记也回滚**：self_heal / problem_solver / reply_orchestrator / creator_image /
   archive_summary / vision_provider / engine 这些对象在 `start()` 之前就创建并持有
   provider/agent，所以必须显式关闭（`application.py:229-247` 注释）。
2. **单个清理失败不跳过后续**：`_run_cleanup_steps` 逐个跑，只把第一个非取消异常留作
   `deferred`；`_run_cleanup_step` 对每个 await 都用 `shield` 包住，
   调用方取消不会丢掉清理。
3. `dispose()` 走的是同一条回滚路径但传空 `started`：用于「构建了却从未 start」的
   初始待机代际（`application.py:405`），且用 `_cleanup_complete` 保证**恰好一次**；
   `run_forever` 开头也据此拒绝复活一个已释放的代际（`:375`）。
</details>

<details>
### 配置缺失 = 强制待机：把面板拉起来让用户就地修

```mermaid
flowchart TD
    A["create_application｜bootstrap/__init__.py:655"] --> B["_load_config_for_reuse -> _load_config_or_defaults"]
    B --> C{"build_config 抛异常 ?"}
    C -- 否 --> C1["_CONFIG_ERROR='' , config 进 _CORE_CACHE"]
    C -- 是 --> C2["_CONFIG_ERROR=<类型: 消息><br/>config 从缓存 pop, 返回 ConfigProxy 默认配置"]
    C2 --> D["standby_service: start_in_standby =<br/>bool(_CONFIG_ERROR) 或 [standby].start_in_standby"]
    C1 --> D
    D --> E{"start_in_standby ?"}
    E -- 是 --> E1["StandbyService: STANDBY, reason='启动即待机'<br/>operator='config'"]
    E -- 否 --> E2["RUNNING, 正常起运行时"]
    E1 --> F["_CONFIG_ERROR 非空 -> set_startup_reason<br/>只改文案, 不换状态"]
    F --> G["controller.start 走 initially_standby 分支<br/>_discard_initial + 按 connect_onebot 同步适配器"]
    G --> H["面板可用; 用户改 config.toml 后点软重启运行 -> resume"]
    H --> I{"新配置仍然坏 ?"}
    I -- 是 --> I1["再次失败: _CONFIG_ERROR 非空且不缓存默认配置<br/>仍可重试"]
    I -- 否 --> J["装配成功, _CONFIG_ERROR 清空"]
    B -.->|启动过程其它异常| K["cli.startup 的 except -> standby_service.record_failure<br/>置 STANDBY + _persist｜cli.py:100"]
```

* 为什么不直接退出：`_load_config_or_defaults` 的注释写得很明确 —— 用默认配置把核心服务
  （面板、配置编辑、命令、数据库）拉起来并进入待机，用户就地修，不必重启进程
  （`bootstrap/__init__.py:543`）。
* 兜底也返回 `ConfigProxy`：配置坏掉时面板/QQ 的「配置重载」仍要能跑，否则这条恢复路径
  会抛 `AttributeError`，用户再没有别的恢复手段。
* **默认配置绝不进缓存**：`_load_config_for_reuse`（`:598`）在 `_CONFIG_ERROR`
  非空时把 `config` 从缓存 pop —— 否则用户修好文件后，每次软重启都会复用这份空配置，
  `_CONFIG_ERROR` 永远清不掉，恢复路径形同虚设。
* `record_failure`（`standby_service.py:152`）与 `set_startup_reason` 的分工：
  前者**改状态**（置 STANDBY + 落盘 + ERROR 日志），后者**只改文案**（非 STANDBY 时直接返回）。
</details>

<details>
### 待机期 OneBot 连接切换：set_onebot 与 _sync_adapter 的补偿

```mermaid
flowchart TD
    A["面板 POST /api/admin/standby/onebot｜dashboard/api.py:2648"] --> B["StandbyService.set_connect_onebot"]
    B --> C{"_transition 忙 ?"}
    C -- 是 --> C1["返回 False + _busy_message"]
    C -- 否 --> D{"值未变化且 phase 不是 failed ?"}
    D -- 是 --> D1["直接返回 True: 未变化"]
    D -- 否 --> E["调 on_onebot_change hook = controller.set_onebot<br/>窗口 = enter_timeout 20s"]
    E --> F["StandbyController.set_onebot｜_standby_runtime.py:263"]
    F --> G{"_app 非空, 即运行中 ?"}
    G -- 是 --> G1["拒绝: 运行中始终使用 OneBot 连接<br/>请先进入待机"]
    G -- 否 --> H["_sync_adapter(desired=enabled)"]
    H --> I{"desired == _adapter_running ?"}
    I -- 是 --> I1["空操作返回 True, 幂等"]
    I -- 否 --> J["phase=onebot_starting 或 onebot_stopping<br/>adapter.start 或 adapter.stop, 窗口 20s"]
    J --> K["_adapter_running = desired<br/>返回 not _aborted"]
    K --> L["成功才提交: 更新 _connect_onebot 并 _persist<br/>data/standby.json"]
    E -.->|超时或被取消| M["compensate: 恢复 previous<br/>exiting 时改为强制断开"]
```

* `_adapter_running` 是控制器自己记账的连接状态，不读适配器 `connected`：
  `_sync_adapter` 在 `adapter is None` 或目标值等于现值时直接返回 True（空操作）。
* `set_onebot` 用 `on_abort=compensate`：服务在取消/超时后**没有提交**这次切换，
  迟到的 IO 完成必须把旧偏好恢复（`_standby_runtime.py:266`）。
* `_start_runtime` 在启动新代际前会先把待机连接交还（`:338`）：避免双重启动，
  也避免早期启动失败时留下一个回滚路径够不着的核心适配器。
* 运行中改监听设置走的是另一条路：`AdapterSupervisor`（`adapter_supervisor.py:87`）
  停→改→启，新设置启动失败则 `reconfigure(previous)` 再启动并抛出；它只依赖
  `AdapterReconfigurable` 能力协议，`config_paths=("adapter",)`，
  `hot_reload_policies` 声明 `adapter.*` 运行期可生效。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `NeoBotApplication._started` | `start()` 末尾 | `stop()` / 回滚 `:210` | 回滚后为 False，`_cleanup_complete=True` |
| `_cleanup_complete` | `stop()` 或回滚结束 | 不清理（防复活标志） | `run_forever` 直接 return，`dispose` 幂等返回 |
| `_shutdown_event` | `request_stop/request_restart/stop` | `start()` 且未请求重启时 clear | 置位后 `run_forever` 退出并进入 `stop()` |
| `_restart_requested` | `request_restart`（/reboot 命令回调） | `request_stop(clear_restart=True)`；进程结束 | CLI 读它决定是否 `execv`（无重启信号时的遗留路径） |
| `ProcessRestartSignal._requested` | `request()`，幂等 | 无清理，进程换掉即消失 | 置位后不可撤销：清理卡住就停在原进程 |
| `StandbyService._state` | `enter/resume/record_failure/初始化` | `resume` 成功回 RUNNING | 停在 STANDBY（enter 失败已接线时不回滚 RUNNING） |
| `StandbyService._transition_active` | `enter/resume/set_connect_onebot` | `try/finally` | 忙时新请求返回 `_busy_message`，不排队 |
| `StandbyController._operation` | 每个 `_perform` | 任务 done 后不再替换；补偿任务可接管 | `pending=True` 时后续动作一律拒绝并给 failure 文案 |
| `StandbyController._phase` | `start/stopping/starting/onebot_*` | 每次迁移开头重置 | `failed` 时 `application` 返回 None，CLI 不发布新代际 |
| `StandbyController._adapter_running` | `_sync_adapter`；`_start_runtime` 成功后置 True | 停机路径置 False | 切换失败仍按旧值记账，由 compensate 恢复 |
| `StandbyController._aborted` | `_report_pending/abort_transition` | `_perform` 开头清 | 置位即拒绝发布代际，并触发 compensate |
| `app._connection_state` | 第 5 步探针 | `stop()` 置 None | 未连接也只是状态，不影响启动成败 |
| `_CONFIG_ERROR` | `_load_config_or_defaults` 失败 | 下一次加载成功 | 非空即强制 `start_in_standby`，且默认配置不进缓存 |

## 易错点

* **超时不是许可**。`_drain_shutdown_task` / `_wait_stage` /
  `_stop_adapter_with_timeout` 三处都是「先报错、再继续等」；取消或超时都不代表组件已停，
  更不代表可以 `execv`。改动这三处前先读它们的注释（`cli.py:117-118` 写着
  「a timeout is a report, NEVER permission to exec early」）。
* **待机期 QQ 命令是断的**（见「范围」第 1 条）。写「/reboot 在待机能用」的文档或测试前，
  先确认 `retain_ingress` 是否已合入当前分支；`fix(3)` 的记录文件也只有
  `description.md`，没有 fix-plan，也没有对应提交。
* **`request_process_restart` 是死链路**，别拿它当重启入口（只有测试引用）。真入口是
  宿主服务 `process_restart`；`/reboot` 命令绑的是 `application.request_restart`
  —— 两者语义完全不同：前者换进程，后者软重启运行时代际。
* **Windows 收不到 SIGTERM**：`add_signal_handler` 抛 `NotImplementedError` 时只给
  SIGINT 装了 `signal.signal` + `call_soon_threadsafe`（`cli.py:51-59`）。
  在 Windows 上 `taskkill`（不带 /F 的优雅语义）不会触发这套停机。
* **`ConnectionTimeoutError` 已不再抛**（`application.py:27-32`）：保留类型只为兼容旧
  `except` 分支；如果你在等它出现，说明对照的是旧实现。
* **隐藏入口**：``--neobot-python-lsp-worker`` 在导入 bootstrap **之前**被拦截并
  `SystemExit`（`cli.py:15-23`）。打包后的可执行文件同时是 LSP worker 与 Bot 服务，
  调试启动失败时先确认走的是哪条分支。
* **回滚顺序是「近似逆序 + 两处刻意调整」**（event_ingress 提前、plugin 先于 adapter）。要新增
  启动步骤时，必须同时在 `_rollback_start` 里给出对应的释放位置，并想清楚它相对
  `event_ingress` / `plugin` / `adapter` 的先后。
* **`_adapter_running` 是记账不是探测**：`_start_runtime` 成功后直接置 True
  （`_standby_runtime.py:352`），前提是 `app.start()` 里的第 4 步确实起了适配器。
  若把 `adapter.start` 挪到更靠后或改成不抛异常，这里的记账会失真。
* **待机状态不跨进程恢复**：`_restore` 只读 `connect_onebot`（`standby_service.py:359`），
  想开箱待机必须配置 `[standby].start_in_standby = true`，不要指望重启后自动回到待机。
* **配置兜底对象不进缓存**：`_load_config_for_reuse` 的 `pop("config")` 是恢复路径的
  命门，删掉它会造成「修好配置也永远复用空配置」的静默哑火。
* **改 `StandbyController` 的动作集合时要同时改三处**：`_perform` 的 `exiting` 判据、
  `cli.set_hooks` 注入的三个回调、以及 `StandbyService` 里对应 hook 的超时值
  （enter 20s / resume 120s），否则会出现「面板点了没反应」或「超时后状态与文件不一致」。
