---
flow: 01b-config-system
covers:
  - app/src/neobot_app/config/
  - app/src/neobot_app/runtime/hot_reload_registry.py
  - app/src/neobot_app/bootstrap/_config.py
verified_against: ed8fd2d
verified_hash: 9666350fcc8b
---

# 01b 配置系统：schema 分层 · 加载校验 · 默认值回落 · 热重载边界

## 范围

本图覆盖 config.toml 的一生：**schema 声明**（`config/schemas/`）、**加载与类型校验**
（`config/loader/`）、**默认值与回落**、**写回与备份**、**版本迁移**，以及
「改完之后怎么生效」的两套语义（`config/hot_reload.py` 分类表 +
`runtime/hot_reload_registry.py` 分发）。

画什么：

* `Config.load` 的完整链路与三处 `ConfigLoadError`；
* `bootstrap/_config.py:14 _load_config`（.env + 官方插件配置迁移 + 加载）与
  `bootstrap/__init__.py:543 _load_config_or_defaults`（失败 → 默认配置 + 强制待机）；
* 热重载三层：分类表 `RULES` → 消费者注册表 `HotReloadRegistry` → 具体消费者；
* 写入侧（`chat_writer`、dashboard `config_manager`）与它们的读盘语义。

**不画什么**（避免与相邻图重叠）：

* 模型注册之后的 provider 路由、原生视觉降级、计费统计 → 见 `05-llm-routing.md`；
* 插件配置（`plugins_data/<插件名>/config.toml`）的原地生效通道
  `runtime/plugin_config_reload.py` → 见 `08-plugins.md`；本图只画分界线：
  `plugin.<插件名>.*` 这个命名空间**不写进本体分类表**；
* `.env` 的逐字段清单与各平台解析 → 只在「敏感项」折叠块里标位置。

规格与现实的差异（先记三条，细节见折叠块）：

1. 「缺少必须项」**不是致命错误**：默认值补全 + 备份后写回 + 日志 warning
   （`loader/manager.py:606`），进程照常启动。
2. 缺 Key 的模型默认**全部降级**（`DegradeEverythingPolicy`），而「必需角色缺配置即致命」的
   严格策略在**生产路径没有任何调用点**（只有测试用）。
3. 面板既能「每请求读盘」（旁路），也能走 `config.reload`（正路），
   两条路径的生效语义不同，且分类表不校验旁路。

## 流程

```mermaid
flowchart TD
    A["进程启动：bootstrap/_config.py:14 _load_config"] --> B["load_env 读 .env + migrate_legacy_plugin_config 搬走 [dashboard]/[console]"]
    B --> D["Config.load(CONFIG_FILE, BotConfig)｜loader/manager.py:539"]
    D --> E{"config.toml 存在?"}
    E -- 不存在 --> E1["existing_data 为空：全默认生成新文件"]
    E -- 存在 --> F["tomlkit.parse(encoding=utf-8-sig)｜:565"]
    F --> G{"解析抛异常?"}
    G -- 是 --> G1["raise ConfigLoadError：原文件保持不变｜:591"]
    G -- 否 --> H{"文件 version 与 schema version 不一致?"}
    H -- 是 --> H1["_apply_migrations 链式迁移｜:254"]
    H -- 否 --> I["_infer_missing_model_params：旧配置补 enabled_params｜:157"]
    H1 --> I
    I --> J["dataclass_to_toml：与现有文件比对缺失项｜converter.py:347"]
    E1 --> J
    J --> K{"首次生成 或 存在缺失项?"}
    K -- 是 --> K1["备份到 config_backup 后整份原子写回｜:620"]
    K -- 否 --> L["不写盘：保留用户文件的键序与注释"]
    K1 --> M["回读文件 → dict_to_dataclass 类型校验与默认值｜converter.py:195"]
    L --> M
    M --> N{"placeholder 字段仍是默认值?"}
    N -- 是 --> N1["warning 列出占位符，不阻断启动"]
    N -- 否 --> O["register_models：缺 Key 只降级｜:279"]
    N1 --> O
    O --> P["build_config → ConfigProxy 包住配置对象｜_config.py:21"]
    P --> Q["bootstrap：_CONFIG_ERROR 非空则强制待机｜__init__.py:543"]
    P --> R["运行期 config.reload：整条链路重跑｜_pipeline.py:96"]
    R --> S["diff_snapshot → HotReloadRegistry.apply｜hot_reload_registry.py:190"]
```

