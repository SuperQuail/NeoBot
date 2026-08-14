# Agent 与模型路由

NeoBot 的核心是一个多 Agent 系统：主回复 Agent 负责对话与任务编排，多个专职子 Agent 负责特定领域任务，所有 Agent 通过模型编号路由到不同配置的 LLM。

## 模型注册表（`models` 配置）

每个模型注册项（`ModelRegistration`）包含：

- `description`：用途说明
- `provider`：供应商（DeepSeek / OpenAI / Anthropic / 硅基流动 SiliconFlow）
- `model_name`：模型名
- `pricing`：计费（每百万 Token 输入/输出/缓存命中价格，`billing_metric` 用于非 Token 计费平台）
- `settings`：采样参数（temperature、top_p、max_output_tokens、timeout 等）；DeepSeek 模型额外支持思考模式（`deepseek_thinking_mode`：enabled/disabled/random，`deepseek_reasoning_effort`：high/max，`deepseek_random_thinking_probability`）

默认注册 7 个模型：

| 字段 | 默认模型 | 用途 |
|---|---|---|
| `primary_chat_model` | deepseek-v4-pro | 主对话（Agent 编号 0） |
| `agent_model_1` | deepseek-v4-flash（max 推理） | 子 Agent（编号 1） |
| `agent_model_2` | deepseek-v4-flash（high 推理） | 子 Agent（编号 2） |
| `agent_model_3` | deepseek-v4-flash（非推理） | 低成本任务（编号 3） |
| `vision_model` | Qwen/Qwen3-VL-8B-Instruct | 图像识别 |
| `tts_model` | FunAudioLLM/CosyVoice2-0.5B | 语音合成 |
| `creator_image_model` | black-forest-labs/FLUX.1-schnell | 生图 |

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

## 专职子 Agent

### Problem Solver（解题 Agent，`app/src/neobot_app/agents/problem_solver.py`）

处理需要深度思考的任务（数学、代码、研究），支持：

- 后台运行 + 完成通知（`notification_retry_seconds`、`max_retries`、`startup_grace_seconds`）
- 结果可保存到沙箱并返回文件路径（`allow_sandbox_output`）
- 每个聊天流最多保留 `max_tasks_per_pipeline`（默认 5）个后台任务
- 超时 `timeout_seconds`（默认 600s）、最大 Token `max_tokens`（默认 20480）、推理强度 `reasoning_effort`（默认 max）

### Self-Heal（自修复 Agent，`app/src/neobot_app/agents/self_heal.py`）

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
