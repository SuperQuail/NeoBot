---
flow: 03b-reply-tools
covers:
  - app/src/neobot_app/reply/tools.py
  - app/src/neobot_app/reply/output_guard.py
  - app/src/neobot_app/reply/vision_context.py
verified_against: 99836cd
verified_hash: 5328f32e99f6
---

# 03b 回复管线的工具面：模型看到什么工具 · 谁执行 · 结果怎么回灌

## 范围

本图覆盖主回复管线（agent 循环）给模型看的**那一张工具表**及其执行侧：

* `reply/tools.py`（2688 行）：`ReplyToolExecutor.definitions`（装配 + 过滤）、`execute`（分派）、
  内建执行器（send_reply / wait / 会话工具 / 技能路由）、`build_reply_toolset`；
* `reply/output_guard.py`：发送前的标注 / 思维链 / 控制词兜底清洗（工具层与发送层共用）；
* `reply/vision_context.py`：原生视觉的**每次请求临时图片附录**（`ReplyVisionContext`）。

**不画什么**（相邻图）：Agent 循环本身的迭代 / 预算 / 空轮次（03-reply-pipeline、04-agent-loop）；
SkillManager 的注册与 `{skill}__{tool}` 命名细节（06-tools-skills）；插件加载（08-plugins）；
AgentToolRuntime 内部各叶子工具的实现（06-tools-skills）；`ReplySender` 的发送与冷却（03）。

**spec / 直觉与现实的差异**（本图逐条落到节点上）：

1. **初次下发的工具表不是「活的」**：`build_reply_toolset` 在构造时就把
   `executor.definitions()` 拍成 `Toolset.specs`；orchestrator 首轮用的是
   `reply_toolset.definitions()`（orchestrator.py:2646）这个快照，之后的重建才走
   `reply_toolset.executor.definitions()`。实测：`preactivate_skills` 之后
   `toolset.definitions()` 里**没有**新技能工具，只有 `executor.definitions()` 有（见「易错点」第 1 条）。
2. **`skills__load_tools` 的「本轮即可直接调用」有前提**：`consume_tools_dirty()` 只在
   **一次工具批次执行完之后**被检查（orchestrator.py:3322）。模型在同一个回合里先调
   `load_tools`、再调刚加载的工具是可以的（同一批次内的后续调用直接走 token 路由），
   但如果它这一轮**只**调了 load_tools，工具表要等到下一次模型调用才刷新。
3. SPLIT-MAP 标注 `reply/tools.py` 为 2537 行，实际 2688 行（含 `build_reply_toolset` 尾部）。

## 流程

