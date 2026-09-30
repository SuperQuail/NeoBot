---
flow: 09c-dashboard-config
covers:
  - app/src/neobot_app/builtin_plugins/dashboard/config_manager.py
  - app/src/neobot_app/builtin_plugins/dashboard/plugin_config.py
  - app/src/neobot_app/builtin_plugins/dashboard/config.py
  - app/src/neobot_app/builtin_plugins/dashboard/hot_reload.py
  - app/src/neobot_app/builtin_plugins/dashboard/security.py
  - app/src/neobot_app/builtin_plugins/dashboard/frontend/src/pages
  - app/src/neobot_app/config/chat_writer.py
  - app/src/neobot_app/config/hot_reload.py
  - app/src/neobot_app/config/loader/backup.py
verified_against: 528fe18
verified_hash: e199875a9f28
---

# 09c 面板配置编辑：三条写入通道 · diff 与掩码 · 前端编辑器数据流

## 范围

本图覆盖**面板里能改配置的那几个入口**，以及它们背后互相独立的三条文件写入通道：

* 本体 `config.toml`：`BotConfigManager`（`read` / `validate` / `save` / `update_section` /
  `update_models` / `update_plugins_proxy`）与 `.env` 的 `EnvFileManager`；
* 插件配置 `plugins_data/<插件名>/config.toml`：`PluginConfigEditor` 与前端插件编辑器；
* 面板自己的配置 `plugins_data/dashboard/config.toml`：`DashboardConfig` +
  `hot_reload.py` 的「运行期安全 / 需重启」逐键声明；
* 三个写入者的保真度对照：`Config.load` 补全写回（`config/loader/manager.py:606`）、
  面板 `_diff_document` 保存、`config/chat_writer.py` 定点写回；
* 前端编辑器数据流：`pages/ConfigManager.tsx`（顶层 tab）、`pages/config/BotConfigPanel.tsx`
  （表单与 TOML 双模式）、`pages/Plugins.tsx` + `pages/plugins/PluginEditorPanel.tsx`、
  `components/SchemaForm.tsx` 与 `components/schema/*`、`api/client.ts` 的状态码语义。

**不画什么**（相邻图）：逐个端点的请求/响应与权限矩阵（`09b-dashboard-api.md`）；
面板 HTTP 服务本身、鉴权中间件、静态产物、`queryCore` 通用取数（`09-dashboard.md`）；
插件加载、热重载本体、`__pycache__` 重建（`08-plugins.md` / `08b-plugin-runtime.md`）；
schema 分层、`Config.load` 全链路、版本迁移、`.env` 逐字段解析（`01b-config-system.md`，
本图只在「三个写入者」对照里引用它）；模型注册之后的 provider 路由（`05-llm-routing.md`）。

**前端为什么不进哈希**：`covers` 里的 `frontend/src/pages` 只有 `.ts/.tsx`，
检查脚本只对 `*.py` 计内容哈希（`scripts/flow/check_flow_diagrams.py:37`），
所以**改前端不会让本图变「过期」**；前端行为的变更必须靠人看到这张图后主动回来改。

**spec / 直觉与现实的差异**（逐条落到节点，证据见「易错点」）：

1. **`None` 不等于「清空」**：`_diff_document` 为它产出 `None`，而 `_merge_into_document`
   见到 `None` 直接 `continue`；键已存在时旧值原地保留，保存**无声无息地不生效**。
2. **面板保存不是最小 diff**：`read()` 把默认值物化进 `config` 载荷，表单原样提交它，
   于是「文件里没有、schema 里有」的字段会被整批写盘。实测 3 个键的文件一次保存变 432 个键。
3. **TOML 模式与表单模式的未知键待遇相反**：表单模式保留未知分区（`_diff_document`），
   TOML 模式却因为 `validate(source=...)` 直查 `BotConfig` 而报「未知配置项」→ **改不动**。
4. **插件配置表单的 `hot_reload` 徽标恒为 True**：`describe_pydantic_model` 硬编码，
   真话只在保存响应的 `message` / `changes` 里。
5. **`dashboard.manage_plugins` / `allow_remote_manage` 声明「需重启」，实际立即生效**：
   `server.py:217 _live_config()` 每次访问都按 mtime 读一遍插件配置文件。
6. **插件页每 20 s 轮询一次列表，列表数组换新会触发配置重读**，未保存草稿被静默覆盖。

## 流程

