---
flow: 24-prompt-chatflow
covers:
  - app/src/neobot_app/prompt/
  - app/src/neobot_app/reply/flow_registry.py
  - app/src/neobot_app/observability/context_recorder.py
  - app/src/neobot_app/observability/prompt_diff.py
verified_against: d525a5b
verified_hash: 73d8dae4968c
---

# 24 提示词系统与聊天流快照

## 范围

无效模板或 enabled 字段按配置文件版本去重告警，文件变化后重新诊断；不在每条回复重复同一配置问题。聊天流提示词和请求快照失败只由登记处记录一条带会话与原因的告警；纯活动状态赋值不再套重复防御日志。

「系统提示词怎么拼出来」与「拼好的提示词怎么给人看」两件事：

* 提示词侧：**块注册表** `prompt/blocks.py`（每块的阶段 / 作用域 / 顺序 / 启用条件）、
  **组合器** `prompt/composer.py`（按阶段拼 system、上下文 user 块与运行时注入）、
  **统一资产入口** `prompt/assets.py`（`raw_text` / `text`，优先 store 覆盖，其次内置，最后兜底）、
  唯一数据文件 `prompt/templates/prompts.toml`；`PromptStore` 的三层取值与默认提示词同步、
  `render_template` 的占位符/转义/空区块规则、`PromptBuilder` 只收集占位符取值、
  `build_role_messages` 的角色消息构造、关键词反应注入；
* 观测侧：`ChatFlowRegistry`（面板「聊天流」数据源）与 `ContextRecorder`（完整提示词历史，纯内存 + 逐份 diff）。

**文本与行为分开**：文本在 `prompts.toml`（用户可覆盖、面板可编辑），阶段/顺序/启停条件在
`blocks.py`。新增一个块 = 注册表加一条 `Block` + TOML 加一个分区，不需要改 builder 的 if 链，
也不需要改编排器的注入顺序。

不在这里：模型路由见 `05`、回复管线的调用时机见 `03`、面板接口见 `09b`、
计费与日志 sink 见 `23`（本图只引用 context_recorder 的内存语义）。

## 流程

```mermaid
flowchart TD
    A["启动: sync_default_prompts 对齐 SRC_DATA 与 DATA_DIR"] --> B["PromptStore(data_dir)"]
    B --> C["_load_default_sections 读内置 prompts.toml"]
    C --> D["_load_merged 叠加 data/prompts/custom"]
    D --> E["_file_signature 按 (mtime,size) 判缓存"]
    E --> F["PromptBuilder 收集占位符取值<br/>群/私聊上下文、时间、编号说明、自适应文本"]
    F --> G["make_context: PromptContext(scope, values, dynamic, features)"]
    G --> G1["_with_fragments: FRAGMENT 渲染成 {块id}<br/>（qq_chat / qq_chat_examples）"]
    G1 --> H["PromptComposer.build_system"]
    H --> H1["Stage.SYSTEM_PREFIX: cot_intro → 子块 → cot_outro"]
    H1 --> H2["Stage.SYSTEM_MAIN: group_chat / friend_chat"]
    H2 --> H3["模板漏写时补回 numbering_guide"]
    H3 --> H4["Stage.SYSTEM_APPEND: 稳定追加块"]
    H4 --> I["SystemPrompt: text + consumed + rendered + skipped"]
    I --> J["build_context: Stage.CONTEXT<br/>system 已消费的去重键置空"]
    J --> K["编排器组装 messages 并发给 provider"]
    K --> K1["_append_round_blocks: per_round 的 SYSTEM_APPEND 块"]
    K --> L["_inject_runtime_blocks: RUNTIME_DATA → REMINDER → TIME"]
    K --> M["ChatFlowRegistry.record_prompt / record_request"]
    K --> N["ContextRecorder 记录完整上下文（逐份 diff）"]
    M --> O["面板聊天流页只读展示"]
    N --> P["面板完整提示词页只读展示"]
    B -.文件变化.-> Q["reload() 或下次签名失配时重载"]
```

