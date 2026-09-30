---
flow: 08b-plugin-runtime
covers:
  - packages/modloader/src/neobot_modloader/runtime.py
  - packages/modloader/src/neobot_modloader/installer.py
  - packages/modloader/src/neobot_modloader/hooks.py
  - packages/modloader/src/neobot_modloader/management.py
  - packages/modloader/src/neobot_modloader/config_store.py
  - packages/modloader/src/neobot_modloader/config_validation.py
  - packages/modloader/src/neobot_modloader/plugins/dispatch.py
verified_against: 08faa3f
verified_hash: bea7db57d3b9
---

# 08b 插件运行时：门面动作矩阵 · 热重载回滚 · 安装器 · 钩子总线

## 范围

本图覆盖 `packages/modloader` 里**运行时门面与安装/钩子**这一层：

* `runtime.py`（2382 行）的 `PluginRuntime` 门面：加载 / 卸载 / 启停 / 热重载 / 快照 / 依赖报告 / 配置读取，以及并发锁与路径绑定；
* `installer.py`：GitHub 来源解析、代理、下载与解压防线、安装 / 更新 / 卸载、备份目录、更新检查；
* `hooks.py`：`PluginHookBus` 的订阅 / 退订 / 优先级 / 超时 / 阻断，`dispatch_envelope` 信封派发与输出捕获；
* `management.py`：`PluginOperationResult` / `PluginSnapshot` / `PluginControlFacade`（面板与插件看到的窄门面）；
* `config_store.py` + `config_validation.py`：`plugin.toml` 的 `[config]` 打底 + `plugins_data/<name>/config.toml` 覆盖 + 校验回落；
* `plugins/dispatch.py`：`Plugin.command/message/...` 装饰器到钩子总线订阅的桥。

**分工（与 08-plugins.md 不重叠）**：

| 内容 | 归谁 |
|---|---|
| 目录扫描规则、`plugin.toml` 字段与类型校验、`__` 与保留名校验、依赖声明解析与五种自动禁用 code、拓扑排序、gN 导入与缓存清理、`DefaultPluginManager` 状态机、两个 register 的相反语义、本体/插件两条配置热重载链 | 08-plugins.md |
| 门面动作矩阵与失败返回契约、热重载回滚（候选代丢弃 + 旧代恢复）、安装器全链路、`PluginHookBus` 与信封派发、插件配置读写校验、运行时并发锁 | 本图 |

**不画什么**：

* 面板端点清单与鉴权 → 09b-dashboard-api；本图只写「哪个动作被哪个端点调用」；
* `Plugin` 装饰器的参数注入与工具绑定 → 06-tools-skills；本图只写它如何变成一条钩子订阅；
* `config.reload`（本体配置）与 `apply_plugin_config_change`（插件配置原地生效管道）→ 08-plugins.md；
* `PythonDependencyInstaller`（PyPI 依赖安装交互）→ 08-plugins.md 细节块。

**spec 与现实的差异**（都在图里保留现状）：

* 全仓**没有文件监听**：`reload` / `reload_all` 只能由面板或插件自身显式触发；
* `reload_all()` 在 `app/` 与 `packages/` 的生产代码里**零调用点**（只有单测），面板也没有「全部重载」按钮；
* 面板的「检查更新 / 更新」与「安装」走**两条不同的路**：前者直连 `installer.update`，后者走 `runtime.install_plugin`；
* 卸载的备份是「先 `copytree` 再 `move`」，`move` 落进刚建好的备份目录 → 实际代码在 `.plugin-backups/<name>-<时间戳>/<name>/`（替换安装的备份是平铺的，两者不一致，已在本机实测）。

## 流程

```mermaid
flowchart TD
    A["build_plugin_runtime / bootstrap/_skills.py:91（装配期同步跑完）"] --> B["PluginRuntime.load_all / runtime.py:426"]
    B --> C["scan_dirs：官方目录在前，第三方目录在后 / runtime.py:251"]
    C --> D["loader.load_all 逐目录：LoadedPlugin / DisabledPlugin / PluginLoadError"]
    D --> E{"load_all 内的前置判据 / runtime.py:443-509"}
    E -- "第三方与官方同名 / 已注册 / 缺 PyPI 依赖 / 主机版本不足" --> E1["跳过 + clear_module_cache，不注册"]
    E -- "_dependency_presence_issues 非空" --> E2["自动禁用：_auto_disabled + 清模块代，不阻断启动"]
    E -- "全部通过" --> F["_register / runtime.py:2114：配置合并 + 校验 + 建 RuntimePluginContext"]
    F --> G["manager.register：写记录 + 名字锁永久保留"]
    G --> H["load_registered / runtime.py:517 -> on_load -> LOADED"]
    H --> I["start_all / runtime.py:522 -> on_start -> RUNNING"]
    I --> J{"运行期入口（没有文件监听）"}
    J -- "面板或插件调 control.set_enabled" --> K["set_enabled / runtime.py:1457"]
    J -- "control.reload" --> L["reload_plugin_result / runtime.py:854"]
    J -- "control.unload / force_unload" --> M["unload_plugin / runtime.py:601"]
    J -- "control.install / uninstall / check_updates" --> N["安装器通道 / runtime.py:1490 :1548 :1576"]
    K --> O["先卸载 -> _persist_enabled_state -> plugin_state.json"]
    L --> P["候选代 load_one -> 转正或 _rollback_failed_generation"]
    M --> Q["_remove_manager_record -> 摘记录 + 清模块代"]
    N --> R["PluginInstaller.install / installer.py:454（GitHub zip，dry_run 与 replace 二选一）"]
    O -.-> S["失败统一收敛为 PluginOperationResult(ok=False, error, requires_restart)"]
    P -.-> S
    Q -.-> S
    R -.-> S
    S --> T["面板 _operation_response / dashboard/api.py:1060-1168"]
    I --> U["snapshot_plugins / runtime.py:1299（每次调用全量 discover_all）"]
    U --> T
```