```mermaid
flowchart TD
    A["GET /api/config / api.py:1408"] --> B["BotConfigManager.read / config_manager.py:422"]
    B --> C["instance()：tomlkit.parse + dict_to_dataclass(BotConfig) / :409"]
    C --> D["载荷 config / raw / schema + source + revision=sha256 前 32 位"]
    D --> E["_mask_sensitive_leaves：密钥值换成空串，只回 secrets_set 布尔 / :878"]
    D --> F["describe_dataclass 后接 apply_model_param_catalog / :264"]
    F --> G["classify(path) 打 hot_reload 与 restart_reason / config/hot_reload.py:82"]
    E --> H{"_can_manage(request) / api.py:172"}
    G --> H
    H -- 只读会话 --> H1["source 清空、raw={}、secrets_hidden=true"]
    H -- 可管理 --> I["前端 applyDoc：draft=config、source=source、清空撤销与历史"]
    H1 --> I
    I --> J["SchemaForm：bindValues 把 draft 覆盖回描述符 / config/shared.ts:89"]
    J --> K["改字段：changeField → setPath 不可变写 + 撤销栈 + 叶子历史"]
    K --> L{"dirty：draft 与 doc.config 整份 JSON 比较 / BotConfigPanel.tsx:85"}
    L -- 未变 --> J
    L -- 已变 --> M["POST /api/config：revision + config 或 source + reload，先过 _require_manage"]
    M --> O{"提交的是哪一份"}
    O -- TOML 原文 --> O1["_restore_masked_source：仍是 *** 的密钥行还原磁盘原值 / :944"]
    O -- 表单草稿 --> O2["fold_model_params_in_config + _restore_masked_secrets / :494"]
    O1 --> P["validate：_validate_payload 查类型与未知键 → 400 + errors[] / :206"]
    O2 --> P
    P --> Q{"expected_revision 等于当前文件哈希"}
    Q -- 不一致 --> Q1["409 ConfigConflictError：不写盘、不备份 / :497"]
    Q -- 一致 --> R["backup_config(max_backups=15) 后 _atomic_write 原子替换 / :503"]
    R --> S{"payload.reload"}
    S -- 否 --> T["返回 read() 快照 → 前端 applyDoc，dirty 归零"]
    S -- 是 --> U["host_commands.call 触发 config.reload，diff_snapshot + summarize_changes"]
    U --> T
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant UI as 前端编辑器
    participant API as DashboardApi
    participant SEC as security 掩码
    participant CM as BotConfigManager / PluginConfigEditor
    participant FS as 磁盘上的配置文件
    participant BK as backup_config
    participant HR as config.hot_reload
    participant HC as host_commands
    participant PCR as plugin_config_reload
    participant PL as 插件 apply_config

    UI->>API: GET /api/config
    API->>CM: read()
    CM->>FS: 读 utf-8-sig 原文 + 解析
    CM->>SEC: 掩码密钥 / 掩码 TOML 原文
    SEC-->>CM: 空串 + secrets_set，原文里是 *** 占位
    CM->>HR: 逐字段 classify(path)
    HR-->>CM: hot_reload + restart_reason
    CM-->>API: config / raw / schema / source / revision
    Note over API,UI: 只读会话在这一步被抹掉 source 与 raw（secrets_hidden=true）
    API-->>UI: 200 文档
    UI->>UI: applyDoc：draft=config，dirty=false
    UI->>UI: 改动走 setPath；dirty 由整份 JSON 比较得出
    UI->>API: POST /api/config revision + config 或 source + reload
    API->>API: _require_manage 不通过直接 403
    API->>CM: save(...)
    CM->>SEC: 还原占位与掩码空串（否则一次保存就把 token 抹成 ***）
    CM->>CM: validate 失败则 400 + errors[]，此时磁盘零变化
    CM->>FS: 用当前内容算 revision
    alt revision 不一致
        CM-->>API: ConfigConflictError
        API-->>UI: 409，前端只提示不自动覆盖，也不重新读取
    else revision 一致
        CM->>BK: 备份旧文件（不致命：失败只记日志）
        CM->>FS: 临时文件 + fsync + os.replace
        CM-->>API: read() 快照
        opt payload.reload
            API->>HC: call config.reload
            HC-->>API: status 与 message
            API->>HR: diff_snapshot + summarize_changes
            HR-->>API: hot_reload / needs_restart 明细
        end
        API-->>UI: 200 与 changes；UI applyDoc 后 dirty=false
    end
    Note over UI,CM: 插件配置是另一条通道：先写 .dashboard.bak，再就地合并写回
    UI->>API: POST /api/plugins/{name}/config revision + config 或 source
    API->>CM: 表单模式先过插件 pydantic model_validate（TOML 模式不校验模型）
    CM->>FS: 就地更新：缺键不删、表改标量静默忽略
    opt reload 且插件登记了 consumer
        API->>PCR: apply_plugin_config_change(before, after)
        PCR->>PL: apply_config 抛异常则保留旧配置并原样回错
        PL-->>PCR: ok 或 error
        PCR-->>API: applied 与 needs_restart 两组键名
    end
```

## 细节

<details>
### 编辑器数据流：读 → 渲染 → 脏标记 → 保存 → 应用

```mermaid
flowchart TD
    A["BotConfigPanel 挂载：useEffect 调 read()"] --> B["runOperation 用 operationRef 串行化：忙时后续操作整个 return"]
    B --> C["api.config() → getResult：带 X-Token，保留 HTTP 状态码"]
    C --> D{"result.ok"}
    D -- 否 --> D1["写 notice 警告；doc 为空则渲染「重试」空态"]
    D -- 是 --> E["applyDoc(data)：doc / draft=config / source，并清空撤销、重做、历史"]
    E --> F["fields = bindValues(doc.schema, draft)，useMemo 依赖 doc 与 draft"]
    F --> G["SchemaForm：changedPaths 与 baseline=doc.config 比对，标出改动项"]
    G --> H["ScalarField / JsonField / ModelList 触发 onChange(新值)"]
    H --> I["changeField：先 getPath 取 before，JSON 全等则直接 return"]
    I --> J["recordChange 压撤销栈（上限 200 条，同时清空重做栈）"]
    I --> K["changedLeaves 逐叶子 pushHistory，每条路径只留最近 20 条"]
    J --> L["setPath：structuredClone 整棵树后 defineProperty 写值"]
    K --> L
    L --> M{"dirty 判定 / BotConfigPanel.tsx:85"}
    M -- 表单模式 --> M1["JSON.stringify(draft) 不等于 JSON.stringify(doc.config)"]
    M -- TOML 模式 --> M2["source 不等于 doc.source"]
    M1 --> N["dispatch dashboard-editor-state：dirty 与 busy"]
    M2 --> N
    N --> O["ConfigManager 顶层 tab 守卫、beforeunload、卸载清理都读这个事件"]
    O --> P["save(reload=true)：revision + mode + 草稿 → api.configSave"]
    P --> Q["成功 applyDoc(saved) 后 dirty 归零；400 填 errors；409 只提示"]
```

