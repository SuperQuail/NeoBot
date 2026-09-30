---
flow: 06-tools-skills
covers:
  - app/src/neobot_app/agent_tools/
  - app/src/neobot_app/skills/
  - app/src/neobot_app/bootstrap/_skills.py
  - app/src/neobot_app/runtime/sandbox_service.py
  - app/src/neobot_app/runtime/sandbox_lock.py
  - app/src/neobot_app/runtime/sandbox_maintenance.py
  - packages/chat/src/neobot_chat/skills/
verified_against: dfe5416
verified_hash: 02b4252f88d7
---

# 06 工具运行时与技能：注册 · native/PTC · 管理员凭据 · 沙箱裁决 · 维护 Agent

## 范围

本图覆盖「模型能碰到的能力」从注册到落地的整条链路：

* `agent_tools/`：`AgentToolRuntime` 的模块装配、定义表、门禁、分发，PTC 解释器与限额，
  管理员凭据（`ToolPermissions`）、子 Agent（`ChildAgentTools`）、进程工具（`ProcessTools`）、LSP（`LspTools`）；
* `skills/`：内置 Python 技能（`SkillModule` / `SkillManager`）的注册、`{skill}__{tool}` 前缀路由、
  常驻 / 延后加载（`SkillToolActivation`）、`agent_tools` 五个按需工具包；
* `packages/chat/src/neobot_chat/skills/`：Markdown 技能（`SKILL.md`）的发现、关键词命中与系统提示注入；
* `runtime/sandbox_service.py`、`sandbox_lock.py`、`sandbox_maintenance.py`：路径裁决、原子写、临时区、
  维护周期的调度与执行。

不在本图内：`04-agent-loop` 画 chat 侧 `Agent` 的工具调用回合；`03-reply-pipeline` 画回复编排与
工具表进入提示词的主干；`05-llm-routing` 画 provider 选择与降级；`01-startup` 画装配顺序。
provider / adapter / 浏览器 / 插件只出现在调用点，不展开。

**spec 与现实的差异（读图前先知道）**：

1. `SandboxLock` 全仓库**没有任何调用点**（`acquire` / `release` / `acquire_temp` / `is_owner` / `is_occupied` 均无调用者，
   只被 `bootstrap/_runtime.py:221` 构造并注入）。「同一时间只有一个 agent 能写沙箱」目前**不成立**。
2. `SandboxManagerSkill` 的 `hold_temp` 只调用 `ensure_temp_dir`，`minutes` 参数不产生任何计时（NO-OP）。
3. `execute_command` 在 `runtime.py:103` 注册时被**无条件跳过**：线协议上的命令工具只有平台名 `pwsh` / `bash`。
4. `config.agent.tools.mode=ptc` 只改变**任务型 Agent**（子 Agent / 解题 / Goal）的呈现；
   主回复管线永远按 native 取叶子工具（`agent_tools_packages.py:60` 显式 `mode="native"`）。

## 流程

```mermaid
flowchart TD
    A["AgentToolRuntime 构造｜runtime.py:49"] --> B["按开关装配模块<br/>files/state 常驻；processes←shell_enabled<br/>web←web_enabled；children←provider 非空<br/>lsp←lsp_enabled"]
    B --> C["逐模块收集工具定义｜:100"]
    C --> D{"名称过滤"}
    D -- "name 是 execute_command" --> D1["跳过：平台正主是 pwsh/bash"]
    D -- "terminal_ 前缀且 terminal_enabled=false" --> D2["跳过：终端整组不下发"]
    D -- "name 已注册过" --> D3["raise ValueError，启动即失败"]
    D -- 通过 --> E["写入定义表与归属表"]
    E --> F["补挂 skill（总是）<br/>read_image（vision_provider 非空）"]
    F --> G{"resolve_mode：native / ptc｜modes.py:25"}
    G -- native --> H["线协议 = NATIVE_TOOLS 与已注册定义的交集"]
    G -- ptc --> I["线协议 = 单个 run_code"]
    H --> J["模型调用 → execute → _execute｜:157 / :173"]
    I --> J
    J --> K{"门禁"}
    K -- "allowed_tools 白名单之外" --> K1["TOOL_DENIED"]
    K -- "非线协议工具且非宿主 direct 调用" --> K2["MODE_TOOL_DENIED"]
    K -- "计划待审批且不在 _PLAN_ALLOWED" --> K3["PLAN_MODE"]
    K -- "执行类工具且无管理员凭据" --> K4["CREDENTIAL_REQUIRED"]
    K -- 通过 --> L["分发：files / children / 其它模块，或 run_code 走 PtcRunner"]
    L --> M["result_json → max_output_bytes 校验｜:264"]
    M -- "超过 262144 字节" --> M1["OUTPUT_LIMIT，不做静默截断"]
    M -- 通过 --> N["finally：state.record_event 记录成功或失败"]
```