主干只有一条：**读盘 → 迁移 → 比对缺失 → 写回补全 → 回读建对象 → 注册模型**。
三个分叉决定成败：解析失败（唯一常见的致命路径）、版本不一致（迁移）、
缺失项（触发整份重写，见易错点）。

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant BO as bootstrap
    participant LD as Config.load
    participant CV as converter
    participant RG as 模型注册表
    participant PX as ConfigProxy
    participant HR as HotReloadRegistry
    participant CS as ConfigConsumer
    participant PN as 面板或命令
    participant DS as 面板插件自身

    BO->>LD: load_env() + migrate_legacy_plugin_config()
    LD->>LD: tomlkit.parse(utf-8-sig) 并按需跑迁移链
    alt 解析失败
        LD-->>BO: raise ConfigLoadError（原文件保持不变）
        BO->>BO: _CONFIG_ERROR 记原因 → 默认配置 + 强制待机
    else 解析成功
        LD->>CV: dataclass_to_toml 比对缺失项
        CV-->>LD: 有缺失则先备份再整份写回
        LD->>CV: dict_to_dataclass 类型校验与默认值回落
        LD->>RG: register_models：缺 Key 记 warning 并降级
        LD-->>BO: BotConfig
        BO->>PX: 包成 ConfigProxy（reload 时原地换内层对象）
    end
    Note over PN,PX: 面板读盘 ≠ 运行内存：保存后必须显式触发重载
    PN->>HR: config.reload → _load_config() 重新加载
    HR->>PX: reload(新配置对象)
    HR->>CS: consumers_for(changed_paths)：前缀命中才调用
    CS-->>HR: 单个失败只记 outcome，不打断其余组件
    Note over DS,PX: 旁路：面板每请求读自己的 config.toml，不走 HR
    DS->>DS: _live_config 按 mtime 重读 manage_plugins / allow_remote_manage
```

两条「不致命」的线：**单个热重载消费者失败**只影响它自己（写进报告 failed）；
**面板读盘失败**回落到已加载快照。唯一会打断启动的是解析失败。

## 细节

<details>
### schema 分层：BotConfig 的 17 个分区加 version，与两处名字重绑

```mermaid
flowchart TD
    A["BotConfig｜bot.py:1651，实际类型是 EnhancedBotConfig｜:1981"] --> B["version: str = 0.7.0，metadata readonly｜:1654"]
    A --> C["bot / chat / models / agent_model / willing / tts / plugins｜:1658-1664"]
    A --> D["message / file_server / adapter / debug / standby / scheduled_task｜:1665-1670"]
    A --> E["agent / web_search / billing / avatars｜:1671-1674"]
    C --> C1["chat 实际是 EnhancedChat｜:1658，共 77 个字段，基类 13 加增强 64"]
    C --> C2["models: registry 模型库 + assignments 调用方引用｜:601"]
    C2 --> C3["iter_role_models 只产出「被引用且库里存在」的角色｜:633"]
    E --> E1["agent 下 11 个子段：creator / memory / problem_solver / sandbox / tools…｜:1517"]
    E1 --> E2["AgentMemoryTrigger｜:1123 group_interval=500 private_interval=200"]
    E1 --> E3["AgentMemoryArchive｜:1162 max_chars=500 max_total_chars=10000"]
    E1 --> E4["AgentToolsConfig｜:1499 mode=native max_agent_iterations=20 max_goal_rounds=8"]
    D --> D1["adapter 内含密钥字段：local_auth_token / reverse_ws_access_token"]
    A --> F["文件末尾重绑：Chat = EnhancedChat｜:1968，BotConfig = EnhancedBotConfig｜:1969"]