要点与阈值：

* `applyDoc` 里 `draft = data.config` 是**浅引用**，靠 `setPath` 的 `structuredClone`
  保证改草稿不动 doc；`doc.config` 同时充当 `baseline`（标黄与恢复默认的比较基准）。
* **dirty 是整份 JSON 比较**，不是字段级：数组顺序变化、整数与浮点写法不同、
  键顺序不同都可能让 dirty 为真；配置越大，每次渲染的两遍序列化越贵。
* 撤销/重做只服务表单模式（TOML 模式的按钮恒 disabled，见 `BotConfigPanel.tsx:311`）。
* 模式切换、重新读取、放弃修改都先 `confirm`，且**不转换草稿**：切换等于用 `doc` 重新
  `applyDoc`，TOML 文本与表单草稿之间没有任何互转（`BotConfigPanel.tsx:99`）。
* 「全部恢复默认」把每个叶子的 `default` 写进草稿（`resetAllDefaults`，可一次撤销），
  但 `default` 为 `null` 的字段会写成 `None` —— 见「易错点」第 1 条。
</details>

<details>
### schema 到表单描述符：kind 判定、模型参数伪字段、未注册类型的兜底

```mermaid
flowchart TD
    A["describe_dataclass(schema, instance, path) / config_manager.py:264"] --> B["逐 field 产出 name/path/label/description/required/default/value"]
    B --> C["_type_name 归一：Union 去掉 None、list/dict、dataclass 归 model、其余归 any"]
    C --> D{"按 target 类型定 kind"}
    D -- dataclass --> D1["kind=group：递归 fields，并汇总 hot_reload_count 与 field_count"]
    D -- List 元素是 dataclass --> D2["kind=model_list：item_fields 加 items 逐条展开"]
    D -- List 是标量 --> D3["kind=list 加 element_type"]
    D -- Dict --> D4["kind=dict"]
    D -- 其它 --> D5["kind=scalar，type 只可能是 int/float/bool/str/any"]
    D1 --> E["metadata：readonly、hidden、options、options_strict 原样带出"]
    E --> F["apply_model_param_catalog：settings 组隐藏目录字段，尾部注入 kind=model_params / model_params.py:327"]
    F --> G{"前端 fieldRegistry 命中 kind"}
    G -- 否 --> G1["resolveFieldComponent 回退 ScalarField 当只读文本，并 console.warn / fieldRegistry.ts:28"]
    G -- 是 --> H["scalar / model_list / model_params / list / dict 各自渲染"]
    G1 --> H
    I["插件配置：describe_mapping 从字典值反推 kind，没有类型信息 / plugin_config.py:200"] --> H
    J["官方插件另有 describe_pydantic_model / config_manager.py:344"] --> K["annotation 名字查表得 int/float/bool/str，未命中一律当 str"]
    K --> L["嵌套 BaseModel 与 List 字段没有 group 与 list 分支，会退化成字符串输入框"]
    K --> M["hot_reload 恒 True、restart_reason 恒空，每个字段都挂「热重载」徽标"]
    L --> H
    M --> H
```

要点：

* `required = not _is_optional(field.type)`；`default = _jsonable(_default_of(field))`，
  `default_factory` 会被**真的调用一次**，抛异常则回落 `None`（`_default_of`，`:123`）。
* `value` 来自「按文件解析出的实例」，因此**文件里没写的键也会带默认值**（这是下一条
  「保存即物化」的根源）；前端只用草稿覆盖 `value`，不改描述符结构。
* `hidden` 只对「同组存在 `model_params` 伪字段」的字段生效（`Field.tsx:20`），
  即模型 `settings` 里的可选参数由伪字段接管，不再单独渲染。
* 没有 enum 分支：枚举靠 `metadata={"options": [...], "options_strict": True}` 表达，
  前端在 `ScalarField` 内部分流成下拉或可自由输入的 Combobox（`ScalarField.tsx:43`）。
* 插件配置两条 schema 路径并存：`plugin_config.read()` 先用 `describe_mapping`；
  `api.plugin_config_get` 若拿到 pydantic 模型再用 `describe_pydantic_model` **整份替换**
  （`api.py:1232`），此时 `plugin.toml` 的注释只用来补 `description`。
</details>

<details>
### 三种编辑模式与 source 保真：TOML 能改什么、只读还能看到什么