主图只画主干：每个动作的前置判据与失败语义在下面 10 个折叠块里。`PluginOperationResult` 是唯一的失败载体，没有动作会向调用方抛业务异常（`reload_plugin` 这个 bool 包装器例外，见细节 2）。

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant P as 面板或插件自身
    participant GW as EventGateway
    participant RT as PluginRuntime
    participant MG as DefaultPluginManager
    participant LD as FilesystemPluginLoader
    participant IN as PluginInstaller
    participant HB as PluginHookBus
    participant PL as Plugin 生命周期回调

    Note over RT,LD: 装配期（同步，bootstrap/_skills.py:190 一次跑完，无 await）
    RT->>LD: load_all：官方目录在前，逐目录导入
    LD-->>RT: LoadedPlugin / DisabledPlugin / PluginLoadError 三选一
    RT->>MG: _register 成功后 register（只登记，不跑生命周期）
    Note over RT,MG: 启动期由 application.start 分两步 await
    RT->>MG: load_registered() -> on_load
    MG->>PL: on_load(ctx)
    RT->>MG: start_all() -> on_start
    MG->>PL: on_start()

    Note over P,RT: 运行期动作（无文件监听，只能显式触发）
    P->>RT: control.reload(name)
    RT->>MG: _cascade_stop_dependents 先停依赖方（不致命）
    RT->>LD: load_one：新 gN 命名空间 + 删 __pycache__
    LD-->>RT: 候选代 LoadedPlugin 或 PluginLoadError
    alt 候选代进入预期状态
        RT->>MG: register + load_plugin + start_plugin
        RT->>RT: 清旧代残留模块，成功
    else 候选代失败
        RT->>MG: _discard_candidate_generation + _restore_old_generation
        RT-->>P: ok=False，文本注明 已恢复旧版本 或 回滚失败原因
    end
    P->>RT: control.set_enabled(name, False)
    RT->>MG: unload（名字锁内串行，OperationBusy 时 ok=False）
    RT->>RT: _persist_enabled_state -> plugin_state.json
    P->>IN: control.install(repo, dry_run, replace)
    IN-->>P: 冲突时回 conflict 结构，磁盘零变化
    IN->>RT: 成功后 load_plugin_path 装载（失败则文件已落盘但 ok=False）
    Note over GW,HB: 事件分发（每条入站事件）
    GW->>HB: dispatch(ctx) / runtime/gateway.py:91
    HB->>PL: 钩子按 priority 降序逐个 await（单个超时或异常不致命）
```

三条「不致命」的线：**单个钩子异常**只跳过它自己；**依赖未满足**是自动禁用不是报错；**热重载失败**必须回滚到旧代（回滚也失败才在文本里加「旧版本回滚失败」）。

## 细节

<details>
### 门面动作矩阵：每个动作的前置校验与失败停在哪

```mermaid
flowchart TD
    A["control 门面 / management.py:80 + runtime.py:64"] --> B{"调用方要做什么"}
    B -- "load_path" --> C["load_plugin_path / runtime.py:532"]
    B -- "unload / force_unload" --> D["unload_plugin / runtime.py:601"]
    B -- "reload" --> E["reload_plugin_result / runtime.py:854（细节 2）"]
    B -- "start / stop / set_enabled" --> G["start_plugin :699 / stop_plugin :756 / set_enabled :1457"]
    B -- "install / uninstall" --> H["install_plugin :1490 / uninstall_plugin :1548（细节 3）"]
    C --> C1{"_is_path_under_plugin_dir / runtime.py:1886"}
    C1 -- 否 --> X1["ok=False 插件路径不在插件目录内"]
    C1 -- 是 --> C2["_path_operation：路径去重 + 名字锁 -> loader.load_one"]
    C2 --> C3["_activate_loaded_plugin / runtime.py:1638"]
    C3 --> C4{"缺 PyPI 依赖 / min_neobot_version / _dependency_issues"}
    C4 -- "缺 PyPI 依赖" --> X2["ok=False state=error + clear_module_cache"]
    C4 -- "主机版本不足" --> X2
    C4 -- "前置未就绪" --> X3["自动禁用 ok=False state=unloaded + _auto_disabled"]
    C4 -- "全部通过" --> C5["_register -> manager.load_plugin -> start_plugin"]
    D --> D1{"manager.get_record 有记录"}
    D1 -- 否 --> X5["ok=False 插件未注册 / 卸载尚未完成 / 已被并发替换"]
    D1 -- 是 --> D2["_cascade_stop_dependents 先停依赖方，再无条件注销配置消费者"]
    D2 --> D4{"_remove_manager_record 摘净且未被并发替换"}
    D4 -- 否 --> X5
    D4 -- 是 --> D5{"旧记录的 error 非空"}
    D5 -- 否 --> OK1["ok=True state=unloaded"]
    D5 -- 是 --> D6{"force=True"}
    D6 -- 是 --> OK2["ok=True + requires_restart=True + 错误文本"]
    D6 -- 否 --> X6["ok=False state=unloaded + 停止错误"]