主图只画主干与四个拒绝点。注册顺序、两种模式、四个 PTC 硬上限、凭据签发、子 Agent 三种编排、
Windows 进程树、技能前缀与按需加载、Markdown 技能注入、沙箱路径七道闸、锁与临时区、
维护 Agent 循环各有一块折叠细节。

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant H as 宿主调用方
    participant R as AgentToolRuntime
    participant P as ToolPermissions
    participant C as CredentialManager
    participant S as SandboxService
    participant M as 工具模块

    H->>R: execute 工具名 参数 与可信 ToolContext
    R->>R: 门禁：CLOSED / 白名单 / 线协议 / 计划模式 / run_code 递归
    R->>P: require context 与动作名
    P->>C: consume 会话 动作 commit=True
    alt 命中可用凭据
        C-->>P: Credential
        Note over C: one_time 立刻置 USED<br/>timed 保持 ACTIVE 不消费
        P-->>R: 放行
    else 没有凭据
        C-->>P: None
        P-->>R: 抛 CREDENTIAL_REQUIRED 带 details
        Note over R,H: 不致命：模型应按指引申请凭据<br/>拿到凭据前重复调用每次同样失败
    end
    R->>S: ensure_temp_dir 取本会话工作目录
    R->>M: module.execute 参数与 context
    M-->>R: dict 结果（后台作业或子 Agent 可继续跑）
    R->>R: result_json 与 max_output_bytes 校验
    R-->>H: 返回 JSON
    Note over R,H: 任何异常都在 finally 记 record_event<br/>子 Agent 的 llm 调用失败等同普通异常
```

## 细节

<details>
### 工具注册全流程：模块 → 定义表 → 线协议过滤

```mermaid
flowchart TD
    A["AgentToolRuntime 构造｜runtime.py:49"] --> B["装配模块列表：files / state 必装<br/>shell_enabled→processes，web_enabled→web<br/>provider 非空→children，lsp_enabled→lsp"]
    B --> C["逐模块收集工具定义｜:100"]
    C --> D{"name 是 execute_command?"}
    D -- 是 --> D1["continue：被平台名 pwsh/bash 取代"]
    D -- 否 --> E{"terminal_ 前缀<br/>且 terminal_enabled=false?"}
    E -- 是 --> E1["continue：终端整组不下发"]
    E -- 否 --> F{"name 已在定义表里?"}
    F -- 是 --> F1["raise ValueError：Duplicate agent tool<br/>不做后者覆盖"]
    F -- 否 --> G["定义表 与 归属表 同时写入"]
    G --> H["补挂 skill（总是）<br/>read_image（有 vision_provider 时）"]
    H --> I["为每个 parameters 建 Draft202012Validator"]
    I --> J{"is_wire_tool 判定｜:131"}
    J -- "mode=ptc" --> J1["只有 run_code 是线协议工具"]
    J -- "mode=native" --> J2["NATIVE_TOOLS 与已注册定义的交集"]
    J1 --> K["definitions 输出给模型"]
    J2 --> K
```

`NATIVE_TOOLS`（`modes.py:7`）共 21 个名字：`read`、`write`、`edit`、`glob`、`grep`、`read_image`、`lsp`、
`run_python`、`pwsh`、`bash`、`web_search`、`web_fetch`、`job_list`、`job_output`、`job_kill`、
`todo_write`、`ask_user_question`、`question_status`、`enter_plan_mode`、`exit_plan_mode`、`skill`。
注册表同时充当「工具是否存在」的唯一事实来源：`capability_names` 给出全集，
`capability_definitions(allowed_tools)` 给出按技能白名单裁剪后的叶子能力；
`reply/tools.py:923` 用 `agent_tools__` 前缀反查这张表来授权。
`LEGACY_FILE_ALIASES`（`modes.py:16`）把 `sandbox_manager__read_file` 等 5 个历史别名
标记为「已去重」：能力存在时旧别名一律不授权。
</details>

<details>
### native 与 ptc：同一批能力的两种模型可见面

```mermaid
flowchart LR
    subgraph 配置["配置层｜config/schemas/bot.py:1499"]
      A["mode 默认 native｜:1503"] --> B["ptc_enabled 默认 True｜:1504"]
      B --> C["shell / terminal / web / lsp_enabled 默认 True"]
    end
    subgraph 解析["resolve_mode｜modes.py:25"]
      D{"mode 取值"} --> D1["both 已废弃：FutureWarning → native"]
      D --> D2["既非 native 也非 ptc：ValueError"]
      D --> D3["ptc 但 ptc_enabled=false：ValueError"]
      D --> E["native"]
      D --> F["ptc"]
    end
    E --> G["线协议：NATIVE_TOOLS 交集，模型直接点名工具"]
    F --> H["线协议：单个 run_code，描述内嵌 SDK 与全部 JSON Schema"]
    G --> I["主回复管线也只取 native｜agent_tools_packages.py:60"]
    H --> J["模型写程序：await tools.NAME 传单个 dict"]
    J --> K["dispatch 回到 runtime.execute，重走全部门禁"]
    G --> L["宿主 direct 调用绕过模式限制（仅 NATIVE_TOOLS）"]
    J --> M["返回 logs / result / logs_truncated"]