```mermaid
flowchart TD
    A["build_reply_toolset / tools.py:2597<br/>构造 executor + 冻结 Toolset.specs"] --> B["ReplyToolExecutor.definitions / tools.py:360"]
    B --> C{"skills_registry.skills 非空?"}
    C -- 有 --> C1["push skills__read_manifest / skills__read_resource"]
    C -- 无 --> D
    C1 --> D{"_skill_manager 有 skill_names?"}
    D -- 有 --> D1["push skills__view_instructions<br/>+ skills__load_tools（无可加载技能则不给）"]
    D -- 无 --> E
    D1 --> E["按 handler 是否为 None 逐个 push 基础回复工具 / tools.py:430-867"]
    E --> F["合并 _activation.tools()：常驻技能 + 本轮已加载 / tools.py:869"]
    F --> G{"self._allowed_tools 非空?"}
    G -- 是 --> G1["只留 _SKILL_GUARD_BASE_TOOLS 与 allowed_tools 的并集 / tools.py:883"]
    G -- 否 --> H
    G1 --> H["is_tool_authorized：视觉规则 + 白名单 + agent_tools 去重 / tools.py:886"]
    H --> I{"同名工具重复?"}
    I -- 是 --> I1["raise ValueError：重复的最终工具定义（构建即失败）"]
    I -- 否 --> J["tools 随模型调用下发 / orchestrator.py:2646,2885"]
    J --> K{"provider.native_vision 相对上一轮变化?"}
    K -- 变化 --> K1["重建 tools + 注入中文说明 user 消息 / orchestrator.py:2783-2787"]
    K -- 无变化 --> L
    K1 --> L{"本轮有 tool_calls?"}
    L -- 无 --> L1["正文直发 / AI 检查 / 空轮次 FAILED（不走工具面）"]
    L -- 有 --> M["逐个调用：授权复查 → tool.call.before → executor.execute"]
    M --> N["结果回灌 role=tool；超时与异常写「工具调用失败」"]
    N --> O{"consume_tools_dirty?"}
    O -- 是 --> O1["立即重建 tools（按需加载生效）"]
    O -- 否 --> J
    O1 --> J
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant OR as ReplyOrchestrator
    participant TS as build_reply_toolset
    participant EX as ReplyToolExecutor
    participant AC as SkillToolActivation
    participant RT as AgentToolRuntime
    participant MD as 模型 provider
    participant VC as ReplyVisionContext
    participant SV as ReplySender

    OR->>TS: 30+ 个 handler + native_vision_provider=provider
    TS->>EX: 构造 executor；definitions() 一次，冻结成 Toolset.specs
    EX->>AC: tools() = 常驻技能 + 本轮已加载技能
    Note over OR,TS: 首轮下发用冻结快照；之后重建才调用 executor.definitions()
    OR->>EX: 每轮（视觉变化 / 按需加载后）重算 definitions()
    OR->>MD: chat(messages, tools)，超时默认 120s（群聊取沉默预算）
    MD-->>OR: tool_calls（可多条，同批串行处理）
    OR->>EX: execute(name, args)，外层 wait_for 超时
    EX->>RT: agent_tools__ / agents__ / background_trigger__ / sandbox_manager__ 需 ToolContext
    RT-->>EX: 叶子工具结果（direct=True，不受 native/PTC 编排模式限制）
    EX-->>OR: 字符串；技能工具内部已 catch 异常并返回「工具执行失败」
    OR->>OR: append role=tool（≤16 KiB；超时/异常→失败文案）
    Note over OR,EX: 工具失败不致命；超时且有沉默余量时直接结束管线
    OR->>VC: refresh_defaults（仅 native_vision）
    VC->>EX: loader.execute('add_image') 逐张默认图
    EX-->>VC: ImageContextResult（失败留文本占位，下轮可重试）
    OR->>VC: request_messages → 末尾追加一条 [视觉上下文] user 附录
    OR->>SV: send_reply handler
    SV->>SV: 再清洗一遍 + 空结果丢弃（返回 False → 工具回执「未发送」）
    OR->>EX: drain_sessions + close（管线收尾；只有关停才取消在途会话工具）
```

## 细节

<details>
### 工具清单：每个工具的出厂条件与执行入口

```mermaid
flowchart TD
    A["ReplyToolExecutor.definitions / tools.py:360"] --> B{"skills_registry 且 .skills 非空"}
    B -- 是 --> B1["skills__read_manifest / skills__read_resource"]
    B -- 否 --> C{"_skill_manager 且 skill_names 非空"}
    C -- 是 --> C1["skills__view_instructions"]
    C -- 否 --> D{"_activation.loader_definition 非 None"}
    D -- 是 --> D1["skills__load_tools（enum = 未加载技能）"]
    D -- 否 --> E
    C1 --> E{"_cancel 注入?"}
    E -- 是 --> E1["cancel"]
    E -- 否 --> F["split_reply / send_reply：无条件常驻"]
    F --> G{"_markdown_image_converter 注入?"}
    G -- 是 --> G1["send_long_reply"]
    G -- 否 --> H{"_wait 注入?"}
    H -- 是 --> H1["wait"]
    H -- 否 --> I["_willing → adjust_reply_willingness / get_willingness_config / manage_willing_config"]
    I --> J["_send_emoji 或 _emoji → send_emoji；_emoji → list_emojis / search_custom_emoji"]
    J --> K["_react_emoji → react_emoji；_search_emoji → search_qq_emoji"]
    K --> L["_tts_service.enabled → speak；_poke_user → poke_user"]
    L --> M{"skill_manager 或 drawing 或 scheduled 或 notification_hub?"}
    M -- 是 --> M1["check_background_tasks"]
    M -- 否 --> N["cancel_task：无条件常驻（即使没有后台系统）"]
    N --> O{"_drawing_manager → check_last_drawing；_scheduled_task_manager → mark_scheduled_task_complete"}
    O --> P["技能工具：_activation.tools()"]
```

一句话版：**`split_reply` / `send_reply` / `cancel_task` 永远在**，其余工具全部取决于
构造时那个 handler 是不是 None；`speak` 还要 TTS 当前 enabled。

