---
flow: 08-plugins
covers:
  - packages/modloader/src/neobot_modloader/loading/
  - packages/modloader/src/neobot_modloader/plugins/registration.py
  - packages/modloader/src/neobot_modloader/loader.py
  - packages/modloader/src/neobot_modloader/manager.py
  - packages/modloader/src/neobot_modloader/dependency.py
  - packages/modloader/src/neobot_modloader/version.py
  - packages/modloader/src/neobot_modloader/state.py
  - packages/modloader/src/neobot_modloader/config_store.py
  - packages/modloader/src/neobot_modloader/config_validation.py
  - packages/modloader/src/neobot_modloader/management.py
  - app/src/neobot_app/runtime/hot_reload_registry.py
  - app/src/neobot_app/runtime/plugin_config_reload.py
  - app/src/neobot_app/bootstrap/_skills.py
verified_against: 99836cd
verified_hash: a9a67a3d2b23
---

# 08 插件系统：扫描 · 加载 · 启停 · 依赖 · 配置热重载

## 范围

本图覆盖 `packages/modloader` 里**除 runtime.py / installer.py / hooks.py 之外**的插件骨架：

* 目录扫描与 `plugin.toml` 元数据：`loader.py`、`loading/manifest.py`、`loading/models.py`；
* 注册与启停状态机、插件句柄与注册表视图：`manager.py`；
* 插件间依赖判定与加载顺序：`dependency.py`、`loading/ordering.py`；
* 模块导入与缓存清理：`loading/importer.py`；启停持久化：`state.py`；
* 插件配置存储与校验：`config_store.py`、`config_validation.py`、`version.py`；
* 两条配置热重载链路：`runtime/hot_reload_registry.py`（本体配置）、`runtime/plugin_config_reload.py`（插件配置原地生效）；
* 装配入口：`bootstrap/_skills.py:91 build_plugin_runtime`。

**不画什么**（避免与相邻图重叠）：

* `modloader/runtime.py`（2328 行编排门面）的逐行细节、`installer.py` 的下载/解压/备份、`hooks.py` 的处理器绑定与参数注入 → 见 `08b-plugin-runtime.md`（待补）。本图只在节点上标注它们的位置与调用顺序。
* `Plugin`（`plugin.py`）的装饰器注册面（命令/工具/Agent/Markdown Skill 绑定）→ 见 06-tools-skills。

**spec 与现实的差异**：实现里**没有文件监听**。全仓没有插件目录 watcher，`reload` 只能由面板按钮 / `plugin_control` 门面 / 插件自身调用触发；`config.reload` 命令只分发**本体**配置（`HotReloadRegistry.apply`），插件配置走 `apply_plugin_config_change` 这条独立通道 —— 两者不互相触发。

## 流程

```mermaid
flowchart TD
    A["build_plugin_runtime / bootstrap/_skills.py:91（同步装配）"] --> B["PluginRuntime.load_all / runtime.py:426"]
    B --> C["scan_dirs(): 官方目录在前, 第三方目录在后 / runtime.py:251"]
    C --> D["FilesystemPluginLoader.load_all / loader.py:82（逐目录）"]
    D --> E{"目录带 __init__.py 或单文件 .py?"}
    E -- 都不是 / 带 _ 前缀 --> E1["跳过: 不是插件, 不报错"]
    E -- 是 --> F["import_module: 清 __pycache__ + 新 gN 命名空间 / importer.py:30"]
    F --> G{"plugin.toml 存在?"}
    G -- 是 --> G1["read_manifest: name / version / priority / dependencies / hot_reload"]
    G -- 否 --> G2["单文件插件: 版本固定 0.1.0, 元数据取 Plugin() 属性"]
    G1 --> H["order_results: 拓扑排序 + 依赖判定 / ordering.py:233"]
    G2 --> H
    H --> I{"依赖问题?（五种 code, 见细节 4）"}
    I -- 有 --> I1["DisabledPlugin: 自动禁用, 不阻断启动, 记 _auto_disabled"]
    I -- 无 --> J["_register: 合并配置 + 校验 + 建上下文 / runtime.py:2114"]
    J --> K["manager.register: 记录 + 名字永久锁 / manager.py:284"]
    K --> L["load_registered: on_load -> LOADED / runtime.py:517"]
    L --> M["start_all: on_start -> RUNNING / runtime.py:522"]
    M --> N["运行期控制入口: set_enabled / reload / unload（面板或命令触发）"]
    N --> O{"改动的是插件配置?"}
    O -- 是, 已登记 config consumer --> O1["apply_plugin_config_change: 只喂运行期安全项 / plugin_config_reload.py:142"]
    O -- 是, 无 consumer --> O2["config_hot_reload? 重载插件 : 提示需重启 / dashboard/api.py:1306"]
    O -- 否 --> P["reload / unload: 先 _cascade_stop_dependents 再动手 / runtime.py:800"]
    O1 -.-> Q["失败: 保留旧配置 + PluginOperationResult(ok=False, error)"]
    P -.-> Q
    I1 -.-> R["前置恢复: _cascade_restore_dependents 自动拉起 / runtime.py:828"]
```