```

模式只决定「任务型 Agent 怎么编排」，不决定能力是否存在：
`_invoke_child`（`runtime.py:316`）给子 Agent 装 `Executor.definitions`，它调
`runtime.definitions(allowed_tools=context.allowed_tools)`，于是子 Agent 在 ptc 下只看到 `run_code`；
主回复管线走 `AgentToolsPackageSkill.get_tools`，固定 `mode="native"`，
所以把配置改成 ptc 不会让主回复变成「只会写程序」。
`directly_exposed`（`:185`）只在宿主显式传 `direct=True` 时成立，且只覆盖 `NATIVE_TOOLS` 成员。
`run_code` 在 native 下不是线协议工具，即使 direct 调用也会 `MODE_TOOL_DENIED`。
</details>

<details>
### PTC：四个硬上限、整张限额表与解释器边界

```mermaid
flowchart TD
    A["PtcRunner.run 入口｜ptc.py:163"] --> B["wall_time_seconds = 30.0｜上限 1"]
    B --> C["解析：max_code_bytes=32768 / max_ast_nodes=4000 / max_ast_depth=64"]
    C --> D["逐语句与表达式 tick：max_steps=30000，每 64 步让出事件循环"]
    D --> E["for 迭代累计：max_iterations = 4000｜上限 2"]
    E --> F["每次 await tools.NAME 计费：max_tool_calls = 32｜上限 3"]
    F --> G["parallel 批量：max_batch_calls=16，整批先计费再执行"]
    G --> H["值遍历：nodes=16000 / depth=32 / string=32768 / int=256bit / collection=4000"]
    H --> I["结果字节：max_result_bytes = 262144｜上限 4"]
    I --> J["日志：max_log_entries=128 / max_log_bytes=16384，超限只置 logs_truncated"]
    J --> K["超时 → PtcError 码 PTC_TIMEOUT；语法 → PTC_SYNTAX"]
    K --> L["工具失败 → ToolCallError，唯一可被程序捕获的异常"]
```

四个「最先撞到」的上限是：单次程序**最多 32 次工具调用**、**墙钟 30 秒**、
**返回值不超过 262144 字节**、**循环累计 4000 次迭代**。
其余限额都是正整数校验（`__post_init__` 拒绝非正数），改小会让既有程序直接失败、
改大只影响单次调用的资源占用，不影响能力授权。
注意三个容易混的预算：`max_steps`（语句/表达式步数 30000）、
`max_iterations`（for 实际迭代 4000）、`max_tool_calls`（工具调用 32）。
另外 `max_output_bytes`（配置默认 262144，`bot.py:1513`）是**外层**结果上限，
与 `max_result_bytes` 是两道不同的闸：外层超限抛 `OUTPUT_LIMIT`。

下面是解释器本身的安全边界：

```mermaid
flowchart TD
    A["_NODES 白名单｜ptc.py:71"] --> B{"节点类型在表内?"}
    B -- 否 --> B1["PTC_SYNTAX：Unsupported syntax"]
    B -- 是 --> C{"Call 节点的函数形态"}
    C -- "Name 且非 parallel 与内置" --> C1["PTC_SYNTAX：任意调用被拒"]
    C -- "Attribute 形态" --> C2["必须 await tools.NAME 且只传一个 dict"]
    C2 --> C3{"attr 在 allowed 内且不是 run_code?"}
    C3 -- 否 --> C3a["PTC_TOOL_DENIED"]
    C3 -- 是 --> D["invoke：调用 dispatch"]
    D --> E["dispatch 回到 AgentToolRuntime.execute，带程序内标记再走一遍门禁"]
    E --> F["外部工具走 external_dispatch，同样重新做参数校验与授权"]
    D -- "抛出 AgentToolError" --> G["包成 ToolCallError：code 截 128 字符，message 截 1024 字符"]
    C -- "try 语句" --> H["只允许一个 except ToolCallError，禁止 finally 与多 handler"]
```

解释器自述的边界（`build_python_sdk`，`:102`）：无 import、函数/类、递归、推导式、while、
元组/集合、切片、f-string、getattr、任意属性；`is`/`is not` 只支持与 `None` 比较；
赋值复制 JSON 值（不做容器别名）；`print` 走有界日志。
保留名 `_RESERVED` = 内置 7 个 + `tools` / `ToolCallError` / `run_code` / `parallel`，赋值即语法错误。
`parallel` 的并发语义只在**整批**工具都属于宿主声明的并发安全集合（`runtime.py:21` 的 `_SAFE_READS`）时成立；
只要有一个不安全，整批退化为串行。批中任一失败会取消并 drain 其余调用，
但**已完成调用的副作用不回滚**；宿主 dispatch 若不配合取消，则杀不掉。
</details>

<details>
### 权限与凭据：require → CREDENTIAL_REQUIRED → 管理员签发 → 重试

```mermaid
sequenceDiagram
    autonumber
    participant R as AgentToolRuntime
    participant P as ToolPermissions
    participant CM as CredentialManager
    participant CS as credential__request
    participant AD as 管理员
    participant EP as 消息入口

    R->>P: require context 与动作名
    Note over R: 动作来源：agent_execute / agent_shared_write<br/>agent_goal / agent_ralph / agent_plan
    P->>CM: consume 会话 动作 commit=True
    alt 有可用凭据
        CM-->>P: 返回 Credential
        Note over CM: one_time 置 USED 立刻失效<br/>timed 持续有效不被消费
        P-->>R: 放行，继续执行
    else 无凭据
        CM-->>P: None
        P-->>R: 抛 CREDENTIAL_REQUIRED 带 details
        R-->>CS: 模型按 details 调用 credential__request
        CS-->>AD: 返回 code 文本，要求管理员在聊天里发送
        AD->>EP: 发送 code
        EP->>CM: try_issue 会话 code 签发者
        Note over CM: 冷却期内一律拒绝（含正确 code）<br/>权限不足 permission_denied，过期 expired
        CM-->>R: 已签发，模型重试同一个工具调用
    end