| 工具 | 出现条件 | 执行入口 |
|---|---|---|
| `skills__read_manifest` / `skills__read_resource` | `_skills_registry.skills` 非空 | `_read_skill_manifest` / `_read_skill_resource`（1 MiB、路径越界与软链接校验） |
| `skills__view_instructions` | `_skill_manager.skill_names` 非空 | `_view_skill_instructions` |
| `skills__load_tools` | 还有「可加载」技能时 | `_load_skill_tools` → `SkillToolActivation.load` |
| `cancel` | `cancel_handler` | `_execute_cancel` |
| `split_reply` / `send_reply` | 恒有 | `_execute_split_reply` / `_execute_send_reply` |
| `send_long_reply` | `markdown_image_converter` | `_execute_send_long_reply` |
| `wait` | `wait_handler` | `_execute_wait`（冷却默认 60s） |
| `adjust_reply_willingness` / `get_willingness_config` / `manage_willing_config` | `willing_service` | 三个 willing 执行器 |
| `send_emoji` | `send_emoji_handler` 或 `emoji_service` | `_execute_send_emoji` |
| `list_emojis` / `search_custom_emoji` | `emoji_service` | 分页上限 200 |
| `react_emoji` / `search_qq_emoji` | 对应 handler | `_execute_react_emoji` / `_execute_search_qq_emoji` |
| `speak` | `tts_service.enabled` 且 `speak_handler` | `_execute_speak`（清洗后为空即拒发） |
| `poke_user` | `poke_user_handler` | `_execute_poke_user` |
| `check_background_tasks` | 任一后台管理器 | `_execute_check_background_tasks` |
| `cancel_task` | 恒有 | `_execute_cancel_task` |
| `check_last_drawing` / `mark_scheduled_task_complete` | 对应管理器 | 各自执行器 |
| 技能工具（`{skill}__{tool}`） | 常驻技能或本轮已加载 | `_execute_skill` / `_execute_session_tool` |
</details>

<details>
### wire 可见性：原生视觉 · 技能常驻策略 · 任务工具模式三因素

```mermaid
flowchart TD
    A["候选工具名 → is_tool_authorized / tools.py:911"] --> B{"以 image_context__ 开头?"}
    B -- 是 --> B1{"provider.native_vision is True?"}
    B1 -- 否 --> X["隐藏"]
    B1 -- 是 --> C
    B -- 否 --> C{"native_vision 且名为三个解析工具之一?"}
    C -- 是 --> X
    C -- 否 --> D{"_allowed_tools 非空且不在白名单?"}
    D -- 是 --> X
    D -- 否 --> E{"agent_tools__ 前缀?"}
    E -- 是 --> E1{"去掉前缀在 runtime.capability_names 里?"}
    E1 -- 否 --> X
    E1 -- 是 --> Y["可见"]
    E -- 否 --> F{"命中 LEGACY_FILE_ALIASES 且别名能力存在?"}
    F -- 是 --> X
    F -- 否 --> Y
    X --> G["不进 tools；被调用时回 authorization_error 文案"]
    H["技能侧：常驻还是按需 / skills/base.py:283-332"] --> H1{"exposed_to_main_agent?"}
    H1 -- 否 --> X
    H1 -- 是 --> H2{"在 eager_tool_skills 里或本轮已激活?"}
    H2 -- 否 --> X
    H2 -- 是 --> Y
    I["任务工具模式 / agent_tools/runtime.py:131-143"] --> I1{"mode == ptc?"}
    I1 -- 是 --> I2["wire 只留 run_code"]
    I1 -- 否 --> I3["wire = NATIVE_TOOLS 与能力集的交集"]
```

三个因素各自独立，别混：

* **原生视觉**（`native_vision_provider.native_vision is True`，即 chat provider）：为真时
  **藏** `image_parse__parse_image`、`drawing__inspect_image`、`user_profile__analyze_user_avatar`；
  不为真时**藏** 所有 `image_context__*`（默认只有 `image_context__add_image`）。没有配置项能覆盖。
* **技能常驻策略**：`SkillManager(eager_tool_skills=...)`，默认集是
  `chat_history / drawing / gallery / image_context / image_pool / image_send`（`skills/__init__.py:50`）；
  其余技能只在 `skills__load_tools` 之后出现。`agent_tools` 伞技能 `exposed_to_main_agent=False`，
  永远不常驻也不可被加载。
* **任务工具模式**：只决定**任务型 Agent**的编排方式；主回复管线用
  `agent_tools_packages` 的按需包（内部固定 `runtime.definitions(mode='native')`），
  所以切到 PTC 也不会把主回复工具换成一个 `run_code`。

`is_tool_authorized` 与 `_policy_authorized` 在 `definitions()`（tools.py:886）与
`execute()`（tools.py:957）两处都跑；orchestrator 里在 `tool.call.before` 前后**各查一次**
（orchestrator.py:3126、3175），因为钩子可以改写工具名与参数。
</details>