节点全部用符号名 + 文件行号；判据写在菱形上，失败语义用虚线 —— 细节展开见下文 12 个折叠块。

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant P as 面板或命令
    participant RT as PluginRuntime
    participant LD as FilesystemPluginLoader
    participant MG as DefaultPluginManager
    participant PL as Plugin(on_load/on_start)
    participant HR as HotReloadRegistry或plugin_config_reload

    Note over RT,LD: 启动装配（同步, 无 await, 装不下就整段跳过）
    RT->>LD: load_all(plugin_dir) 逐目录（官方目录先）
    LD->>LD: 导入模块（新 gN 命名空间）+ order_results 拓扑排序
    LD-->>RT: LoadedPlugin / DisabledPlugin / PluginLoadError 三选一
    RT->>RT: 存在性依赖 + PyPI 依赖 + min_neobot_version 检查（任一不过 = 跳过加载, 不致命）
    RT->>MG: register(plugin, context)（只登记, 不 await 生命周期）
    Note over RT,MG: 之后 load_registered / start_all 才跑生命周期
    RT->>MG: load_plugin(name)
    MG->>PL: on_load(ctx)（抛错 → ERROR + teardown, 其余插件继续装）
    RT->>MG: start_plugin(name)
    MG->>PL: on_start()（抛错 → ERROR, 已加载的模块不回滚, 可直接重载）

    Note over P,RT: 运行期操作（显式触发, 没有文件监听）
    P->>RT: set_enabled(false) 或 unload 或 reload
    RT->>MG: _cascade_stop_dependents: 先停依赖方（失败不致命, 只记 _auto_disabled）
    MG-->>RT: 名字锁内串行（ReentrantLock 同任务可重入）
    RT->>LD: reload: load_one(path) 重新导入
    LD-->>RT: 新代模块（旧代模块在成功后清缓存）
    alt 新代进入预期状态
        RT->>MG: register + load + start（候选代转正, 然后恢复依赖方）
    else 新代失败
        RT->>RT: _rollback_failed_generation: 丢弃候选代 + 恢复旧代（08b 待补）
    end
    P->>HR: 面板保存插件配置（勾选 reload）
    HR->>HR: classify_plugin_path 最长前缀 -> 只挑运行期安全项
    HR-->>P: ok 或 needs_restart 或 error（error 时旧配置保持不变）
```

三条「不致命」的线要记牢：**单个插件加载失败**只影响它自己；**依赖未满足**是自动禁用而不是异常；**配置消费者失败**只回滚这一次改动，不影响其它组件。

## 细节

<details>
### 发现与元数据：扫描规则、plugin.toml 字段与类型校验

```mermaid
flowchart TD
    A["discover_all(plugin_dir) / loader.py:62"] --> B{"路径存在且是目录?"}
    B -- 不存在 --> B1["返回空列表 + info 日志（按空目录处理）"]
    B -- 是文件 --> B2["PluginLoadError(NotADirectoryError)"]
    B -- 是 --> C["sorted(iterdir()) 按 entry.name 升序 / loader.py:71"]
    C --> D{"entry.name 以 _ 开头?"}
    D -- 是 --> D1["跳过: 约定的停用前缀（快照里显示 enabled=False）"]
    D -- 否 --> E{"是 *.py 文件?"}
    E -- 是 --> E1["_discover_file: 版本固定 0.1.0, 无 manifest"]
    E -- 否 --> F{"是目录且有 __init__.py?"}
    F -- 否 --> F1["跳过: 不是插件, 不算错误"]
    F -- 是 --> G["read_manifest(plugin.toml) / manifest.py:13"]
    G --> H["name / version / description / author / priority"]
    H --> I["dependencies: parse_dependency().describe() 原样保留"]
    I --> J["python_dependencies（兼容 pypi_dependencies / requirements）"]
    J --> K["hot_reload / config_hot_reload: read_optional_bool, 缺省 True"]
    K --> L["missing_python_dependencies: importlib.metadata 逐个探测"]
    L --> M["order_discovery_results: 标注 auto_disabled / disabled_reason / ordering.py:260"]