```

`require` 的 docstring 写明「never grant from model text」：`context` 必须是宿主铸造的
`ToolContext`（`contracts.py:9`，`__post_init__` 校验 owner 与 `chat_flow_id` 必须含冒号），
模型参数里伪造的身份不参与判定。
当前会触发凭据检查的位置：`_EXECUTION` 六个工具（`run_python` / `execute_command` / `bash` / `pwsh` /
`terminal_open` / `terminal_send`）→ `agent_execute`；`write`/`edit` 且路径以 `shared:` 开头 →
`agent_shared_write`；`create_goal`、`update_goal` 的 resume/edit → 先要 `human_request` 再要 `agent_goal`；
`ralph` → `human_request` + `agent_ralph`；`_approve_plan` → `agent_plan`。
`update_goal` 的 complete/blocked 走另一条闸：没有真人请求时必须匹配到正在运行的目标轮，
否则 `GOAL_ROUND_REQUIRED`。
凭据不是重试型错误：`permissions.py:29` 明确写「拿到凭据之前重复调用每次都会同样失败」，
且「凭据不等于操作系统沙箱」。
</details>

<details>
### 子 Agent / workflow / ralph：三种编排的差异与上限

```mermaid
flowchart TD
    A["ChildAgentTools｜delegation.py:49"] --> B["_create 铸造子 context：owner 换成 child 前缀<br/>depth=parent+1，human_request=False，allowed_tools 继承"]
    B --> C{"容量检查｜:207"}
    C -- "depth 达到 max_depth=3" --> C1["depth_limit"]
    C -- "同 parent 运行中子会话达到 max_children=8" --> C2["child_limit"]
    C -- "实例内保留会话达到 max_sessions=256" --> C3["session_limit"]
    C -- 通过 --> D["每会话一个 JSON 状态文件，fsync 后原子替换"]
    D --> E{"模型调用哪个工具"}
    E -- subagent --> F["prompt 入队，后台跑 _run"]
    E -- subagent_fork --> G["必须显式给 history，否则 history_required"]
    E -- send_message --> H["续跑空闲子会话；pending 上限 32；allowed_tools 只取交集"]
    E -- interrupt_agent --> I["取消当前轮，队列消息全部 park"]
    E -- workflow --> J["parallel 或 pipeline，steps 最多 8"]
    E -- ralph --> K["max_rounds 最多 8，每轮全新子会话"]
    J --> L["pipeline 把上一步 result 当不可信数据拼进 prompt，某步非 completed 即 break"]
    K --> M["要求结构化 JSON 报告：complete 需 evidence，blocked 需 blocked_reason"]
    L --> N["两者都返回 independently_verified=false"]
    M --> N
    F --> O["结束才触发 completion_callback"]
```

`max_agent_iterations`（默认 20，`bot.py:1510`）是**每个子 Agent 每轮**的模型回合上限，
`max_child_agents`（默认 8）与 `max_goal_rounds`（默认 8）分别喂给 `max_children` 与 `max_rounds`。
其余边界：`max_pending=32`、`max_messages=512`、`max_text_chars=65536`、
`max_summary_chars=8192`、`max_state_bytes=1MiB`。
子 context 的 `human_request` 恒为 `False`，所以子 Agent **永远无法**创建 goal 或启动 ralph
（`HUMAN_REQUIRED`）；`send_message` 只能把 `allowed_tools` 收窄成交集，不会放大权限。
进程重启后 `_restore` 逐文件校验血缘（owner 不同、agent_id 相同、depth 不差 1、白名单越权都会拒绝），
合法会话被 park 成 idle 且 outcome 记为 `recovered`，只有显式 `send_message` 才会再跑。
</details>

<details>
### 进程工具：一次命令的限流、超时与 Windows 进程树终止

```mermaid
flowchart TD
    A["run_python / pwsh / bash 入口｜processes.py:359"] --> B["_validate：先校验参数，再考虑起进程"]
    B --> C["_start：锁内限流，全局记录上限 256"]
    C -- "同 owner 运行中 job 达到 8" --> C1["resource_limit 拒绝"]
    C -- 通过 --> D["cwd = workspace_resolver 解析出的可信工作区，必须存在"]
    D --> E["create_subprocess_exec，env 注入 PYTHONIOENCODING 与 PYTHONUNBUFFERED"]
    E --> F{"os.name"}
    F -- nt --> G["CREATE_NEW_PROCESS_GROUP，再挂 _WindowsTree 的 Job Object"]
    F -- posix --> H["start_new_session=True，killpg 可用"]
    G --> G1{"Job Object 附加成功?"}
    G1 -- 否 --> G2["立刻终止进程树并抛 process_start_failed"]
    G1 -- 是 --> I["_watch：双流泵 + 超时或停止事件"]
    H --> I
    I --> J{"先满足哪个"}
    J -- "超时" --> J1["status=timed_out"]
    J -- "进程正常退出" --> J2["status=completed"]
    J -- "收到取消" --> J3["status=cancelled"]
    J1 --> K["finally：先关 Job 句柄（KILL_ON_JOB_CLOSE），再等真实进程句柄"]
    J2 --> K
    J3 --> K
    K --> L["_terminate_tree：nt 走 taskkill 带 /T /F（5s 上限），posix 走 killpg SIGKILL"]
    L --> M["回收管道，置 done 事件"]
    M --> N{"后台作业且有完成回调?"}
    N -- 是 --> O["callbacks 里 publish 任务更新：工具输出是数据，不是授权"]