<details>
### executor 分派：授权 → 计划模式 → 内建 if 链 → 技能路由

```mermaid
flowchart TD
    A["execute(name, args) / tools.py:955"] --> B{"is_tool_authorized?"}
    B -- 否 --> B1["authorization_error：白名单 / 已去重 / 视觉不匹配三种文案"]
    B -- 是 --> C{"非 agent_tools__ 且共享运行时处于计划待审批?"}
    C -- 是且不在 safe 集 --> C1["返回 ok=false code=PLAN_MODE"]
    C -- 否 --> D["内建 if 链：cancel → split_reply → send_reply → wait → willing → emoji → speak → poke → 后台 → send_long_reply"]
    D --> E["skills__read_manifest / read_resource / view_instructions / load_tools"]
    E --> F{"name 含 __ 且有 skill_manager?"}
    F -- 否 --> F1["raise ToolError: Unknown reply tool"]
    F -- 是 --> G["取 token；缺失且 capture 可用则现取；仍无 → 未知工具: name"]
    G --> H["剥离 _SKILL_INTERNAL_KEYS；注入 pipeline_key / _requester_id / _numbering_mapping"]
    H --> I["agents__ 前缀才注入 _delegate_context"]
    I --> J{"is_session_tool(name)?"}
    J -- 是 --> K["_execute_session_tool：后台提交 + 通知"]
    J -- 否 --> L["_execute_skill：agent_tools__ / agents__ / background_trigger__ / sandbox_manager__ 必须先有 ToolContext"]
    L --> M["CURRENT_INVOCATION 注入 dispatch / external / history，finally 里 reset"]
    K --> N["orchestrator 外层 wait_for 兜超时"]
    M --> N
```

* 授权失败**不抛异常**：返回中文字符串给模型（`Error: …`），模型可以改参数重试。
  只有完全未知的名字才会 `raise ToolError`，由 orchestrator 记成工具失败。
* 技能路由要求「可信聊天身份」：`conv_kind in {group, private}` 且 `conv_id` 是数字；
  缺失时 `agent_tools__*` 返回 `{"ok": false, "code": "CONTEXT_REQUIRED"}`。
* 技能工具的真实执行在 `SkillManager.execute`（skills/base.py:409）：`{prefix}__{tool}` 精确匹配
  owner，token 对不上返回「工具不可用或已更新」；技能内部异常被 catch 成
  `工具执行失败 [name]: <脱敏摘要>` —— **工具面看不到异常**，只有日志里有。
</details>

<details>
### 结果回灌与失败语义：role=tool · 16 KiB 截断 · 连续失败软提示

```mermaid
flowchart TD
    A["逐个 tool_call / orchestrator.py:3078"] --> B["tool.call.before 可改写 name 与 args；改写后重算 wait 余量与授权"]
    B --> C["asyncio.wait_for(executor.execute, tool_timeout)"]
    C -- 正常 --> D["tool.call.after 可替换 result；原生视觉时收集 image_parts"]
    C -- 超时 --> E["tool_error=工具 X 执行超时；若已有沉默余量则 cancel_for_silence 直接 return"]
    C -- 异常 --> F["tool_error=工具 X 执行失败：类型 + 脱敏摘要（300 字）"]
    D --> G["_bounded_tool_text 截断到 16 KiB"]
    G --> H["messages.append role=tool + tool_call_id + content"]
    E --> I["tool_failure_streak[name|args] 计数 +1"]
    F --> I
    I --> J{"连续失败 >= 3 次?"}
    J -- 是 --> J1["附软提示：不要再重复尝试（只提示，不短路）"]
    J -- 否 --> K
    J1 --> K["append role=tool：工具调用失败：…"]
    H --> L["成功则清零该指纹的计数"]
    K --> M["consume_tools_dirty → 重建 tools"]
    L --> M
    M --> N["manual_parts 追加本轮图片；视觉刚降级再补一条 user 说明"]
```

* `tool_timeout` = 沉默余量（有预算时）否则 `max(模型响应超时, wait 秒数 + 依赖超时 10s)`
  （orchestrator.py:3117-3124）；模型响应超时群聊取 `group_agent_silent_timeout_seconds` 默认 120s。
* **超时**：有沉默预算 → 结束整条管线；没有预算（私聊等）→ 只把失败写回给模型。
* **异常**：工具失败绝不冒泡出管线；异常摘要先脱敏再进上下文。
* 结果永远是字符串：`ImageContextResult` 是 `str` 子类，图片以 `image_parts` **带外**返回，
  orchestrator 必须在转成文本**之前**读走它（tools.py:1093-1095 与 orchestrator.py:3197-3201 两处）。