```

类型校验点（任一不合法该插件变成 `PluginLoadError`，不影响其它插件）：`enabled` 必须 bool、`priority` 必须 int、`dependencies` 必须是 string list、`python_dependencies` 不能含空串、`tags` 最多 16 项且单项不超过 32 字符、`[config]` 必须是 table。`min_neobot_version` 只在 `runtime.py:260 _host_version_error` 里比较，且**只在插件 enabled 时检查**；无法比较（源码运行、版本号非数字开头）时跳过检查并打 warning。
单文件插件（`plugins/foo.py`）没有 manifest 可读：版本恒为 `0.1.0`，依赖/优先级/热重载能力全部取 `Plugin(...)` 上的属性。
</details>

<details>
### 插件 ID 校验与同名去重：__ 是硬禁止、官方插件是保留字

```mermaid
flowchart TD
    A["validate_plugin_name(name) / registration.py:70"] --> B{"非空, 且形如 字母数字下划线点短横线, 长度 1..64?"}
    B -- 否 --> B1["ValueError: invalid plugin name"]
    B -- 是 --> C{"是 . 或 .. , 或跨路径分隔?"}
    C -- 是 --> C1["ValueError: must be a single path-safe component"]
    C -- 否 --> D{"名字含连续两个下划线?"}
    D -- 是 --> D1["ValueError: 与工具命名空间 {plugin}__{tool} 冲突"]
    D -- 否 --> E["通过: 名字同时决定数据目录 plugins_data/name/"]
    E --> F{"第三方插件与官方插件同名?"}
    F -- 是 --> F1["忽略第三方副本, 只 warning, 并清掉它的模块代 / runtime.py:300"]
    F -- 否 --> G["scan_dirs: 官方目录先扫, 第三方目录后扫 / runtime.py:251"]
    G --> H{"名字命中官方插件目录?"}
    H -- 是 --> H1["installer.is_reserved: 保留字, 面板内不能安装或更新"]
    H -- 否 --> H2["manageable: 可安装 / 更新 / 卸载"]
```

数据目录也有越界防线：`runtime.py:2192 _plugin_data_dir` 要求 `data_dir / name` 解析后仍是 `data_dir` 的**真子目录**，否则抛 `ValueError` 并让注册失败。工具全局名另有约束：`validate_qualified_tool_name` 要求 `{plugin}__{tool}` 整体匹配 `[A-Za-z0-9_-]{1,64}`（点号本身合法，但拼出来的名字超长或带点会被拒）。
</details>

<details>
### 依赖声明解析：名字 + 逗号分隔的版本约束，无法比较一律放行

```mermaid
flowchart TD
    A["plugin.toml 的 dependencies=[dashboard>=1.0.0] 或 Plugin(dependencies=[...])"] --> B["parse_dependency(raw) / dependency.py:57"]
    B --> C["拆成 name + specifier: name 走插件名同一套校验"]
    C --> D{"specifier 为空?"}
    D -- 是 --> D1["任意版本: matches() 直接返回 True"]
    D -- 否 --> E["_validate_specifier: 逗号分条, 每条 = 可选操作符 + 版本"]
    E --> F{"操作符"}
    F -- "~= 兼容发布" --> F1["_compatible_release_satisfied: 1.4.2 展开为 大于等于 1.4.2 且小于 1.5.0"]
    F -- "大于等于 / 小于等于 / 等于 / 不等 / 大于 / 小于" --> F2["compare_plugin_versions: 只比数字段"]
    F -- 缺省 --> F3["按等于处理"]
    F1 --> G{"可比较?"}
    F2 --> G
    F3 --> G
    G -- 否 --> G1["返回 None: 调用方按满足放行（源码运行 0.0.0 等）"]
    G -- 是 --> H["多条约束取与: 任一条 False 即 False"]
    H --> I["resolve_load_order 只拦 False / ordering.py:144"]
    D1 --> I
```

版本口径（`version.py`）：`1.0` 与 `1.0.0` 相等（去尾零）；预发布后缀被忽略，`1.0.0-alpha.1` 按 `1.0.0` 处理；`compare_plugin_versions` 对**任一侧解析不出数字**或**全零版本**（源码运行回落 `0.0.0`）返回 `None`，语义是「无法比较，别拦」。
`parse_dependencies` 额外拒绝两类写法：单个字符串（必须是列表）、同名依赖声明两次。
</details>

<details>
### 依赖未满足的自动禁用：五种 code 与沿依赖链的传播

```mermaid
flowchart TD
    A["resolve_load_order(entries, unavailable) / ordering.py:62"] --> B["同名只留第一个, 其余进 duplicates"]
    B --> C["逐插件 parse_dependencies"]
    C --> D{"解析抛错?"}
    D -- 是 --> D1["dependency-invalid: 依赖声明非法"]
    D -- 否 --> E["_cycle_members: DFS 找全部环上节点 / ordering.py:183"]
    E --> F{"在环上?"}
    F -- 是 --> F1["dependency-cycle: 附一条闭合路径"]
    F -- 否 --> G["反复扫描直到不再新增: 阻塞沿依赖链传播"]
    G --> H{"逐条依赖判据"}
    H -- "前置自己已被禁用" --> H1["dependency-disabled"]
    H -- "记录不存在但在 unavailable" --> H2["dependency-disabled: 前置被停用"]
    H -- "记录不存在且不在 unavailable" --> H3["dependency-missing: 缺少前置插件"]
    H -- "记录存在但版本判定为 False" --> H4["dependency-version"]
    H -- "全部满足" --> I["进入 _visit 拓扑序"]
    I --> J["外层排序键: priority 降序, 同级按名字升序 / ordering.py:111"]
    D1 -.-> K["结果: PluginOrdering(ordered, blocked, duplicates)"]
    F1 -.-> K
    H1 -.-> K
    H2 -.-> K
    H3 -.-> K
    H4 -.-> K
