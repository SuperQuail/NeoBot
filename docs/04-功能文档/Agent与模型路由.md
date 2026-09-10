# Agent 与模型路由

NeoBot 的核心是一个多 Agent 系统：主回复 Agent 负责对话与任务编排，多个专职子 Agent 负责特定领域任务，所有 Agent 通过模型编号路由到不同配置的 LLM。

## 模型库与调用方（`models` 配置）

模型**单独存储**在模型库 `[[models.registry]]`，每个条目（`ModelDefinition`）包含：

- `key`：调用方引用名（唯一，字母/数字/下划线/点/短横线）
- `description`：用途说明（生图模型还会作为 Agent 选择依据）
- `provider`：供应商（DeepSeek / OpenAI / Anthropic / 硅基流动 SiliconFlow …）
- `model_name`：模型名
- `pricing`：计费（每百万 Token 输入/输出/缓存命中价格，`billing_metric` 用于非 Token 计费平台）
- `settings`：采样参数（temperature、top_p、max_output_tokens、timeout 等）；DeepSeek 模型额外支持思考模式（`deepseek_thinking_mode`：enabled/disabled/random，`deepseek_reasoning_effort`：high/max，`deepseek_random_thinking_probability`）
- `native_vision`、`balance_query_hint`：原生视觉开关与该模型的余额查询方式

调用方在 `[models.assignments]` 中只保存 key，因此同一个模型可以被多个调用方复用：

| 调用方字段 | 默认 key | 用途 |
|---|---|---|
| `primary_chat_model` | deepseek-v4-pro | 主对话（Agent 编号 0） |
| `agent_model_1` | deepseek-v4-flash-max | 子 Agent（编号 1，max 推理） |
| `agent_model_2` | deepseek-v4-flash-high | 子 Agent（编号 2，high 推理） |
| `agent_model_3` | deepseek-v4-flash-off | 低成本任务（编号 3，非推理） |
| `vision_model` | qwen3-vl-8b | 图像识别（缺 Key 时降级） |
| `tts_model` | cosyvoice2 | 语音合成（TTS 关闭时不注册） |
| `creator_image_models`（列表） | ["flux-schnell"] | 生图（可分配多个 key） |

注册时机：配置加载时按模型库条目逐个注册到运行时模型注册表（同名 key 只注册一次）；`vision_model` / `tts_model` 缺 Key 时只告警并降级，主对话 / Agent 模型缺 Key 会直接报错并列出全部缺失项。

## Agent 模型路由（`agent_model` 配置）

每个 Agent 通过编号（0-3）选择使用的模型：

| 字段 | Agent | 默认编号 |
|---|---|---|
| `main_agent` | 主回复 Agent | 0 |
| `creator` | Creator（生图/表情包） | 1 |
| `memory` | 记忆 Agent | 1 |
| `chat_interaction` | 聊天互动 Agent | 1 |
| `willingness` | 回复意愿 Agent | 1 |
| `scheduled_task` | 定时任务 Agent | 1 |
| `archive_summary` | 档案自动总结 | 1 |
| `self_heal` | 自修复 Agent | 3（低成本非推理） |

## 共享工具与 PTC

主回复、解题与新子 agent 共用 `agent.tools` 任务工具模式，修改配置后重启切换：

- `mode="native"`（默认）：直接使用精简文件、Python／shell、网络、默认 Python LSP、作业和基础任务／交互工具；不暴露 `run_code`、持久终端、goal、subagent、workflow、Ralph 或审计查询。
- `mode="ptc"`：任务工具线上仅暴露 `run_code`，基础与复杂编排叶子只能通过其程序调用，不能直接调用。默认 `ptc_enabled=true` 表示 PTC 能力可用，但仍默认普通模式；关闭该能力时不能选择 PTC。旧 `both` 配置会告警并按精简普通模式加载；建议更新为 `native`。
- 主聊天的聊天、图片、凭据、文件交付业务仍原生可见。仅重复 `sandbox_manager` 文本读写／编辑／glob／grep 别名隐藏且拒绝；目录列表、二进制及收发工具保留。

敏感操作复用管理员凭据，模式切换不扩大继承 ACL 或真人权限，图片复用现有视觉链路。LSP 默认使用正式依赖 pylsp，`lsp_servers={}` 不表示禁用，需使用 `lsp_enabled=false`。完整清单、边界与配置见 [Agent 工具与 PTC](Agent工具与PTC.md)。

## 专职子 Agent

### Problem Solver（解题 Agent，[`app/src/neobot_app/agents/problem_solver.py`](../../app/src/neobot_app/agents/problem_solver.py)）

处理需要深度思考的任务（数学、代码、研究），支持：

- 后台运行 + 完成通知（`notification_retry_seconds`、`max_retries`、`startup_grace_seconds`）
- 结果可保存到沙箱并返回文件路径（`allow_sandbox_output`）
- 每个聊天流最多保留 `max_tasks_per_pipeline`（默认 5）个后台任务
- 超时 `timeout_seconds`（默认 600s）、最大 Token `max_tokens`（默认 20480）、推理强度 `reasoning_effort`（默认 max）
- 共享工具模式使用 canonical 工具和默认网络／Python LSP，不再注册旧 `search/read_page/search_status/write_file/read_file/parse_image` 别名
- `get_chat_context` 与 `submit_solution` 协议保留：普通模式直接调用，PTC 中在 `run_code` 内调用；解题 Agent 的 PTC 线上仅有 `run_code`