</details>

<details>
### 原生视觉切换：工具增删与「只多给一轮」的重试

```mermaid
flowchart TD
    A["每轮循环开头读 provider.native_vision / orchestrator.py:2783"] --> B{"与 native_vision_active 不同?"}
    B -- 是 --> B1["更新标记 + 重建 tools"]
    B1 --> B2["append user：视觉能力变更，原生视觉已关闭…"]
    B -- 否 --> C
    B2 --> C["模型调用"]
    C --> D{"调用后 native_vision 由真变假?"}
    D -- 是 --> D1["标记置假 + 重建 tools + record_debug native_vision_fallback"]
    D -- 否 --> E
    D1 --> E{"本轮 tool_calls 为空?"}
    E -- 是且刚降级 --> F["vision_fallback_bonus=True；append user 提醒按需调用 image_parse__parse_image；continue"]
    E -- 否 --> G["正常处理工具调用或正文"]
    F --> C
    D1 -.-> H["三个解析工具恢复可见：image_parse__parse_image / drawing__inspect_image / user_profile__analyze_user_avatar"]
    D1 -.-> I["image_context__add_image 反向隐藏"]
    F -.-> J["循环上限 max_iterations+1，bonus 只多买一轮 / orchestrator.py:2763-2765"]
```

* 两处检测点：**循环开头**（`2783`，检测任意方向的变化）与**模型调用之后**（`2972`，只检测真→假）。
  前者会补一条「[视觉能力变更]」提示；后者补的是「[原生视觉回退]」并允许额外一轮。
* 降级后模型不能凭空声称看过图片：注入的 user 文案明确要求「按需调用
  `image_parse__parse_image`，不能声称已经看到图片」。
* 图片本身不重发：降级的轮次里已经加载的 `image_parts` 会被丢弃（附录只在
  `native_vision_active` 为真时拼接），失败是「看不到」而不是「看到旧图」。
</details>

<details>
### 输出兜底三入口：工具层 → 发送层 → 切分层的调用时序

```mermaid
flowchart TD
    A["入口一 工具层 / tools.py:1606"] --> A1["send_reply：clean_text(text) 再 clean_segments(raw_segments)"]
    A1 --> A2["split_reply / send_emoji / speak / send_long_reply 各自 clean_text"]
    A2 --> A3["remember_split_preview 只记「真正暴露给模型」的预览（deque 8 条）"]
    A3 --> B["入口二 发送层 / sender.py:439"]
    B --> B1["reply.postprocess.after 钩子改写后再清洗一遍（幂等）"]
    B1 --> B2["clean_segments，suppress_control_tokens 仅对可信自动切分关闭"]
    B2 --> B3["全清空 → 丢弃、返回 False、状态退回 GENERATING"]
    B2 --> C["入口三 切分/后处理层 / postprocess.py:72"]
    C --> C1["is_control_token_only(整段) → 判空，避免把正文里的 cancel 当指令"]
    C1 --> C2["fence_after_segment 跨段维持围栏状态，围栏内不清洗"]
    C2 --> C3["超长 / 超句数 → 默认回复替换 fallback_used + 三条出路指引"]
    A1 --> D["should_drop：原文确有标注且清洗后只剩标注 → 丢弃"]
    D --> E["保守取舍：编号后不是已知名字就不削，缩进不无条件压平"]
```

三个入口的分工：

1. **工具层**让模型看见「自己真正发出去的是什么」；`send_reply` 返回的正文就是清洗后的文本。
   清洗后为空时**直接不发**并回一段可操作的中文提示（tools.py:1627-1633）。
2. **发送层**是最后一道：插件钩子可以改逐条内容，所以清洗必须再来一遍；
   全部清空时返回 `False`，`send_reply` 把它翻译成「没有可发送的正文或图片，未发送」，
   避免模型以为已经回复而结束整轮。
3. **切分层**决定「这条还算不算一句话」：`cancel` 只有整段就是一个裸控制词才被吞掉，
   `cancel 是什么意思` 原样保留。

已知取舍写在模块 docstring 里：无法标注的脏草稿（例如「192: 我是一条鱼」而 192 后不是
已知名字）会被保留 —— 精度优先于召回。
</details>

<details>
### 视觉上下文：默认图片预算、失败可见、可重试