```mermaid
flowchart TD
    A["本体配置页 mode = form 或 toml，默认 form / BotConfigPanel.tsx:15"] --> B{"dirty"}
    B -- 是 --> B1["switchMode 先 confirm：明确告知不转换草稿"]
    B -- 否 --> C["applyDoc(doc) 丢弃草稿后 setMode(next)"]
    B1 --> C
    C --> D{"mode=form"}
    D -- 是 --> D1["SchemaForm 渲染 fields，baseline 与 values 分别来自 doc 与 draft"]
    D -- 否 --> D2["textarea 直接编辑整份 config.toml 原文 source"]
    D2 --> E["保存只提交 source：后端先还原 *** 占位，再做语法与类型校验"]
    E --> E1{"原文里有 schema 之外的键"}
    E1 -- 有 --> E2["400 未知配置项，文件改不动（表单模式反而能存）"]
    E1 -- 无 --> E3["落盘：注释与顺序由 tomlkit 保留"]
    F["只读会话：manage_plugins=false 或远程且 allow_remote_manage=false"] --> F1["写操作全部 403；GET /api/config 抹掉 source 与 raw"]
    F1 --> F2["TOML tab 仍可点，但内容为空串，dirty 恒 false，保存按钮 disabled"]
    G["插件配置页 / Plugins.tsx:120"] --> G1{"form_supported"}
    G1 -- 否 --> G2["表单 tab disabled，只能 TOML"]
    G1 -- 是 --> G3["applyDocument 优先回到 form"]
    G4{"source_available"} -- 否 --> G5["TOML tab disabled，后端 save(source) 也会直接拒绝"]
    G4 -- 是 --> G3
```

要点：

* 本体配置**没有** `source_available` 字段，只有权限抹除；插件配置有，且含密钥时
  `read()` 直接返回空的 `source` 与 `source_available: false`（`plugin_config.py:349`）。
* `_restore_masked_source` 只认「值仍是 `***`」的行；用户真把某个密钥改成 `***`，
  保存后会被换回旧值 —— 这是设计（`config_manager.py:944`）。
* `.env` 侧根本没有原文模式（`source_available: false`、`secret_policy: write_only`），
  前端只提供表单：`value` 与 `has_value` 分开返回，敏感键的 `value` 恒为空串。
</details>

<details>
### revision 乐观锁：五条写路径的口径与 409 的前端待遇

```mermaid
flowchart TD
    A["revision = sha256(文件字节) 的前 32 位 / config_manager.py:72"] --> B{"文件不存在"}
    B -- 是 --> B1["返回空串：首次保存必须不带 revision，否则恒冲突"]
    B -- 否 --> C["读盘算哈希"]
    C --> D{"调用点"}
    D -- BotConfigManager.save --> D1["校验与还原全部做完之后才比对 revision / :497"]
    D -- update_section --> D2["进入函数先比对，再读文档 / :538"]
    D -- update_models --> D3["先比对，再做引用检查与 key 派生 / :664"]
    D -- update_plugins_proxy --> D4["先比对，再构造 ProxySettings / :587"]
    D -- EnvFileManager.save --> D5["先查键名合法，再比对 revision / :1355"]
    D -- PluginConfigEditor.save --> D6["先比对，再决定走 source 还是 config / plugin_config.py:370"]
    D1 --> E{"相等"}
    D2 --> E
    D3 --> E
    D4 --> E
    D5 --> E
    D6 --> E
    E -- 否 --> E1["抛 ConfigConflictError 或 PluginConfigConflictError"]
    E -- 是 --> F["继续写盘：备份后原子替换"]
    E1 --> G["api 层统一映射成 409 / api.py:1441"]
    G --> H{"前端"}
    H -- 本体配置 --> H1["notice 警告加 toast，保留草稿，不自动重新读取"]
    H -- 插件配置 --> H2["configError 展示，按钮保持可用，草稿同样保留"]
```

要点：

* `revision` 是**内容哈希**，不是自增版本号：任何外部改动（`chat_writer`、`Config.load`
  补全写回、手工编辑、甚至只改注释）都会让面板的下一次保存 409。
* 面板每次保存后都会把响应里的新 `revision` 写回 `doc`，所以连续保存不会互相冲突。
* 两个标签页同时编辑：后保存者必 409，且**不覆盖**对方内容（这才是乐观锁的意义）。
* 冲突只回一条文案，不带服务端当前内容 —— 与档案编辑的 409（带当前 version 与内容）
  不同，想对齐得先点「重新读取」。
</details>

<details>
### 保存之后怎么生效：「需重启」提示的三个独立来源

```mermaid
flowchart TD
    A["表单字段徽标 HotBadge / FieldChrome.tsx:4"] --> A1{"descriptor.hot_reload"}
    A1 -- undefined --> A2["不渲染徽标"]
    A1 -- true --> A3["热重载，title 用 restart_reason 或默认文案"]
    A1 -- false --> A4["需重启"]
    A1 -- partial_hot_reload --> A5["分组显示「部分热重载」"]
    B["本体：describe_dataclass 调 classify(path) / config/hot_reload.py:82"] --> B1["按最长前缀命中 RULES，未命中默认需重启"]
    B1 --> B2["models / adapter / tts / plugins / agent / bot.account 等整段需重启"]
    B1 --> B3["chat / bot / willing / message 命中热重载规则"]
    C["保存后：api._reload_config / api.py:1482"] --> C1["先用运行中的配置对象拍快照"]
    C1 --> C2["host_commands.call 触发 config.reload"]
    C2 --> C3{"status 是 ok"}
    C3 -- 否 --> C4["ok=false，message 原样回前端，不抛异常"]
    C3 -- 是 --> C5["diff_snapshot 后再 summarize_changes"]
    C5 --> C6["changes 里 hot_reload 与 needs_restart 两组明细回前端展示"]
    D["插件配置：hot_reload_policies / dashboard/hot_reload.py:101"] --> D1["运行期安全的 8 个键：探针四项、bot_info_cache_ttl、log_buffer_size、history_max_days、allow_archive_delete"]
    D --> D2["声明需重启的 10 个键：host、port、base_path、三个安全开关、会话超时、Cookie、限流两项"]
    D1 --> E["apply_plugin_config_change：只有存在可原地生效的键才调 apply_config"]
    E --> E1{"apply_config 抛异常"}
    E1 -- 是 --> E2["保留旧配置，回「已保存但立即生效失败」"]
    E1 -- 否 --> E3["applied 与 needs_restart 一起回前端"]
    F["未登记 consumer 的插件"] --> F1["沿用插件本体的 config_hot_reload 标记，只提示需重启"]
```

