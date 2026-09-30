# 图清单与拆分依据（spec(13)）

> 每张图的文件、covers 与状态。新增图先在这里登记，再落盘。

## 1. 图清单与「改了什么 -> 更新哪张图」

> 分层规则：**一个图 = 一个可独立评审的子系统**。单个文件超过 ~800 行、或内部有明显
> 独立状态机/外部依赖时，拆成多张图（见 §4 的拆分依据）。

### 3.1 总览

| 图 | 文件 | 覆盖范围 | 最近核对 |
|---|---|---|---|
| 00 全局视图 | [00-overview.md](./00-overview.md) | 进程启动 -> 入站 -> 处理 -> 出站 -> 停机 | dfe5416 |

### 3.2 骨架层（配置 · 装配 · 模型）

| 图 | 文件 | 覆盖范围 |
|---|---|---|
| 01 启动/停机/待机 | [01-startup-shutdown.md](./01-startup-shutdown.md) | cli / bootstrap / application / standby / adapter_supervisor |
| 01b 配置系统 | \`01b-config-system.md\` | config/schemas（bot.py 1783 行）/ loader / 校验 / 热重载入口 |
| 05 模型路由 | [05-llm-routing.md](./05-llm-routing.md) | assembly/agents.py、bootstrap/_providers.py、chat/models.py |
| 05b provider 与原生视觉降级 | \`05b-provider-native-vision.md\` | providers/*（deepseek/anthropic/native_vision）、异常契约、计费统计 |

### 3.3 主链路层（消息进 -> 回复出）

| 图 | 文件 | 覆盖范围 |
|---|---|---|
| 02 适配器入站 | [02-inbound-message.md](./02-inbound-message.md) | adapter 包、message/queue.py、runtime/gateway.py、inbound_pipeline |
| 02b 回复意愿概率 | [02b-willing-probability.md](./02b-willing-probability.md) | willing/ 全部 + event_pipeline 的决策入口 |
| 02c 事件管道 | \`02c-event-pipeline.md\` | runtime/event_pipeline.py（1468 行：去重/命令/队列/回复后积压/通知） |
| 03 回复管线 | [03-reply-pipeline.md](./03-reply-pipeline.md) | orchestrator 状态机/冷却/看门狗、sender、postprocess、output_guard |
| 03b 回复管线工具面 | \`03b-reply-tools.md\` | reply/tools.py（2537 行：模型可见工具集与 executor） |
| 04 Agent 循环 | [04-agent-loop.md](./04-agent-loop.md) | chat/runtime/agent.py、problem_solver、self_heal |
| 06 工具与技能 | [06-tools-skills.md](./06-tools-skills.md) | agent_tools/、skills/、沙箱 |
| 09 面板 | [09-dashboard.md](./09-dashboard.md) | dashboard 路由/鉴权/静态产物/前端 |
| 09b 面板接口面 | \`09b-dashboard-api.md\` | dashboard/api.py（2564 行）端点清单与权限 |
| 09c 面板配置编辑 | \`09c-dashboard-config.md\` | config_manager.py（1464 行）+ 前端编辑器数据流 |
| 10 联网搜索 | [10-web-search.md](./10-web-search.md) | web_search/ 三级回退 |
| 12 浏览器自动化 | \`12-browser-automation.md\` | browser/agent_browser/manager.py（2084 行）+ actions + lifecycle |
| 13 渲染与卡片 | \`13-render-cards.md\` | runtime/html_card.py、help_card、markdown_image、emoji、screenshot |
| 14 表情包与图像解析 | \`14-emoji-image-parse.md\` | emoji/、image/、vision_detect/、image_pipeline |

### 3.4 能力与子系统层

| 图 | 文件 | 覆盖范围 |
|---|---|---|
| 07 记忆与档案 | [07-memory-archive.md](./07-memory-archive.md) | packages/memory、archive_memory_summary、storage、contracts |
| 07b 档案自动总结 | \`07b-archive-summary.md\` | archive_memory_summary.py（1871 行）细节 |
| 08 插件系统 | [08-plugins.md](./08-plugins.md) | modloader 包、hot_reload_registry、plugin_config_reload |
| 08b 插件运行时 | \`08b-plugin-runtime.md\` | modloader/runtime.py（2168 行）+ installer + hooks |
| 11 小游戏 | [11-minigame.md](./11-minigame.md) | builtin_plugins/minigame/ |
| 15 绘画 | \`15-drawing.md\` | drawing/service.py（1821 行）+ drawing 工具 |
| 16 定时任务 | \`16-scheduled-tasks.md\` | runtime/scheduled_tasks.py、sleep_service、standby、notifications |
| 17 命令系统 | \`17-commands.md\` | commands/、内置命令、权限树、命令重名来源前缀 |
| 18 用户画像与好感度 | \`18-user-profiles.md\` | user_profiles.py（752 行）、favorability.py、memory 摘要 |
| 19 凭据与安全 | \`19-credentials-security.md\` | credentials/、panel_auth.py、check_secrets、沙箱裁决 |
| 20 头像与文件服务 | \`20-avatar-files.md\` | avatar_store.py、core/file_server.py、image_pool |
| 21 联网解析与 B 站 | \`21-web-parse-bilibili.md\` | web_parser/、bilibili/、audio/ |

### 3.5 数据与观测层

| 图 | 文件 | 覆盖范围 |
|---|---|---|
| 22 存储与迁移 | \`22-storage-migrations.md\` | neobot_storage（uow/engine/alembic/models）、database/ |
| 23 计费与统计 | \`23-billing-stats.md\` | statistics/（billing 850 行、tracker）、observability/ |
| 24 提示词与聊天流 | \`24-prompt-chatflow.md\` | prompt/、ChatFlowRegistry、面板聊天流 |

## 2. 为什么这么拆（拆分依据）

本轮按「代码规模 + 独立状态机 + 独立外部依赖」三条判据重新划分，实测数据（行数）：

\`\`\`text
reply/orchestrator.py       4465   -> 03 主图 + 03b 工具面
dashboard/api.py            2564   -> 09b
reply/tools.py              2537   -> 03b
modloader/runtime.py        2168   -> 08 主图 + 08b
browser/agent_browser/mgr   2084   -> 12
runtime/archive_memory...py 1871   -> 07 主图 + 07b
drawing/service.py          1821   -> 15
config/schemas/bot.py       1783   -> 01b
agents/self_heal.py         1678   -> 04 细节块
runtime/html_card.py        1651   -> 13
agents/problem_solver.py    1497   -> 04 细节块
runtime/event_pipeline.py   1468   -> 02c
dashboard/config_manager.py 1464   -> 09c
bootstrap/__init__.py       1413   -> 01 细节块
message/queue.py            1316   -> 02 细节块
minigame/__init__.py        1180   -> 11
\`\`\`

判据：**单文件 >800 行或含独立状态机/外部依赖的，单独成图**；否则并入所属子系统图的折叠细节。
反例警戒：不要为了凑数量把「一个类的两个方法」拆成两张图 —— 图的价值在于「一眼看懂一条链路」。

## 5. 「随改随更新」的约定

1. 改动落在某张图 \`covers:\` 范围内，**必须**在同一 PR 内更新该图，并把
   \`verified_against\` 更新为当前提交短号（\`check_flow_diagrams.py --update --update-commit\`）。
2. 新增跨模块链路（新的回退/降级链）时**新增一张图**，不要塞进旧图。
3. 新增图必须登记到 §3 并写清 covers；删除图要同步删索引行。
4. CI 里 F1/F3 阻断、F2 用 \`--strict-drift\` 阻断；本地 pre-commit 只跑 F1/F3（毫秒级、零误报）。