块被跳过不丢信息：`block_skip_reason` 返回的中文原因进 `SystemPrompt.skipped`，同时记一条
debug「提示词块已跳过」——排查「这段为什么没注入」先看那里，而不是猜配置。

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant BS as bootstrap
    participant PS as PromptStore
    participant AS as assets
    participant PB as PromptBuilder
    participant PC as PromptComposer
    participant OR as ReplyOrchestrator
    participant FR as ChatFlowRegistry
    participant CR as ContextRecorder

    BS->>PS: sync_default_prompts + PromptStore(data_dir)
    PS->>PS: 读内置模板并叠加 custom 覆盖
    OR->>PB: build_group_chat_prompt / build_friend_chat_prompt
    PB->>AS: raw_text(section, key) 逐分区取模板
    AS-->>PB: custom → 内置 → fallback
    PB->>PC: build_system(make_context(...))
    PC->>PC: SYSTEM_PREFIX(cot) → SYSTEM_MAIN → SYSTEM_APPEND
    PC-->>PB: SystemPrompt(text, consumed, skipped)
    PB->>PC: build_context(ctx, system) 渲染 CONTEXT 块
    PC-->>PB: user 块（system 已消费的键置空）
    PB-->>OR: system 文本 + context_blocks
    OR->>PC: _append_round_blocks / inject(RUNTIME_DATA→REMINDER→TIME)
    OR->>FR: record_prompt + record_request
    OR->>CR: record(messages, meta)
    Note over FR,CR: 三处登记全部 try/except，绝不影响本次回复
```

## 细节

<details>
### PromptStore 的三层取值与缓存签名

```mermaid
flowchart TD
    A["PromptStore(data_dir)"] --> B["_load_default_sections<br/>读包内 templates/prompts.toml"]
    B --> C["_load_merged<br/>叠加 data/prompts 下的用户文件"]
    C --> D["sections: key -> {template, enabled, ...}"]
    D --> E{"get(key) / template(key)"}
    E -- 命中 --> F["返回该分区"]
    E -- 缺失 --> G["返回 default（空串）<br/>template_or_fallback 才回退内置兜底"]
    F --> H["_file_signature 记录 mtime 判是否需要重载"]
    G --> H
    H --> I["reload() 手工/启动时重载"]
```

三层是「**包内默认 -> 用户覆盖 -> 内置兜底**」。`_file_signature`（`store.py:152`）决定要不要重读，
所以**改提示词文件后不必重启**，但要保证 mtime 真的变了（同秒内多次写可能漏更新）。
`get()` 缺失或空白时返回 `default`（空串），只有 `template_or_fallback` / `get_template_value`
会回退内置兜底（`store.py:258` / `:119`）。
`enabled(key, default=True)`（`:272`）是分区的总开关：`enabled=false` 的分区在
`PromptComposer.block_skip_reason` 里先被跳过（`SYSTEM_MAIN` 主模板例外），
模板文本本身则由 `assets.raw_text` 按 custom → 内置 → fallback 解析。
</details>

<details>
### 模板渲染：占位符、转义与空区块

```mermaid
flowchart TD
    A["render_template(template, values)"] --> B{"模板全空白?"}
    B -- 是 --> B1["返回空字符串"]
    B -- 否 --> C["template_placeholders 扫描真实占位符"]
    C --> D["先把 {{ 与 }} 换成哨兵<br/>避免把字面量花括号当占位符"]
    D --> E["safe_format(template, **values)"]
    E --> F["strip_empty_tag_blocks 循环删除空区块"]
    F --> G["压缩连续空行并 strip"]
