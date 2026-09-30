# 写图核出的代码事实（按图归档）

> 这份清单是**写流程图时的副产品**：每张图都要求作者逐个 read/grep 核对代码，
> 于是「文档说的 / 直觉以为的」与「代码实际做的」之间的差异被逐条挖出来。
>
> * 早期 45 条（W1–W50）是按发现顺序编号的，仍在 [SPLIT-MAP.md](./SPLIT-MAP.md) §3；
> * 2026-09-30 之后的批次改成 **\`<图号>-<序号>\`** 命名，按图归档在本文件，便于「改这张图时顺手看一眼坑」。
> * 每条都给了 \`文件:行号\`；**修掉一条就把该条标记为 ✅ 并注明提交号**，不要直接删（作者可能还在引用）。

## 05b provider 与原生视觉降级

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| 05b-1 | \`raise_if_image_unsupported\` 对**任何**响应先 \`await response.aread()\` | \`packages/chat/src/neobot_chat/providers/vision.py:35\`、\`base.py:278\` | 流式 SSE 在逐行 yield 前被整体缓冲；「首字节前才重试」窗口消失，\`started\` 不再代表首 token 延迟 |
| 05b-2 | 降级 notice 只在 \`_strip_images=True\` 时注入 system，主链路写死 False | \`providers/native_vision.py:137\`、\`bootstrap/_providers.py:69\` | 降级文案**对用户与模型都不可见** |
| 05b-3 | \`orchestrator.py:2972\` 的「恢复工具 + 重试一轮」在主链路不可达（要求 native_vision 由真变假） | \`reply/orchestrator.py:2972\` | 降级后工具集不会自动恢复 |
| 05b-4 | anthropic 不传 \`check_status\` → 4xx/5xx 抛 \`httpx.HTTPStatusError\` 而非 \`ProviderError\` | \`providers/anthropic.py:163/253\` | 只按 ProviderError 分类会漏路径 |
| 05b-5 | 面板模型连通性测试用独立 httpx + 固定 Bearer，不走 provider 鉴权头 | \`dashboard/model_probe.py:171\` | 对 Anthropic 官方端点必报鉴权失败 |
| 05b-6 | 图片位置限制只在 deepseek/anthropic 两条序列化路径上 | \`providers/openai.py:87\` | 「同一段历史能不能发出去」随供应商变化 |
| 05b-7 | 重试白名单 \`{500,502,503,504}\`，**429 不重试**；第 3 次遇 5xx 直接 raise | \`providers/base.py:15\` | 最多 3 次请求而非 3 次重试 |

## 09b 面板接口面（api.py 2787 行）

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| 09b-1 | \`can_manage\` **两个口径**：配置/模型用 \`console.manage_plugins\`，档案/prompts/scheduled 用 \`_can_manage(request)\`（还看 loopback） | \`api.py:1415/1530/1626/1810\` vs \`:2162/2216/2233/1880/2536\` | 远程只读会话拿到 \`can_manage:true\`+\`secrets_hidden:true\` 自相矛盾响应：按钮可点、点下去 403 |
| 09b-2 | 三个 GET 也要 manage（archives 的 summarize 状态 / snapshots / snapshot） | \`api.py:2422/2475/2498\` | 只读会话能读档案全文却读不了压缩历史 |
| 09b-3 | \`GET /api/archives/over-limit\` 前端零调用（75 条路由唯一） | \`server.py:390\`、\`endpoints.ts:126\` | 改它不影响任何页面 |
| 09b-4 | \`GET /api/bots\` 是全仓唯一裸 JSON 数组响应 | \`api.py:366\` | 补 \`_json_ok\` 会静默打断概览页 |
| 09b-5 | \`/api/auth/status\` 的 \`authenticated\` 恒 false（硬编码、公开端点不注入会话） | \`api.py:200\` | 判登录态只能用 \`/api/auth/me\` |
| 09b-6 | 同一份 API 两套失败语义：用量接口异常回 200+\`available:false\`，\`/api/plugins\` 回 500 | \`api.py:444\` vs \`:898\` | 前端错误处理必须分类 |
| 09b-7 | \`config/billing/preview\` 不要 manage、也不检查 \`[billing].enabled\`，会按请求体脚本名加载执行 | \`api.py:594\`、\`billing.py:804/441\` | 名字受单段文件名校验，但「试算接口会跑代码」需知情 |
| 09b-8 | \`/api/admin/resume\` 与 \`/api/admin/reboot\` 是同一张皮（都转发 \`_soft_restart\`） | \`api.py:2624-2632\` | 日志/403 文案分不出用户点的是哪个 |
| 09b-9 | \`_int_arg\` 是纯钳制（\`?limit=99999\`→200、非数字→默认），无提示 | \`api.py:2694\` | 「传 500 只回 200」的答案 |
| 09b-10 | \`_read_json\` 25 个调用点四种待遇：20 显式 400 / 4 处不包 try / 1 处宽容 | \`api.py:1890/1917/1943/2546/2574\` | 400 的栈来源不同 |
| 09b-11 | 档案内部表 \`memory_counter\` 禁编辑、禁压缩，**但可删除** | \`api.py:2254/2395\` | 「内部表只读」在删除面前不成立 |
| 09b-12 | \`_schedule_power_action\` 返回的 \`power_state\` 是**动作前**旧值；\`_power_tasks\` 强引用必须保留 | \`api.py:2579/2598\` | 前端必须轮询；GC 掉任务会让待机/重启被静默腰斩 |
| 09b-13 | \`plugin_reload\` 是四个 \`/{name}/\` 端点里唯一不查存在性的 | \`api.py:1063\` | 错误文案来自运行时 |
| 09b-14 | \`_display_names\` TTL 到期是整表 clear（非逐键） | \`api.py:2005\` | 128 条流 5s 轮询会一次性重查 DB |
| 09b-15 | 读接口的权限面比想象宽：档案全文/提示词/历史/定时/日志/用量对**任何已登录会话**开放 | \`api.py\` 多处 | 只裁剪了 config source/raw、analysis prompts 正文与 .env |

## 13 渲染与卡片

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| 13-1 | \`html_card.set_screenshots\` / 模块级 \`_screenshots\` **生产零调用** → \`get_screenshots()\` 恒 None | \`runtime/html_card.py\`、\`commands/service.py:120-127\` | 「回落模块级默认」是死分支；真注入只有 bootstrap 与显式传参 |
| 13-2 | \`index.json["pages"]\` 只写不读，\`is_fresh\` 只看 fingerprint/renderer_version/size | \`runtime/help_cache.py:205-265\` | 页数变化不会触发重渲染 |
| 13-3 | \`StagedImage.expires_at\` 只写不读；TTL 300s 硬编码、配置层零命中；池只删引用不删磁盘文件 | \`image_pool.py:116\`、\`bootstrap/_runtime.py:60\` | 图片暂存池不按配置走，磁盘文件残留 |
| 13-4 | Markdown 转图模板带 2 个 cdnjs 外链 + 内联 \`<script>\`，与「自包含无外链」红线相反 | \`reply/markdown_image.py:34/40\` | 仓内唯一允许脚本的渲染路径 |
| 13-5 | \`convert\` 对浏览器渲染 **TimeoutError 不降级**，只有非超时异常才落 pillowmd | \`reply/markdown_image.py:220\` | 超时时直接抛给调用方 |
| 13-6 | \`_card_image_dir\` 未注入时回落 \`converter._output_dir\` → 卡片图与长文转图共目录、共用清理器 | \`commands/service.py:335\` | 清理策略互相影响 |
| 13-7 | \`render_card_image\` 四档尝试共用单个 20s timeout，预渲染路径无外层预算（单张最坏 80s） | \`html_card.py:1763\`、\`builtin.py:391\` | full_page 两档在超时场景几乎走不到 |

## 14 表情包 / 图像解析 / 本地视觉

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| 14-1 | **解析失败被永久固化**：\`[解析失败]\`/\`[未配置视觉模型]\` 写进 .txt 侧文件，非空即权威 | \`emoji/service.py:562-626\` | 没配视觉模型时批量导入的表情包永不重试 |
| 14-2 | **随机表情包用 \`randint(1, emoji_count)\` 会打空**：编号只增不减、删除留洞 → 命中空洞静默不发 | \`emoji/service.py:716-815\`、\`orchestrator.py:1946\` | 「偶尔这次没发表情包」的根因之一 |
| 14-3 | **\`group_agent_silent_timeout_seconds = 0\` 会让等图变成无限等** | \`image/parser.py:111\`、\`orchestrator.py:4333\` | 群聊「不等图」不能填 0 |
| 14-4 | onnxruntime 不可用时启动期**跳过模型库扫描** → \`available\` 恒 False、工具永不出现，\`neobot init\` 也无效 | \`bootstrap/_services.py:339-350\` | 削弱「装 ultralytics + 放模型即可用」的引导 |
| 14-5 | 摘要阈值（\`[library].default_conf\`）与实际过滤阈值（条目 \`conf\`）不是同一来源 | \`emoji/service.py:231/318\` | 提示百分比是错的 |
| 14-6 | \`emoji_add\` 的 \`image_source="skill_import"\` 被丢（无描述时解析回写硬编码「部署者提供」） | \`emoji/service.py:338/621\` | 来源字段不可信 |
| 14-7 | 两套哈希口径：表情包用 sha256(原始字节)，入站图片描述缓存用 md5(放大后字节) | \`image/parser.py:159\` | 同一张图两条链路各存一份 |
| 14-8 | \`parse_image\` 工具**不吃图片描述缓存**，与自动解析各付一次视觉调用 | \`skills/image_parse_skill.py\` | 重复计费与重复延迟 |
| 14-9 | \`parse_image.timeout_seconds\`（默认 300s / 上限 1800s）被当作**下载**超时 | \`skills/image_parse_skill.py:809/887\` | 单张图下载可阻塞 5 分钟 |
| 14-10 | 读接口有副作用：\`emoji_count/get_entry/list_entries/search_entries\` 先同步 sha256 新文件 | \`emoji/service.py:900\` | 热路径反复读会抖磁盘 |
| 14-11 | \`VisionDetectService.inspect_image\` 是**零调用点死接口** | \`vision_detect/service.py:427\` | 本地检测不参与自动图片解析 |
| 14-12 | 图片大小上限只在 image_context 生效（10 MiB），另两处构造不传 \`max_bytes\` | \`image_context_skill.py:179\` vs \`vision_detect_skill.py:35\` | 限制形同虚设 |
| 14-13 | 表情包去重保留 **mtime 更旧**的一份；\`increment_usage\` 是 UPDATE，记录不存在时静默无效 | \`emoji/service.py:526\`、\`repositories/emoji.py:186\` | use_count 恒 0、删的不是新文件 |
| 14-14 | \`neobot init\` 默认 \`force=False\`：已删文件的索引条目只计数不移除 | \`cli.py:965\`、\`model_library.py:313\` | 幽灵条目要 \`--force\` 才清 |

## 维护约定

1. 新增图时在对应小节追加；**不要**改早期 W 编号（外部文档/提交信息引用过）。
2. 修掉一条：把该行标记 \`✅ 已修（提交号）\`，保留原文便于回溯。
3. 图里的「易错点」应指向本文件的条目号，避免同一事实两处描述不一致。