要点：

* 三个来源**互不校验**：字段徽标来自静态分类表，保存后的 `changes` 来自真实配置对象
  diff，插件的结论来自插件自己的声明。三者可能互相矛盾（见「易错点」第 5、6 条）。
* `config.reload` 失败不致命：`api._reload_config` 返回 `ok=false` 与文案，
  保存本身已经成功，前端只把 notice 标成 warning（`BotConfigPanel.tsx:234`）。
* 插件原地生效只覆盖「运行期安全」的键；`apply_config` 收到的是**整份新配置**，
  「只应用一部分」由消费者自己保证（`runtime/plugin_config_reload.py:151`）。
* 面板自己的配置里，`manage_plugins` 与 `allow_remote_manage` 被声明为需重启，
  但 `server.py:240` 每次请求都读盘取值 —— 声明与现实不符。
* 插件配置保存后前端**不渲染** `changes` 明细（`PluginEditorPanel` 没接这个字段），
  只有一句 `message`；本体配置页则会展开「已生效 / 需重启」两个折叠列表。
</details>

<details>
### 备份与历史值恢复：磁盘备份、TOML 注释、前端撤销与字段历史

```mermaid
flowchart TD
    A["写盘前的统一动作：backup_config(file, backup_dir, max_backups) / loader/backup.py:16"] --> B["备份名 = 源文件名 + 时间戳到毫秒 + 原后缀"]
    B --> C["只轮转同一来源的备份：config 与 .env 互不挤占额度"]
    C --> D{"调用点与份数"}
    D -- "BotConfigManager.save / update_section / update_models / update_plugins_proxy" --> D1["max_backups=15"]
    D -- "EnvFileManager.save" --> D2["max_backups=30"]
    D -- "chat_writer.write_chat_values" --> D3["默认 15，可传入"]
    D -- "Config.load 补全写回" --> D4["同级 config_backup 目录，默认 15"]
    D -- "PluginConfigEditor.save" --> D5["不轮转：固定一份 config.toml.dashboard.bak，就地覆盖"]
    E["备份失败"] --> E1["只记 error 日志，不阻断写入（备份不是事务）"]
    F["前端可恢复的历史"] --> F1["撤销栈 200 条，重做栈随之清空"]
    F --> F2["字段历史每条路径 20 条，弹窗里点「恢复」写回草稿"]
    F --> F3["每个字段的「恢复默认」用描述符的 default，不读磁盘"]
    F --> F4["放弃修改 = 用 doc 重新 applyDoc，回到最近一次读取或保存的状态"]
    G["TOML 注释的保真"] --> G1["本体与插件配置都用 tomlkit 就地改，不重建文档"]
    G --> G2["插件配置首次生成时把 plugin.toml 的 [config] 注释写进文件"]
    G --> G3["本体配置的注释只在写入键附近保留，程序不主动生成说明"]
```

要点：

* 备份是**覆盖前**的副本（`shutil.copy2`），失败只记日志：真正保证不写坏的只有
  「临时文件 + fsync + `os.replace`」这条原子替换（`config_manager.py:80`）。
* 备份保留份数按「同名前缀」轮转，因此把 `config.toml` 备份与 `.env` 备份分得很清；
  在此之前两者同名，`.env` 的明文密钥被写进名为 config 的文件（`backup.py:19` 注释）。
* 面板**没有**「从备份恢复」入口：恢复要么靠 TOML 模式手改，要么人工从
  `data/config_backup/` 复制回去。
* 插件配置的 `.dashboard.bak` 放在配置文件同目录，只留最近一次，且写入失败被吞掉
  （`except OSError: pass`）。
</details>

<details>
### 三个写入者：谁保注释、谁保未知键、谁会把配置写胖