```

三条容易踩的规则（`prompt/render.py`，全仓唯一实现，绕开它就会出现行为分叉）：

1. 占位符只认 `{name}` 形式，且名字必须是 `[A-Za-z_][A-Za-z0-9_]*`；
2. 想写**字面量**花括号必须写成 `{{` / `}}`，否则会被当占位符；
3. 只含空白的 XML 风格区块（如 `<群友信息>` 与 `</群友信息>` 之间只有换行）**会被删掉**，
   所以可选区块可以放心写在模板里，不需要在 Python 侧拼字符串。
</details>

<details>
### 块注册表与阶段：cot 前缀、FRAGMENT 与 CATALOG

```mermaid
flowchart TD
    A["Stage.SYSTEM_PREFIX｜blocks.py"] --> A1["cot_intro → cot_at_mention → gentle_language<br/>→ cot_avoid_bot_chat → cot_no_bluffing<br/>→ cot_no_game_topics → cot_no_echo_images → cot_outro"]
    B["Stage.FRAGMENT"] --> B1["qq_chat / qq_chat_examples：不单独注入<br/>渲染成 {块id} 给主模板引用"]
    C["Stage.CATALOG"] --> C1["label_* / bili_*：不经过注入管道<br/>assets.text(id) 按键读取"]
    D["Stage.CONTEXT / RUNTIME_DATA / REMINDER / TIME"] --> D1["user 块按阶段顺序追加<br/>TIME 是 terminal，保证在最后一条"]
    E["Block.requires"] --> E1["config_flag / feature / dynamic_present<br/>返回未通过原因"]
    F["per_round / once_per_activation"] --> F1["每轮由编排器追加 / 每次激活只发一次"]
    G["section_enabled：分区 enabled=false"] --> G1["主模板例外：SYSTEM_MAIN 永远启用"]
```

`Stage` 共 12 个值：`SYSTEM_PREFIX` / `SYSTEM_MAIN` / `SYSTEM_APPEND` / `FRAGMENT` / `CATALOG` /
`CONTEXT` / `RUNTIME_DATA` / `REMINDER` / `TIME` / `TOOL_RESULT` / `STATUS` / `SUBAGENT`。
`SYSTEM_PREFIX` 是全局 cot 板块：总开关 `prompt_optimizations.cot_enabled` 管整段，子块各有开关
（`at_mention_reply` / `gentle_language` / `avoid_bot_chat` / `no_bluffing` / `no_game_topics` /
`no_echo_images`），默认全开；关掉子块只跳过该块，`cot_intro` 与 `cot_outro` 仍在（整段仍是 `<cot>…</cot>`）。
主模板里的旧 `<cot>` 已改名 `<思维模式要求>`，避免与真正的 cot 前缀重名。
`blocks.validate_blocks()` 做注册表自检：id 唯一、非主模板必须有 TOML 分区或 `text`、
`per_round` 块的 order 必须大于所有稳定追加块、同阶段同作用域 order 不能冲突。
</details>

<details>
### PromptBuilder → PromptComposer：取值与拼装分离

```mermaid
flowchart TD
    A["build_group_chat_prompt / build_friend_chat_prompt"] --> B["_group_context_values / _friend_context_values<br/>汇总群友、印象、关键词反应等占位符"]
    B --> C["_time_values + _build_numbering_guide"]
    C --> D["_make_ctx(scope, values, dynamic={'adaptive_text': _adaptive_block()})"]
    D --> E["self._composer.build_system(ctx)"]
    E --> F["build_context_messages(ctx, system) 填 context_blocks"]
    F --> G["返回 system.text"]
    H["编排器侧的后处理"] --> H1["_append_round_blocks 追加 per_round 的 SYSTEM_APPEND 块"]
    H --> H2["_at_mention_wait_message 追加等待指引 user 块"]
    H --> H3["prompt.build.before / after 钩子可改写或短路"]
    I["builder 的按块渲染入口"] --> I1["build_current_time_message / build_short_time_message"]
    I --> I2["member_archive_hint / build_group_chat_resume_text"]
    I --> I3["_inject_member_archives：是否注入成员档案"]
```

`PromptBuilder` 不再自己拼分区：`_append_adaptive` 这个分叉点已删除，自适应文本现在是
`SYSTEM_APPEND` 里的 `adaptive_prompt` 块（`text=dynamic_text("adaptive_text")`），
builder 只把 `_adaptive_block()`（读 `data/自适应提示词.txt`，按 mtime 缓存）放进 `dynamic`。
`_group_profile_max_chars` 与档案系统的 `max_chars=500` 仍是**两个不同的上限**：
前者只为渲染长度服务（见 FINDINGS 07-2），改一个不会影响另一个。
</details>

<details>
### 角色消息构造与关键词反应

```mermaid
flowchart TD
    A["build_role_messages(entries, bot_account, ...)"] --> B["_role_for_message 判角色"]
    B --> C{"bot_account 相同?"}
    C -- 是 --> D["assistant"]
    C -- 否 --> E["user"]
    D --> F["_render_role_message 渲染单条"]
    E --> F
    F --> G["_build_from_entries 批量组装"]
    G --> H["messages 列表"]
    I["KeywordReactionBuilder.build(rules, ...)"] --> J["_match_rule 命中规则"]
    J --> K["_render_message_text 渲染消息文本"]
    K --> L["collect 收集反应片段"]
    L --> H