```

`ProcessConfig` 默认值（`processes.py:33`）：`default_timeout=30.0`、`max_timeout=300.0`、
`max_wait=30.0`、每流 `output_limit_bytes=64KiB`、`max_spill_bytes=32MiB`、`max_spill_files=512`、
`max_jobs_per_owner=8`、`max_terminals_per_owner=4`、`max_records=256`、
`max_command_chars=128KiB`、`cleanup_timeout=5.0`。
限流按 `owner` 统计、跨会话生效（访问本身更严），所有者校验把「别人的 id」和「不存在的 id」
都回同一个 `not_found`，不给出存在性预言。
Windows 侧 `_WindowsTree` 用 Job Object 的 kill-on-close 兜住「父进程已退出、子进程还在跑」的情况，
`taskkill` 只在启动或附加失败时兜底；`:124` 的 terminate 会 `WaitForSingleObject` 真实句柄，
避免「宣告完成时孙进程还在跑」。终端是持久**管道** shell（非 PTY，无 TUI、无交互 stdin），
`terminal_signal interrupt` 先发 CTRL_BREAK_EVENT（nt）或给进程组发 SIGINT（posix），
随后**无条件**走 `_cancel_and_wait`。
</details>

<details>
### 技能注册：最终名前缀与 {skill}__{tool} 路由

```mermaid
flowchart TD
    A["build_all_skills｜skills/__init__.py:62"] --> B["按注入依赖决定注册集合，disabled_skills 是黑名单"]
    B --> C["SkillManager.register｜base.py:169"]
    C --> D{"名称合法：字母数字下划线短横线、长度不超过 64<br/>不含双下划线、不以单下划线结尾?"}
    D -- 否 --> D1["ValueError：名称无效"]
    D -- 是 --> E{"同名技能已注册?"}
    E -- 是 --> E1["ValueError：已注册"]
    E -- 否 --> F["get_tools 必须返回 list；execute 必须是 async 协程"]
    F --> G["前缀 = tool_prefix 或 技能名"]
    G --> H["最终名 = 前缀 + 双下划线 + 局部工具名"]
    H --> I{"最终名合法且不是保留名?"}
    I -- 否 --> I1["无效报错；保留名是 skills__read_manifest 与 skills__read_resource"]
    I -- 是 --> J{"局部名重复或最终名已被占用?"}
    J -- 是 --> J1["ValueError：重复的最终工具定义，报出占用者"]
    J -- 否 --> K["登记执行令牌，登记最终名归属"]
    K --> L["session_tools 必须是已声明局部名的子集"]
    L --> M["execute 按最终名精确路由，令牌不匹配回「工具不可用或已更新」"]
    M --> N["技能抛异常：先脱敏再作为文本返回，不向模型抛栈"]
```

前缀**可以被多个技能共享**（`tool_prefix` 属性，`base.py:83`），因此路由必须按最终名精确匹配
（`_final_owners`），不能按技能名反查 —— 这正是 `agent_tools` 五个包能共用前缀的前提。
单条工具定义上限 `_MAX_SCHEMA_BYTES=64KiB`；`_validate_schema` 会拒绝外部 `$ref`、
递归 `$ref`、`prefixItems`/元组 `items`、非法正则与悬空指针。
`session_tools` 声明的工具走「提交后立即返回、后台完成再通知」的会话模式
（`reply/tools.py:1052` 分流），非会话工具直接 await。
</details>

<details>
### 技能按需加载：常驻 / 延后 / skills__load_tools / agent_tools 五包

```mermaid
flowchart TD
    A["SkillManager 构造｜base.py:156"] --> B{"eager_tool_skills"}
    B -- "None" --> B1["全部技能的工具常驻，历史行为"]
    B -- "默认集合" --> B2["常驻 6 个：chat_history / drawing / gallery / image_context / image_pool / image_send"]
    B2 --> C["其余技能只留一行摘要，进 get_instructions"]
    C --> D["SkillToolActivation｜activation.py:27"]
    D --> E["tools 取 常驻 + 已激活 的工具集"]
    D --> F["候选人非空才生成 skills__load_tools，enum 即候选技能名"]
    F --> G["模型调用 skills__load_tools 传技能名数组"]
    G --> H{"逐个名字判定"}
    H -- "不在技能名单" --> H1["未知技能名"]
    H -- "已加载或已常驻" --> H2["已经可用，无需重复加载"]
    H -- "可见工具为空（白名单或能力限制）" --> H3["当前会话无法使用"]
    H -- "可加载" --> I["加入 activated，置 dirty 标记"]
    I --> J["宿主 consume_dirty 后重建本轮工具表"]
    K["agent_tools 伞技能｜agent_tools_skill.py:12"] --> L["exposed_to_main_agent=False：不常驻也不可加载"]
    L --> M["build_agent_tool_packages 拆 5 包：files / exec / web / plan / misc"]
    M --> N["共享前缀 agent_tools，工具名前后一致，执行复用伞技能入口"]