```mermaid
flowchart TD
    A["所有写入者最终都落到同一份 data/config.toml"] --> B{"写入者"}
    B -- 启动补全 --> C["Config.load / loader/manager.py:601"]
    C --> C1["dataclass_to_toml 用 schema 重建整份文档 / converter.py:347"]
    C1 --> C2["新文档的头部固定写四行自动生成警告"]
    C2 --> C3["用户注释、未知分区、未知键全部丢失"]
    C3 --> C4["仅当首次生成或存在缺失项时写盘，并先备份"]
    B -- 面板保存 --> D["BotConfigManager.save / config_manager.py:467"]
    D --> D1["_diff_document 只挑相对当前文件变化的键 / :1086"]
    D1 --> D2["托管树之外的键既不删也不改，注释与顺序由 tomlkit 保留"]
    D2 --> D3["表数组逐元素 diff：面板不认识的元素键同样保留 / :1059"]
    D3 --> D4["前缀之外的副作用：draft 里的默认值会被当成变更写盘"]
    B -- 命令定点写 --> E["chat_writer.write_chat_values / chat_writer.py:104"]
    E --> E1["只改 [chat] 段指定键，缺段就在文档里建表"]
    E1 --> E2["写盘前后各校验一次，回读不一致就报失败"]
    E2 --> E3["其它内容含注释与顺序完全不动"]
    F["插件配置：PluginConfigEditor.save / plugin_config.py:360"] --> F1["提交里的键就地替换或新增，未提交的键保留"]
    F1 --> F2["已有子表遇到标量提交时直接跳过该键（静默不生效）"]
```

实测对照（本机跑 `BotConfigManager` 与 `Config.load`，同一份 3 键 + 未知分区的文件）：

| 写入者 | 用户注释 | 未知分区 / 未知键 | 默认值 | 备注 |
|---|---|---|---|---|
| `Config.load` 补全写回 | **丢** | **丢** | 全量写盘（实测 434 键） | 头部四行警告自陈「所有除了键值的内容（包括注释）都会在重新执行程序时丢失」 |
| 面板 `_diff_document` 保存 | 保留 | 保留 | **全量写盘**（实测 3 键变 432 键） | 因为 `read()` 的 `config` 载荷已经带全部默认值，diff 只相对文件 |
| `chat_writer` 定点写 | 保留 | 保留 | 不动 | 只写调用方点名的键 |
| `PluginConfigEditor` | 保留 | 保留（未提交的键不删） | 不主动补全 | 首次保存会把表单里的默认值一并写进文件 |

结论：**面板不是「最小 diff 写入器」**。它的 diff 保证的是「不删除我不认识的东西」，
并不保证「只写我改过的东西」；真正的低副作用写入者是 `chat_writer`。
</details>

<details>
### 掩码与还原：两个占位符、三类还原路径、各自漏在哪

```mermaid
flowchart TD
    A["敏感键判定：is_sensitive_key 匹配 api key / token / password / secret / credential / authorization / security.py:21"] --> B{"载体"}
    B -- "结构化配置 JSON" --> B1["_mask_sensitive_leaves：字符串值换空串，同时记 secrets_set 布尔 / :878"]
    B1 --> B2["schema 描述符的 default 与 value 也要掩码：分组节点带整段字典副本 / :979"]
    B -- "config.toml 原文" --> C1["_mask_toml_source：整行值换成 ***，保留缩进与行尾注释 / :928"]
    C1 --> C2["只匹配简单键值行：数组、多行、时间等复杂值原样放过"]
    B -- ".env" --> D1["敏感键 value 恒为空串，只回 masked 与 has_value / config_manager.py:1207"]
    D1 --> D2[".env 不回原文：source_available 恒 false"]
    B -- "插件配置" --> E1["mask_mapping 把敏感键换成八个圆点占位 / security.py:72"]
    E1 --> E2["含密钥时整份不返回 source，TOML 模式直接不可用 / plugin_config.py:349"]
    F["回写时的还原"] --> F1["表单：_restore_masked_secrets 空串换回现有值 / :1002"]
    F --> F2["原文：_restore_masked_source 仍是 *** 的行换回磁盘原值 / :944"]
    F --> F3["插件表单：restore_mapping 占位或空串沿用原值，新值才覆盖 / security.py:88"]
    F1 --> G["想清空密钥只能走 TOML 模式：表单里的空串会被当成未改动"]
```

要点：

* **三个占位符不是同一个**：本体原文用 `***`（`config_manager.py:905`），
  `.env` 与插件配置用八个圆点 `SECRET_PLACEHOLDER`（`security.py:55`），结构化载荷用空串。
  排查「界面显示什么」时先分清是哪条通道。
* 掩码是**按最后一段键名**判定的（`is_sensitive_key(path[-1])`），
  所以 `models.registry.*.settings.max_output_tokens` 这类名字里带 token 的字段
  也会被当成密钥掩码进 `secrets_set` —— 实测该键出现在 `secrets_set` 里，
  面板上它是个普通数字输入框，值却是空串。
* 回归风险点：结构化的空串还原只在「当前值是非空字符串」时生效
  （`_restore_masked_secrets` 的 `isinstance(existing, str) and existing`），
  密钥原本为空时，表单里的空串就是空串。
</details>

<details>
### 前端轮询与 dirty 竞态：20 秒一次的列表刷新会覆盖未保存草稿