```

**四个判定入口不能混用**，这是启动期最容易踩的坑：

| 入口 | 时机 | 判据 | 不满足的后果 |
|---|---|---|---|
| `ordering._evaluate` | `loader.load_all` 排序时 | 静态快照 + `unavailable` 名单 | 变 `DisabledPlugin` |
| `runtime._dependency_presence_issues` | `load_all` 注册阶段 | 只查记录**在不在**，不要求已加载 | 自动禁用（跳过注册） |
| `runtime._dependency_issues` | 启动 / 激活 / 重载插件 | 要求前置状态在 LOADED 或 RUNNING，且版本满足 | 返回 `ok=False` + 原因 |
| `PluginRegistryView.dependency_issues` | 面板查询 | 同上一行，但只产出文本 | 只展示，不拦操作 |

注册阶段之所以只查「在不在」：`load_all` 只做扫描与登记，各插件的 `on_load` 发生在之后的 `load_registered()`，此时要求前置就绪会把**所有**依赖插件误判成自动禁用（`runtime.py:364` 的注释写明了这一点）。
注意自动禁用条目在 `loader.load_all` 里同样会清模块缓存 —— 被禁用的插件不该把自己的模块代留在 `sys.modules`。
</details>

<details>
### 加载顺序与模块缓存清理：gN 代际命名空间 + 删 __pycache__

```mermaid
flowchart TD
    A["import_module(path, name) / importer.py:30"] --> B["importlib.invalidate_caches()"]
    B --> C["rmtree(插件目录下 __pycache__): 防止复用旧 .pyc"]
    C --> D["模块名 = namespace.安全名_路径sha1前12位_gN / importer.py:63"]
    D --> E["sys.modules[module_name] = module 之后 exec_module"]
    E --> F{"exec 抛错?"}
    F -- 是 --> F1["clear_module_cache(本代) 后原样抛出"]
    F -- 否 --> G["last_module_names = 该前缀下全部子模块（含 . 子模块）"]
    G --> H["clear_module_cache(names) / importer.py:24"]
    H --> I["按名字长度倒序删除: 自身 + 所有 name. 前缀的子模块"]
    I --> J["清理点① 导入失败；② load_all 里被自动禁用或被官方同名覆盖"]
    J --> K["清理点③ _activate_loaded_plugin 依赖未满足；④ 已注册时跳过重复注册"]
    K --> L["清理点⑤ _register 异常（注册失败滞留在 sys.modules）；⑥ 重载成功后清旧代"]
```

namespace 分两个：第三方插件 `neobot_user_plugins`，官方插件 `neobot_builtin_plugins`（`runtime.py:140`、`runtime.py:145`）。
**反直觉之处**：模块名里带自增代际 `_gN`，所以「热重载会复用到旧模块」在当前实现里不成立 —— 真正保证新代码生效的是**删掉 `__pycache__`**（避免按源码 mtime 判定时命中旧字节码）。清理 `sys.modules` 的作用变成了「不留孤儿代」：注册失败、被禁用、被同名覆盖的插件，其模块不会注册进管理器，留着只占内存并污染排查视野。
</details>

<details>
### 注册装配：配置三段合并 + 校验回落 + 上下文注入

```mermaid
flowchart TD
    A["_register(loaded) / runtime.py:2114"] --> B["validate_plugin_name 再校验一次"]
    B --> C["_plugin_data_dir: data_dir/name, 越界即抛错"]
    C --> D["_manifest_configs.setdefault: 缓存 plugin.toml 的 [config] 默认值"]
    D --> E["PluginConfigStore.read(): [config] 打底 + plugins_data/name/config.toml 覆盖"]
    E --> F["嵌套表递归合并 merge_plugin_config / config_store.py:27"]
    F --> G["validate_plugin_config(model, merged, stored) / config_validation.py:14"]
    G --> H{"能过 config_model 校验?"}
    H -- 否 --> H1["只回退出错的已存字段, 再不行回退模型默认值"]
    H1 --> H2["记 _config_errors[name], 面板展示告警"]
    H -- 是 --> H3["清除 _config_errors[name]"]
    H2 --> I["RuntimePluginContext(plugin_name, plugin_dir, data_dir, config, hook_bus, plugin_registry ...)"]
    H3 --> I
    I --> J["manager.register(plugin, context) / manager.py:284"]
    J --> K{"名字已注册?"}
    K -- 是 --> K1["ValueError: 插件已注册"]
    K -- 否 --> L["写 PluginRecord + setdefault 名字锁（永久保留）"]
    L --> M["记录 _loaded_modules / _loaded_paths / _loaded_sources / _loaded_flags"]
    M --> N["_auto_disabled.pop(name): 注册成功即依赖已满足"]
    J -.-> O["异常: clear_module_cache + 返回 False"]
