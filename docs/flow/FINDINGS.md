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

## 07b 档案自动总结与压缩

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| 07b-1 | \`flush_all\` 不只看 \`_retry_ready\`（W17），也**不看 \`is_standby\`、不看 \`provider is None\`** | \`archive_memory_summary.py:791/888/240\` | 每次关闭都给退避中的会话再叠一次 failures |
| 07b-2 | \`_tool_executor is None\` 时循环第 1 轮就 break → 0 成功 0 失败，却走 \`_commit_success\` 清账并打印「档案已更新」 | \`:493-494\` | 档案一字未动但报告成功 |
| 07b-3 | \`_is_tool_failure\` 对**工具返回文本**做子串匹配；熔断阈值 3 是**累计**而非日志所说的「连续」 | \`:2122-2125\` | 正文含 "Tool error" 等词即计失败 |
| 07b-4 | \`_commit_success\` 写回字典只有 count/messages → 成功一次即抹掉 \`failures/retry_after\` | \`:762\` | 冷却复位靠这个，但查不到失败历史 |
| 07b-5 | 手动/批量压缩**不查冷却也不查退避**（只抢单飞键），但手动失败会写进自动压缩的退避表 | \`:1271/1449/1073/1473\` | 手动操作会推迟后台自动重试 |
| 07b-6 | \`max_total_chars=0\` 时 \`list_over_limit\` 恒空 → **批量压缩入口永远 0 条** | \`archive_service.py:496\` | 「关闭治理后仍可手动压缩」只对单条路径成立 |
| 07b-7 | \`wait_pending_overflow_tasks\` 无生产调用点；\`close()\` 只关 provider | \`:1842\` | 在途溢出压缩任务无人等待 |
| 07b-8 | 三种时钟三种持久化：计数器退避（epoch/落库）、溢出退避（epoch/内存）、服务侧冷却（monotonic/内存） | \`archive_service.py:673/740\` | 重启后后两者清零，「重启立刻又压一次」是预期 |
| 07b-9 | \`_favorability_min/_max\` 读了不用；技能侧读的键名与 schema 不一致 | \`:127-128\`、\`skills/__init__.py:186\` | 工具侧钳制恒为默认 ±5/±1000，与提示词口径分叉 |
| 07b-10 | \`_format_counter_message\` 是死函数；messages 缓冲只留末 interval 条 | \`:2151/270\` | 长冷却 + 消息洪水会把最早的待总结消息永久挤出 |
| 07b-11 | 轮次用满也走 \`_commit_success\`，与「模型交卷」同一条清账路径 | \`:425\` | 未完成的总结被记为成功 |
| 07b-12 | 溢出压缩判定只看「成功写过 + 长度 ≤ target」，无事实保真校验 | \`:1070\` | 「写一半但达标」会被保留 |

## 09c 面板配置编辑

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| 09c-1 | **\`None\` 不是「清空」**：\`_merge_into_document\` 见 None 直接 continue → 保存返回 200 但文件不变 | \`config_manager.py:1143\` | 受影响字段：\`file_server.public_url\`、\`web_search.engines\`、\`web_search.engine_timeout_seconds\`（「恢复默认+保存」对它们无效） |
| 09c-2 | **面板不是最小 diff 写入器**：read 载荷带全部默认值，表单整份回传 | \`config_manager.py:1086\` | 3 键的 config.toml 保存一次变 432 键，并首次写入 \`version = "0.6.0"\` |
| 09c-3 | **TOML 模式遇未知键完全无法保存**（400「未知配置项」），而表单模式同文件保存成功并保留未知分区 | \`config_manager.py:454/497\` | 与 \`_diff_document\` 的卖点相反 |
| 09c-4 | 插件配置表单的 \`hot_reload\` 徽标**恒 True**（硬编码） | \`config_manager.py:374\` | dashboard 的 port / manage_plugins 也显示「热重载」 |
| 09c-5 | \`manage_plugins\`/\`allow_remote_manage\` 声明「需重启」，实际每请求读盘立即生效 | \`dashboard/hot_reload.py:65\` vs \`server.py:217\` | 远程关掉 allow_remote_manage 后下一个请求即 403 |
| 09c-6 | **插件页 20s 轮询静默丢弃未保存草稿**（\`setItems\` 换新数组触发依赖 effect 重跑） | \`Plugins.tsx:112/139\` | 用户输入 20s 内消失；该页还绕过 queryCore 重复请求 |
| 09c-7 | 插件配置 TOML 模式不跑 pydantic 校验 | \`api.py:1263\` | 非法值延迟到插件加载才暴露 |
| 09c-8 | 插件配置「表改标量」被静默忽略 | \`plugin_config.py:413\` | 用户以为改了 |
| 09c-9 | 插件配置保存响应里的 \`changes\` 前端不渲染 | \`api.py:1304\`、\`Plugins.tsx:274\` | 「需重启」明细看不到 |
| 09c-10 | 两个密钥占位符（本体 \`***\`、.env/插件 8 圆点）；\`is_sensitive_key\` 按末段键名误伤 | \`config_manager.py:905\`、\`security.py:55\` | \`max_output_tokens\` 被掩码并进 secrets_set |
| 09c-11 | .env 敏感键无法通过面板清空；保存即改 os.environ 但需 reload 才重建注册表 | \`config_manager.py:1365/1403\` | 改完密钥要重启才生效 |
| 09c-12 | SPLIT-MAP 里 config_manager.py 行数标注 1464 有误，实际 **1621** | 本文档 §2 | 已修正 |

## 08b 插件运行时（runtime 2382 行 / installer / hooks）

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| 08b-1 | **卸载备份嵌一层**：先 \`_backup\` 再 \`shutil.move(target, backup_path)\`，目标目录已存在 → 实际落在 \`<stamp>/<name>/\`；替换安装的备份却是平铺的 | \`installer.py:684-694/601\` | 两条路不一致，备份只增不减 |
| 08b-2 | \`reload_all()\` 生产零调用点（只有测试调用） | \`runtime.py:1234\` | 面板没有「全部重载」按钮 |
| 08b-3 | **卸载失败也注销配置消费者**：\`unload_plugin\` 在进名字锁前无条件 unregister，无回滚 | \`runtime.py:601-605\` | 之后保存该插件配置回落成「需重启」 |
| 08b-4 | \`_loaded_flags\` 不随卸载清理（只有 set_enabled(false) 会 pop） | \`:1806\` | 卸载后改 plugin.toml 的 hot_reload 不生效 |
| 08b-5 | **面板「更新」绕过 runtime**：直调 \`installer.update\` 再 \`control.reload\`，不写 plugin_state.json、不做依赖预检 | \`dashboard/api.py:1095\` | 与「安装」语义不对称 |
| 08b-6 | **同步钩子的 timeout 是假的**：\`to_thread\` 里的 handler 不会被 wait_for 取消 | \`hooks.py:280-295/428\` | 超时只算「未 handled」，线程仍跑完 |
| 08b-7 | **安装是先下载后判冲突**：保留字/同名/dry_run 三条拒绝路径都已消耗整包下载 + 解压 | \`installer.py:454\` | dry_run 也要下载 |
| 08b-8 | **两套版本比较结论相反**：\`1.0.0-rc1\` 在 installer 里更小、在 version.py 里相等；依赖侧「不能比较即放行」、更新侧「即已最新」 | \`installer.py:151\`、\`version.py\` | 同版本号两条链路结论不同 |
| 08b-9 | \`snapshot_plugins\` 每次全量 \`discover_all()\`（面板轮询/状态卡/更新检查都触发） | \`runtime.py:1299\` | 面板刷新是重操作 |
| 08b-10 | 门面失败语义不对称：\`set_enabled(true)\` 先落盘再装载，\`(false)\` 卸载失败不落盘 | \`runtime.py\` | 面板开关会「弹回去」 |

## 12 浏览器自动化（browser 3938 行 + lifecycle）

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| 12-1 | **\`agent.browser.data_dir\` 是死配置**；schema 里根本没有 headless/port 字段，getattr 永远回落默认 | \`config/schemas/bot.py:1312\`、\`bootstrap/_runtime.py:160\` | 面板改不了无头/端口 |
| 12-2 | **\`open_web\` 与运行时会话不是同一个 profile** | \`cli.py:330\` | 文档「登录一次后续无头复用」不成立 |
| 12-3 | **\`hold()\` 一族是死 API**（只有测试调用） | \`browser_lifecycle.py\` | 「保活 2 小时」不可达，600s 未 touch 必被回收 |
| 12-4 | \`BrowserSkill._check_lifecycle\` 调用**不存在的方法** \`should_auto_close()\` | \`skills/browser_skill.py:98\` | 谁接回去谁立刻 AttributeError |
| 12-5 | \`_MAX_RETRIES=2 / _RETRY_INTERVAL=1.0\` 零读取点；真实重试在 start()/导航里 | \`manager.py:37-38\` | fix(12) 的「导航最坏 3 次」与代码不符 |
| 12-6 | **\`_playwright_chromium_path\` 只认 \`chrome-win/\`**：本机实测拿到旧构建 r1148，win64 永远匹配不到；\`sorted()[-1]\` 是字典序 | \`manager.py\` | 自动检测可能选到旧浏览器 |
| 12-7 | **\`click\` 几乎永远 \`success=True\`**（无条件返回） | \`manager.py:649\` | 必须看 url + 重新 snapshot 才知是否生效 |
| 12-8 | \`network_route(abort=True)\` 可**永久挂起**（\`page.listen.wait()\` 无超时，且没进 to_thread）；\`mock_body\` 被完全忽略 | \`manager.py:1924\` | mock 响应体不存在 |
| 12-9 | **三个观测点是黑洞**：console logs / page errors / dialog status 读的 window 变量没有任何安装器 | \`manager.py\` | 恒为 ""/false |
| 12-10 | 标注截图 rect 恒空画不出编号；\`actions.shot()\` 把 JPEG 写进 .png 且零调用点 | \`manager.py:1545\` | 两个接口名不副实 |
| 12-11 | \`_ensure_page\` 的 \`except (PageDisconnectedError, Exception)\` 让任何探活异常都整机重启 | \`manager.py:350-356\` | 一次瞬时失败会让**所有聊天流**的标签页消失 |
| 12-12 | **标签页 index 两套口径**（list_tabs 过滤后下标 vs tab_ids 原始下标） | \`manager.py:1698-1750\` | 错位就关错页 |
| 12-13 | \`close()\` 注释与实现不符（Windows 上正常退出也会 taskkill /F）；只清 \`_tab_pages\` 不清 \`_tab_labels\`；state 回灌不对称 | \`manager.py\` | 「仅在残留时强杀」不成立 |
| 12-14 | **\`scripts/open_browser.bat/.sh\` 必然报错**：用了不存在的 \`--profile-dir\`（CLI 只有 \`--user-data-dir\`） | \`scripts/open_browser.*\` | 手动登录入口直接失败 |
| 12-15 | 文档说 \`browser_video\` 是「解析视频地址」，实现是 **GIF 录屏** | \`docs/04-功能文档/浏览器.md\` | 文档口径错 |

## 15 绘画子系统（drawing 2792 行）

| # | 事实 | 位置 | 影响 |
|---|---|---|---|
| 15-1 | 默认尺寸自相矛盾：代码 \`512x512\`，工具提示词写「未指定时默认 1024x1024」 | \`drawing/config.py:15\` vs \`skills/drawing_skill.py:102\` | 模型按提示词理解会错 |
| 15-2 | **绘画零计费**：目录内 0 处 usage/billing；生图裸 httpx 绕开 chat Provider；图库自动描述也不 \`record()\`；\`agent:image_parse\` 是合法模块名却无写入点 | \`drawing/\`、\`statistics/tracker.py:29\` | 生图成本不进账 |
| 15-3 | hub 存在时 \`poll_notification\` 与 \`_notification_queues\` 是死分支 | \`orchestrator.py:3818-3831\` | 排障要看 hub 队列 |
| 15-4 | 没有任务队列 / 任务级超时 / 取消接口，忙时直接回 busy | \`manager.py:99/219/621\` | 并发提交直接失败 |
| 15-5 | \`draw_max_retries\` 只重试**通知**不重试绘图 | \`manager.py:529-594\` | 绘图失败从不自动重提 |
| 15-6 | 宽限期被硬夹 \`sleep(min(grace, 3.0))\` | \`manager.py:262\` | 配置加大无效 |
| 15-7 | 清理循环懒启动：\`CreatorImageService.start()\` 无调用点 | \`service.py:155/327\` | 纯生图部署只有 close 时清 tmp |
| 15-8 | \`close()\` 清空 tmp 全部文件与记录 → 历史 \`tmp_xxx\` 引用失效 | \`service.py:148-153/340\` | 停机后历史图片打不开 |
| 15-9 | 占位描述被持久化并优先读回（同 14-1 的姊妹问题） | \`service.py:1408/58-68\` | 占位符变成正式描述 |
| 15-10 | 哈希去重会**真删文件**（保留 mtime 最新）；图库容量先 count 再写（可越过）；\`gallery_add\` 不查重 | \`service.py:264-313/1565/713\` | 同图可入库两份、并发越界 |
| 15-11 | 面板后台绘图静默为空：探测的 \`list_active\` 在 \`BackgroundDrawingManager\` 上不存在 | \`dashboard/api.py:788\` | 面板看不到后台任务 |
| 15-12 | SSRF 边界不一致：\`url:\` 前缀走公网校验，chat 图片段 URL 不校验 | \`service.py:1292-1317\` | 内网可达性差异 |
| 15-13 | SPLIT-MAP 行数过时：drawing/service.py 标注 1821，实测 **2017** | 本文档 §2 | 已修正 |

## 维护约定

1. 新增图时在对应小节追加；**不要**改早期 W 编号（外部文档/提交信息引用过）。
2. 修掉一条：把该行标记 \`✅ 已修（提交号）\`，保留原文便于回溯。
3. 图里的「易错点」应指向本文件的条目号，避免同一事实两处描述不一致。