```

补充（这些动作没单独画，判据同样在门面里）：

| 动作 | 前置校验 | 失败返回 |
|---|---|---|
| `start_plugin` | 记录存在；已在 RUNNING 且 `error is None` 时直接 ok；`_dependency_issues` 为空；UNLOADED 时先补一次 `load_plugin` | `ok=False` + 依赖文本，或未进 RUNNING 的 `_operation_result_from_record` |
| `stop_plugin` | 记录存在；UNLOADED 且无错误、或 STOPPED 且未 `stop_failed` 时直接 ok | `stop_failed=True` 时 ok=False，错误留在 `record.error`，下次 stop 会重试 |
| `set_enabled(false)` | 记录不存在则跳过卸载，直接持久化 false | 卸载失败时**不落盘**（面板看到的是启停失败） |
| `set_enabled(true)` | 先 `_persist_enabled_state(true)` 再 `load_plugin_path(start=True)` | 装载失败时 state 文件已经写了 true，重启会再试一次 |
| `snapshot_plugins` | 每次调用都 `discover_all()`（全量扫描）；未加载但缺 PyPI 依赖的条目被标成 error | 只读，不抛错 |
| `reload_plugin`（bool 包装） | 转调 `reload_plugin_result` | 只有 `ok=False` 且 `state=unloaded` 且 `path is None` 才 `raise KeyError`，其余失败只返回 False |

</details>

<details>
### 热重载回滚：返回契约与「候选代必须被丢弃」不变量

```mermaid
flowchart TD
    A["reload_plugin_result / runtime.py:854（名字锁内）"] --> B["先 _cascade_stop_dependents 停依赖方"]
    B --> C{"_loaded_flags[name][0] 为真"}
    C -- 否 --> X1["拒绝：ok=False + requires_restart=True"]
    C -- 是 --> D{"定位路径 _loaded_paths -> _find_plugin_path"}
    D -- "找不到" --> X2["ok=False 插件未找到"]
    D -- "找到" --> F["loader.load_one：新 gN 命名空间 + 删 __pycache__"]
    F --> G{"结果可用：非 PluginLoadError / 未改名 / PyPI 依赖齐"}
    G -- 否 --> X3["清新代模块 + ok=False（错误文本或 重载不能更改名称）"]
    G -- 是 --> H{"旧记录 old_record 是否存在"}
    H -- 否 --> H1["_activate_loaded_plugin：按新装处理"]
    H -- 是 --> L["_remove_manager_record(expected=old_record, force=False)"]
    L --> M{"记录摘净且 removed.error 为空"}
    M -- 否 --> N["_restore_old_generation -> _failed_reload_result"]
    M -- 是 --> P["_register 新代（配置重新合并 + 校验）"]
    P --> Q{"注册成功"}
    Q -- 否 --> N
    Q -- 是 --> R["manager.load_plugin + start_plugin(start=True)"]
    R --> S{"进入预期状态 RUNNING / LOADED"}
    S -- 是 --> T["清旧代残留模块 -> ok=True -> _cascade_restore_dependents"]
    S -- 否 --> U["_rollback_failed_generation"]
    U --> V["_discard_candidate_generation：丢弃候选代 + 清它的模块代"]
    V --> W["_restore_old_generation：重新注册旧 plugin 对象，按原状态恢复"]
    W --> X6["_failed_reload_result：已恢复旧版本 / 旧版本回滚失败: 原因"]
```

回滚细节（`runtime.py:1095-1211`）：

* `_discard_candidate_generation`：候选记录还挂在 manager 上时先 `remove_plugin`；候选状态是 `ERROR` 时直接 `force=True`；强删后记录仍在就把「无法移除失败的新版本」拼进错误文本；只有 manager 里已经没有该记录时才清 `_loaded_modules` / `_loaded_paths` 与模块代。
* `_restore_old_generation`：用 `manager.register(old_record.plugin, old_record.context)` 重新注册；旧状态是 RUNNING 就 `load_plugin` 后视情况 `start_plugin`，是 LOADED 就只 `load_plugin`，**其余状态直接把 `state/error/stop_failed` 写回记录**（不跑生命周期）。
* 失败文本只有两种形态：`插件新版本激活失败: ...; 已恢复旧版本` 或 `...; 旧版本回滚失败: ...`；`ok` 恒为 False，`state` 取恢复后的实时状态。
* 取消（`asyncio.CancelledError`）也走回滚：先回滚再 `raise`，回滚错误只记日志。
* 成功时不恢复依赖方会留下半死状态，所以 `_cascade_restore_dependents` 只在 `ok=True` 时调用。

</details>

<details>
### 安装与更新与卸载：来源、代理、压缩包防线与 ID 冲突二选一

```mermaid
flowchart TD
    Z["control 门面：install / uninstall（更新检查见细节 9）"] --> A["install_plugin / runtime.py:1490"]
    Z --> P["uninstall_plugin / runtime.py:1548：官方拒绝 -> 已注册则先 unload -> installer.uninstall 备份后移走 -> _state_store.forget"]
    A --> B["PluginInstaller.install / installer.py:454"]
    B --> C["parse_spec：owner/repo@branch 正则 / installer.py:258"]
    C -- "失败" --> X1["ok=False：无法解析仓库地址 / 非法分支名"]
    C --> D["_fetch_bytes -> _ensure_allowed_url 域名白名单 / installer.py:276"]
    D -- "域名或下载失败" --> X1
    D --> E["tempfile.mkdtemp 到 plugin_dir.parent，前缀 .install-"]
    E --> F["_extract：条目<=5000 / 解压体积<=256MiB / 拒符号链接与上跳 / 跳过 .pth / :696"]
    F -- "失败" --> X3["ok=False 超限、无 plugin.toml 或存在多个插件目录"]
    F --> G["read_manifest 取 name/version + validate_plugin_name"]
    G -- "失败" --> X3
    G --> H{"installer.is_reserved(name)：命中官方插件目录"}
    H -- 是 --> X5["ok=False 保留字冲突 conflict.kind=official"]
    H -- 否 --> I{"dry_run"}
    I -- 是 --> OK1["ok=True 只探测不写盘，同名时回 conflict 结构"]
    I -- 否 --> J{"data/plugins/<name> 已存在"}
    J -- 否 --> M["shutil.move 暂存目录 -> 目标目录"]
    J -- 是 --> K{"replace 显式替换"}
    K -- 否 --> X6["ok=False 结构化 conflict：磁盘零变化，不删不备份"]
    K -- 是 --> L["_backup -> data/.plugin-backups/<name>-YYYYmmdd-HHMMSS（copytree，忽略 __pycache__）"]
    L --> M
    M --> N["ok=True + version + backup_path"]
    N --> O["runtime：_persist_enabled_state(True) -> load_plugin_path(start)"]
    O -- "装载失败" --> X8["文件已落盘但 ok=False：已安装 xx，但加载失败: ..."]
    O --> OK2["ok=True：state / path / version / backup_path 透传"]