```mermaid
flowchart TD
    A["Plugins.tsx 挂载"] --> B["load() 一次"]
    B --> C["setInterval 每 20000 ms 再 load 一次 / Plugins.tsx:112"]
    C --> D["load 里 setItems(data.items || [])，每次都换新数组"]
    D --> E{"依赖 items 的 effect / Plugins.tsx:139"}
    E --> F["先清空 configDocument、notice、errors"]
    F --> G["再 read(selectedId) 重新拉插件配置"]
    G --> H["applyDocument 覆盖 draft 与 source，editorVersion 加一"]
    H --> I["表单被 key 重建，dirty 由真变假：用户输入在 20 秒内被静默丢弃"]
    J["已有的 dirty 守卫"] --> J1["切换插件：confirm 后才放弃"]
    J --> J2["重复读取 / 放弃修改：confirm 后才执行"]
    J --> J3["停用、卸载、重载按钮：dirty 时 disabled"]
    J --> J4["beforeunload 与站内链接跳转：dirty 时拦截"]
    J1 --> K{"轮询触发的自动重读"}
    J2 --> K
    J3 --> K
    J4 --> K
    K -- 无守卫 --> L["这是唯一一条不确认就丢弃草稿的路径"]
    M["本体配置页的对比"] --> M1["BotConfigPanel 只在挂载时读一次，没有任何轮询"]
    M1 --> M2["但 ConfigManager 顶层 tab 守卫与 beforeunload 都在"]
    N["保存后的回读"] --> N1["applyDoc(saved) 是覆盖式的：草稿等于服务端返回值"]
    N1 --> N2["保存期间继续输入会丢，靠 operationRef 把按钮全部 disabled 来回避"]
```

要点：

* 插件列表页用的是**裸 `setInterval` 加直接 `api.plugins()`**，没有接 `queryCore`，
  所以它既不受 `useQuery` 的去重保护，也会与 Dashboard 页的同一接口各拉一份。
* 该 effect 的依赖里同时有 `items` 与 `read`，`read` 是 `useCallback`（依赖 `applyDocument`）
  稳定，真正的触发器就是每次轮询换新的 `items` 数组。
* 想修的话，最小改动是让 effect 只依赖 `selectedId`（用 ref 读 `items` 做存在性判断），
  或在重读前判断 `dirtyRef.current`。
* `editorVersion` 只用来给 `SchemaForm` 换 key（强制重建输入组件），
  它同时也是「草稿被外部覆盖」的信号。
</details>

<details>
### 另外三条局部写路径：分区、模型库、插件代理

```mermaid
flowchart TD
    A["update_section(section, values) / config_manager.py:524"] --> A1["section 必须是合法标识符，否则 400"]
    A1 --> A2["把提交值浅合并进该分区，构造 new_config"]
    A2 --> A3["_filter_managed(strict={section}) 丢掉未声明键后再校验"]
    A3 --> A4["strict 的含义：正在编辑的分区出现未知键仍然报错"]
    B["update_models(upsert / delete / assignments) / :647"] --> B1["delete 前查引用：仍被角色引用则拒绝并列出角色名"]
    B1 --> B2["upsert 缺 key 时按模型名派生唯一引用名（小写、非字母数字转连字符、重名加序号）/ :795"]
    B2 --> B3["settings.params 伪字段先折叠回 enabled_params 与 extra_body"]
    B3 --> B4["assignments 校验角色名与 key 存在性；除视觉与 TTS 外必须有值"]
    B4 --> B5["派生出的 key 通过 resolved 出参回给前端（saved_key）"]
    C["update_plugins_proxy(mode, host, port) / :572"] --> C1["先用 ProxySettings 校验，再只改 [plugins] 的三个键"]
    C1 --> C2["同样走 _filter_managed 与 diff 合并"]
    D["三条路径的共同点"] --> D1["都只改自己负责的那一段，其它段原样保留"]
    D --> D2["都共享 revision 冲突检查与 backup_config(max_backups=15)"]
    D --> D3["成功后都返回 read() 全量文档，前端整份替换"]
```

要点：

* `_filter_managed` 是「校验视图」而不是「写入视图」：它只用于 `validate`，
  真正合并进文档的是 `_diff_document` 的结果（两者对未知键的态度必须一致才安全）。
* `strict` 表达的是「本次正在编辑的分区」：`update_section` 必传，
  所以对官方插件配置分区（如 `[minigame]`）的编辑**不允许**出现 schema 之外的键。
* `update_models` 的 `delete` 只挡「被调用方引用」，不挡「被其它分区引用」；
  删掉正在被 `agent_model` 编号引用的 key，会在重启后被模型注册表报缺配置。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `revision` | 每次 `read()` 与保存响应带回，前端存进 `doc` | 下一次读取或保存响应覆盖 | 不匹配则 409，磁盘零变化，前端保留草稿 |
| `dirty` | 前端整份 JSON 比较（表单比 `draft`，TOML 比 `source`） | `applyDoc`：读取、保存、放弃、模式切换、轮询重读 | 不阻断保存，只拦住切换 tab、切换模式与关页面 |
| `busy` / `operation` | `runOperation` 与 `act()` 进入时置位 | `finally` 里清空 | 期间所有写按钮 disabled；`operationRef` 让重复点击直接返回 |
| `errors` | 400 响应里的 `errors[]` | 下一次读取、校验通过、模式切换 | 有值时插件页 `canSave` 为假，本体页只展示不拦保存 |
| `notice` | 保存或读取的结果 | 下一次 `applyDoc` | 只是提示层，不改变任何数据 |
| `changes` | `config_save(reload=true)` 或 `config_reload` 的响应 | 放弃修改、下一次保存 | 只影响展示「已生效 / 需重启」 |
| `secrets_set` / `secrets_hidden` | `read()` 掩码时写入；只读会话置 `secrets_hidden` | 每次读取重算 | 密钥永远不回明文；只读会话连原文也拿不到 |
| `hot_reload` / `restart_reason` | `describe_dataclass` 逐字段调 `classify(path)` | 随 schema 重新生成 | 仅影响徽标与提示，不影响保存 |
| `config_error`（插件） | 插件加载时配置校验失败 | 配置改对后重载 | 插件按默认值运行，面板显示「已回落到默认值运行」 |
| `runtime_config`（面板自身） | `apply_config` 成功后 | 进程重启 | `apply_config` 抛异常时保留旧对象，面板继续用旧值 |
| `config_backup/*` | 每次写盘前 `backup_config` | 超过保留份数时按 mtime 删除 | 备份失败只记日志，写入照常进行 |
| `.dashboard.bak` | 插件配置每次保存前 | 下一次保存覆盖，只留一份 | 备份失败被吞掉 |