```

`Chat` 与 `BotConfig` 在文件末尾被**重新赋值**成增强版：任何
`from ...schemas.bot import BotConfig` 拿到的都是 `EnhancedBotConfig`，
所以 `[chat]` 段里能写 `reply_mode`、`agent_max_iterations` 这些基础 `Chat` 没有的键。
`KeyWordRule` 是 `TypedDict`（`bot.py:15`），不是 dataclass：
它走 `_validate_type` 的 TypedDict 分支校验，字段缺失不报错。
`ModelAssignments.SINGLE_ROLES` 用 `ClassVar` 声明，因此**不是配置字段**，
不会被写进 TOML（`bot.py:574`）。
</details>

<details>
### 加载链路与三处 ConfigLoadError：哪一步失败会怎样

```mermaid
flowchart TD
    A["Config.load(file_path, schema)｜loader/manager.py:539"] --> B["import neobot_app.config.migrations：装饰器注册迁移表｜:553"]
    B --> C{"file_path.exists()?"}
    C -- 否 --> Z["existing_data = {}"]
    C -- 是 --> D["open(encoding=utf-8-sig) → tomlkit.parse().unwrap()｜:565"]
    D --> E{"抛异常?"}
    E -- 是 --> E1["load_error 记下，existing_data 清空｜:582"]
    E1 --> E2["raise ConfigLoadError：解析失败，保持原文件｜:591"]
    E -- 否 --> F{"version 与 schema().version 不同?"}
    F -- 是 --> F1["_apply_migrations：链式，每步强制推进 version｜:254"]
    F -- 否 --> G["_infer_missing_model_params：仅旧配置缺 enabled_params｜:599"]
    F1 --> G
    Z --> G
    G --> H["dataclass_to_toml 生成待写文档｜:601"]
    H --> I{"should_write：首次 或 有缺失项｜:606"}
    I -- 否 --> J["回读 → dict_to_dataclass"]
    I -- 是 --> K["backup_config 到同级 config_backup｜:620"]
    K --> L["_atomic_write_text(tomlkit.dumps)｜:624"]
    L --> M{"写盘失败?"}
    M -- 是且文件原先不存在 --> M1["raise ConfigLoadError：无法生成配置文件｜:632"]
    M -- 是且文件已存在 --> M2["只记 error 日志，继续用内存里的 schema 数据"]
    M -- 否 --> J
    M2 --> J
    J --> N["_check_placeholders：placeholder 字段等于默认值就 warning｜:642"]
    N --> O["register_models：缺 provider / model_name / URL / Key 记 findings｜:649"]
    O --> P["registry.clear 后逐个 register：全局模型表被整体替换｜:496"]
```

三处 `ConfigLoadError` 的触发条件：

| 行号 | 触发条件 | 生产路径可达性 |
|---|---|---|
| `manager.py:591` | 文件存在但 TOML 解析失败 | **可达**：手改坏、BOM 之外的编码错误 |
| `manager.py:632` | 文件不存在且写盘失败（无权限/只读目录） | **可达**：首次部署权限问题 |
| `manager.py:489` | 严格策略下必需模型角色缺配置 | **不可达**：没有生产调用点传策略 |

排序细节：解析失败**立即**抛错，绝不进入「补全缺失项 → 写回」——
否则 `dataclass_to_toml` 会把 schema 的全部字段当成缺失项，
用默认值整份覆盖用户配置（`manager.py:588` 注释写明）。
</details>

<details>
### 默认值与回落优先级：TOML 值 → 类型强转 → 默认值 → 类型占位符

```mermaid
flowchart TD
    A["单字段取值｜converter.py:195 dict_to_dataclass"] --> B["_get_config_value：先按字段名，再按 metadata aliases｜:287"]
    B --> C{"TOML 里取到值?"}
    C -- 无 --> D["回落②：field.default / default_factory｜:237"]
    C -- 有 --> E["_validate_type 类型校验与强转｜:38"]
    E --> F{"校验通过?"}
    F -- 否 --> G["warning 类型不匹配，视为缺失项后走默认值｜:213"]
    F -- 是 --> H["_apply_probability_clamp：group_chat_chance 与 random_sticker_probability 钳到 0..1｜:22"]
    H --> I["写进 kwargs"]
    D --> I
    G --> I
    I --> J["嵌套 dataclass：靠 _resolve_nested_type_from_default 认子类｜:265"]
    J --> K["DeepSeekModelSettings 比 ModelSettings 多 3 个思考参数｜bot.py:218"]
    E --> L["强转细则：int←float/str、float←int/str、str←任意可 str() 的值"]
    E --> M["bool←int：0/1 直接转，其它值按非零为真并 warning｜:180"]
    N["回落③：字段不存在时写回用的是类型占位符 0 / 0.0 / false / 空串｜:492"] --> O["因此「必须项」缺失只会被补成占位值，不会报错"]