```

`role_messages.py:29 _user_message` / `:33 _role_for_message` / `:73 build_role_messages` 是**唯一**的角色转换实现；
`keyword_reaction.py` 负责「命中关键词时追加反应提示」，它的 `_normalize_depth`（`:149`）控制嵌套层数上限。
两者都在请求构造期同步执行，失败即当轮无这段（不重试）。
</details>

<details>
### ChatFlowRegistry：面板「聊天流」的数据源与有界策略

```mermaid
flowchart TD
    A["回复管线: record_prompt(pipeline_key, system_prompt, model)"] --> B["_state(pipeline_key)"]
    C["record_request(messages, model, iteration)"] --> B
    D["set_active(active)"] --> B
    B --> E{"已有该流?"}
    E -- 否 --> F["新建 ChatFlowState + _evict_if_needed"]
    E -- 是 --> G["就地更新字段"]
    F --> H["_clip 截断 system_prompt 到 max_prompt_chars"]
    G --> H
    C --> I["只保留最近 max_messages 条 + _summarize_message"]
    H --> J["面板 snapshot(pipeline_key)"]
    I --> J
    J --> K["background_tasks: 询问各 task provider"]
```

四个上限都在构造期夹紧（`flow_registry.py:71-74`）：`max_flows` / `max_messages` /
`max_message_chars`（下限 200）/ `max_prompt_chars`（下限 1000）。
**三处写入全部 try/except + debug 降级**（`:104/:127/:142`）—— 登记失败绝不影响回复。
`register_task_provider`（`:147`）是插件/子系统把「该流的后台任务」接进面板的入口（bootstrap 装配时注册）。
</details>

<details>
### ContextRecorder：纯内存 + 逐份 diff + 图片只留哈希

```mermaid
flowchart TD
    A["ContextRecorder(limit=100, legacy_dir)"] --> B["record(messages, meta)"]
    B --> C{"第 1 份?"}
    C -- 是 --> D["存完整快照作为基准"]
    C -- 否 --> E["diff_payload 只存相对上一份的补丁"]
    E --> F["sanitize_images: base64 换 sha256"]
    D --> F
    F --> G{"超过 limit?"}
    G -- 是 --> H["淘汰最旧一份并重新定基"]
    G -- 否 --> I["留在内存"]
    H --> I
    I --> J["read_entry / read_latest 逐份 apply_patch 重建"]
    J --> K["面板完整提示词页（09b）"]
```

模块 docstring 写明三条性质，别再按「落盘实现」理解它：

1. **纯内存**：重启即清空，磁盘上没有 `ctx_*.json`；`legacy_dir` 只在「清空历史」时用来删旧文件；
2. **逐份 diff**：回复管线的 messages 逐轮追加，补丁极小，100 份常驻约 1–2 MB；
3. **图片脱敏**：`data:image/...;base64` 换成 sha256（与图库去重同口径），面板不搬 MB 级 base64。

`read_entry` / `read_latest` 返回的是**内部对象**，调用方只读；逐份重建时返回新对象可放心使用（docstring 约定）。
读写异常一律只记 debug（`prompt_diff` 的 apply_patch 失败同此）。
</details>

<details>
### 提示词 diff 的实现边界

```mermaid
flowchart TD
    A["diff_payload(old, new)"] --> B["_diff 递归比较"]
    B --> C{"类型"}
    C -- dict --> D["按键递归"]
    C -- list --> E["_diff_list 按索引/长度差"]
    C -- 标量 --> F["记 op: set / add / remove"]
    D --> G["patch 列表"]
    E --> G
    F --> G
    G --> H["patch_bytes / payload_bytes 统计体积"]
    H --> I["apply_patch(base, patch) 重建"]
    I --> J["apply_patch_copy 不修改入参的版本"]