```mermaid
flowchart TD
    A["每轮 native_vision_active / orchestrator.py:2843"] --> B["refresh_defaults，timeout = 依赖超时 10s 或沉默余量"]
    B --> C{"max_images = chat.native_vision_default_image_count 默认 4，<=0?"}
    C -- 是 --> C1["清空 _automatic，不加载任何默认图"]
    C -- 否 --> D["扫 queue.entries：replied_messages + message，只收进过编号表的消息"]
    D --> E["键（message_id, image_index）；引用命中去重并移到末尾（视为最近）"]
    E --> F["selected = 末尾 max_images 张，最新优先"]
    F --> G["先替换 _automatic 再 await：取消不会复活旧图"]
    G --> H{"该键已有 image_url 缓存?"}
    H -- 是 --> H1["复用，不重复下载"]
    H -- 否 --> I["loader.execute('add_image') 逐张加载"]
    I -- 成功 --> I1["文本标签 + image_url 块"]
    I -- 失败/超时 --> I2["只留文本：加载失败，未看到图片：原因（下一轮可重试）"]
    H1 --> J["request_messages：automatic + manual_parts 合成一条 user 附录"]
    I1 --> J
    I2 --> J
    J --> K["manual_parts（模型主动 add_image）不参与 max_images 截断"]
    K --> L["visible_content_length：每张图按 3072 字符估 token，base64 不计入"]
```

* 附录永远在**请求边界**追加（`append_image_context`），历史保持纯文本：
  自动图 `[默认加载图片]`、工具图 `[主动加载图片]`，两者都带 `tool_call_id` 与元数据 JSON。
* 加载失败**不静默**：占位文本写明「图片尚未加载或加载超时，不能判断其内容」，
  下一轮 `refresh_defaults` 会重试（键相同但缓存里没有 image_url 块）。
* 主动加载（`image_context__add_image`）是普通工具，不是会话工具；它自己的限额是
  单图 10 MiB、单次合计 20 MiB、2000 万像素、最长边 4096（超限等比缩小）。
* `_estimate_tokens` 用 3072/张的保守估值，避免把 base64 当成正文 token 把预算算爆。
</details>

<details>
### 会话工具生命周期：1 运行 + 1 排队 · 超时 · 通知

```mermaid
flowchart TD
    A["_execute_session_tool / tools.py:1100"] --> B{"_closed?"}
    B -- 是 --> B1["ok=false status=closed"]
    B -- 否 --> C{"args 里有 pipeline_key?"}
    C -- 否 --> C1["ok=false status=missing_pipeline"]
    C -- 是 --> D{"该管线已有运行中的会话工具?"}
    D -- 否 --> E["_start_session_tool 起 asyncio task"]
    D -- 是 --> F{"已有排队项?"}
    F -- 是 --> F1["ok=false status=queue_full（上限 1 运行 + 1 排队）"]
    F -- 否 --> F2["入队；返回 status=queued，要求立即结束本轮"]
    E --> G["_run_session_tool：wait_for(execute, timeout_seconds + 10)"]
    G --> H{"_classify_session_result"}
    H -- 成功 --> H1["status=completed + 会话工具结果通知"]
    H -- 失败 --> H2["status=failed + 失败通知"]
    G -- 超时 --> H3["status=timeout（默认 300s，上限 1800s）"]
    G -- 取消 --> H4["status=cancelled，异常继续抛出"]
    H1 --> I["publish 到 NotificationHub；发布失败只告警"]
    H2 --> I
    H3 --> I
    I --> J["done 回调：清任务表 → 起下一个排队项（已关闭则不起）"]
    J --> K["_record_session_completion 保留最近 5 条，供 check_background_tasks"]
    E --> L["cancel_task：取消运行中任务并丢弃排队项"]
```

* 声明为会话工具的技能工具只有两个：`image_parse__parse_image`
  （image_parse_skill.py:139）与 `sandbox_manager__download_file`（sandbox_manager_skill.py:84）。
* `_parse_session_timeout`：`0 / None / 布尔 / NaN / 畸形` → 300；负数钳到 1；上限 1800。
  **`timeout_seconds=0` 不是「不超时」**，而是回落到 300 秒。
* 结果分类看 `error/errors` 键、`status in {cancelled, error, failed, failure, timeout}`、
  以及 `ok` 的真值（字符串 "false"/"no"/"0"/"none"/"" 都算失败，`ok=None` 也算失败）。
* 会话工具**活过本轮回复**：管线结束只 `drain_sessions`（等它跑完），
  只有进程关停的 `close()` 才 `cancel()` 在途任务。
</details>

<details>
### 与 skills / agent_tools 的边界：同一能力两个入口的差异