```

优先级只有三级，且**没有第四级**（没有环境变量覆盖 config.toml 的机制）：
文件值（类型校验通过）> dataclass 默认值 > 类型占位符。
概率钳位只覆盖两个字段（`converter.py:16`），其余数值越界原样保留 ——
「配了 3.0 的概率却没被拦」不是 bug，是只有这两个字段登记了范围检查。
别名机制是历史兼容口：`chat.group_Response_coefficient` 是
`group_response_coefficient` 的别名（`bot.py:75`），规范名优先。
</details>

<details>
### 配置项到消费者的映射：谁声明 config_paths，谁真的 apply_config

```mermaid
flowchart TD
    A["装配 bootstrap/__init__.py:784 HotReloadRegistry([AdapterSupervisor])"] --> B["AdapterSupervisor｜adapter_supervisor.py:28"]
    B --> B1["name=adapter；config_paths=(adapter,)"]
    B --> B2["apply：ReverseWsSettings.resolve 解析新监听设置｜:129"]
    B --> B3["reconfigure：停监听 → 改设置 → 重启；失败回滚旧设置｜:144"]
    A --> C["软重启会重建 provider：先 unregister 再 register｜__init__.py:1182"]
    C --> D["ProviderReloadConsumer｜provider_reload.py:36，name=provider"]
    D --> D1["config_paths=(models,)：模型库与平台密钥"]
    D --> D2["apply：builder(config) 出 ProviderBundle，再对 3 个挂载点原子换引用｜:78"]
    D --> D3["新主模型不可用则抛错，保留旧 provider｜:80"]
    D --> D4["全部替换成功后才 dispose 旧对象｜:97"]
    A --> E["DashboardConfigConsumer｜dashboard/hot_reload.py:82"]
    E --> E1["config_paths=(plugin.dashboard,)：走 modloader 通道，不进 HotReloadRegistry"]
    E --> E2["apply_config → plugin.apply_runtime_config 原地刷新｜:114"]
    F["全仓实现 ConfigConsumer 的类只有这三个"] --> G["没登记的组件 = 改了要重启，或者改完根本没生效"]
```

三个挂载点（`bootstrap/__init__.py:290`）：`reply` → 编排器、
`image_parse` → 图片解析、`archive_summary` → 档案总结。
只有 `reply` 与 `image_parse` 有关闭旧 provider 的拆卸函数，
`archive_summary` 的 dispose 是空操作（它不持有需关闭的资源）。
</details>

<details>
### 热重载分类表：最长前缀优先、未登记即需重启、后登记可翻案

```mermaid
flowchart TD
    A["config/hot_reload.py:40 RULES 基线表"] --> B["静态标需重启：bot.account / chat.key_word / models / tts / adapter / plugins / agent…"]
    A --> C["静态标可热重载：chat / bot / willing / message｜:59-62"]
    D["classify(path)｜:82"] --> E["_rule_for：逐条比较前缀，必须整段相等｜:66"]
    E --> F{"命中规则中最长的那条"}
    F --> G["同长度时后一条胜：判断写的是 大于等于 而不是 大于｜:76"]
    F --> H{"一条都不命中?"}
    H -- 是 --> H1["返回 False，原因「未登记为热重载配置」｜:86"]
    I["register_rule(rule)｜:90"] --> J["先删同 path 再追加：后登记覆盖静态表｜:98"]
    J --> K["HotReloadRegistry.register 灌入消费者的 hot_reload_policies｜registry.py:150"]
    K --> L["结果：adapter 与 models 从静态表的 False 被升级为 True"]
    M["误标风险一"] --> M1["前缀长反而更保守：bot 为 True 不会盖住 bot.account，因为后者更长"]
    M1 --> M2["误标风险二：apply 抛错只记 outcome，报告不看 failed 就以为全生效"]
