---
flow: 08b-plugin-runtime
covers:
  - packages/modloader/src/neobot_modloader/runtime.py
  - packages/modloader/src/neobot_modloader/hot_reload.py
  - app/src/neobot_app/runtime/local_control.py
  - packages/modloader/src/neobot_modloader/development.py
  - packages/modloader/src/neobot_modloader/installer.py
  - packages/modloader/src/neobot_modloader/hooks.py
  - packages/modloader/src/neobot_modloader/management.py
  - packages/modloader/src/neobot_modloader/config_store.py
  - packages/modloader/src/neobot_modloader/config_validation.py
  - packages/modloader/src/neobot_modloader/plugins/dispatch.py
  - packages/modloader/src/neobot_modloader/plugins/injection.py
  - packages/modloader/src/neobot_modloader/plugin.py
  - packages/modloader/src/neobot_modloader/context.py
  - packages/modloader/src/neobot_modloader/bot.py
  - packages/modloader/src/neobot_modloader/message.py
  - packages/modloader/src/neobot_modloader/events.py
  - packages/modloader/src/neobot_modloader/messaging.py
  - packages/modloader/src/neobot_modloader/rules.py
  - packages/modloader/src/neobot_modloader/plugins/commands.py
  - packages/modloader/src/neobot_modloader/sdk/
  - scripts/plugin_ci.py
  - scripts/plugin_ci_support.py
  - scripts/plugin_ci_process.py
  - scripts/plugin_ci_pytest.py
  - scripts/plugin_registry.py
  - scripts/plugin_compat.py
  - scripts/plugin_ecosystem.py
  - scripts/plugin_demo.py
  - scripts/plugin_demo/
verified_against: 6d95ad1
verified_hash: 6a242654104c
---

# 08b 插件运行时：门面动作矩阵 · 热重载回滚 · 安装器 · 钩子总线

## 范围

本图覆盖 `packages/modloader` 里**运行时门面与安装/钩子**这一层：

* `runtime.py` 的 `PluginRuntime` 门面：加载 / 卸载 / 启停 / 热重载 / 快照 / 依赖报告 / 配置读取，以及并发锁与路径绑定；
* `hot_reload.py`：已加载源码的线程指纹扫描、稳定保存防抖、运行代复核与监测任务收尾；
* `development.py`：同一实例内加载新建插件、选择开发监听、全局禁用/停用/路径校验；
* `installer.py`：GitHub 来源解析、代理、下载与解压防线、安装 / 更新 / 卸载、备份目录、更新检查；
* `hooks.py`：`PluginHookBus` 的订阅 / 退订 / 优先级 / 超时 / 阻断，`dispatch_envelope` 信封派发与输出捕获；
* `management.py`：`PluginOperationResult` / `PluginSnapshot` / `PluginControlFacade`（面板与插件看到的窄门面）；
* `config_store.py` + `config_validation.py`：`plugin.toml` 的 `[config]` 打底 + `plugins_data/<name>/config.toml` 覆盖 + 校验回落；
* `plugins/dispatch.py`：`Plugin.command/message/...` 装饰器到钩子总线订阅的桥。
* `sdk/`：模型契约、动作/资源/教程/页面、运行代绑定，以及插件工程生成、确定性 ZIP、安装、存储租约与维护期升级工具；详见[插件 SDK 与工程验收](../04-功能文档/插件SDK与工程验收.md)。

统一动作通过 `control.invoke_action` 在插件名字锁内定位当前就绪记录，绑定其实际上下文后校验身份、权限、输入和输出。
停用插件只读取包内静态契约，不执行入口。发送入口在 `Bot` 与上下文统一归一化，消息链可按段查询并保留未知段。

静态契约先统一校验 Schema 子节点容器与正则表达式，再进行默认值脱敏和字段引用检查。畸形声明返回字段位置诊断，`check --json` 仍输出结构化失败报告；内部遍历不重复添加同类兜底。

教程步骤可以增加 `command={text, context, reply?}`，声明与静态契约共用结构校验并深拷贝导出。它只描述实际聊天入口，不注册或代发命令；目标引用仍必须对应现有字段、动作、资源或页面锚点，命令可达性由作者业务用例验证。内置生成器提供配置和 `/ping` 的示例。