```mermaid
flowchart TD
    A["同一叶子能力的两个入口"] --> B["入口 A：agent_tools__read 等按需包 / skills/agent_tools_packages.py"]
    A --> C["入口 B：sandbox_manager__read_file 等旧别名 / agent_tools/modes.py:16"]
    B --> B1["必须先 skills__load_tools(['agent_tools_files'])"]
    B1 --> B2["包只取 runtime.definitions(mode='native') 的子集；名字仍是 agent_tools__read"]
    B2 --> B3["执行 → AgentToolsSkill.execute → runtime.execute(direct=True)"]
    C --> C1["is_tool_authorized 直接判假"]
    C1 --> C2["authorization_error 提示改用 agent_tools__read（PTC 时在 run_code 内调用）"]
    D["image_parse__parse_image：技能会话工具"] --> D1["后台执行 + 通知，默认 300s、上限 1800s"]
    E["agent_tools__read_image：agent_tools_misc 包"] --> E1["同步解析工作区内文件，<=10 MiB，直接返回描述"]
    F["agent_tools 伞技能 / agent_tools_skill.py:25"] --> F1["exposed_to_main_agent=False 且 get_tools()=[]：不常驻、不可被 load_tools 选中"]
```

* 五个按需包共享前缀 `agent_tools`，因此加载前后工具名完全一致
  （`agent_tools__read` 等），模型不用区分来源；路由按**最终名**精确匹配。
* 执行入口统一走伞技能的 `execute`，所以凭据、计划模式、归属校验完全相同；
  包本身只是「呈现方式的裁剪」。
* `agent_tool_capabilities()`（tools.py:901）算的是**能力集**（与 wire 呈现无关），
  `ptc_enabled` 时额外包含 `run_code`；它被塞进 `ToolContext.allowed_tools`，
  供 runtime 二次校验「这个叶子工具是否在本轮授权范围内」。
* 计划待审批时，旧工具入口（除 safe 列表外）一律返回 `PLAN_MODE`，
  防止模型用「不经过 run_code 的老路」绕过执行限制。
</details>

<details>
### 上限与阈值一览：写死在代码里的数字

```mermaid
flowchart LR
    A["_MAX_TOOL_TEXT_CHARS = 16 KiB / tools.py:96"] --> A1["会话工具结果与错误摘要的截断"]
    B["_MAX_SKILL_RESOURCE_BYTES = 1 MiB / tools.py:97"] --> B1["skills__read_resource 超限直接拒绝"]
    C["_MAX_EMOJI_PAGE_SIZE = 200 / tools.py:99"] --> C1["list_emojis 单页上限"]
    D["_parse_session_timeout 默认 300，区间 1..1800 / tools.py:1344"] --> D1["0 与畸形值回落 300"]
    E["_split_previews deque maxlen=8 / tools.py:290"] --> E1["segments 溯源只认最近 8 条预览"]
    F["wait 冷却默认 60s / tools.py:1758"] --> F1["冷却期内直接回提示，不等待"]
    G["_TOOL_FAILURE_HINT_AFTER = 3 / orchestrator.py:67"] --> G1["同工具同参连续失败 3 次附软提示"]
    H["MAX_KNOWN_SENDER_NAMES = 200 / output_guard.py:35"] --> H1["名字按长度降序取前 200"]
    I["_MAX_PREFIX_PASSES = 6 / output_guard.py:38"] --> I1["每行最多剥 6 层前缀"]
    J["visible_content_length 每图 3072 / vision_context.py:114"] --> J1["图片代价按保守值计入预算"]
    K["_MAX_COMPLETED_HISTORY = 5 / tools.py:1543"] --> K1["check_background_tasks 只显示最近 5 条完成记录"]
```