```

分类表回答的是「**改完这项要不要重启**」，它**不是**调用闸门（见下一块）。
前缀匹配按点分段（`registry.py:181`），所以 `adapter` 不会命中 `adapter_x`；
但 `_rule_for` 用的是「段数组前缀」比较，`bot` 同样不会命中 `bot_data`。
</details>

<details>
### 面板即时读盘 与 热重载声明：两条语义在同两个键上打架

```mermaid
flowchart TD
    subgraph 本体配置
      A["面板 config_manager.read()｜config_manager.py:422"] --> A1["每次现读 config.toml + dict_to_dataclass，不触发模型注册"]
      A1 --> A2["面板显示的是磁盘状态；bot 运行用的是内存 ConfigProxy"]
      A3["面板保存 save()｜:467"] --> A4["revision 不一致就 409 冲突｜:497"]
      A4 --> A5["备份 + 原子写回 + 回读校验｜:504"]
      A5 --> A6["只有再调 host_commands.call('config.reload') 才进内存｜api.py:1499"]
    end
    subgraph 面板插件配置
      B["面板自身 server._live_config｜server.py:217"] --> B1["按 (mtime_ns, size) 缓存重读 plugins_data/dashboard/config.toml"]
      B1 --> B2["manage_plugins / allow_remote_manage 每次请求读盘｜:239"]
      B3["hot_reload.py:65-66 这两个键声明 hot_reload=False 需重启"] --> B4["分类结论只影响提示与报告，不构成闸门"]
    end
    C["config.reload 组装的 changed_paths"] --> C1["hot_reload 与 needs_restart 两组都进｜_pipeline.py:124"]
    C1 --> C2["consumers_for 只按 config_paths 前缀挑人｜registry.py:168"]
    C2 --> C3["宣称需重启的前缀，只要消费者声明了照样被调用"]
    C3 --> C4["report.to_dict 附在命令返回值里：applied / failed 两组"]
```

同一个「立即生效」在本仓库有**三种互不校验的实现**：命令入口的消费分发（`adapter`
`models`）、面板对自己插件配置的每请求读盘（`manage_plugins`、
`allow_remote_manage`）、以及插件配置的原地生效通道（`08-plugins.md`）。
排查「改了为什么生效/不生效」时，先确定改的是哪一个文件：本体 `config.toml`、
面板插件 `plugins_data/dashboard/config.toml`、还是其它插件目录。
</details>

<details>
### 死配置与弱契约清单：配了不生效的那些键

```mermaid
flowchart TD
    A["AgentMemoryArchive.auto_compact_chars=200｜bot.py:1171"] --> A1["全仓只有声明这一处引用"]
    A1 --> A2["真正生效的是 max_chars=500 与 max_total_chars=10000｜:1175 / :1183"]
    B["AgentProblemSolver 文档称路由看 agent_model.problem_solver｜:1255"] --> B1["AgentModelRouting 根本没有 problem_solver 字段｜:656"]
    B1 --> B2["_pipeline.py:198 传 agent_name=problem_solver，getattr 落回 default_index=1"]
    B2 --> B3["在 TOML 写 problem_solver 无效果，且下次补全写回会把该键抹掉"]
    C["AgentModelRouting 的八个编号字段｜:659-693"] --> C1["有调用点：main_agent｜_providers.py:42、archive_summary｜_services.py:382、self_heal｜_runtime.py:426"]
    C --> C2["无任何调用点：creator / memory / chat_interaction / willingness / scheduled_task"]
    C2 --> C3["它们只出现在提示词分析器的展示清单里｜__init__.py:1418"]
    D["严格策略 ModelAvailabilityPolicy｜availability.py:79"] --> D1["生产路径没有人传 availability_policy"]
    D1 --> D2["register_models 默认 DegradeEverythingPolicy｜manager.py:315"]
    E["占位符检查 _check_placeholders｜manager.py:193"] --> E1["只认 metadata placeholder 且值等于默认值：bot.account=0"]
```

编号字段的真实语义：`resolve_agent_model_name`（`assembly/agents.py:38`）读
`config.agent_model.〈角色〉` 得到 0-3 的编号，再经 `AGENT_ROLE_NAMES`
（0→`primary_chat_model`、1→`agent_model_1`…）转成 `assignments` 里的角色名，
最后查模型库拿 model_ref。角色查不到就**回落到角色名本身**（`:62`），
那是给尚未迁移的旧配置留的兼容口，面板上会看到模型名是一串角色名。
</details>

<details>
### 敏感项位置与脱敏链路（只标位置，不列任何真实值）

```mermaid
flowchart TD
    A["app/.env｜ENV_FILE｜core/constants.py:27"] --> A1["〈平台名〉_URL 与 〈平台名〉_APIKey，大小写不敏感查找｜schemas/env.py:124"]
    A1 --> A2["平台别名表：siliconflow / 硅基流动 / deepseek / opencodego｜:24"]
    A2 --> A3["load_env 把每个键写进 os.environ，并给缺失键追加注释块｜loader/env.py:60"]
    B["config.toml 内的密钥"] --> B1["adapter.local_auth_token｜bot.py:907"]
    B1 --> B2["adapter.reverse_ws_access_token｜bot.py:937"]
    B2 --> B3["也可用环境变量 NEOBOT_LOCAL_ADAPTER_TOKEN / NEO_BOT_ADAPTER_TOKEN"]
    C["面板脱敏规则｜dashboard/security.py:21"] --> C1["敏感键正则：api_key / token / password / secret / credential / authorization"]
    C1 --> C2["结构化 config 与 schema 默认值置空串，secrets_set 只回是否已设置｜config_manager.py:878 / :979"]
    C1 --> C3["原文 source 行内值替换成占位符；提交回来仍是占位符则还原磁盘值｜:928 / :944"]
    C1 --> C4["只读会话拿不到 source 与 raw，响应标 secrets_hidden｜api.py:1416"]
    D["日志侧"] --> D1["redact 抹掉 sk- 前缀与 bearer / token= 形式｜security.py:32"]
    D1 --> D2["mask_secret 只留首尾各 4 字符，注释写明仅用于日志"]