命令显式声明 `permission` 时，`plugins/commands.py` 将 DSL 参数解析接入宿主命令表，复用权限、帮助、别名及重名回退；省略权限时保留钩子匹配路径。`IncomingEvent` 与组合规则统一读取原事件和消息链，`create_task` 托管的后台交互在插件停止时先取消再释放业务资源。`message_session` 和 `wait_for_message` 按机器人、会话与用户隔离后续消息，超时、取消或停止均注销监听。

`init` 从 SDK 安装包中的 starter 素材生成入口、实际命令注册测试、README、AGENTS 和 GUIDE；完整表单教程与命令验证样例在同一个工程内。修改声明后显式导出契约，再执行相同的静态、业务、确定性打包与最终 ZIP 安装流程；生成器不覆盖已有目录，也不自动修改真实宿主配置。

插件工程检查、打包与维护期升级按以下流程执行。升级需要退出宿主并取得操作系统租约，只有带存储声明的插件适用。

```mermaid
flowchart LR
    T[插件模板] --> I[init 独占创建新工程]
    I --> C[静态声明与资源引用检查]
    C --> E[导出契约比较与真实业务 suite]
    E --> Z[两次构建摘要一致]
    Z --> S[输入 ZIP 安装启停重载]
    S --> R[本地候选绑定源码树与包摘要]
    R --> A[受控重测重建并再次验收输入 ZIP]
    Z --> U[退出宿主取得存储租约]
    U --> DEP[预检旧版与候选的前置闭包]
    DEP --> B[备份代码与数据后在副本迁移]
    B --> V[按实际宿主版本和前置顺序激活候选]
    V -->|成功| OK[保留业务数据与备份]
    V -->|失败| BACK[恢复旧代码配置和数据库并验证旧版]
```

Windows 新建工程采用验证后独占创建与复制，避免只读文件句柄阻止整目录改名；不会覆盖已有目标。维护升级通过 `--builtin-dir` 显式接收官方来源，只导入并启动目标的前置闭包，候选与回滚采用同一来源；缺失、停用、版本不符和依赖成环均在数据迁移前退出。自动回滚覆盖升级目标，不覆盖前置自身可能产生的业务写入；维护前需备份关联数据。维护升级不承诺无停机或强杀断电后的自动事务续作。迁移失败、候选启动写入后失败、最低宿主版本不符与在线租约冲突均有实际回归。

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

* `[plugins].watch` 默认 `false`，开启并重启后，每 1s 扫描已就绪且支持热重载的插件，源码指纹稳定至少 300ms 后调用现有 `reload_plugin_result`；面板与插件自身仍可显式重载；
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
    H --> I["start_all / runtime.py:499：on_start -> RUNNING<br/>watch=True 再启动源码监测"]
    I --> J{"运行期入口"}
    J -- "面板或插件调 control.set_enabled" --> K["set_enabled / runtime.py:1457"]
    J -- "control.reload 或源码保存稳定" --> L["reload_plugin_result / runtime.py:848"]
    J -- "本机 /v1/plugins/dev" --> DV["development.set_enabled<br/>静态检查 + 加载新插件 + 选择监听"]
    DV --> DW["当前实例选定源码监听<br/>后续保存才触发事务重载"]
    DW -- 保存稳定 --> L
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

主图只画主干：每个动作的前置判据与失败语义在下面的折叠块里。运行时门面以
`PluginOperationResult` 返回失败；新增本机开发入口使用 `DevelopmentError(code, message)`，
由控制服务转成统一 JSON 错误，不把开发入口的异常与既有 bool 包装器混为一谈。

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant P as 面板或插件自身
    participant LC as 本机 CLI 控制服务
    participant DV as PluginDevelopment
    participant GW as EventGateway
    participant RT as PluginRuntime
    participant HW as PluginHotReloader
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

    opt plugins.watch=True
        RT->>HW: start_all 末尾 await start() 建立指纹基线
        HW->>HW: 每 1s 在线程扫描，稳定至少 300ms
        HW->>RT: reload_plugin_result(_expected, auto_install_dependencies=False)
    end
    opt 独立 CLI / Textual 选择某个插件开发
        LC->>DV: set_enabled(name, true)
        DV->>DV: 先检查全局启用、实例内路径、静态契约与原启停状态
        DV->>RT: 新建插件 load_plugin_path，禁止自动安装依赖
        DV->>HW: 复用全局监测器或 names 过滤的单一监测器
        LC->>DV: status(name) 读取开发选择与监测结果
        DV-->>LC: development 与 reload sequence/status/error
    end
    opt 本机显式重载
        LC->>RT: reload_plugin_result(_expected=原记录和状态)
        Note over LC,RT: 依赖联动后锁内复核；停止、停用或换代已完成则返回409
    end
    Note over P,RT: 运行期动作（显式与自动触发共用事务）
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
    RT->>DV: stop_all 首先关闭开发选择与自持监测器
    RT->>HW: 再停止全局监测器，等待在途重载/回滚
    RT->>MG: 再逆序 stop_plugin(name)
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
* 新代成功后恢复依赖方；新代失败但旧代恢复就绪时也要恢复依赖方，取消操作同样先恢复再传播取消。
* `_auto_disabled` 保存全部前置名称，按依赖拓扑恢复多前置和传递依赖，恢复失败写进结果，不能冒充整体成功。
* 包内默认配置按插件代更新缓存；候选代失败恢复旧缓存，卸载清理缓存，避免重载后沿用旧清单默认值。

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