这些值全在代码里，`config.toml` 改不到；调参需要改代码。与配置项相连的只有：
`chat.native_vision_default_image_count`（默认 4）、`chat.wait_cooldown_seconds`（默认 60）、
`chat.agent_wait_max_seconds`（默认 60）、`chat.agent_max_iterations`（默认 200）。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `Toolset.specs`（首轮工具快照） | `build_reply_toolset` 里的 `definitions()` | 不清理；后续重建走 `executor.definitions()` | 预激活 / 首轮加载的技能工具**不在首轮表里**，要等一次重建 |
| `_split_previews`（≤8 条） | `remember_split_preview`（split_reply / AI 检查暴露的预览） | deque 自然淘汰；随执行器释放 | 未匹配预览时 `segments` 一律独立清洗，`ai_check_approved` 不能跳过清洗 |
| `_ai_check_pending` | `_build_ai_check_prompt` | `send_reply` 成功 / `cancel` / `send_long_reply` 成功 | 下一轮无 tool_calls → `FAILED`「AI回复检查未通过」 |
| `_session_task_info` / `_session_task_queue` | `_start_session_tool` / 排队 | done 回调、`cancel_task`、`close()` | 排队满 → `queue_full`；关停后提交被拒 |
| `_session_completed` | `_record_session_completion` | `close()`；超过 5 条截断 | 只影响 `check_background_tasks` 视图，不影响执行 |
| `_skill_tokens` | `definitions()` 时 `capture_execution_token` | 随执行器释放 | token 对不上 →「工具不可用或已更新」/「未知工具」 |
| `_closed` | `close()`（幂等） | 不清理 | 之后的会话工具提交、排队消费、新任务启动全部被拒 |
| `_activation._activated` / `_dirty` | `load()` / `preactivate_skills` | 随执行器释放；`consume_dirty` 只清标记 | 未加载的技能工具不可见，但**已经注册**的名字仍可执行 |
| `vision_context._automatic` | `refresh_defaults` | 下一轮整体替换 | 加载失败留文本占位，并在下一轮重试 |
| `vision_context.manual_parts` | 每轮 `image_parts` 追加 | 随管线对象释放 | 不受 `max_images` 截断（主动加载没有张数上限） |
| `native_vision_active`（管线局部变量） | orchestrator:2784 / 2976 | 管线结束即消失 | 只影响 `tools` 与图片附录；system 提示词里的 `[native_vision]` 段不会跟着改 |

## 易错点

* **首轮工具表是快照，不是活列表（本轮实测）**：`build_reply_toolset` 冻结
  `Toolset.specs`，orchestrator 首轮用 `reply_toolset.definitions()`。实测
  `preactivate_skills(["dummy"])` 之后 `toolset.definitions()` 里没有 `dummy__ping`，
  `executor.definitions()` 里有，且 `consume_tools_dirty()` 为 True。
  后果：插件 `preactivate` 意图（minigame 的 `agent_reply(preactivate=[...])`）在
  **首轮模型调用里拿不到新工具 schema**，要等模型先调一次别的工具触发重建才补上。
  排查「插件说预激活了但模型不会用」时先看这里。
* **`is_tool_authorized` 被调用两次不是冗余**：`definitions()` 过滤 + `execute()` 拦截，
  orchestrator 还在钩子前后各查一次（钩子能改工具名）。别把其中一处当死代码删掉。
* **视觉规则是双向的**：`native_vision=True` 藏三个解析工具；`!= True` 藏 `image_context__*`。
  没有开关能同时拿到两边——这正是「切换时必须重建 tools」的原因。
* **`agent_tool_capabilities()` 与 wire 呈现无关**：它算的是能力集（决定 `ToolContext.allowed_tools`），
  `ptc_enabled` 只影响这里是否包含 `run_code`，不影响主回复管线直接调用叶子工具。
* **技能 allowed-tools 白名单是「全部命中技能都声明才生效」**（orchestrator.py:2162-2172）；
  生效时 `_SKILL_GUARD_BASE_TOOLS` 里的会话基础设施（cancel/send_reply/wait/
  check_background_tasks/cancel_task/agents__delegate…）**不能被限制掉**，这是有意设计。
* **同参数连续失败的软提示只提示不短路**（orchestrator.py:3258）：部署修好后必须还能继续调用；
  反过来，看到 3 次失败提示不等于工具被禁用。
* **`drain_sessions` ≠ `close`**：管线结束只等在途会话工具跑完（通知要靠它），
  只有进程关停才取消。任何新代码用 `close()` 收尾一轮回复都会砍掉在途 `parse_image`。
* **`image_context__add_image` 与 `image_parse__parse_image` 是两种能力**：前者把图片塞进
  原生视觉上下文（普通工具、不限额张数、受字节/像素限制），后者走独立视觉模型解析
  （会话工具、后台执行、默认 300s）。它们在原生视觉开关下互为镜像，别混用。
* **计划待审批的 safe 列表里有已被去重的旧别名**（`sandbox_manager__read_file` 等，
  tools.py:967-972）：共享运行时存在时这些名字先被 `is_tool_authorized` 拦掉，
  列表里的条目是死条目，不是「计划模式下仍可用」的承诺。
* **`timeout_seconds=0` 不是「不超时」**：会话工具的 0/None/布尔/NaN 一律回落 300 秒，
  真正的上限是 1800 秒，且外层还要再加 10 秒收尾窗口。