```

密钥**不在 config.toml 里**（模型 API Key 全在 `.env`），config.toml 里只有适配器 token。
三条脱敏路径互相独立，任何一条漏了都会明文出网：
接口响应（`read()` 的 config/raw/schema 三份副本）、TOML 原文
（`_mask_toml_source`）、日志（`redact`）。
表单提交的空串不能当「用户清空」——`_restore_masked_secrets` 会还原成磁盘现值，
想真正清空必须用 TOML 原文模式。
</details>

<details>
### 三个写入者：保真度从高到低，各有各的丢键风险

```mermaid
flowchart TD
    A["写入者① Config.load 补全写回｜manager.py:601-627"] --> A1["整份由 schema 重新生成：未知键、自定义分区、注释全部消失"]
    A1 --> A2["文件头注释自己写明「除键值外内容都会丢失」｜converter.py:360"]
    B["写入者② chat_writer 定点写｜chat_writer.py:104"] --> B1["[chat] 段不存在就在文档里创建：往游离 dict 写是历史坑｜:136"]
    B1 --> B2["写盘前用 dict_to_dataclass 预校验，写盘后回读比对｜:154 / :171"]
    B2 --> B3["只服务 /add_admin 与两个白名单键｜_commands.py:56"]
    C["写入者③ 面板 save()｜config_manager.py:467"] --> C1["_diff_document 只提交变化的键，未知键保留｜:1086"]
    C1 --> C2["表数组逐元素 diff，避免整段替换丢键｜:1059"]
    D["迁移写手 plugin_config_migration｜:76"] --> D1["先把 [dashboard]/[console] 搬进插件数据目录｜:126"]
    D1 --> D2["已存在的插件配置以文件值为准，再删本体分区并备份｜:131 / :152"]
    E["原子写 utils/atomic.py:37"] --> E1["tmp + fsync + os.replace；Windows 占用退避重试 5 次｜:18"]
    E1 --> E2["备份轮转：每个来源各留 15 份，按 mtime 淘汰｜backup.py:54"]