```

动机写在注释里：全部常驻时实测**超过 2 万 token**，而 `agent_tools` 的 20 个常驻工具
18 小时内只被调用 2 次、每次却占约 8.9K 字符（`skills/__init__.py:45`）。
`get_all_tools`（忽略按需策略）专供不经过主回复管线的独立 Agent（如沙箱维护 Agent）；
`get_skill_tools` 供只挂部分技能的子 Agent 取「已加前缀」的定义。
`exposed_to_main_agent=False` 的技能既不在 `deferred_skill_names` 里，也不会出现在加载候选里。
加载失败不是错误路径：未知 / 重复 / 不可见都会以人类可读文本回给模型，`_dirty` 只在真的新增时置位。
</details>

<details>
### Markdown 技能：SKILL.md 的发现、关键词命中与注入时机

```mermaid
flowchart TD
    A["data/skills 下的 SKILL.md｜bootstrap/__init__.py:913"] --> B["SkillRegistry.discover｜registry.py:207"]
    B --> C{"单文件解析"}
    C -- "frontmatter 缺失或非法" --> C1["记入 errors，跳过该技能"]
    C -- 通过 --> D["name 必须 kebab-case 含字母且不超过 64，并与父目录同名"]
    D --> E["keywords 规范化：最多 64 项、2048 字符"]
    E --> F{"同名技能再次出现?"}
    F -- 是 --> F1["保留先出现者，冲突写进 errors"]
    F -- 否 --> G["存入注册表，key 为裸名"]
    G --> H["装配 Agent 时挂 build_skill_preprocessor"]
    H --> I["每轮 _prepare 先跑预处理器｜inject.py:8"]
    I --> J{"消息里有非空文本 user 消息?"}
    J -- 否 --> J1["pop 掉 _matched_skills，清上一轮残留"]
    J -- 是 --> K["按最后一条 user 文本匹配，limit=3"]
    K --> L["按命中关键词数降序写入 state 的 _matched_skills"]
    L --> M["Agent._prepare 只保留 Skill 实例｜agent.py:249"]
    M --> N["set_skills 渲染进系统提示"]
    N --> O["skills__read_manifest 与 skills__read_resource 按需读正文与资源"]
    O --> P["_build_allowed_paths 追加技能目录为可读路径"]
```

匹配**只用 keywords**（`registry.py:399`）：把 keywords 按空白与中英标点切分，
统计长度不小于 2 的词在查询文本里出现的个数，同分保持注册顺序；
`description` 不参与匹配。最多注入 3 个（注释写明与 README 一致），
且每轮都重算：没有用户消息时显式清理，避免上一轮命中污染本轮。
注意这是与内置技能**完全不同的第二套系统**：SKILL.md 提供的是提示词元数据 + 正文按需读取，
不注册任何工具，也不授予权限；插件通过 `register_many(owner, skills)` 以 `owner:name` 注册，
`unregister_owner` 整批注销，frontmatter 的 `allowed-tools` 会进入回复执行器的白名单过滤。
</details>

<details>
### 沙箱路径裁决：resolve_agent_path 的七道闸

```mermaid
flowchart TD
    A["resolve_agent_path 入口｜sandbox_service.py:163"] --> B{"owner 与 chat_flow_id 非空且在长度上限内?"}
    B -- 否 --> B1["PermissionError：trusted owner 与 flow 必填"]
    B -- 是 --> C{"chat_flow_id 是否规范?"}
    C -- "含冒号" --> C1["必须 group:数字 或 private:数字，否则拒绝别名拼写"]
    C -- "不含冒号" --> C2["必须等于清洗结果且字符集受限"]
    C1 --> D{"value 以 shared: 开头?"}
    C2 --> D
    D -- 是 --> E["首段必须在白名单目录：tools / docs / assets / gift / emoji / gallery"]
    E --> E1{"该目录注册了外部只读根?"}
    E1 -- "write=true" --> E1a["PermissionError：shared resource is read-only"]
    E1 -- "只读" --> E2["基准换成外部只读根"]
    D -- 否 --> F["基准 = temp/{chat_flow_id}"]
    E2 --> G["拒绝 .. 段、盘符、冒号、Windows 保留设备名（含数据流）"]
    F --> G
    G --> H["拼接后 resolve，判定是否仍在基准之内"]
    H --> I{"在基准之内?"}
    I -- 否 --> I1["PermissionError：outside current flow/shared directory"]
    I -- 是 --> J["逐级检查 symlink 与 junction，命中即拒（含指向另一允许根的链接）"]
    J --> K{"write 且不在沙箱根内?"}
    K -- 是 --> K1["PermissionError：write outside sandbox"]
    K -- 否 --> L{"is_path_allowed 判定"}
    L -- "在沙箱或只读根内" --> M["返回绝对路径，后续 IO 再各自校验"]
    L -- 否 --> L1["PermissionError：path is not allowed"]
```

这是「受信上下文」版本：`owner` 与 `chat_flow_id` 只能由宿主传入，
模型参数里的 `owner` / `chat_flow_id` / `pipeline_key` 会被 `AgentFileTools.execute`（`:155`）
判为 `untrusted_context` 直接拒绝。
旧的 `resolve_path`（`:141`）只做「拼 `temp/{清洗后的 flow id}` + 沙箱边界检查」，
没有 shared 白名单与符号链接检查，新代码应走 `resolve_agent_path`。
`_sanitize_flow_id`（`:503`）先删 `..` 与斜杠，再把 `<>:"|?*` 和控制字符换成下划线，
去掉首尾空格与点，空串回落 `unknown` —— 冒号被拒的规范判定正是为了避免两个不同身份
经清洗后落进同一个目录。
</details>

