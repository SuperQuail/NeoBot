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
| 01 启动/停机/待机 | [01-startup-shutdown.md](./01-startup-shutdown.md) ✅ | cli / bootstrap / application / standby / adapter_supervisor |
| 01b 配置系统 | \`01b-config-system.md\` | config/schemas（bot.py 1783 行）/ loader / 校验 / 热重载入口 |
| 05 模型路由 | [05-llm-routing.md](./05-llm-routing.md) ✅ | assembly/agents.py、bootstrap/_providers.py、chat/models.py |
| 05b provider 与原生视觉降级 | \`05b-provider-native-vision.md\` | providers/*（deepseek/anthropic/native_vision）、异常契约、计费统计 |

### 3.3 主链路层（消息进 -> 回复出）

| 图 | 文件 | 覆盖范围 |
|---|---|---|
| 02 适配器入站 | [02-inbound-message.md](./02-inbound-message.md) ✅ | adapter 包、message/queue.py、runtime/gateway.py、inbound_pipeline |
| 02b 回复意愿概率 | [02b-willing-probability.md](./02b-willing-probability.md) ✅ | willing/ 全部 + event_pipeline 的决策入口 |
| 02c 事件管道 | \`02c-event-pipeline.md\` | runtime/event_pipeline.py（1468 行：去重/命令/队列/回复后积压/通知） |
| 03 回复管线 | [03-reply-pipeline.md](./03-reply-pipeline.md) ✅ | orchestrator 状态机/冷却/看门狗、sender、postprocess、output_guard |
| 03b 回复管线工具面 | \`03b-reply-tools.md\` | reply/tools.py（2537 行：模型可见工具集与 executor） |
| 04 Agent 循环 | [04-agent-loop.md](./04-agent-loop.md) ✅ | chat/runtime/agent.py、problem_solver、self_heal |
| 06 工具与技能 | [06-tools-skills.md](./06-tools-skills.md) ✅ | agent_tools/、skills/、沙箱 |
| 09 面板 | [09-dashboard.md](./09-dashboard.md) ✅ | dashboard 路由/鉴权/静态产物/前端 |
| 09b 面板接口面 | \`09b-dashboard-api.md\` | dashboard/api.py（2564 行）端点清单与权限 |
| 09c 面板配置编辑 | \`09c-dashboard-config.md\` | config_manager.py（1464 行）+ 前端编辑器数据流 |
| 10 联网搜索 | [10-web-search.md](./10-web-search.md) ✅ | web_search/ 三级回退 |
| 12 浏览器自动化 | [12-browser-automation.md](./12-browser-automation.md) | browser/agent_browser/manager.py（2084 行）+ actions + lifecycle |
| 13 渲染与卡片 | [13-render-cards.md](./13-render-cards.md) | runtime/html_card.py、help_card、markdown_image、emoji、screenshot |
| 14 表情包与图像解析 | [14-emoji-image-parse.md](./14-emoji-image-parse.md) | emoji/、image/、vision_detect/、image_pipeline |

### 3.4 能力与子系统层

| 图 | 文件 | 覆盖范围 |
|---|---|---|
| 07 记忆与档案 | [07-memory-archive.md](./07-memory-archive.md) ✅ | packages/memory、archive_memory_summary、storage、contracts |
| 07b 档案自动总结 | \`07b-archive-summary.md\` | archive_memory_summary.py（1871 行）细节 |
| 08 插件系统 | [08-plugins.md](./08-plugins.md) ✅ | modloader 包、hot_reload_registry、plugin_config_reload |
| 08b 插件运行时 | \`08b-plugin-runtime.md\` | modloader/runtime.py（2168 行）+ installer + hooks |
| 11 小游戏 | [11-minigame.md](./11-minigame.md) ✅ | builtin_plugins/minigame/ |
| 15 绘画 | [15-drawing.md](./15-drawing.md) | drawing/service.py（1821 行）+ drawing 工具 |
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
| 23 计费与统计 | [23-billing-stats.md](./23-billing-stats.md) | statistics/（billing 850 行、tracker）、observability/ |
| 24 提示词与聊天流 | [24-prompt-chatflow.md](./24-prompt-chatflow.md) | prompt/、ChatFlowRegistry、面板聊天流 |

## 3. 写图过程中核出的「代码与直觉不符」清单

> 这些不是猜测，是写图时逐个 grep/read 核对出来的事实。**有图才有这些发现** ——
> 建议逐条开 bugfix 或至少进 issue；在修之前，图里保留现状并标注，不要按「应该有」画。

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| W1 | **待机期 QQ 命令不可达**：\`stop()\` 无条件执行 \`event_ingress.stop\`，\`EventGateway.stop\` 退订全部 4 个订阅（全仓仅此一处订阅） | \`runtime/application.py:457\`、\`runtime/gateway.py:63\` | 待机后 \`/reboot\` 收不到；\`standby_service.py:274\` 的「命令仍可用」与 \`bugfixes\` 里 \`fix(3)\`「已修复」在 HEAD 上都不成立（\`retain_ingress\` 只在分支 \`feat/wip-followups\`） |
| W2 | **\`SandboxLock\` 是死装配**：\`acquire/release/acquire_temp/is_owner/is_occupied\` 全仓零调用点 | \`runtime/sandbox_lock.py\` | 「同一时间只有一个 agent 写沙箱」实际不成立；真正的保护只有进程内 \`file_lock\` + \`atomic_write\` |
| W3 | **\`hold_temp\` 是 NO-OP**：只回显分钟数，无计时器/标记 | \`skills/sandbox_manager_skill.py:873\` | 临时文件仍按 1800s mtime 被清理 |
| W4 | **\`auto_compact_chars\`（默认 200）是死配置**：全仓只有定义处，无读取点 | \`config/schemas/bot.py:1171\` | 面板改了没有任何效果 |
| W5 | **\`ConnectionTimeoutError\` 已不再抛**，\`cmd_run\` 里的 \`except\` 是死分支 | \`runtime/application.py:27-32\`、\`cli.py:297\` | 旧文档/旧图若写「等连接超时会启动失败」是过时画法 |
| W6 | **\`StandbyController.request_process_restart\` 是死链路**（除单测无调用方）；真入口是宿主服务 \`process_restart\`，而 \`/reboot\` 绑的是 \`application.request_restart\` | \`bootstrap/_standby_runtime.py:285\`、\`dashboard/api.py:2667\` | 「换进程」与「换代际」两条路极易混 |
| W7 | **\`execute_command\` 注册时被无条件跳过** | \`agent_tools/runtime.py:103\` | 线协议命令工具只有 \`pwsh\`/\`bash\`；传 \`execute_command\` 得 UNKNOWN_TOOL |
| W8 | **\`mode=ptc\` 只影响任务型 Agent**：主回复管线固定 \`definitions(mode="native")\` | \`skills/agent_tools_packages.py:60\` | 「切了 PTC 没变化」是预期行为 |
| W9 | **不存在 \`minigame__card\` 工具**（spec(8) 描述的显式发卡工具在全仓 0 命中） | \`builtin_plugins/minigame/\` | 工具通道不发卡；文档口径需更正 |
| W10 | **小游戏每日上限硬编码 5/5**，且判定是 check-then-act（并发可越过）；只有签到用 INSERT rowcount 做到了真幂等 | \`minigame/service.py:31-32\` | 面板改不了，并发下上限不硬 |
| W11 | **\`add_score\` 无下界保护**（\`apply_points\` 才有 \`score + :delta >= 0\`） | \`minigame/service.py:151\` | 传负 delta 可写出负余额 |
| W12 | **插件没有文件监听**：热重载只能由面板/命令显式触发；插件配置与本体配置是两条独立通道 | \`runtime/hot_reload_registry.py\`、\`runtime/plugin_config_reload.py\` | 「改了就会自动生效」是误解 |
| W13 | **插件版本无法比较时一律放行**（\`version_satisfies -> None\`），源码运行 0.0.0 亦然 | \`modloader/version.py\` | 「明明写了 \`>=\` 却没拦住」是设计如此 |
| W14 | **同名插件：第三方被静默丢弃**（仅一条 warning，面板无提示） | \`modloader/loader.py\` | 安装后「插件没生效」难排查 |
| W15 | **压缩回滚不再触发容量治理**：\`set_if_version\` 只 WARNING 不拦截 | \`packages/memory/src/neobot_memory/archive_service.py:365\` | 管理员可写入超限档案，靠 \`list_over_limit\` 暴露 |
| W16 | **\`_run_summary\` 异常分支无显式 \`return False\`**（注解标 \`-> bool\`，实际 \`None\`） | \`runtime/archive_memory_summary.py:561-569\` | 调用方按 falsy 处理所以行为正确，但类型注解是错的 |
| W17 | **\`flush_all\` 不看 \`_retry_ready\`**：关闭收尾会把退避中的会话强行总结一次 | \`runtime/archive_memory_summary.py:791\` | 与 \`record_message\` 判据不一致 |
| W18 | **\`_rollback_start\` 不是 \`started\` 的严格逆序**（\`event_ingress\` 提前、\`plugin\` 排在 \`adapter\` 前） | \`runtime/application.py:217\` | 文档写「逆序」是近似说法 |
| W19 | **CLI 路径与 standalone 步数不同**：CLI 传 \`owns_plugins=False\`，插件由 \`cli.py\` 先起，\`app.start\` 的 S3/S7 被跳过 | \`cli.py:61/94\` | 读「13 步」要带条件 |
| W20 | **Windows 上 SIGTERM 无人处理**（\`add_signal_handler\` 回退只装了 SIGINT） | \`cli.py:51-59\` | 优雅停机只能 Ctrl+C 或面板 |
| W21 | **原生视觉包装器不代理 \`registered_key\`**：只代理 native_vision/model/max_tokens/vision_degradation | \`packages/chat/src/neobot_chat/providers/native_vision.py\` | 开原生视觉后 \`getattr(provider,'registered_key')\` 恒空，计费回落 model_name，默认库 4 个 chat 条目同名 → **按模型绑定的计价脚本会串条目** |
| W22 | **\`problem_solver\` 不是路由字段**：\`getattr(routing,'problem_solver',1)\` 恒回落 1；\`creator/memory/chat_interaction/willingness/scheduled_task\` 五个编号字段无 resolve 调用点 | \`app/src/neobot_app/assembly/agents.py\`、\`bootstrap/_pipeline.py:196\` | 配置里没有可改的开关；五个字段只被提示词目录读取 |
| W23 | **声明 native_vision 的主模型可能被整体丢弃**：视觉模型不可用时直接 \`return (None, error)\` | \`bootstrap/_providers.py:62\` | 「能启动但不会回复」的一种来源 |
| W24 | **\`resolve_agent_model_name\` 回退返回角色名而非 key** | \`assembly/agents.py:62\` | 默认库无该 key → ValidationError → 被上层解释成「主模型不可用」 |
| W25 | **\`strip_images\` 主链路写死 False** | \`bootstrap/_providers.py:69\` | 回退到自己没有视觉的模型时不剥图也不报错 |
| W26 | **会话字段永远为空**：\`CURRENT_CONVERSATION_KIND/ID\` 只有读取没有 setter | \`agents/*\` | 解题/自愈的用量记录恒无会话信息 |
| W27 | **默认模型库 pricing 全 0** → 不配 \`billing_script\` 时 \`builtin_cost\` 恒 0 | \`config/schemas/bot.py\` | 「费用为 0」不是 bug，是配置缺省 |
| W28 | **「内容类失败不重试」只在引擎内部成立**：\`SearchManager.search\` 的重试与失败类型无关，结构类叠加重试最多 4 次 HTTP | \`web_search/manager.py:132/158\` | 与 fix(9) v2 的 A10「HTTP ≤2 次」不符 |
| W29 | **\`signals.empty\` 短路只有 Bing HTTP 会置位** | \`web_search/engine.py:231\` | 「页面明说无结果」在第 ②③ 级被当普通失败继续回退 |
| W30 | **浏览器通道把抓取失败归成 CONTENT**（\`classify_failure\` 没传 error） | \`web_search/browser_channel.py:242\` | 排查「超时却说错配页」看这里 |
| W31 | **浏览器级没有整级预算**；\`engine_budgets\` 只有 duckduckgo=15s（设计稿 8s） | \`web_search/manager.py\` | 冷启动+预热+重试+翻页可远超 \`browser_timeout_seconds=8\` |
| W32 | **\`_resolve_chromium\` 只认 \`LOCALAPPDATA/ms-playwright\`** | \`web_search/browser_channel.py:72\` | 非 Windows 上 \`available()\` 恒 False（静默少一级） |
| W33 | **\`set_global_concurrency\` 无调用点** → 全局信号量恒 None | \`web_search/manager.py\` | 全局并发上限不生效；限速是「实例 × 引擎名」 |
| W34 | **未知引擎名会抛穿整条链路**：\`get_engine\` 抛 ValueError，而 \`_try\` 只捕 TimeoutError | \`web_search/engine.py:437\` | 变成工具层 \`[错误]\` 而不是 degraded 响应 |
| W35 | **\`research\` 二次编号留别名**：\`_reindex_results\` 只加键不删旧键 | \`web_search/session.py\` | 实测 4 条结果编号两次后 \`all_results\` 返回 7 项（对象重复） |
| W36 | **插件本体热重载靠删 \`__pycache__\` + 新 \`_gN\` 命名空间**，且没有文件监听 | \`modloader/loader.py\` | 「改了自动生效」是误解；只能由面板/命令触发 |
| W37 | **四个依赖判定入口语义不同**（注册只查在不在 / 启动要求 READY / 面板只展示） | \`modloader/runtime.py:327\`、\`manager.py:224\` | 用错入口会把所有依赖插件误判自动禁用 |
| W38 | **两处「重复注册」语义相反**：HotReloadRegistry 先注册者胜，插件配置消费者后登记覆盖 | \`runtime/hot_reload_registry.py:135\` | 注册顺序会静默改变行为 |
| W39 | **\`load_all\` 注册顺序固定官方目录在前** | \`modloader/loader.py:82\` | 官方插件依赖第三方插件时 on_load 顺序可能与依赖方向相反 |
| W40 | **小游戏工具通道的 300s 是「认人窗口」且是全局单槽** | \`minigame/__init__.py:72\` | 并发用工具会串人；与成语接龙 60s 对局态不是一回事 |
| W41 | **抽签两个兜底不是同一档**（\`pick_level\` 末档「凶」vs \`level_for\` 未知回落「平」），开凶兆后权重和 111 | \`minigame/service.py\` | 概率口径与直觉不符 |
| W42 | **\`streak\` 读的是「今天」那一行**：昨天连签、今天没签 → streak=0 且 checked_in_today=false | \`minigame/service.py\` | 面板/工具展示的连签天数会「归零」 |
| W43 | **\`add_bottle\` 新瓶 id 用 \`ORDER BY id DESC LIMIT 1\`** | \`minigame/service.py:319\` | 并发下拿到的不是本条的 id |
| W44 | **卡片降级三种口径**：漂流瓶发卡片文本、接龙丢弃纯文本返回值、签到/抽签命令通道不出图 | \`minigame/*\` | 「为什么有的玩法没图/没字」看这里 |
| W45 | **\`web_search_package.build_web_search_package\` 无运行时调用点**；\`self_heal.py:774\` 不转发浏览器/预算配置 | \`web_search_package.py:229\` | 自愈链路的搜索行为与主链路不一致 |
| W46 | **首轮工具表是冻结快照**：\`build_reply_toolset\` 构造时把 \`executor.definitions()\` 拍成 \`Toolset.specs\`，首轮模型调用用冻结表，后续重建才重新取 | \`reply/tools.py:2683\`、\`orchestrator.py:2646\` | 插件 \`preactivate\`（如 minigame \`agent_reply(preactivate=[...])\`）在**首轮拿不到新工具 schema**；首轮模型不调工具则整轮都看不到 |
| W47 | **\`skills__load_tools\` 的「本轮即可直接调用」以「已发生过一次工具批次」为前提** | \`reply/tools.py\`（dirty 只在工具批次后检查） | 同批次内后续调用能执行，但 schema 不在首次下发里 |
| W48 | **视觉规则是双向的**：native_vision=True 藏 image_parse/drawing/user_profile 三个工具；!=True 藏 \`image_context__*\`，且无配置可覆盖 | \`reply/tools.py:930-938\` | 切换原生视觉会静默改变模型可见工具集 |
| W49 | **会话工具 1 运行 + 1 排队；\`timeout_seconds=0\` 回落 300 而非「不超时」**，外层再加 10s；\`drain_sessions\` ≠ \`close\`（管线结束只等不取消） | \`reply/tools.py\` | 「设 0 表示不限时」是误解 |
| W50 | **计划模式 safe 列表里有死条目**：\`sandbox_manager__read_file\` 等已被 \`is_tool_authorized\` 去重拦掉 | \`reply/tools.py\` | 白名单条目不生效，排查时先看去重 |
| W51 | **\`raise_if_image_unsupported\` 无条件 \`await response.aread()\`**：流式路径会把整个 SSE 响应先读进内存 | \`packages/chat/src/neobot_chat/providers/vision.py:35\`、\`base.py:278\` | 「首个字节到达前才重试」的窗口几乎消失，\`started\` 标志不再代表首 token 延迟 |
| W52 | **原生视觉降级的 system notice 只在 \`_strip_images=True\` 时注入**，而主链路写死 False | \`providers/native_vision.py:137-154\`、\`bootstrap/_providers.py:69\` | 降级文案**对用户与模型都不可见**，只进日志 |
| W53 | **\`orchestrator.py:2972-2988\` 的「恢复工具 + 追加提示 + 重试一轮」在主链路不可达**：它要求 native_vision 由真变假，而 strip_images=False 时降级仍上报 True | \`reply/orchestrator.py:2972\` | 原生视觉降级后工具集不会自动恢复 |
| W54 | **anthropic provider 不传 check_status** → 走 \`raise_for_status\`，4xx/5xx 抛 httpx.HTTPStatusError 而非 ProviderError | \`providers/anthropic.py:163/253\` | 只按 ProviderError 分类会漏路径 |
| W55 | **面板模型连通性测试用独立 httpx + 固定 Bearer**，不走 provider 的 \`_build_headers\` | \`builtin_plugins/dashboard/model_probe.py:171\` | 对 Anthropic 官方端点必然报「鉴权失败」；面板测试 ≠ provider 可用性 |
| W56 | **图片位置限制只在两条序列化路径上**（deepseek/anthropic），OpenAI 的 \`_build_payload\` 零限制 | \`providers/openai*.py:87\` | 「同一段历史能不能发出去」随供应商变化 |
| W57 | **重试白名单不含 429**；且第 3 次尝试遇 5xx 时直接 raise → 最多 3 次请求而非 3 次重试 | \`packages/chat/src/neobot_chat/providers/base.py:15\` | 限流不会被重试；重试次数与直觉差 1 |
| W58 | **视觉与主模型不可用的返回文案不同**（\`_providers.py:63\` vs \`:89\`） | \`bootstrap/_providers.py\` | 排查「为什么没回复」要看是哪一条文案 |
| W59 | **\`app/src/neobot_app/credentials/\` 不是 API Key 仓库**：它是聊天动作口令（chat_flow 维度，五次未命中冷却 300s）；API Key 走 .env -> EnvConfig -> RegisteredModel.api_key | \`credentials/model.py:23\`、\`service.py:26\` | 排查「密钥无效」时不要进这个模块 |

> 维护约定：这张表随图一起维护。修掉一条就把对应行删掉，并在相关图的「易错点」里更新描述。

## 2. 为什么这么拆（拆分依据）

本轮按「代码规模 + 独立状态机 + 独立外部依赖」三条判据重新划分。
实测口径：`wc -l` 等价（`split(/\r?\n/).length - 1`，含空行），脚本 `scripts/flow/_audit.cjs` 可复跑。

```text
app/builtin_plugins         38 文件  15345 行   -> 11 小游戏 + 09/09b/09c 面板
app/skills                  42 文件  12904 行   -> 06 工具与技能
app/runtime                 32 文件  12831 行   -> 01/01b/02c/07/07b/13/16/20（按子系统拆）
pkg/modloader               37 文件  11843 行   -> 08 主图 + 08b 运行时
app/reply                   12 文件  10230 行   -> 03 主图 + 03b 工具面
pkg/adapter                 39 文件   8534 行   -> 02 适配器入站
pkg/chat                    36 文件   5207 行   -> 04 Agent 循环 + 05 provider
app/config                  18 文件   5112 行   -> 01b 配置系统
app/agent_tools             14 文件   4105 行   -> 06 工具与技能
app/browser                  5 文件   3938 行   -> 12 浏览器自动化
pkg/storage                 42 文件   3917 行   -> 22 存储与迁移
app/bootstrap               10 文件   3744 行   -> 01 启动装配
app/agents                   3 文件   3479 行   -> 04 Agent 循环
app/(root)                  12 文件   3462 行   -> 17 命令 + 18 画像 + 19 凭据 + 20 头像
app/drawing                  5 文件   2792 行   -> 15 绘画
app/message                  6 文件   2626 行   -> 02 入站 + 02c 事件管道
app/web_search               8 文件   2523 行   -> 10 联网搜索
app/statistics               7 文件   1620 行   -> 23 计费与统计
```

单文件 Top（拆分依据，行数含空行）：

```text
reply/orchestrator.py        4861  -> 03 主图 + 03b 工具面
dashboard/api.py             2787  -> 09b
reply/tools.py               2688  -> 03b
modloader/runtime.py         2382  -> 08 主图 + 08b
browser/agent_browser/mgr.py 2262  -> 12
runtime/archive_memory_s...  2153  -> 07 主图 + 07b
drawing/service.py           2017  -> 15
config/schemas/bot.py        1969  -> 01b
runtime/html_card.py         1832  -> 13
agents/self_heal.py          1819  -> 04 细节块
agents/problem_solver.py     1641  -> 04 细节块
dashboard/config_manager.py  1621  -> 09c
runtime/event_pipeline.py    1613  -> 02c
bootstrap/__init__.py        1577  -> 01 细节块
message/queue.py             1484  -> 02/02c 细节块
minigame/__init__.py         1350  -> 11
cli.py                       1069  -> 01 细节块
adapter/local/store.py       1066  -> 02 细节块（本地适配器）
```

判据：**单文件 >800 行或含独立状态机/外部依赖的，单独成图**；否则并入所属子系统图的折叠细节。
反例警戒：不要为了凑数量把「一个类的两个方法」拆成两张图 —— 图的价值在于「一眼看懂一条链路」。

## 5. 「随改随更新」的约定

1. 改动落在某张图 \`covers:\` 范围内，**必须**在同一 PR 内更新该图，并把
   \`verified_against\` 更新为当前提交短号（\`check_flow_diagrams.py --update --update-commit\`）。
2. 新增跨模块链路（新的回退/降级链）时**新增一张图**，不要塞进旧图。
3. 新增图必须登记到 §3 并写清 covers；删除图要同步删索引行。
4. CI 里 F1/F3 阻断、F2 用 \`--strict-drift\` 阻断；本地 pre-commit 只跑 F1/F3（毫秒级、零误报）。