```

补充事实：

* **代理**：`ProxySettings(mode=system|none|custom, host, port)`（`installer.py:58`）在装配期取 `config.plugins.proxy_*`；面板保存代理先 `control.set_installer_proxy`（内存，下一次下载即生效）再写 `config.toml`（`persist=false` 时只写内存，重启回退旧值）。`custom` 必须有 host、端口必须 1-65535，否则构造即 `ValueError`。
* **下载**：`_fetch_bytes_sync` 用 `urllib` + 可选 `ProxyHandler`；`content-length` 超 64 MiB 先拒，读流累计再超也拒（`MAX_ARCHIVE_BYTES=64MiB`、`MAX_EXTRACTED_BYTES=256MiB`、`MAX_ARCHIVE_ENTRIES=5000`）；解压体积按 zip 中央目录声明累加，不是实际写入字节数。
* **先后顺序**：整包**先下载**再判冲突 —— 保留字、ID 冲突、`dry_run` 三条拒绝路径都已经花掉一次网络下载和一次解压到暂存目录。
* **`dry_run` 也要下载**：要用远端 `plugin.toml` 才能回 `name/version/conflict`。
* **`install_plugin` 不传 `expected_name`**：只有 `installer.update`（`installer.py:582`）校验「期望插件名」，面板的更新走的就是它。
* **备份目录**：`BACKUP_DIR_NAME = ".plugin-backups"`，位置是 `plugin_dir.parent`（默认 `data/`）。替换安装的备份是平铺的 `<name>-<stamp>/`；**卸载的备份会再嵌一层** —— `_backup` 先 `copytree` 建好目录，`shutil.move(target, backup_path)` 遇到已存在目录会把源目录挪进去，实际代码在 `<name>-<stamp>/<name>/`。两条路都不做清理，备份只增不减。
* **写入失败会还原备份**：`shutil.move` 抛错且目标目录还不存在时，把备份搬回原位再返回 `ok=False`（`installer.py:558-563`）。
* **卸载不删代码**：`installer.uninstall` 只把插件目录移进备份并 `forget` 启停状态；`_loaded_sources` / `_loaded_paths` 被 pop，但 `_loaded_flags` 不清（见易错点）。

</details>

<details>
### 钩子总线订阅侧：装饰器到 HookRegistration、优先级与退订

```mermaid
flowchart TD
    A["Plugin.command / message / notice 装饰器 / plugin.py:116"] --> B["bind_handlers / plugins/dispatch.py:19"]
    B --> C["context.hook_bus.subscribe / hooks.py:113"]
    D["插件直接调 ctx.hook_bus.subscribe 或 subscribe_runtime"] --> C
    C --> E["HookRegistration：post_type/message_type/... + rule + priority + timeout + block + block_ai_reply"]
    E --> F["_extract_event_model：取 handler 首参的 pydantic 注解 / hooks.py:414"]
    F --> G["加锁 append 后按 priority 降序排序，Python 稳定排序保持同级插入序"]
    G --> H["HookSubscription.unsubscribe：_active 幂等，列表按对象身份过滤 / hooks.py:26"]
    B --> I["post_type 固定 message；message_type 由 private/group 决定 / dispatch.py:124"]
    B --> J["rule：命令走 pattern.match，命中或 parse_error!=ignore 才算 handled / dispatch.py:40"]
    B --> K["block 默认：command=True，message=False；priority 默认 10 / plugin.py:122"]
    C --> L["subscribe_runtime：RuntimeInterceptorRegistration，按 kind/stage/source/target 匹配（细节 5）"]
