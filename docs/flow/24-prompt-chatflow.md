---
flow: 24-prompt-chatflow
covers:
  - app/src/neobot_app/prompt/
  - app/src/neobot_app/reply/flow_registry.py
  - app/src/neobot_app/observability/context_recorder.py
  - app/src/neobot_app/observability/prompt_diff.py
verified_against: 04d93a4
verified_hash: 3fa9343ebb32
---

# 24 提示词系统与聊天流快照

## 范围

「系统提示词怎么拼出来」与「拼好的提示词怎么给人看」两件事：

* 提示词侧：`PromptStore` 的三层取值与默认提示词同步、`render_template` 的占位符/转义/空区块规则、
  `PromptBuilder` 的分区装配、`build_role_messages` 的角色消息构造、关键词反应注入；
* 观测侧：`ChatFlowRegistry`（面板「聊天流」数据源）与 `ContextRecorder`（完整提示词历史，纯内存 + 逐份 diff）。

不在这里：模型路由见 `05`、回复管线的调用时机见 `03`、面板接口见 `09b`、
计费与日志 sink 见 `23`（本图只引用 context_recorder 的内存语义）。

## 流程

```mermaid
flowchart TD
    A["启动: sync_default_prompts 对齐 SRC_DATA 与 DATA_DIR"] --> B["PromptStore(data_dir)"]
    B --> C["_load_default_sections 读内置 prompts.toml"]
    C --> D["_load_merged 叠加用户覆盖"]
    D --> E["_file_signature 按 mtime 判缓存"]
    E --> F["PromptBuilder.build_*"]
    F --> G["render_template: 占位符替换 + 空区块清理"]
    G --> H["build_role_messages: 组装角色消息"]
    H --> I["orchestrator 作为 system 提示词发出去"]
    I --> J["ChatFlowRegistry.record_prompt / record_request"]
    I --> K["ContextRecorder 记录完整上下文（逐份 diff）"]
    J --> L["面板聊天流页只读展示"]
    K --> M["面板完整提示词页只读展示"]
    B -.文件变化.-> N["reload() 或下次签名失配时重载"]
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant BS as bootstrap
    participant PS as PromptStore
    participant PB as PromptBuilder
    participant RE as render_template
    participant OR as ReplyOrchestrator
    participant FR as ChatFlowRegistry
    participant CR as ContextRecorder

    BS->>PS: sync_default_prompts + PromptStore(data_dir)
    PS->>PS: 读内置模板并叠加用户覆盖
    OR->>PB: build（角色 / 群聊 / 私聊）
    PB->>PS: template(key)
    PS-->>PB: 模板文本
    PB->>RE: render_template(模板, 占位符值)
    RE-->>PB: 渲染结果（空区块已清理）
    PB-->>OR: system 提示词
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
    E -- 缺失 --> G["fallback_template 内置兜底"]
    F --> H["_file_signature 记录 mtime 判是否需要重载"]
    G --> H
    H --> I["reload() 手工/启动时重载"]
```

三层是「**包内默认 -> 用户覆盖 -> 内置兜底**」。`_file_signature`（`store.py:315`）决定要不要重读，
所以**改提示词文件后不必重启**，但要保证 mtime 真的变了（同秒内多次写可能漏更新）。
`enabled(key, default=True)`（`:425`）是分区的总开关：`enabled=false` 的分区在 `PromptBuilder` 侧
直接跳过（`builder.py:81 _section_enabled`）。
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
### PromptBuilder：分区装配与自适应段

```mermaid
flowchart TD
    A["PromptBuilder(config, store, ...)"] --> B["_section_enabled 过滤关闭的分区"]
    B --> C["_context_values 汇总占位符取值"]
    C --> D["_time_values / build_current_time_message / build_short_time_message"]
    D --> E["_inject_member_archives 决定是否注入成员档案"]
    E --> F["_group_profile_max_chars 限制群画像长度"]
    F --> G["_build_numbering_guide 消息编号说明"]
    G --> H["_append_adaptive 追加自适应提示词"]
    H --> I["_merge_prompt_fragments 合并片段"]
    I --> J["最终 system 提示词"]
```

值得注意的两点：

* `_append_adaptive`（`builder.py:455`）是「自适应提示词」的唯一注入点，内容来自
  `_get_adaptive_prompt`（可选择走模型生成或读缓存）；
* `_group_profile_max_chars`（`:515`）与档案系统的 `max_chars=500` 是**两个不同的上限**：
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
| 分区开关 `enabled` | 提示词文件 | 文件改回 true | `enabled=false` 的分区在 builder 侧被跳过 |
| `ChatFlowState.active` | `set_active(True)` | `set_active(False)` 或淘汰 | 只影响面板展示，不影响回复 |
| 聊天流条数 | `_state` 新建时 | `_evict_if_needed` | 超限淘汰最旧流 |
| 提示词历史 | `ContextRecorder.record` | 超限淘汰最旧 + **重启清空** | 读写异常只记 debug |
| 后台任务 provider | `register_task_provider`（bootstrap） | 不清理（进程级） | provider 异常由取用方兜底 |

## 易错点

* **`render_template` 是全仓唯一实现**：任何自己写 `str.format` 的地方都会漏掉转义与空区块清理，
  表现是「模板里留着一个空标签」或「字面量花括号被吃掉」。
* **提示词历史不落盘**：面板看到的完整提示词重启即失；它和 `DebugRecorder` 的文件录制是**两条独立链路**
  （后者落盘、按保留期清理，见 `23-billing-stats.md`）。
* **聊天流登记三处都吞异常**：面板显示空白时先怀疑 `pipeline_key` 不一致或 `max_* ` 上限夹紧，
  而不是「回复管线坏了」。
* **两个 max_chars 不同源**：提示词渲染的群画像长度（`_group_profile_max_chars`）与档案系统
  `max_chars=500` 互不影响（FINDINGS 07-2），改配置前先确认改的是哪一个。
* **diff 不是标准 JSON Patch**：只服务提示词历史，`apply_patch` 只接受本仓库 `diff_payload` 的产物。
* **`sync_default_prompts` 只对齐内置模板**：用户覆盖文件不会被它改写，但把内置模板删了会同步回来。
