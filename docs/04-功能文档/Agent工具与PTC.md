# Agent 工具与 PTC

NeoBot 的 `agent_tools` 技能与解题 agent 共用工具运行时，采用 DSH 风格的工具编排、文件版本保护、作业与子 agent 管理。主 agent 保留已有聊天、图片、凭据、文件收发与定时任务技能，不需要另起文件操作 agent。

## 配置与启用

`agent.tools.enabled` 默认 `true`，需要沙箱服务；也可通过 `agent.skill.disabled_skills` 中的 `agent_tools` 禁用。修改配置后重启 Bot，使注册快照与运行服务一致。本功能不启动另一台 Web 服务。

```toml
[agent.tools]
enabled = true
mode = "native"          # 普通模式；复杂编排改为 "ptc" 后重启
ptc_enabled = true       # PTC能力可用，但不会自动切换模式
lsp_enabled = true       # 默认Python LSP
lsp_servers = {}         # 空映射仍使用内置pylsp；不是关闭LSP
shell_enabled = true
terminal_enabled = true
web_enabled = true
max_agent_iterations = 20
max_goal_rounds = 8
max_child_agents = 8
max_output_bytes = 262144
```

`mode` 同时控制主回复的 `agent_tools` 技能、解题和新子 agent 的任务工具。默认 `native` 仅提供精简基础工具，不提供 `run_code` 或复杂编排；`ptc` 的任务工具线上仅提供 `run_code`，所有基础／高级叶子必须在程序内调用，直接调用叶子会被拒绝。不再提供混合工具模式；旧配置 `both` 会给出迁移警告并按精简 `native` 加载，建议改为明确的 `native` 或 `ptc`，不会因升级默认值而无法启动。`ptc_enabled=true` 只表示能力可用，不表示默认选用 PTC；`ptc_enabled=false` 与 `mode="ptc"` 组合属于无效配置。模式通过配置并重启切换，不由模型自行改写。

主聊天的聊天、图片、凭据、文件收发等业务工具仍原生可见，不因 PTC 而隐藏。仅重复的 `sandbox_manager__read_file/write_file/edit_file/glob_files/grep_files` 从主 Agent 隐藏且拒绝执行，改用 canonical 文件工具；`list_files`、二进制文件和收发入口保留。新子 agent 使用装配时提供的主模型，不接受模型自行选择可执行程序或任意模型凭证。

## 工具清单

主 agent 的以下名称均带 `agent_tools__` 前缀；解题／子 agent 内部使用无前缀名称。实际注册受沙箱、模型、视觉、网络及 LSP 配置控制。

| 类别 | 工具 | 调用方式 |
|---|---|---|
| 文件 | `read`, `write`, `edit`, `glob`, `grep` | native 直接；PTC 程序内 |
| 代码执行 | `run_python`, Windows `pwsh` 或其他平台 `bash` | native 直接；PTC 程序内 |
| 后台作业 | `job_list`, `job_output`, `job_kill` | native 直接；PTC 程序内 |
| 网络 | `web_search`, `web_fetch` | native 直接；PTC 程序内 |
| 视觉与技能 | `read_image`, `skill` | native 直接；PTC 程序内 |
| 任务与交互 | `todo_write`, `ask_user_question`, `question_status`, `enter_plan_mode`, `exit_plan_mode` | native 直接；PTC 程序内 |
| 代码导航 | `lsp`（默认 Python） | native 直接；PTC 程序内 |
| 编排入口 | `run_code` | 仅 PTC 线上入口，native 拒绝 |
| 持久管道终端 | `terminal_open`, `terminal_send`, `terminal_read`, `terminal_signal`, `terminal_list`, `terminal_close` | 仅 PTC 程序内 |
| 长目标 | `create_goal`, `get_goal`, `update_goal` | 仅 PTC 程序内 |
| 子任务 | `subagent`, `subagent_fork`, `list_agents`, `send_message`, `interrupt_agent`, `subagent_result` | 仅 PTC 程序内 |
| 批处理 | `workflow`, `ralph` | 仅 PTC 程序内 |
| 新工具审计 | `session_search`, `session_event_read`, `session_event_search`, `session_event_trace`, `session_trace` | 仅 PTC 程序内 |

不再重复提供 `execute_command` alias。解题 Agent 的共享模式删除旧 `search/read_page/search_status/write_file/read_file/parse_image` 别名，改用新版网络、文件、图片工具。`get_chat_context` 与 `submit_solution` 的业务协议保留：native 原生调用，PTC 在 `run_code` 程序内调用，因此解题 Agent 的 PTC 线上也只有 `run_code`。

### PTC 示例

配置 `mode="ptc"` 并重启后，调用 `agent_tools__run_code`，参数为 `code` 和简短 `description`。程序使用受限 Python 子集，而不是任意 Python、TypeScript 或宿主 `exec`：