<details>
### 源码自动热重载：线程指纹扫描、300ms 防抖与停止优先

```mermaid
flowchart TD
    A["全局 watch=True 或开发选择 names 集合"] --> B["全局 start_all 或选定插件加载后 start 建指纹基线"]
    B --> C["_run：每 1s 唤醒一次；poll_once 持有 _poll_lock"]
    C --> D["_targets：names 有值时先过滤<br/>只取 LOADED / RUNNING 且 hot_reload=True 的已加载路径"]
    D --> E["asyncio.to_thread(_scan)：读取源码与根清单，计算 SHA-256"]
    E --> F{"回到事件循环：_still_current 且未 stopping？"}
    F -- "已置 stopping" --> EXIT["结束本轮目标并退出监测任务"]
    F -- "记录、状态、路径、模块代已改变" --> C
    F -- "仍是当前代" --> G{"扫描得到 OSError？"}
    G -. "入口短暂删除或不可读" .-> G1["相同错误只告警一次；保留旧代与旧指纹"]
    G1 --> C
    G -- "可读" --> H{"已有同一路径的 observation？"}
    H -- "首次观察" --> H1["建立基线，不重载"]
    H1 --> C
    H -- "已有基线" --> I{"指纹与已处理内容相同？"}
    I -- "相同" --> I1["清 pending，继续观察"]
    I1 --> C
    I -- "不同" --> J["新 pending 记录 changed_at；连续不同保存重新计时"]
    J --> K{"同一 pending 稳定至少 300ms？"}
    K -- "不足 300ms" --> C
    K -- "达到阈值" --> L["先记已尝试指纹；同内容失败不重复重载"]
    L --> M["reload_plugin_result：保留原 RUNNING / LOADED 意图<br/>auto_install_dependencies=False + _expected(record, state)"]
    M --> N{"名字锁内：record / state / enabled 仍匹配？"}
    N -. "手工停止、停用或换代已先完成" .-> N1["ok=False 自动重载已取消；不启动候选"]
    N -- "匹配" --> O["沿用事务：候选试导入 -> 转正；失败清候选并恢复旧代"]
    O --> P["按拓扑恢复仍有自动恢复意图且启用的依赖方<br/>记录 reload sequence/status/error 与日志"]
    N1 --> C
    P --> C
```

* `hot_reload.py:_fingerprint` 对单文件读取 `.py`；包内递归读取 `.py`，另读根目录的
  `plugin.toml` 与 `plugin.contract.json`。路径和内容采用长度前缀编码，文件排序后计算摘要。
  忽略隐藏文件/目录、符号链接、`__pycache__`、`node_modules`、`venv`、`build`、`dist`、`plugins_data`。
  静态页面资源由页面 revision 轮询更新，不触发 Python 生命周期。
* `poll_interval=1.0` 秒，`debounce=0.3` 秒；防抖在后续轮询复核，因此不承诺保存 300ms 后立即完成重载。
* `_still_current` 在扫描返回后核对 record 身份、状态、路径、模块代及热重载标志；
  `_expected` 在 runtime 名字锁内再次核对 record、state 和持久化 enabled。已经完成的手工停止优先，
  自动重载不能把已停止/停用插件重新启动。依赖方仍由既有级联机制暂时停用和恢复。