```

`HookRegistration` 的字段就是筛选器：六个 `*_type` 字段做**全等**比较（`hooks.py:54`），没有通配；`coerce` 只在 `event_model` 存在且首参注解是 `BaseModel` 子类时做模型校验。排序只在**插入时**做一次（`sort(key=priority, reverse=True)`），退订只是重建列表、不重排。装饰器侧的重名处理、`parse_error=ignore` 语义与依赖注入校验属于 `Plugin` 面，见 06-tools-skills；本图只关心它产出的那条订阅。

</details>

<details>
### 钩子总线派发侧：过滤、rule、超时隔离与 block_ai_reply

```mermaid
flowchart TD
    I["EventGateway.handle / runtime/gateway.py:74"] --> J["hook_bus.dispatch(ctx) / hooks.py:188"]
    J --> K["bind_event_context 绑 ContextVar，finally 复位（ctx.agent_reply 靠它找到当前事件）"]
    K --> L["_dispatch / hooks.py:201"]
    L --> M{"ctx.raw_event 是 dict"}
    M -- 否 --> X1["直接返回：一个钩子都不跑"]
    M -- 是 --> N["构造 inbound_event 信封 -> dispatch_envelope（细节 5）"]
    N --> O{"envelope.consumed"}
    O -- 是 --> X2["ctx.consume() 后返回，钩子不再执行"]
    O -- 否 --> P["锁内筛 matches(event) 得到本次钩子快照"]
    P --> Q{"ctx.consumed 已置位"}
    Q -- 是 --> X3["break：后续钩子不再执行"]
    Q -- 否 --> R{"hook.rule(event) 通过"}
    R -- "抛异常" --> X4["log.exception 后跳过该订阅（事件继续）"]
    R -- "False" --> X5["continue 跳过本钩子"]
    R -- "True 或 None" --> S["coerce：pydantic event_model 或原始 dict，校验失败回落原始 event"]
    S --> T["_call_hook / hooks.py:280：_capture_output 按任务上下文捕获 stdout/stderr"]
    T --> Y{"超时或抛异常"}
    Y -- 是 --> X6["return False：本次不算 handled，block 不生效，事件继续"]
    Y -- 否 --> Z{"block_ai_reply"}
    Z -- 是 --> Z1["ctx.block_ai_reply() + record_ai_reply_block(event)"]
    Z -- 否 --> Z2{"block"}
    Z1 --> Z2
    Z2 -- 是 --> Z3["ctx.consume() 后 break"]
    Z2 -- 否 --> Z4["继续下一个钩子（事件交给主链路）"]
```

要点：

* **同步 handler 的超时拦不住**：`_call_handler` 对非协程用 `asyncio.to_thread`，`asyncio.wait_for` 超时只让等待方抛 `TimeoutError`，线程里的 handler 会继续跑完（返回值被丢弃，计为未 handled）。
* **handled 的判据是「没超时且没抛异常」**，不是返回值：装饰器包装出的 `dispatch` 恒返回 None，所以 `block=True`（命令默认）意味着「模式命中就吞掉这条事件」。
* **输出捕获按 ContextVar 路由**（`_ContextRoutedStream`，`hooks.py:327`）：并发 await 的钩子互不串台，`finally` 里上报，handler 抛异常也不丢已产生的输出；`sys.stdout is None`（pythonw 或 PyInstaller --noconsole）时 write 直接丢弃长度，不炸。
* 被 `block_ai_reply` 拦下时仍会继续跑其余钩子；只有 `block` 才 `break`。`agent_reply` 意图通过 `bind_event_context` 的 ContextVar 落到本次事件上（`agent_intent.py:27`），dispatch 结束后必定复位。

</details>

<details>
### 信封派发：四类生产者、拦截器替换规则与 consumed 短路

```mermaid
flowchart TD
    A["inbound_event：hook_bus.dispatch 构造，stage=post_type / hooks.py:206"] --> E
    B["output：RuntimeOutput.write / observability/output.py:40，kind=output stage=channel"] --> E
    C["log：loguru sink / observability/logging.py:123，kind=log stage=日志级别"] --> E
    D["reply_lifecycle：sender 发送前后 / reply/sender.py:184 与 reply/debug.py:33"] --> E
    E["dispatch_envelope / hooks.py:266"] --> F{"envelope.consumed"}
    F -- 是 --> X1["break：后续拦截器不再执行"]
    F -- 否 --> G["锁内筛 matches：kind/stage/source/target 全等匹配 / hooks.py:86"]
    G --> H["_call_interceptor / hooks.py:297：_capture_output 带 target=envelope.target"]
    H --> I{"返回类型"}
    I -- "RuntimeEnvelope" --> J["整体替换信封，后续拦截器看到新信封"]
    I -- "dict" --> K["payload.update(result)：只并字段，不换信封"]
    I -- "None（超时或异常）" --> L["保持原信封，只 log.warning 或 log.exception"]
    J --> M{"还有下一个拦截器"}
    K --> M
    L --> M
    M --> N["返回最终信封给调用方"]
    N --> O["dispatch 侧：payload 里的 event 是 dict 就写回 ctx.raw_event"]
    N --> PP["sender 侧：consumed 为真 -> 用 envelope.result 短路发送"]
    N --> QQ["dashboard 订阅 kind=log 记指标 / dashboard/__init__.py:94"]