```python
await tools.write({"file_path": "result.txt", "content": "answer = 42\n"})
page = await tools.read({"file_path": "result.txt"})
return page["content"]
```

支持赋值、列表／字典、索引、有限循环、条件、比较、部分内置函数、`print`、`return`、`try/except ToolCallError` 及 `await tools.name({...})`。工具可用性和参数依实际 schema 决定；程序中的每个工具调用重新经过权限检查，不能通过 PTC 扩大技能白名单。容器赋值采用 JSON 值复制语义，不提供 Python 对象别名／任意属性操作；不支持 import、函数定义或宿主对象访问。

```python
results = await parallel([
    {"tool": "read", "args": {"file_path": "a.txt"}},
    {"tool": "read", "args": {"file_path": "b.txt"}}
])
return [results[0]["content"], results[1]["content"]]
```

只有整批均被宿主标记为并发安全时才并行，否则串行执行。默认 PTC 墙钟上限 30 秒、最多 32 次工具调用、单批 16 个；步骤、循环、AST、整数、容器、日志和完整返回值也有限额。真正的 Python 数值计算和文件生成使用 `run_python`，不要把 PTC 当作完整 Python 解释器。

主 agent 的程序可调用当前暴露的命名空间技能（如 `tools.credential__request(...)`）；调用会返回原执行器再次校验。图片工具返回的带外图片仍通过原有原生视觉消息链路交给主模型，不将 base64 打印进程序结果。

## 文件与权限

默认路径是当前聊天的临时目录。调用者身份来自服务端真实消息／任务上下文，不接受模型填写 owner、pipeline、human 等字段。当前聊天中的不同 agent 可共享文件内容，但不能共享“已读取版本”的观察记录。跨聊天临时目录、路径穿越及链接绕过被拒绝。共享目录须显式指定 `shared:tools/...`、`shared:docs/...` 等允许的命名空间。

`read` 返回行号、版本和分页位置；长行还提供列续读。覆盖已有文本前须完整读取；`edit` 使用完整文件内容进行唯一替换／`replace_all`，不拿截断预览覆盖原文件。成功写入／编辑前进当前 owner 的观察版本；并发更新可传 `expected_version`，过期版本拒绝。写入使用同目录临时文件、fsync 和原子替换，保留空字符串写入能力。

搜索默认最多 100 路径／250 匹配，有文件数、遍历量、字节与时间上限。无本机 ripgrep 时使用受限扫描及独立正则子进程；不在宿主事件循环运行不可信正则。结果注明 `truncated`、原因及统计是否完整；当前搜索实现不自动生成全量 spill 文件，需缩小范围继续检索。

敏感操作复用现有 `credential__request` → 管理员发送 code → 重试的流程：

| action | 授权范围 |
|---|---|
| `agent_execute` | Python、命令、终端执行；旧接口覆盖二进制文件 |
| `agent_shared_write` | 修改共享持久文件 |
| `agent_plan` | 批准计划进入执行 |
| `agent_goal` | 创建／编辑／恢复长目标 |
| `agent_ralph` | 启动有界独立尝试循环 |

这些 action 需要超级管理员。凭据按聊天流与 action 绑定，保留原有一次性／限时语义；不是按脚本参数指纹绑定。凭据缺失不会执行敏感操作；返回申请方法而不是自动签发。计划待审批时，新的执行工具及旧文件／委派入口均受执行层约束；已有后台任务不会因为创建计划而自动回滚，需主动停止。

**权限审批不是操作系统沙箱。** `run_python`、shell、已部署语言服务器仍以宿主可用权限执行；不能向不可信用户无审批开放。PTC 的受限语法不授予额外 OS 权限。文件版本锁协调同一服务实例，不能承诺阻止任意外部进程的竞争写入。

## 作业、终端与子任务

`run_in_background=true` 返回作业 ID，使用 `job_output` 增量读取，`job_kill` 停止；工作目录由宿主绑定，不接受模型自行覆盖。默认执行总超时 30 秒、最大 300 秒（参数单位秒）；后台也有总时限。输出保留有界尾部及限额 spill，配额耗尽明确标为不完整。进程内 Jobs 不在重启后继续运行。

Windows 使用进程组和 Job Object 管理进程树，POSIX 使用独立进程组；关闭运行时会取消、等待收尾，然后关闭状态数据库。没有 PowerShell 7 时可使用系统 `powershell.exe`，工具描述与结果注明实际版本。持久终端为管道进程而非 PTY，不支持 TUI；超时／取消／终止会关闭终端。

`subagent` 创建独立上下文；`subagent_fork` 获取明确传入的父历史快照。运行中 `send_message` 排队到下一回合；`interrupt_agent` 停止当前回合但保留可继续的会话。只能控制直属子 agent，继承工具范围不得扩大。子会话按 owner 存储在宿主私有状态目录，重启后恢复为空闲，不自动执行。