<details>
### 沙箱并发与临时区：装配了却没生效的锁，以及真正的保护

```mermaid
flowchart TD
    A["SandboxLock｜sandbox_lock.py:10"] --> B["bootstrap/_runtime.py:221 构造，注入 SandboxService 与 SandboxManagerSkill"]
    B --> C["全仓库没有 acquire / release / acquire_temp / is_owner 的调用点"]
    C --> C1["结论：当前不构成任何互斥，别把它当既有保证"]
    D["真正在起作用的是文件级串行"] --> E["SandboxService.file_lock：按规范化路径的 RLock，引用计数归零即回收"]
    E --> F["atomic_write：同目录 mkstemp，前缀 .neobot-write-"]
    F --> G["写入 + flush + fsync 后再 os.replace 原子替换"]
    G --> H["异常路径 chmod 0600 后 unlink 临时文件"]
    H --> I["进程被强杀才留下的孤儿临时文件"]
    I --> J["维护器按前缀正则加 mtime 超过 3600 秒清理，显式跳过符号链接与 junction"]
    D --> K["容量：max_total_size 默认 2GiB（装配时注入）"]
    K --> L["check_capacity 返回剩余字节，不大于 0 视为不足"]
    D --> M["temp/{chat_flow_id}：ensure_temp_dir 幂等创建"]
    M --> N["TempCleaner：mtime 超过 1800 秒即删；清理锁忙时返回 skipped=busy"]
```

`SandboxLock` 的类注释宣称「主持有者拥有完整写权限、临时持有者只能访问 temp/{chat_flow_id}」，
但 `SandboxService.__init__` 把 `lock` 存进 `self._lock` 后再未使用，
`SandboxManagerSkill` 同样只赋值不使用，全仓库也不存在任何 `acquire` 调用 ——
**读代码时不要以为沙箱写操作被单会话互斥保护**。
`hold_temp` 工具（`sandbox_manager_skill.py:873`）只调 `ensure_temp_dir` 就返回
「已保活 N 分钟」，没有任何计时器或标记，属于纯回显。
同一个文件的跨进程写入没有锁：`file_lock` 是进程内 `threading` 原语，
多进程共享同一沙箱目录时只靠原子替换保证「不写坏」，不保证「不互相覆盖」。
</details>

<details>
### 沙箱维护 Agent：独立循环、调度判据与执行体

```mermaid
flowchart TD
    A["_make_maintenance_coro｜bootstrap/__init__.py:301"] --> B["常驻技能 = archive / file_storage / sandbox_maintenance / sandbox_manager"]
    B --> C["_loop 先 sleep 60 秒再进入调度"]
    C --> D["读 MaintenanceRunRecord 的最近成功时间与状态"]
    D --> E["plan_maintenance_run｜:133"]
    E --> F{"上次状态是 failed 或 running?"}
    F -- 是 --> F1["due=true：上次没正常收尾，立即补跑"]
    F -- 否 --> G{"从未成功过?"}
    G -- 是 --> G1["due=true"]
    G -- 否 --> H{"距上次成功达到 interval_seconds?"}
    H -- 是 --> H1["due=true；默认间隔 10800 秒"]
    H -- 否 --> H2["due=false：写 skipped 记录，休眠取 60 到 1800 秒分片"]
    F1 --> I["_begin 建 running 记录"]
    G1 --> I
    H1 --> I
    I --> J["Agent：max_iterations=30，command_timeout=120，system_prompt=维护提示词"]
    J --> K["invoke 一条用户消息：请执行一次完整的沙箱维护清理"]
    K --> L["工具链：check_capacity → scan_temp_files → get_maintenance_status → 读 文件存储.md → 清理"]
    L --> M["trigger_maintenance → SandboxMaintenanceManager.run_once"]
    M --> N{"进程内维护锁非阻塞拿到?"}
    N -- 否 --> N1["skipped=true，reason=已有维护在运行"]
    N -- 是 --> O["先跑孤儿原子写清理（与变更门无关）"]
    O --> P{"force 或确有文件变更?"}
    P -- 否 --> P1["skipped=true，reason=无文件变更"]
    P -- 是 --> Q["搬进工作线程：清错放与垃圾 → 整理命名 → 更新 文件存储.md → 刷容量 → 写 .last_maintenance"]
    Q --> R["_finish 记 success 或 failed 与 tool_calls，再休眠一个间隔"]
```