```

插件配置与代码分离：默认值随插件包走（`plugin.toml` 的 `[config]`），用户改动落在 `plugins_data/<插件名>/config.toml`，**重装/更新插件不会丢配置**；校验失败不硬失败 —— 非法已存字段回落默认值并记 `_config_errors`，插件拿到的配置保证能通过它自己的 `config_model`（面板这类「配置坏掉就再无修复入口」的插件全靠这条）。
</details>

<details>
### 启停状态机与依赖联动：谁先停、谁来恢复

```mermaid
flowchart TD
    A["set_enabled(name, enabled) / runtime.py:1457"] --> B{"enabled?"}
    B -- 否 --> C["unload_plugin: 先 _cascade_stop_dependents, 再摘记录"]
    C --> D["_persist_enabled_state(false): PluginStateStore 落盘, 无存储则记内存"]
    B -- 是 --> E["_persist_enabled_state(true)"]
    E --> F["load_plugin_path(start=True)"]
    F --> G["_activate_loaded_plugin: PyPI 依赖 -> min_neobot_version -> _dependency_issues"]
    G --> H{"依赖问题?"}
    H -- 有 --> H1["自动禁用: 记 _auto_disabled[name]=(前置, 原因), 返回 ok=False 且 state=unloaded"]
    H -- 无 --> I["register -> manager.load_plugin -> on_load -> LOADED"]
    I --> J["manager.start_plugin -> on_start -> RUNNING"]
    J --> K{"进入 RUNNING 且 record.error 为空?"}
    K -- 否 --> K1["_operation_result_from_record: ok=False + 未进入预期状态"]
    K -- 是 --> L["_cascade_restore_dependents: 把因它被禁用的插件重新拉起"]
    C --> M["_cascade_stop_dependents: dependents_of(传递闭包), 只处理 LOADED/RUNNING 的依赖方"]
    M --> N["恢复时机只有两处: reload 成功 / set_enabled(true) 成功"]
```

状态机本体在 `manager.py`：`_load_plugin_locked` 只接受 UNLOADED / STOPPED 起步，`_start_plugin_locked` 在 STOPPED 时会先补一次 `load_plugin`；`on_load` / `on_start` 抛错都进 ERROR 并立刻 `_teardown_owned_resources`（清理回调、事件订阅、Agent 注销、插件数据库关闭，`manager.py:583`）；已处于 STOPPING 或 `_teardown_depth>0` 时再次 stop 直接返回 False，不污染外层那次停止的记账。
`_cascade_restore_dependents` 只认 `_auto_disabled` 里 `前置 == 刚恢复的插件` 的条目；路径找不到就静默丢弃该条目（插件目录被删了）。
</details>

<details>
### 操作并发：可重入名字锁 + 拒绝逆序等待的 OperationBusy

```mermaid
flowchart TD
    A["_named_operation(name) / runtime.py:1818"] --> B["_operation_gate 只在取锁或建锁时持有, 不跨锁等待"]
    B --> C{"当前任务已持有该名字锁?"}
    C -- 是 --> C1["直接复用: ReentrantLock 同任务可重入, 回调里再进不会自死锁"]
    C -- 否 --> D{"别的任务持有?"}
    D -- 否 --> E["acquire 名字锁（懒建）"]
    D -- 是 --> F["_held_lock_names: 本任务已持有的全部名字"]
    F --> G{"当前 name 小于已持有名字的最大值?"}
    G -- 是 --> G1["raise OperationBusy: 不按逆序等待, 避免两个插件互相卸载时死锁"]
    G -- 否 --> E
    E --> H["yield 给操作体, finally release"]
    H --> I["_prune_operation_lock: 锁空闲且无路径绑定才删除"]
    A --> J["manager 侧第二把锁 _plugin_locks[name] / manager.py:291"]
    J --> K["setdefault 建锁: 名字锁永久保留, 替换会让排队者与新记录竞争"]
    K --> L["remove_plugin 在锁内做 expected 身份比对: 记录被换过就放弃移除"]
    L --> M["_PathOperation: 按路径先去重, 防同一路径并发导入两次"]
    G1 -.-> N["调用方收到 PluginOperationResult(ok=False, error=操作占用) 并剪枝锁"]