`workflow` 接受有界声明式 `steps`，`mode` 为 `parallel` 或 `pipeline`，不是第二个任意代码执行器。`ralph` 每轮创建新子上下文，检查结构化 worker 报告，报告完成必须带 evidence；`worker_complete` 只表示子 agent 报告完成，不是独立评估。

## 交互、计划与长目标

`ask_user_question` 返回待答 `question_id`，通过既有通知系统展示问题。原请求用户在同聊天回复：

```text
/agent-answer <question_id> PDF
/agent-answer <question_id> {"format": "PDF", "language": "中文"}
```

单个问题可直接写文本，多个问题使用问题 id 到答案的 JSON 对象。只有真实消息入口能记录回答，工具参数不能伪造答案、审批或 human 来源。回答后通过 `question_status` 读取；对子任务可再 `send_message` 继续。旧解题提交入口保留完成回传协议，等待人工的多轮协作优先用可续跑子 agent。

`enter_plan_mode` 建立计划状态，`exit_plan_mode(plan=...)` 申请审批；没有 `agent_plan` 凭据时保留待审批状态，可在凭据签发后提交同一计划重试。

`create_goal` 和 `update_goal` 的编辑／恢复要求真实顶层用户请求及相应凭据。主回复回合结束后，GoalDriver 才以非 human 身份继续同一目标；按版本和轮数预留、执行、结算，默认最多 8 轮。遇到待答问题、待审批计划、凭据不足或异常会停下并等待人工。新真人消息取消当前续跑，重启后也不会自动重新启动，需真人 `resume`。完成判断依据 agent 更新的目标状态，不冒充独立事实验证。

审计查询只检索这套新工具的脱敏事件，不自动读取整个历史聊天库。工具事件、目标、问题和计划使用 SQLite 持久化；程序源码、完整工具输入／输出和凭据秘密不写入审计事件。

## 默认 Python LSP

Python LSP 是正式安装依赖（`python-lsp-server`），默认 `lsp_enabled=true`，`.py`／`.pyi` 使用当前 Python 环境的内置 `pylsp`，首次调用时才启动服务器。源码安装使用当前解释器的 `-I -m pylsp` 隔离启动，避免工作区同名 `pylsp.py` 劫持；打包版通过专用 stdio worker 启动。`lsp_servers={}` 仍启用这些默认服务器。关闭需明确设置 `[agent.tools]` 下的 `lsp_enabled=false` 并重启。

用户 `lsp_servers` 映射会覆盖同扩展名的默认配置或增加其他语言，未覆盖的扩展名继续保留默认配置；不支持用空映射关闭单个扩展。例如将 `.py` 改为已安装的 Pyright（`.pyi` 仍使用默认 pylsp）：

```toml
[agent.tools.lsp_servers.".py"]
command = ["pyright-langserver", "--stdio"]
language_id = "python"
```

客户端接受 `definition`、`references`、`implementation`、`hover` 四种操作；默认 Python pylsp 支持 `hover`、`definition`、`references`，不提供 `implementation`。后者取决于自定义服务器是否实现；不支持时返回 `lsp_unsupported_operation`，不会伪装成 definition 结果。路径限制当前工作区，行／列使用 1-based UTF-16。服务器命令由部署配置提供并解析绝对可执行路径；模型无法指定命令，服务器的写文件请求被拒绝。启动失败明确报错，不在工具调用时自动安装服务器。修改服务器配置同样需要重启。

### 部署验证与冻结打包

标准源码／wheel 部署随项目依赖安装 `python-lsp-server`，无需 Node.js 或单独安装编辑器插件。服务器按需启动并使用 stdio，不监听额外端口。

自行使用 PyInstaller 打包时，需保留 console/stdio（不能使用 `--windowed`），并传入 `--additional-hooks-dir scripts/pyinstaller_hooks`，收集 pylsp 插件元数据、Jedi/Parso 数据和 Markdown 转换器。冻结入口使用专用 worker flag，不把 Bot 可执行文件当作 `python -m pylsp`；冻结 worker 禁用仅用于签名美化的外部 formatter。已验证独立 onedir worker 的真实导航，不代表已构建或验证完整 Bot 冻结包。

## 代码入口

- [共享运行时与工具模块](../../app/src/neobot_app/agent_tools/runtime.py)
- [主 agent 技能适配](../../app/src/neobot_app/skills/agent_tools_skill.py)
- [文件工具](../../app/src/neobot_app/runtime/agent_file_tools.py)
- [解题 agent 接入](../../app/src/neobot_app/agents/problem_solver.py)
- [配置](../../app/src/neobot_app/config/schemas/bot.py)

本功能不引入 Cordis 动态自修改、实验 Agent Teams，也不替换现有图片发送、文件下载、定时提醒及长期文件索引。