整个周期是同步文件系统操作（整树 rglob、rmtree、move），必须 `asyncio.to_thread`，
否则会卡住事件循环数秒（`sandbox_maintenance.py:64` 的注释就是这条历史坑）；
因此互斥从「事件循环天然串行」变成了显式 `_MAINTENANCE_LOCK`，拿不到就跳过本轮。
「有没有变更」只看 `tools` / `docs` / `assets` 与 `文件存储.md` / `TODO.md` 的 mtime 是否新于
`.last_maintenance`，所以安静运行时绝大多数轮次会跳过；孤儿临时清理**必须**放在变更门之前，
否则安静 Bot 上的残留永远清不掉。
`interval_seconds` 来自 `agent.sandbox.maintenance.interval_seconds`，
CLI 侧（`cli.py:558`）有同构的一份循环，两条路径共用同一套 prompt 与调度函数。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| 定义表与归属表 | AgentToolRuntime 构造期一次性写入 | 无（close 只停后台任务） | 重名直接 raise，进程启动失败 |
| `_closed` 标志 | close 首行 | 不重置 | 之后所有 execute 回 CLOSED |
| 计划模式 | enter_plan_mode 与 StateTools | exit_plan_mode 或人工审批 | 非白名单工具回 PLAN_MODE，不执行 |
| 一次性凭据 | credential__request 建 pending，管理员发文本后 ACTIVE | consume 置 USED；cleanup 清 pending 与已用 | 无凭据回 CREDENTIAL_REQUIRED，操作零副作用 |
| 子会话状态与 outcome | 创建为 queued，启动为 running，结束定终态 | close 全部 park 成 idle | 重启恢复为 idle 且 outcome=recovered，只有 send_message 能再启动 |
| 子会话状态文件 | _persist 每次变更后 fsync 再替换 | close 不删（保留会话） | 写盘失败回滚内存状态，outcome=failed 且 error=persistence_failed |
| 进程与终端记录 | _start 写入记录表 | 前台结束即弹出；close 清空 | 超上限回 resource_limit；Job 附加失败回 process_start_failed |
| spill 字节与文件计数 | _Capture.append 预留后累加 | close 删除临时目录（计数不重置） | 超限置 spill_failed，结果里 spill_limit_reached=true |
| `_matched_skills` | inject_skills 每轮覆盖写 | 无用户文本消息时 pop | 只是提示词数据，不授权任何工具 |
| 已激活技能集合 | SkillToolActivation.load | 随执行器对象生命周期 | 不可见技能只回文本提示，不抛错 |
| 沙箱临时目录 | ensure_temp_dir 幂等创建 | TempCleaner 按 1800 秒 mtime 删 | 目录被清后旧路径失效，需重新解析 |
| `.last_maintenance` 标记 | 维护周期末尾写时间戳 | 无（只读比较） | 标记不存在时视为有变更，首跑必做 |
| SandboxLock 持有者 | 无调用点 | 无 | 当前不参与任何裁决，不可依赖 |

## 易错点

* **SandboxLock 是死装配**：`acquire` / `acquire_temp` / `is_owner` / `is_occupied` 全仓库零调用点，
  `SandboxService._lock` 与 `SandboxManagerSkill._lock` 赋值后未使用。想加互斥必须自己接线。
* **`hold_temp` 是 NO-OP**：`minutes` 只出现在返回文案里，没有保活计时，临时目录照样按 mtime 被清。
* **`execute_command` 注册时被跳过**（`runtime.py:103`）：线协议命令工具只有 `pwsh` / `bash`；
  直接把 `execute_command` 交给 runtime 会得到 `UNKNOWN_TOOL`。
* **PTC 只在任务型 Agent 上生效**：主回复管线固定按 native 取叶子工具，
  排查「切了 ptc 没变化」时先看调用方是 `AgentToolsPackageSkill` 还是 `_invoke_child`。
* **三个 PTC 预算别混用**：`max_steps`（30000 步）、`max_iterations`（4000 次 for 迭代）、
  `max_tool_calls`（32 次工具调用）；墙钟 30.0 秒是独立的一道闸，超时回 `PTC_TIMEOUT`。
* **`parallel` 的并发是整批判定**：混入一个非并发安全工具就整批串行；
  失败批次会取消其余调用，但**已完成调用的副作用不回滚**。
* **PTC 里只能 catch `ToolCallError`**：`except Exception` 与 `finally` 会被 AST 校验直接拒绝，
  其他错误以 `PtcError` 终止整个程序。
* **凭据不是重试型错误**：没有凭据时每次调用都以同样原因失败，必须先 `credential__request`
  并由管理员签发；`one_time` 用一次即 USED，`timed` 不会被 consume 掉。
* **子 Agent 永远不是「真人请求」**：`human_request=False` 是硬事实，
  所以子 Agent 无法创建 goal、无法启动 ralph；`send_message` 只能收窄工具白名单。
* **ralph 的报告只是自述**：`independently_verified` 恒为 false，`complete` 必须带非空 `evidence`
  字符串、`blocked` 必须带 `blocked_reason`，否则降级为 `continue` 继续烧轮数。
* **技能前缀可以共享，路由必须按最终名**：`agent_tools` 五个包同前缀；
  重复的最终工具名会让 register 直接抛错，改用「按技能名反查」会路由到错误实现。
* **两套「技能」互不相干**：Markdown 技能（SKILL.md，最多命中 3 个，只进系统提示）
  与内置技能（工具表里的 `{skill}__{tool}`）同名也不冲突；改一套不要以为另一套跟着变。
* **维护循环的「跳过」不等于什么都没做**：孤儿原子写残留每轮都清；
  反过来只有 `force=True` 才跳过变更门，常规调用不会强跑。
* **跨进程没有沙箱写锁**：`file_lock` 是进程内原语，多进程共享沙箱目录时只保证
  「文件不会写坏」（原子替换），不保证「互相不覆盖」。