```

保真度排序：面板保存（只改变动键，注释与未知键都在）> chat_writer（文档级原地改）>
`Config.load` 补全（整份重建）。三者都走原子写，写前都备份到 `config_backup`，
但**只有 `Config.load` 的整份重写是无人值守自动发生的** ——
它是「面板里加的自定义分区在重启后消失」这类现象的第一嫌疑。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `bootstrap._CONFIG_ERROR` | `_load_config_or_defaults` 捕获异常时写原因｜`__init__.py:553` | 下一次加载成功时清空｜`:563` | 非空即强制 `start_in_standby`｜`:698`，并写入待机原因文案｜`:703`；兜底配置不进复用缓存｜`:607` |
| 磁盘 config.toml | 三个写入者（loader 补全 / chat_writer 定点 / 面板整份） | 用户手改或面板 TOML 模式 | 解析失败一律不改文件并抛 `ConfigLoadError`；写失败只有「文件原本不存在」是致命的 |
| `version` 字段 | schema 默认 0.7.0；迁移链每步强制推进｜`manager.py:275` | 无 | 找不到迁移链：warning 后用旧数据继续，下次启动再试 |
| `ConfigProxy._config` | `build_config` 构造；`reload(new)` 原地替换｜`proxy.py:15` | 进程重启 | 兜底对象同样包成 ConfigProxy，否则面板与命令的重载入口会 AttributeError｜`__init__.py:562` |
| `HotReloadRegistry._consumers` | `register`：同名忽略，先注册者胜｜`registry.py:146` | `unregister`（软重启前）｜`:156` | 一个都不命中 → 报告写「没有组件声明关心本次改动的配置项」｜`:96` |
| `config.hot_reload.RULES` | 模块常量 + `register_rule` 追加覆盖 | 只有测试调 `unregister_rule` | 未登记路径默认「需要重启」，不会静默生效 |
| `dashboard._config_cache` | `_live_config` 按 (mtime_ns, size) 更新｜`server.py:228` | 文件被删则返回空字典 | 读盘失败按空字典处理，调用点回落到启动时的快照值 |
| `model_params._inferred_keys` | `_infer_missing_model_params` 调 `mark_inferred`｜`model_params.py:486` | `clear_inferred`（测试） | 只用于面板提示「已按旧配置推断，请复核」 |
| `data/config_backup` | 每次写盘前 `backup_config` | 超过 15 份按 mtime 淘汰｜`backup.py:54` | 备份失败只记 error 日志，写盘照常进行｜`backup.py:38` |
| 面板表单里的密钥空串 | 面板 `read()` 掩码后回传 | `_restore_masked_secrets` 在保存时还原｜`config_manager.py:1002` | 用户以为清空了其实没清；要清空只能用 TOML 原文模式 |

## 易错点

* **「必须项缺失」不会拦启动**：missing_required 只打 warning，随后被默认值/类型占位符补全并写回
  （`manager.py:606`）。配置里少写一整段，结果是「用默认值悄悄跑起来」。
* **缺 Key 不是错误**：默认 `DegradeEverythingPolicy`（`manager.py:315`），缺 Key 只让该功能降级；
  「严格致命」策略（`availability.py:79`）在生产路径无人调用，看到它别以为会拦。
* **只有三处 `ConfigLoadError`**，且只有前两处可达：解析失败（`:591`）、
  无法生成文件（`:632`）、严格策略下的模型缺配置（`:489`）。
  「配置缺失 → 强制待机」这条线实际由**解析失败**触发。
* **补全写回是整份重写**：只有 schema 认识的键会被写出去，用户自定义分区、更新版本留下的新字段、
  以及全部注释都会消失（有备份）。面板保存路径不会（`_diff_document`），
  所以「面板里加的东西重启后没了」优先怀疑这条。
* **面板显示磁盘，bot 用内存**：面板配完不点重载/不调 `config.reload`，
  运行中的 bot 仍按旧配置跑；反之手改文件不重载也一样。
* **分类表不是闸门**：`changed_paths` 把 hot 与 needs_restart 两组都送进
  `consumers_for`（`_pipeline.py:124`），命中只看 `config_paths` 前缀。
  静态表写着 `models` 需重启，实际因为 `ProviderReloadConsumer` 登记了
  `hot_reload_policies` 而变成立即生效——报告里的 hot/needs_restart 计数来自分类表，
  才是一致的口径。
* **`_live_config` 绕过整套机制**：`manage_plugins`、`allow_remote_manage`
  标着「需重启」（`dashboard/hot_reload.py:65`），实际每次请求读盘。
  安全开关「改了没重启也生效」是这里的刻意设计（避免把管理员锁在门外），
  别据此推断其它键也这样。
* **迁移链断了不报错**：`_resolve_migration_chain` 返回空只 warning，然后拿旧结构走补全写回
  （`manager.py:262`）。改 schema `version` 前必须先补上迁移函数。
* **`Chat` / `BotConfig` 是文件末尾的重绑**（`bot.py:1968`）：
  读 schema 时看到基类 `Chat` 的定义不要以为生效的是它。
* **编号路由只对三个角色生效**（`main_agent` / `archive_summary` / `self_heal`），
  另外五个编号字段（`creator`、`memory`、`chat_interaction`、
  `willingness`、`scheduled_task`）**没有任何读取点**；解题 Agent 想要的
  `agent_model.problem_solver` 字段根本不存在，永远回落到编号 1。
* **`auto_compact_chars` 是死配置**（`bot.py:1171`）：写它没有任何效果，
  档案长度相关行为由 `max_chars` 与 `max_total_chars` 决定。
* **概率钳位只覆盖两个字段**（`converter.py:16`）：其它数值字段越界原样保留，
  不要以为加载期做了全量范围校验。
* **表单清空密钥是无效操作**：掩码空串会被还原成磁盘现值；要清空得用 TOML 原文模式。