```

`RuntimeOutput.write` 用 `create_task` 异步派发（不 await），所以日志类拦截器**不阻塞**产生方；`sender.send_with_timeout` 是 `await dispatch`，能真正改写 `payload` 里的 message 或被 `consumed` 短路（短路时直接返回 `envelope.result`，不发消息）。`source` 与 `target` 是插件做定向拦截的抓手，`target` 形如 `group:<id>`。

</details>

<details>
### 插件配置读写与校验：默认值打底、非法已存值回落

```mermaid
flowchart TD
    A["plugin.toml 的 config 段：打包默认值 / runtime.py:_manifest_config:2086"] --> C
    B["plugins_data/<name>/config.toml 用户值 / config_store.py:24"] --> C
    C["PluginConfigStore.read -> merge_plugin_config 递归合并 / config_store.py:27"] --> D
    D{"tomllib 解析失败或不是 dict"} -- 是 --> X1["warning + 按空字典：只用打包默认值"]
    D -- 否 --> E["_register / runtime.py:2114 调 validate_plugin_config"]
    E --> F{"model 是 pydantic 模型"}
    F -- 否 --> OK1["原样返回 merged，无告警"]
    F -- 是 --> G{"model_validate(merged) 通过"}
    G -- 是 --> OK2["_dump 后注入 RuntimePluginContext.config"]
    G -- 否 --> H["_invalid_top_level_keys 提取顶层非法字段 / config_validation.py:53"]
    H --> I["drop = 非法键 交 已存键：只回落用户写下的字段"]
    I --> J{"用 repaired 重校验通过"}
    J -- 是 --> K["用修复值 + 告警"]
    J -- 否 --> L{"model() 默认值可构造"}
    L -- 是 --> M["用模型默认值 + 告警"]
    L -- 否 --> N["退回 merged + 告警（保证返回值仍可校验）"]
    K --> O["_config_errors[name] -> 快照 config_error 字段展示"]
    M --> O
    N --> O
    O --> PP["面板 plugin_config_values 读的是磁盘原始合并值，不含回落"]
```

* `PluginConfigStore` 只读文件：写入由面板或用户完成（`config_store.py:44`），路径是 `plugins_data/<name>/config.toml`；插件升级新增的配置项靠「默认值打底」自动补上。
* 校验失败**不硬失败**：非法已存字段回落打包默认值，仍非法用模型默认值，最差退回原始 merged 并附告警 —— 返回值保证能过插件自己的 `config_model`（面板这类「配置坏掉就再无修复入口」的插件全靠这条）。
* 打包默认值本身非法属于插件作者问题：`drop` 只删「已存键 交 非法键」，不动默认值。
* 与配置热重载的分工：面板保存后「原地生效」还是「重载插件」由 `config_consumer` 是否存在加 `config_hot_reload` 决定（`dashboard/api.py:1297-1316`），管道细节见 08-plugins.md。

</details>

<details>
### 面板交互面：谁调哪个动作、结果怎么回

```mermaid
flowchart TD
    A["dashboard/api.py:_plugin_control / api.py:152 <- ctx.plugin_control / runtime.py:2171"] --> B
    A --> C
    A --> D
    A --> E
    A --> F
    A --> G
    A --> H
    A --> I
    A --> J
    A --> K
    A --> L
    B["GET /api/plugins -> control.snapshot() / api.py:896"]
    C["POST plugins/<name>/toggle -> control.set_enabled / api.py:1060"]
    D["POST plugins/<name>/reload -> control.reload / api.py:1073"]
    E["POST plugins/<name>/update -> installer.update 后 control.reload / api.py:1095"]
    F["POST plugins/<name>/uninstall -> control.uninstall / api.py:1116"]
    G["POST plugins/install -> control.install / api.py:1143"]
    H["GET plugins/probe -> control.probe / api.py:1182"]
    I["GET plugins/check_updates -> control.check_updates / api.py:1191"]
    J["GET 与 POST plugins/<name>/config -> config_model/defaults/values + 写盘 / api.py:1231 :1262"]
    K["POST plugins/proxy -> control.set_installer_proxy + config.toml / api.py:1018"]
    L["starship 与 status_card -> control.snapshot() 只读汇总"]
    C --> X1["面板自身保护：不能从面板停用面板 / api.py:1053"]
    D --> X2["面板自身保护：不支持热重载 / api.py:1071"]
    F --> X3["不能卸载面板自身 / api.py:1114"]
    E --> X4["官方插件或未声明 repo 直接 400 / api.py:1087"]
    G --> X5["dry_run 回 ok 加 conflict；否则 _operation_response 统一映射 / api.py:1147"]
```

* **动作到结果**：所有动作返回 `PluginOperationResult`，`_operation_response` 把 `ok/error/state/requires_restart/conflict/backup_path` 映射成 HTTP；`conflict` 走 409，官方保留字与参数错走 400。
* **`update` 是唯一绕过 runtime 的写路径**：面板直接拿 `self._service("plugin_runtime").installer` 调 `installer.update(name, repo, branch)`（内部 `replace=True`、带 `expected_name`），成功后**再** `control.reload`；这条路上 `_persist_enabled_state` 不会被调用，也不做「依赖未满足自动禁用」的判定（reload 里才有）。
* **命令通道没有插件管理**：全仓没有插件管理命令，插件管理只存在于面板；插件想自我管理只能拿 `ctx.plugin_control`（`management.py:80` 的窄门面，`install/unload/reload` 都在里面，**没有面板层的 `_require_manage` 鉴权**）。
* 面板保存插件配置后的三条分叉（consumer 原地生效 / `control.reload` / 提示重启）在 08-plugins.md 有图；本图只标出它调的是 `control.reload`。

</details>

<details>
### 并发与锁：ReentrantLock、OperationBusy 与路径绑定

```mermaid
flowchart TD
    A["load_all 注册段 / runtime.py:463"] --> B["threading.RLock _scan_guard：同步扫描期间防多线程重入"]
    C["_named_operation(name) / runtime.py:1819"] --> D["async with _operation_gate 只护字典 setdefault，不跨锁等待"]
    D --> E{"本任务已持有该名字锁"}
    E -- 是 --> F["直接复用：ReentrantLock 同任务可重入，回调里再进不自死锁"]
    E -- 否 --> G{"他任务持有该锁"}
    G -- 否 --> H["await lock.acquire()"]
    G -- 是 --> I["_held_lock_names：本任务当前持有的全部名字"]
    I --> J{"name 小于已持有名字的最大值"}
    J -- 是 --> X1["raise OperationBusy：不按逆序等待，防两插件互卸死锁"]
    J -- 否 --> H
    H --> K["yield 操作体；失败路径同样 _prune_operation_lock 后返回 ok=False"]
    K --> L{"锁空闲且 name 不在 _operation_paths 里"}
    L -- 是 --> V["删除名字锁（只增不减的是 manager 侧，runtime 侧必须剪枝）"]
    L -- 否 --> W["保留：有人排队或路径绑定仍在"]
    N["_path_operation(path) / runtime.py:1839"] --> O["resolve_known_name + 用户计数：同一路径并发导入先按路径去重"]
    O --> PP["bind(name)：记住原绑定，取锁失败就 _rollback_binding"]
    PP --> Q{"operation.commit() 被调用"}
    Q -- 否 --> R["释放时回滚路径绑定、清理未提交预留"]
    Q -- 是 --> S["_committed_operation_paths 保留 路径到名字 的绑定"]