### Self-Heal（自修复 Agent，[`app/src/neobot_app/agents/self_heal.py`](../../app/src/neobot_app/agents/self_heal.py)）

通过 loguru ERROR sink 累积异常，触发后自动唤起 Agent 诊断、尝试安全修复并写 debug 报告，通过通知系统向管理员私聊推送。关键参数：

- 触发阈值：`traceback_threshold`（默认 3 个带 traceback 的异常）或 `rate_threshold`（默认 60 秒内 10 个错误）
- 节流：`min_interval_seconds`（默认 300s）、`daily_limit`（默认每日 5 次，防止费用失控）
- 接收人：`admin_account`，留空回退到 `chat.admin_accounts[0]`

## 主 Agent 执行循环

主回复 Agent 在提示词约束下执行工具调用循环（`packages/chat` 中的 Agent 运行时）：

1. 构建提示词（人设、当前时间、聊天记录、档案、技能说明）
2. 调用主模型，得到回复文本或工具调用
3. 工具调用经 SkillManager / 插件工具注册表执行并回填结果
4. 循环直至生成最终回复（send_reply）、取消（cancel）或达到 `agent_max_iterations`（默认 200）

关键约束配置（`chat` 段）：

- `agent_wait_max_seconds`：wait 工具单次最大等待（默认 60s）
- `agent_max_iterations`：单轮回复最大工具迭代次数
- `group_agent_silent_timeout_seconds`：群聊回复管线最长静默时间（默认 60s），wait 等待不计入

## 委托（delegate）与多轮协作

主 Agent 委托子 Agent 时保持 `session_id` 延续；若子 Agent 返回中间回复（缺少信息、需要确认等），主 Agent 应继续调用 delegate 并携带 `previous_response` 补充上下文，直到任务完成。此行为在提示词的「任务处理要求」中约束。

## 相关配置

`agent` 段（`Agent` 配置）：`creator`（图像创作）、`system`（工作目录）、`memory`（记忆）、`problem_solver`、`browser`、`sandbox`、`skill`、`file_operation`、`self_healing`。详见 [05-配置参考](../05-配置参考.md)。

## 相关代码文件

| 文件 | 说明 | 关键类/函数 |
|---|---|---|
| [agents/problem_solver.py](../../app/src/neobot_app/agents/problem_solver.py) | 解题 Agent：后台解题、完成通知、沙箱输出 | `ProblemSolverAgent`、`ProblemSolverManager`、`build_problem_solver_agent` |
| [agents/self_heal.py](../../app/src/neobot_app/agents/self_heal.py) | 自修复 Agent：异常累积触发、诊断修复、通知管理员 | `SelfHealAgent`、`SelfHealManager`、`build_self_heal_agent` |
| [runtime/notifications.py](../../app/src/neobot_app/runtime/notifications.py) | 后台任务完成通知（绘图/解题等） | `BackgroundNotificationHub` |
| [runtime/archive_memory_summary.py](../../app/src/neobot_app/runtime/archive_memory_summary.py) | 档案自动总结 Agent 的运行时服务 | `ArchiveMemoryAutoSummaryService` |
| [runtime/freeze_service.py](../../app/src/neobot_app/runtime/freeze_service.py) | 运维冻结熔断：一键停掉回复管线、档案自动总结与管线内排队调用（`/freeze`、网页面板） | `FreezeService` |
| [skills/agent_delegation.py](../../app/src/neobot_app/skills/agent_delegation.py) | 主 Agent 委托子 Agent 的 delegate 工具 | `AgentDelegationSkill` |
| [providers/base.py](../../packages/chat/src/neobot_chat/providers/base.py) | LLM Provider 抽象与 HTTP 基础实现 | `Provider`、`BaseHTTPProvider` |
| [providers/openai.py](../../packages/chat/src/neobot_chat/providers/openai.py) | OpenAI 兼容 Provider（含 DeepSeek 官方/OpenAI 样式思考模式转换） | `OpenAIProvider` |
| [graph/graph.py](../../packages/chat/src/neobot_chat/graph/graph.py) | Agent 执行图（节点/边/入口） | `StateGraph` |
| [graph/executor.py](../../packages/chat/src/neobot_chat/graph/executor.py) | 编译后的图执行器（工具循环） | `CompiledGraph` |
| [graph/nodes.py](../../packages/chat/src/neobot_chat/graph/nodes.py) | 内置图节点（技能注入节点） | `skill_node` |
| [tools/registry.py](../../packages/chat/src/neobot_chat/tools/registry.py) | Agent/工具注册表 | `AgentRegistry` |
| [config/schemas/bot.py](../../app/src/neobot_app/config/schemas/bot.py) | 模型注册表与 Agent 路由的配置定义 | `Models`、`AgentModelRouting`、`ModelRegistration` |
