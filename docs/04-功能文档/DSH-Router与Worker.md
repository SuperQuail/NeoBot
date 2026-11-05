# DSH Router 与 Worker

把 NeoBot 当 **Router**、DeepSeek Harness（DSH）当 **Worker**：用户在 QQ 里聊需求，
NeoBot 判断任务复杂度、**先问用户要不要开 DSH**，确认后把任务分派给开发机上的
DSH 会话；执行中可以查状态、补信息、改方向，结果由 NeoBot 总结回复。

本文只描述 NeoBot 侧（Router + 网关 + 内置插件）。开发机 daemon 在独立仓库
`neobot-dsh-worker`，协议见其 `PROTOCOL.md`。

## 1. 角色边界

- **Router（NeoBot 主回复 Agent）**：接人、全局记忆、任务分派、进度/结果汇总；
  Router 模式下不执行具体任务。
- **Worker（DSH Session）**：独立上下文执行代码任务，不直接对用户说话。
- **daemon（开发机 DSH 插件）**：只做会话生命周期、事件上报、命令执行、审批转发；
  只出站连接 NeoBot。

## 2. 动态启用（不按聊天流静态白名单）

1. 默认普通模式，工具面不变；
2. 用户提需求，主 Agent 判断是否复杂开发任务；
3. 复杂 → 调 `dsh_router__propose` 生成提案（目录、模式、预计动作），向用户确认；
4. 用户确认 → 调 `dsh_router__dispatch`，**此时才激活 Router 模式**；
5. 该聊天流从下一轮起只保留只读/回复工具 + `dsh_router__*`；
6. 任务全部闭环 / 用户 `/dsh exit` / 进程重启 → 复位。

Router 模式激活后，每次模型调用前注入 `[Router 任务表]` user 块（任务号、状态、
最近摘要、卡点），由插件提供、核心只负责追加。

## 3. 工具与命令

工具（默认按需加载，主 Agent 通过 `skills__load_tools` 加载 `dsh_router`）：

| 工具 | 作用 |
|---|---|
| `dsh_router__propose` | 生成提案，不产生副作用 |
| `dsh_router__dispatch` | 派发任务（要求有未过期提案），激活 Router 模式 |
| `dsh_router__tasks` | 活跃/最近任务表 |
| `dsh_router__status` | 单任务详情 |
| `dsh_router__send` | 插话：`steer` 下一步生效 / `queue` 空闲再跑 |
| `dsh_router__cancel` | 取消当前轮 |
| `dsh_router__approve` | 回答越界审批（one-shot） |
| `dsh_router__exit` | 退出 Router 模式 |

命令：`/dsh status|tasks|pending|approve|cancel|exit|help`（默认超级管理员，插件配置 `command_permission` 可调）。

## 4. 网关与协议

核心网关只做传输与鉴权，不解析 DSH 语义：

```text
POST /dsh/daemon/sync    # 上报 reports + 拉取 commands（长轮询）
GET  /dsh/daemon/health  # 观察 daemon 连接状态
Authorization: Bearer <token>
```

- 请求：`{v, daemon_id, seq, cursor, health, reports, acks}`；
- 报告：`task.event / task.done / perm.request / daemon.health`，消息类型字段
  `kind`，事件分类在 `payload.phase`（`stage / blocker / progress / artifact`）；
- 命令：`daemon.hello / task.dispatch / task.input / task.cancel / task.status / perm.answer`；
- 去重：报告按 `(daemon_id, seq)`；命令按 `id`，未 ack 的命令会重发；
- 网关 `enabled=false` 时不建服务、不监听，插件工具返回「网关未启用」。

## 5. 通知与审批

- worker 事件 → 插件转成语义行 → `BackgroundNotificationHub`（`source=dsh_router`）；
- 会话活跃时在下一轮注入，空闲时唤醒一轮后台回复；
- 事件级节流（默认 45s）；卡点/失败不节流；
- 审批请求与失败：**私聊** `force=True` 绕过发言策略；**群聊**仍遵守策略，
  被 `SpeechBlocked` 时落 pending，用 `/dsh pending` 查看、`/dsh approve` 处理。

## 6. 配置

见 [05-配置参考](../05-配置参考.md) 的 `agent.dsh` 一节。最小配置：

```toml
[agent.dsh.gateway]
enabled = true
host = "127.0.0.1"
port = 8791
token = "<32+ 字节随机值>"

[agent.dsh.router]
enabled = true
ask_before_enable = true
```

插件配置在 `data/plugins_data/dsh_router/config.toml`（面板「插件 → dsh_router → 配置」），
至少配置 `workspaces`（允许执行任务的目录白名单，realpath 校验）。

## 7. 当前实现状态

| 部分 | 状态 |
|---|---|
| 核心 `RouterModeService` + 工具面裁剪 + 任务表注入 | 已实现，测试覆盖 |
| 核心最小网关 + acks 重投 + 长轮询 | 已实现，`app/tests/modules/dsh_gateway/` 115 用例 |
| 内置插件 `dsh_router` | 已实现：任务表/8 个工具/通知/审批/`/dsh` 命令，38 个用例 |
| 开发机 bundle `neobot-dsh-worker` | 骨架 + 协议客户端已完成；DSH 会话适配层待 SPIKE |

## 8. 排障

| 现象 | 处理 |
|---|---|
| 工具返回「DSH 网关未启用」 | 检查 `agent.dsh.gateway.enabled` 与 token；看启动日志 `dsh_gateway.configured` |
| daemon 401 | 两端 token 不一致；网关日志会记录拒绝 |
| 任务一直 running 无进展 | `/dsh status <id>`；daemon 断线会在 `task_stale_seconds` 后标 stale |
| 群聊审批没出现 | 发言策略拦截；`/dsh pending` 查看，或把群加入受信会话 |
| Router 模式退不掉 | `/dsh exit`；或等 `auto_exit_idle_minutes` 后自动退出 |