```

* 两个层级：`_operation_gate`（`asyncio.Lock`）只保护 `_operation_locks` 与 `_operation_paths` 的字典操作，**绝不跨名字锁等待**，避免整运行时头阻塞。
* `ReentrantLock`（`manager.py:21`）的 `is_free()` 把 `_pending > 0`（有人排队）也算「不空闲」，所以剪枝不会把排队者脚下的锁删掉；`is_owned_by_current_task()` 是重入判据。
* **逆序等待即拒绝**：当前任务已持有 `b` 却要取 `a`（`a` 小于已持有名字最大值）时抛 `OperationBusy`，调用方剪枝后返回 `ok=False` 的「操作占用」；`load_plugin_path` 在 `bind` 前已导入模块，这条路径会**先清模块代**再返回，避免 sys.modules 孤儿。
* manager 侧还有第二把锁 `_plugin_locks[name]`（`manager.py:291`，setdefault 永久保留），`remove_plugin` 在锁内做 `expected` 身份比对，记录被换过就放弃移除。

</details>

<details>
### 两套版本比较：依赖判定「无法比较即放行」与更新判定「无法比较即相等」

```mermaid
flowchart TD
    A["compare_versions / installer.py:151（更新检查用）"] --> B["_VERSION_PART_RE 抓字符串里任意位置的数字段与字母段"]
    B --> C["逐段比较：两个数字段比数值，数字段优先于字母段"]
    C --> D{"一侧先缺段"}
    D -- "剩余段是字母（预发布）" --> E["缺段一侧更小：1.0.0 大于 1.0.0-rc1"]
    D -- "剩余段是数字" --> F["缺段一侧更小：1.0 小于 1.0.1"]
    D -- "两侧都缺" --> G["返回 0"]
    B --> H{"一个数字段都没有（如 dev）"}
    H -- 是 --> I["返回 0 即相等：永不提示有更新"]
    J["compare_plugin_versions / version.py:34（依赖与最低版本用）"] --> K["parse_version 只认 v 号加数字点分 的前缀"]
    K --> L["_trimmed 去尾零：1.0 等于 1.0.0"]
    K --> M{"任一不可解析 或 全零版本"}
    M -- 是 --> N["返回 None 即无法比较"]
    M -- 否 --> O["补齐位数后按元组比较"]
    N --> PP["Dependency.matches 只有 False 才判不满足 / dependency.py:49"]
    PP --> Q["放行：源码运行 0.0.0 与非数字版本号都拦不住"]
    N --> R["_host_version_error 同样跳过 min_neobot_version 检查并 warning / runtime.py:260"]
    A --> S["check_update：compare_versions 大于 0 才是 available / installer.py:648"]
    J --> T["预发布口径不同：version.py 把 1.0.0-rc1 当成 1.0.0"]