```

失败路径也必须剪枝：`load_plugin_path` / `unload_plugin` / `start_plugin` / `stop_plugin` / `reload_plugin_result` 在 `ok=False` 时都调用 `_prune_operation_lock`，否则 ghost 操作会一直占着名字锁，后续面板操作全变成「操作占用」。
`ReentrantLock` 的 `_pending` 计数是给「闲置剪枝」用的：有人正在排队等锁时 `is_free()` 为假，不能被剪掉。
</details>

<details>
### 插件本体热重载：候选代转正，失败必须回滚旧代

```mermaid
flowchart TD
    A["reload_plugin_result(name) / runtime.py:854"] --> B["先 _cascade_stop_dependents: 重载要短暂摘掉插件"]
    B --> C{"_loaded_flags[name] 的第一位为 False?"}
    C -- 是 --> C1["直接拒绝: 声明不支持热重载, requires_restart=True"]
    C -- 否 --> D["定位代码: _loaded_paths 优先, 否则 _find_plugin_path 重新发现"]
    D --> E["loader.load_one: 重新导入（新 gN 命名空间 + 删 __pycache__）"]
    E --> F{"是新 LoadedPlugin 且名字没变?"}
    F -- 否 --> F1["清新代模块缓存, 拒绝（重载不能改名）"]
    F -- 是 --> G["_remove_manager_record(force=False): 摘旧记录"]
    G --> H{"旧记录摘干净且没有错误?"}
    H -- 否 --> H1["_restore_old_generation: 重新注册旧 plugin 对象并恢复原状态"]
    H -- 是 --> I["register 新代 -> load_plugin -> start_plugin"]
    I --> J{"新代进入 RUNNING / LOADED?"}
    J -- 是 --> K["清旧代残留模块, 成功, 随后 _cascade_restore_dependents"]
    J -- 否 --> L["_rollback_failed_generation: 丢弃候选代 + 恢复旧代"]
    L -.-> M["失败文本: 已恢复旧版本 / 旧版本回滚失败: 原因"]
```

判据细节：`hot_reload` 与 `config_hot_reload` 的最终取值是「`plugin.toml` 显式声明优先，否则取 `Plugin(...)` 的属性，都没有则 True」（`loader.py:276`、`loader.py:279`），快照里已加载插件用 `_loaded_flags` 覆盖发现结果（`runtime.py:1355`）。
回滚细节（旧代重新注册、按原状态恢复 RUNNING/LOADED、候选代清理）见 `08b-plugin-runtime.md`（待补）；本图只标出「失败必须回到旧代」这条不变量。
</details>

<details>
### 配置热重载（本体侧）：HotReloadRegistry 的前缀匹配与失败隔离

```mermaid
flowchart TD
    A["装配: HotReloadRegistry(consumers) / bootstrap/__init__.py:784"] --> B["register(consumer) / hot_reload_registry.py:135"]
    B --> C{"满足 ConfigConsumer 协议?"}
    C -- 否 --> C1["TypeError: 必须实现 name / config_paths / hot_reload_policies / apply_config"]
    C -- 是 --> D{"同名消费者已注册?"}
    D -- 是 --> D1["忽略 + warning（先注册者胜, 幂等）"]
    D -- 否 --> E["追加进列表: 调用顺序 = 注册顺序, 由装配方表达依赖"]
    E --> F["hot_reload_policies 非空 -> register_rules 写进 config.hot_reload 分类表"]
    F --> G["_reload_config: changed_paths = 改动项 path 并集 / _pipeline.py:124"]
    G --> H["consumers_for(paths) / hot_reload_registry.py:168"]
    H --> I["_matches: 点分前缀匹配, path 等于 prefix 或以 prefix 加点开头"]
    I --> J{"任一 config_paths 命中?"}
    J -- 否 --> J1["该消费者不被调用: 没有它关心的改动就不打扰"]
    J -- 是 --> K["apply: 按注册顺序逐个 await apply_config"]
    K --> L{"单个抛异常?"}
    L -- 是 --> L1["记 outcome(applied=False, error) 后继续下一个"]
    L -- 否 --> L2["记 outcome(applied=True)"]
    L1 --> M["HotReloadReport: applied / failed / summary"]
    L2 --> M
```

空 `changed_paths` 直接返回空元组；前缀匹配按「点分」而不是字符串包含，所以 `adapter` **不会**命中 `adapter_x`（`hot_reload_registry.py:181`）。单消费者失败被吞成 `ReloadOutcome`，其余组件继续 —— 这是刻意的失败隔离，代价是「部分生效」在返回值里，不看 `failed` 字段就发现不了。
软重启会重新装配 bot 侧组件，`bootstrap/__init__.py:1182` 先 `unregister` 旧消费者再注册新的：旧消费者持有已释放对象，留着会被喂到死对象上。
</details>

<details>
### 插件配置原地生效：最长前缀分类 + 无 hot 项不调用

```mermaid
flowchart TD
    A["面板保存插件配置且勾选 reload / dashboard/api.py:1297"] --> B{"插件登记了 config consumer?"}
    B -- 否 --> B1["回落: config_hot_reload=True 则 control.reload(name), 否则提示需重启"]
    B -- 是 --> C["before = 保存前的 plugin_config_values(control, name)"]
    C --> D["after = 保存后重新读盘的生效配置"]
    D --> E["diff_plugin_config: 逐 key 比对, 只留真正变化的 / plugin_config_reload.py:113"]
    E --> F["路径 = plugin.插件名.key / :25"]
    F --> G["classify_plugin_path: 最长前缀优先匹配 hot_reload_policies / :45"]
    G --> H{"命中了任何策略?"}
    H -- 否 --> H1["按需要重启处理（保守假设, 新字段不会被误判为可热重载）"]
    H -- 是 --> I["按策略拆成 hot 集合与 needs_restart 集合"]
    I --> J{"hot 集合为空?"}
    J -- 是 --> J1["不调用 apply_config, 返回 ok=False + needs_restart"]
    J -- 否 --> K["await consumer.apply_config(after)"]
    K --> L{"抛异常?"}
    L -- 是 --> L1["返回 error, 旧配置保持不变（消费者保证不部分应用）"]
    L -- 否 --> L2["ok=True + applied 列表, 面板提示 N 项立即生效"]