```

这套 diff 是**为提示词场景定制**的：`_resolve`（`:229`）支持路径词元，
`json_safe`（`:248`）保证可序列化，`count_image_refs` 统计图片数（面板展示「本条含 N 张图」）。
它不是通用 JSON Patch（RFC 6902）实现，别拿外部工具生成的 patch 喂给它。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| PromptStore 缓存签名 | `_file_signature`（mtime/size） | 下次重载覆盖 | 同秒内二次写入可能不触发重载 |
| 分区开关 `enabled` | 提示词文件 | 文件改回 true | `block_skip_reason` 先查分区；主模板（SYSTEM_MAIN）不受影响 |
| cot 前缀与子块开关 | `[prompt_optimizations]` 的 `cot_enabled` 与 6 个子块 | 配置改回 true | 关闭的块进 `skipped`，整段前缀随之消失或缩短 |
| 块跳过原因 | `PromptComposer.block_skip_reason` | 每次构建重算 | 同时进 `SystemPrompt.skipped` 与 debug「提示词块已跳过」 |
| FRAGMENT 占位符取值 | `_with_fragments` | 每次 `build_system` 重算 | 片段关闭/为空时显式给空值，避免 `{qq_chat}` 以字面量泄漏 |
| `ChatFlowState.active` | `set_active(True)` | `set_active(False)` 或淘汰 | 只影响面板展示，不影响回复 |
| 聊天流条数 | `_state` 新建时 | `_evict_if_needed` | 超限淘汰最旧流 |
| 提示词历史 | `ContextRecorder.record` | 超限淘汰最旧 + **重启清空** | 读写异常只记 debug |
| 后台任务 provider | `register_task_provider`（bootstrap） | 不清理（进程级） | provider 异常由取用方兜底 |

## 易错点

* **`render_template` 是全仓唯一实现**：任何自己写 `str.format` 的地方都会漏掉转义与空区块清理，
  表现是「模板里留着一个空标签」或「字面量花括号被吃掉」。
* **提示词历史不落盘**：面板看到的完整提示词重启即失；它和 `DebugRecorder` 的文件录制是**两条独立链路**
  （后者落盘、按保留期清理，见 `23-billing-stats.md`）。
* **「这段提示词为什么没注入」先看 `skipped`**：组合器把块级原因（分区关闭 / 配置开关关闭 /
  缺少运行时内容 / 渲染为空）都记进 `SystemPrompt.skipped` 与 debug 日志；
  builder 不再是唯一注入点，per_round 块由编排器 `_append_round_blocks` 追加、运行时块由 `inject` 追加。
* **cot 前缀不在主模板里**：`<cot>…</cot>` 由 `Stage.SYSTEM_PREFIX` 块拼成并放在 system 最前面，
  改 `group_chat` 里的 `<思维模式要求>` 不会影响它；关 `prompt_optimizations.cot_enabled`
  只让前缀消失，主模板照常。旧配置的 `chat.gentle_language_enabled` 已迁移成
  `prompt_optimizations.gentle_language`（配置版本 0.9.0 → 0.10.0，见 `01b-config-system.md`）。
* **主模板是分区开关的安全例外**：`assets.asset_enabled` 与 `block_skip_reason` 都让
  `SYSTEM_MAIN` 无视 `enabled=false`，否则一次误配会让机器人彻底没有提示词。
* **未登记的自定义分区走兼容回退**：`PromptContext.raw_template` 先试 `assets.raw_text`，
  未注册的 section 抛 `KeyError` 后退回 store/packaged；面板仍可编辑，但没有 stage 元数据。
* **聊天流登记三处都吞异常**：面板显示空白时先怀疑 `pipeline_key` 不一致或 `max_* ` 上限夹紧，
  而不是「回复管线坏了」。
* **两个 max_chars 不同源**：提示词渲染的群画像长度（`_group_profile_max_chars`）与档案系统
  `max_chars=500` 互不影响（FINDINGS 07-2），改配置前先确认改的是哪一个。
* **diff 不是标准 JSON Patch**：只服务提示词历史，`apply_patch` 只接受本仓库 `diff_payload` 的产物。
* **`sync_default_prompts` 只对齐内置模板**：用户覆盖文件不会被它改写，但把内置模板删了会同步回来。