* 同一路径在级联恢复期间换了 record / 模块代时保留先前指纹；加载期间再次保存的内容
  由后续轮询继续发现，不能将它直接覆盖成「新代基线」。一份失败内容只尝试一次，修正后保存再试。
* `stop_all` 先关闭开发选择自持的监测器，再 `await` 全局 `PluginHotReloader.stop()`：置 stopping，中止后续目标，等待在途扫描、
  候选激活和回滚完成，再逆序停止插件。等待使用 shield；调用方取消也先等待收尾，再传播取消。
  不自动发现/启用新插件，不自动安装依赖，也不因入口短暂删除卸载仍工作的旧代。

</details>

<details>
### 同实例插件开发：源码加载与选定监听，不经过插件安装器

```mermaid
flowchart TD
    C["Textual / CLI: POST /v1/plugins/dev"] --> G["本机服务: Bearer + Host + Origin + JSON 守卫"]
    G --> S{"enabled 为真?"}
    S -- 否 --> OFF["移除该 names 选择<br/>无选择时停止自持监测器，不停插件"]
    S -- 是 --> EN{"全局第三方插件启用?"}
    EN -- 否 --> ERR["DevelopmentError -> schema_version=1 JSON 错误"]
    EN -- 是 --> P{"实例插件直接子目录<br/>且非符号链接?"}
    P -- 否 --> ERR
    P -- 是 --> CK["线程执行 SDK 静态检查，不导入作者代码"]
    CK --> ST{"静态与清单名有效<br/>且未停用、未停止、无异目录同名?"}
    ST -- 否 --> ERR
    ST -- 是 --> L{"是否首次加载?"}
    L -- 是 --> LOAD["当前 PluginRuntime.load_plugin_path<br/>auto_install_dependencies=False"]
    LOAD --> HOT{"加载成功且支持热重载?"}
    L -- 否 --> HOT
    HOT -- 否 --> ERR
    HOT -- 是 --> W["加入 names<br/>复用全局监测器或仅监听选定插件"]
    W --> B["建立基线并开始扫描<br/>源码保存沿用现有事务重载"]
    B --> STATUS["status 返回 development 与 reload 结果<br/>仍是原宿主 PID"]
```

全局 `[plugins].watch` 已开启时复用原监测器；关闭单个开发选择不会撤销用户显式开启的
全局监听。未开启时，开发入口的 `names` 过滤也在扫描返回后的代际复核中生效，取消选择
不会被已排队扫描重新拉起。源码加载不等于下载/安装插件，本机控制能力没有安装端点。
原生页面产物继续使用 Dashboard 的 revision 更新，不引入第二份机器人或另一套生命周期。
依赖插件被手动停用时撤销自动恢复意图；恢复循环在该插件名字锁内再次核对启用标志，
不会因前置重载结束而重新启动已经成功停用的插件。

</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `development.names` / 自持 watcher | 本机开发入口检查后加入选定插件 | 取消开发选择或 `development.close`；自持 watcher 收尾后停止 | 全局禁用、停用、已停止、异目录同名或静态无效都拒绝，不导入新候选 |
| `watcher.results[name]` | 自动重载尝试时递增 sequence，写 reloading / succeeded / failed | 下次自动重载更新；状态接口只读副本 | 失败保留旧代；修正后再次保存才重试同一插件 |
| `_hot_reloader._task` / `_stopping` | watch 构造监测器；`start_all` 在插件启动后建基线并起任务 | `stop_all` 先置停止标志并等待任务结束 | 扫描或重载失败记日志；收尾等待候选/回滚完成后才停止插件 |
| `_observations[name]` 的 fingerprint / pending / changed_at | `poll_once` 在线程扫描返回后更新 | 目标不再就绪时删除；`start` 清空重建基线 | 同内容失败只试一次；级联换代保留同路径基线，不吞后续保存 |
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
* **自动重载复用事务与依赖联动**：文件监测不维护第二套生命周期；候选失败恢复旧代，手工停止先完成则名字锁内取消自动重载。关机必须先等待监测任务结束，不能直接 cancel 掉处于回滚中的事务。
* **创建插件不走插件安装器**：本机开发入口先检查全局第三方插件开关，再静态验收与同实例
  加载；不能绕过停用/停止状态、自动安装依赖或把同名官方插件当成新建插件选择监听。
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