```

路径命名空间刻意**不写进本体分类表**（`plugin_config_reload.py:12`）：插件配置不属于 `config.toml`，混进去会让面板的本体配置页冒出幻觉条目。
dashboard 是这套通道的样板：`hot_reload=False` / `config_hot_reload=False`（`dashboard/__init__.py:29`），但登记了消费者并逐项声明 —— 8 项运行期安全（`latency_probe_interval_seconds`、`latency_probe_idle_seconds`、`latency_probe_active_window_seconds`、`latency_probe_gate_check_seconds`、`bot_info_cache_ttl`、`log_buffer_size`、`history_max_days`、`allow_archive_delete`），10 项需重启（`host`、`port`、`base_path`、`manage_plugins`、`allow_remote_manage`、`session_timeout_minutes`、`secure_cookies`、`trust_proxy_headers`、`login_max_failures`、`login_rate_limit_window_seconds`）。面板持有 HTTP 服务与监听端口，整插件重载会切断当前保存请求并丢掉内存指标，所以「立即生效」只能走原地通道。
</details>

<details>
### 跨插件调用：require 校验就绪与版本，call 有三种能力形态

```mermaid
flowchart TD
    A["插件 A: ctx.plugins.require(name, specifier) / manager.py:202"] --> B{"注册表里有这个名字?"}
    B -- 否 --> B1["PluginDependencyError: 前置插件未加载"]
    B -- 是 --> C["PluginHandle.require / manager.py:131"]
    C --> D{"record.state 在 LOADED 或 RUNNING?"}
    D -- 否 --> D1["PluginDependencyError: 前置插件未就绪（附当前状态）"]
    D -- 是 --> E["satisfies(specifier): version_satisfies, 只有 False 才拒绝, None 放行"]
    E --> F["handle.call(capability, payload) / manager.py:144"]
    F --> G{"capability 在 _capability_names(plugin) 里?"}
    G -- 否 --> G1["KeyError: 插件未导出该能力"]
    G -- 是 --> H["形态① 有 call_capability 方法 -> 直接调用"]
    H --> I["形态② 有 invoke_capability 方法 -> 直接调用"]
    I --> J["形态③ capabilities 是映射: 取 target, 调用 target 本身或其 .call / .invoke"]
    J --> K["_maybe_await: 同步返回值也接受（不强制协程）"]
    K --> L["optional(name): 不存在或未就绪返回 None, 不抛错"]
    L --> M["反向依赖 dependents_of(name, transitive) / manager.py:224"]
    M --> N["面板: dependency_report(name) 依赖 / 问题 / 反向依赖 / 自动禁用原因"]
    M --> O["停用 / 卸载 / 重载时被 _cascade_stop_dependents 消费"]