```

同一份「1.0.0-rc1 对 1.0.0」在两个实现里结论相反（安装器：rc 更小；version.py：相等），所以**依赖约束与更新提示可能互相矛盾**。两条「无法比较」的兜底方向也不同：依赖侧偏**放行**（宁可少拦），更新侧偏**相等**（远端是非数字版本时永远显示「已是最新」，既不误报也不提示）。`version_at_least` 是第三个入口（主机版本），同样在 host 为 `0.0.0` 时返回 None 跳过检查。

</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `_loaded_modules` / `_loaded_paths` / `_loaded_sources` | `_register` 成功 | `_clear_plugin_tracking`（按值比对，避免清掉并发替换后的新记录） | 清完即返回 `ok=False`，插件不再出现在 `manager.names()` |
| `_loaded_flags[name] = (hot_reload, config_hot_reload)` | `_register` | **只有 `set_enabled(false)` 会 pop**；`_clear_plugin_tracking` 不碰 | 卸载后重新发现同一插件时，快照显示的是上一次加载时的 flags |
| `_auto_disabled[name] = (前置, 原因)` | 排序结果、`_dependency_presence_issues`、`_dependency_issues`、`_cascade_stop_dependents` | `_register` 成功、`_cascade_restore_dependents` 成功、`set_enabled(true)` 成功 | 前置一直缺失则保持 unloaded，启动不受影响 |
| `_operation_locks[name]` | `_named_operation` 或 `_PathOperation._acquire` 懒建 | `_prune_operation_lock`（`is_free()` 且无路径绑定） | 失败路径也剪枝；不剪则后续面板操作全变「操作占用」 |
| `_operation_paths` / `_committed_operation_paths` | `_PathOperation.bind` 与 `commit` | 未 commit 时 `_rollback_binding`；`_clear_plugin_tracking` 调 `_prune_operation_state` | 同路径并发导入被路径锁挡住，不会出现两个任务同时导入同一路径 |
| `plugin_state.json` | `set_enabled` 与 `install_plugin`（成功后写 true） | `uninstall_plugin` 调 `forget` | 文件损坏按空状态处理并 warning，不阻断启动；无 store 时回落 `_memory_enabled` |
| `data/.plugin-backups/<name>-<stamp>/` | `_backup`（替换安装与卸载都调） | 没有任何清理策略 | 备份失败即整次操作 `ok=False`；卸载时实际代码在 `<stamp>/<name>/` 这一层 |
| `.install-*` 暂存目录 | `install` 用 `mkdtemp(dir=plugin_dir.parent)` | `finally` 里 `rmtree(ignore_errors=True)` | 任何失败都回 `PluginInstallResult(ok=False, error)`，暂存目录必删 |
| `_config_errors[name]` | `_register` 调 `validate_plugin_config` 带回告警时 | 同处校验通过时 pop；`_clear_plugin_tracking` 也清 | 只影响快照与面板提示，插件拿到的配置保证可校验通过 |
| `_plugin_config_consumers[name]` | `register_plugin_config_consumer`（字典赋值，后登记覆盖） | `unload_plugin` **无条件**注销；插件自己也会注销 | 卸载失败也已经注销，面板随后回落「需要重启」 |
| `_CAPTURE_STDOUT` 与 `_CAPTURE_STDERR`（ContextVar） | `_capture_output` 进入钩子或拦截器前 set | `finally` 里 reset 并上报已捕获输出 | 上报失败被吞（不能影响钩子链）；handler 抛异常也不丢已产生输出 |
| `record.error` 与 `record.stop_failed` | `DefaultPluginManager` 的生命周期回调（08-plugins.md） | 成功 reload 或重新 load | `unload` 遇非空 error 返回 `ok=False`，只有 `force=True` 才 ok 且带 `requires_restart=True` |

## 易错点

* **卸载备份会嵌一层**（本次核对实测）：`_backup` 先建好 `<name>-<stamp>/`，`shutil.move(target, backup_path)` 遇到已存在目录会把插件目录挪进去，所以回滚一个被卸载的插件要搬的是 `.plugin-backups/<name>-<stamp>/<name>`，不是 `backup_path` 本身；替换安装的备份才是平铺的。两条路都不清理备份。
* **`reload_all()` 生产零调用点**：只有 `packages/modloader/tests/test_runtime.py` 在调，面板没有「全部重载」按钮。把它当生效链路写文档是错的。
* **一次失败的卸载也会注销配置消费者**：`unload_plugin` 在进入名字锁之前就调 `unregister_plugin_config_consumer(name)`，没有回滚。之后面板保存该插件配置会回落成「重载」或「需要重启」。
* **`_loaded_flags` 不随卸载清理**：`set_enabled(false)` 会显式 pop，`unload_plugin` 走的 `_clear_plugin_tracking` 不会。卸载后改了 `plugin.toml` 的 `hot_reload`，重新发现出的快照仍用旧 flags，直到下一次 `_register`。
* **安装是「先下载后判冲突」**：保留字、同名未替换、`dry_run` 都会把整包拉下来并解压到暂存目录；`probe` 才是零网络探测，但它只查本地目录、不查远端。
* **面板「更新」绕过 runtime**：`api.py:1095` 直调 `installer.update`（带 `expected_name`、`replace=True`）再 `control.reload`。这条链不写 `plugin_state.json`、不做依赖预检，和「安装」的语义不完全对称。
* **同步钩子的 `timeout` 是假的**：`asyncio.to_thread` 里的 handler 无法被 `wait_for` 取消，超时只是「不再等」，线程会继续跑；要真能被取消必须写成 `async def`。
* **`block=True` 是「命中即吞」**：handled 的判据是没超时没异常，与 handler 内部做了什么无关；命令默认 `block=True`、消息默认 `block=False`（`plugin.py:122`）。
* **拦截器返回 None 不等于失败**：超时、异常、正常返回 None 都保持原信封，只记 warning 或 exception；要改信封必须返回 `RuntimeEnvelope`，只改负载返回 dict（只做 `payload.update`）。
* **`snapshot_plugins` 是重操作**：每次调用 `discover_all()`（含单文件插件导入），面板轮询、星舰状态卡、`_snapshot_for`（进而 `check_plugin_update`）都会触发；`dependency_report` 对未注册插件同样要扫全目录。
* **`set_enabled(true)` 先落盘再装载**：装载失败后 `plugin_state.json` 里已经是 true，重启会再试一次；反之卸载失败不会落盘 false，面板上的开关会「弹回去」。
* **两套版本比较不能互换**（细节 9）：依赖判定用 `version.py`（无法比较即放行），更新提示用 `installer.compare_versions`（无法比较即相等）；预发布号在两边结论相反。
* **同名第三方被静默丢弃**发生在 `load_all`（`runtime.py:453`）并且**会清掉刚导入的模块代**；两处「重复注册」语义相反（`HotReloadRegistry` 先到先得 对 `register_plugin_config_consumer` 后到覆盖）见 08-plugins.md 的 W14 与 W38，改 `load_all` 或配置通道时两张图一起改。