## 易错点

1. **`None` 不会清空已存在的键**（实测）：`_diff_document` 会为 `None` 生成变更，
   而 `_merge_into_document` 见到 `None` 直接 `continue`（`config_manager.py:1143`）。
   现象：文件里 `public_url = "http://example.com"`，提交 `None` 保存后文件不变、
   回读仍是旧值，接口返回 200。真正会删键的是「提交里没有这个键」（走 `_DELETE`）。
   受影响的具体字段是三个 `Optional` 且 `default=None` 的项：
   `file_server.public_url`、`web_search.engines`、`web_search.engine_timeout_seconds`，
   「全部恢复默认 + 保存」对它们无效。
2. **面板保存会把默认值写胖**（实测）：`read()` 的 `config` 载荷来自实例，包含所有默认值；
   表单把它整份提交，diff 只相对「文件里现有内容」，于是 3 个键的文件一次保存变 432 个键，
   并第一次出现 `version = "0.6.0"`。改动 `bot.py` 的默认值后，面板保存过的配置不会跟着变。
3. **TOML 模式在存在未知键时完全不能保存**（实测）：`validate(source=...)` 直接
   `_validate_payload(BotConfig, parsed, ...)`，任何 schema 之外的分区或键都报「未知配置项」；
   而表单模式对同样的文件可以正常保存并保留它们。想加自定义分区又只用 TOML 模式编辑，
   会陷入「保存不了」，而提示只给一个路径名。
4. **插件配置表单的 `hot_reload` 徽标恒为 True**：`describe_pydantic_model` 硬编码
   `"hot_reload": True`（`config_manager.py:374`），所以 `dashboard` 插件的 `port`、
   `manage_plugins` 也显示「热重载」，与它自己 `hot_reload.py` 的声明相反。
5. **`manage_plugins` 与 `allow_remote_manage` 声明需重启，实际立即生效**：
   `server.py:217 _live_config()` 按 mtime 与 size 缓存读盘，两个 property 都走它。
   远程把 `allow_remote_manage` 改成 false，下一个请求就被 403 ——
   「避免把管理员锁在门外」的假设不成立。
6. **插件页 20 秒轮询会丢未保存草稿**：列表轮询换新 `items` 数组，依赖 `items` 的
   effect 重跑，清空 `configDocument` 并重新读取。其它路径都有 `dirty` 守卫，唯独这条没有。
7. **插件配置的 TOML 模式不做模型校验**：`plugin_config_save` 只在表单模式跑
   `model.model_validate`（`api.py:1263`）；TOML 模式只解析语法，写进去的非法值
   要等插件加载时才发现，表现为 `config_error` 与「回落到默认值运行」。
8. **插件配置「表改标量」被静默忽略**：`PluginConfigEditor._merge_into_document` 遇到
   「现有值是子表、提交值是标量」时 `continue`（`plugin_config.py:413`），不报错也不写入。
9. **插件配置的改动明细前端看不到**：保存响应里有 `changes`（`api.py:1304`），
   但 `Plugins.tsx:274` 只用 `message`；要看明细得看响应体。
10. **两个密钥占位符**：本体原文是 `***`，`.env` 与插件配置是八个圆点；
    文档与排障时不要混用（`config_manager.py:905` 对 `security.py:55`）。
11. **按字段名判敏感会误伤**：`is_sensitive_key` 命中键名里的 `token`，
    于是 `models.registry.*.settings.max_output_tokens` 也被掩码并记进 `secrets_set`
    （实测输出里能看到该路径），但它在表单里其实是普通数字框。
12. **`.env` 保存后会就地改 `os.environ`**（`config_manager.py:1403`），
    但模型注册表要等 `config.reload` 才重建；`env_save` 的默认文案就是
    「环境变量已保存；模型注册表需重载后生效」。
13. **`.env` 敏感键无法通过面板清空**：空值被当作「未改动」直接跳过
    （`config_manager.py:1365`），只有非空新值才覆盖；删除要显式走 `deletes`。
14. **`MAX_STRING_LENGTH = 200_000` 只约束 config.toml**：`.env` 与插件配置没有长度上限。
15. **`config_manager.py` 的行数在两处不一致**：SPLIT-MAP §2 的清单写 1621 行（实际值），
    §3.3 的表格写 1464 行。以 `read` 工具与 `wc` 等价口径为准：1621 行。

### 与 SPLIT-MAP §3 的关系

W12（插件没有文件监听、插件配置与本体配置是两条独立通道）与本图的通道划分一致，
本图把它画细：两条通道各有自己的 revision、备份与「需重启」判据。
上文 1 到 14 条不在 W1-W50 里，属于本次写图新核出的差异；其中最该先修的是
第 1 条（静默不生效）与第 6 条（静默丢草稿），两者都是「用户以为成功了」的类型。