```

能力名规则：`[A-Za-z0-9_.:-]{1,64}`（`validate_capability_name`）。`PluginHandle.ready` 读的是**被持有那个记录**的状态（句柄通常持的是前置插件），所以 `require().call()` 在插件自己的 `on_load` 里调用依赖方时常因前置仅 LOADED、未 RUNNING 之外的组合而抛错 —— 跨插件调用应放在 `on_start` 之后，或先用 `optional()` 判空。
`dependents_of` 完全基于插件**声明**的 `plugin.dependencies`（解析失败按无依赖处理），不看运行时是否真的调用过。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `PluginState.UNLOADED` | 初始值；`_unload_plugin_locked` 成功后 | 下一次 `register`+`load` | 取消/未完成时返回 `ok=False, state=unloaded` 并附原因 |
| `LOADING -> LOADED` | `manager._load_plugin_locked`（on_load 正常返回后） | `unload` / `remove_plugin` | on_load 抛错 -> `ERROR` + 立即 teardown；插件不参与后续 |
| `STARTING -> RUNNING` | `manager._start_plugin_locked`（on_start 正常返回后） | `stop` / `unload` | on_start 抛错 -> `ERROR`（模块仍注册，可直接重载） |
| `STOPPING -> STOPPED` | `manager._stop_plugin_locked` | `start_plugin` 会先补 `load_plugin` | on_stop 抛错 -> `stop_failed=True` 且错误进 `record.error`，下次 stop 重试 |
| `ERROR` | on_load / on_start 异常或被取消 | 成功重载、或 STOPPED 后重新 load、或移除记录 | 终态：不自动恢复，面板显示 `record.error` |
| `_auto_disabled[name]=(前置, 原因)` | `_remember_auto_disabled`（排序结果 / 依赖未满足 / 联动停用） | `_register` 成功、`_cascade_restore_dependents` 成功、`set_enabled(true)` 成功 | 前置一直缺失则保持 unloaded，启动不受影响 |
| `_loaded_modules / _loaded_paths / _loaded_sources / _loaded_flags` | `_register` | `_clear_plugin_tracking` | 清理时按值比对，避免清掉并发替换后的新记录 |
| `manager._plugin_locks[name]` | `manager.register` 的 setdefault | 原则上不清理 | 锁被替换会让排队者与新记录竞争，所以只增不减 |
| `runtime._operation_locks[name]` | `_named_operation` 懒建 | `_prune_operation_lock`（空闲且无路径绑定） | 失败路径也剪枝，避免 ghost 操作占锁 |
| `plugin_state.json`（PluginStateStore） | `set_enabled` 落盘（临时文件 + 原子替换） | `uninstall_plugin` 调 `forget` | 文件损坏按空状态处理并 warning，不阻断启动 |
| `_plugin_config_consumers[name]` | `register_plugin_config_consumer`（后登记覆盖先登记） | `unload_plugin` 主动注销 / 插件自行注销 | 未登记则面板回落「需要重启」 |
| `_config_errors[name]` | `_register` 校验失败 | 校验通过时弹出 / `_clear_plugin_tracking` | 只影响提示，插件拿到的配置保证可校验通过 |
| `HotReloadRegistry._consumers` | `register`（同名忽略） | `unregister`（软重启前） | 一个都不命中时报告写「没有组件声明关心本次改动的配置项」 |

## 易错点

* **没有文件监听**：改完插件代码不会自动生效。面板「重载」按钮 / `control.reload` / 插件里调 `plugin_control` 才是触发点；`config.reload` 只重载**本体**配置。
* **`hot_reload=False` 是硬闸**：`_loaded_flags[name][0]` 为假时重载直接被拒并置 `requires_restart=True`（`runtime.py:904`）。dashboard 就是靠这条 + 配置消费者，把「立即生效」改走原地通道。
* **依赖未满足 ≠ 报错**：它变成 `DisabledPlugin` / `auto_disabled`，程序照常启动；面板上看到的是「自动禁用 + 原因」，重置依赖后会被 `_cascade_restore_dependents` 自动拉起，不需要用户手工启用。
* **版本无法比较时放行**：`version_satisfies` 返回 `None` 时 `_evaluate` 不拦；源码运行 `0.0.0`、非数字版本号都会走这条路 —— 「明明写了约束却没拦」是设计如此。
* **注册阶段只查依赖在不在**（`_dependency_presence_issues`）：跨目录场景下可能出现「前置已注册但还没 `on_load`」的窗口，此时插件在 `on_load` 里 `require().call()` 会抛 `PluginDependencyError`。跨插件调用放到 `on_start` 之后更稳。
* **清理模块缓存 ≠ 让新代码生效**：新代码靠 `_gN` 新命名空间 + 删 `__pycache__`；清理是为了不留孤儿模块代（注册失败、被禁用、被官方同名覆盖三种情况必须清）。
* **`clear_module_cache` 按「名字长度倒序 + 前缀」删**：传进来的名字包含全部子模块，顺序反了会先删父再删子（子模块名仍能匹配前缀，所以实际仍能删净）；但只传顶层名字不会删掉 `pkg.sub`。
* **插件名含连续两个下划线直接拒绝**：与工具全局名 `{plugin}__{tool}` 的分隔符冲突，早失败好过在 `bind_tools` 阶段整批注册失败。
* **官方插件与第三方插件同名时静默丢弃第三方**：只有一条 warning，没有任何面板冲突提示（安装路径的冲突提示是 `installer.probe` 的另一回事，见 08b 待补）。
* **两处「重复注册」语义相反**：`HotReloadRegistry.register` 同名忽略（先注册者胜），`PluginRuntime.register_plugin_config_consumer` 是字典赋值（后登记覆盖）。
* **联动停用只发生在 `stop/unload/reload` 入口**，恢复只发生在 `reload` 成功或 `set_enabled(true)` 成功；手工 `manager.stop_plugin` 绕过 runtime 不会触发联动。
* **操作锁只增不减是刻意的**（manager 侧），runtime 侧的操作锁却要主动剪枝 —— 改这两个字典时别把策略搞反。
* **`plugin.toml` 与 `Plugin(...)` 的 name/version 必须一致**：不一致在 `validate_manifest_conflicts` 直接报错（`manifest.py:98`），而 `dependencies`/`priority`/`min_neobot_version` 是「manifest 优先，缺失才回落到代码」。
* **`_cascade_restore_dependents` 只认配对的前置名**：如果联动停用时记的前置名字与实际恢复的插件不同（例如中途改了依赖声明），条目会被静默丢弃，插件再也拉不起来。
