# QQ 官方机器人

NeoBot 支持两种 QQ 接入通道，并可以**同时运行**：

- **official**（新部署默认）：直接使用 QQ 官方机器人 API v2（AppID/AppSecret 或手机 QQ 扫码绑定），无需第三方框架。
- **OneBot**（老配置升级默认）：NapCat 等第三方框架通过反向 WebSocket 连入，功能最全。

`[adapter].mode` 取 `onebot` / `official` 时只跑一条通道；取 `dual` 时两条通道**同时运行**，对应两个不同的机器人 QQ 号，都可以正常收消息与回复。面板左侧「机器人通道」页（嵌在面板内容区，不覆盖工具栏）可以查看两条通道的连接/账号/官方绑定状态；选择会写入 `config.toml`，重启后保留；改模式后热重载即可增删通道，不需要软重启。

默认值语义（0.11.0 起）：**新部署默认 `official`**；从老版本升级上来的配置如果未显式配置过 `[adapter].mode`，迁移时补成 `onebot`，保持升级前行为。

## 快速开始

1. 启动 NeoBot，打开网页面板，左侧进入「机器人通道」。
2. 选择「双通道并行」（或按需只选其中一条）。
3. 官方卡片在未绑定时显示二维码：手机 QQ 扫码（或打开页面上的绑定 URL）完成绑定；凭据自动保存到 `data/qqbot/credentials.json`，之后启动不再扫码。控制台同时打印 ASCII 二维码与绑定 URL。
4. 也可以不用扫码：在 `config.toml` 的 `[adapter]` 填 `qq_appid` / `qq_client_secret`（或用环境变量 `NEOBOT_QQ_APPID` / `NEOBOT_QQ_SECRET`），保存后热重载即可。
5. OneBot 侧仍按原来的反向 WS 配置连接 NapCat；两条通道互不影响，任何一条断开不会停掉另一条。

## 双通道回复选路

- 每个聊天流默认使用 **OneBot** 回复：如果该会话只在 OneBot 出现，就用 OneBot；只在官方出现（官方 openid 会话），就用官方；两条通道都见过的会话优先 OneBot；未知会话（定时任务/主动推送）在双待下优先 OneBot，OneBot 未连接时用官方。
- 预留了按条指定通道的接口：
  - 模型工具 `send_reply` / `send_long_reply` 支持可选参数 `channel`，取 `auto`（默认，跟随事件来的通道）/ `onebot` / `official`；
  - 内部发送 `adapter.send(..., channel=...)` / `adapter.call_api(..., channel=...)` 同样可显式指定。
- 显式指定的通道未启用或未连接时，发送会**明确失败**（不会静默改投另一条），错误会回给模型/调用方。
- 一轮回复里的文字、Markdown 长图、图片会尽量走同一个通道（跟随该回复事件的通道，除非显式覆盖）。

## 官方 ID ↔ QQ 号 / 群号映射（人工）

官方 openid **就是**该通道的本地用户/群 ID（字符串主键）；它和真实 QQ 号/群号没有 API 可以互转，但可以**人工**建立映射，让系统把某个通道的用户/群当作已知 QQ 身份（用于展示、黑白名单与管理员判定）：

> 过渡说明：早期版本把 openid 派生为 13 位合成整数。现在官方通道直接使用 openid 字符串；旧合成号只通过 `data/qqbot/identities.json` 做**只读反查**（迁移/旧数据兼容），不再分配新合成号。

- **管理员命令**：
  - `/linkqq <QQ号>`（管理员级别权限）：把**发送者本人**映射到真实 QQ 号（5~11 位纯数字）；也支持 `/linkqq @用户 <QQ号>` 映射被 @ 的人。这条命令写入的映射是 **trusted** 的，可用于管理员/次级管理员权限判定。官方群@事件里的 `mentions` 会按正文里 @ 标记的真实顺序解析成 at 段，所以官方通道也能用 @ 形式，且「命令在前、@ 在后」不会打乱解析；群全量消息 content 里的 @机器人 标记在 openid 可识别时补成 bot at 段；群场景 member_openid 兜底命中时不补 at 段，但 `mentioned_self` 权威结论为被 @，命令/必回照常触发。
  - `/linkgroup <群号>`（管理员级别权限，群聊中使用）：把**当前群**映射到真实 QQ 群号（5~12 位纯数字），之后提示词/群黑白名单按真实群号识别。
- **Agent 工具**：`user_identity__link_user_qq(user_id, qq_number[, channel])`、`user_identity__link_group_number(group_id, group_number[, channel])`，以及对应的 get/unlink。Agent 写入的映射**只影响展示**，不参与权限判定（防止模型自己把用户映射成管理员）；管理员映射必须由人类管理员用命令建立。官方群@事件的 `mentions` 会解析为被 @ 用户；官方发送侧 @ 用户必须用 markdown 内嵌 `<qqbot-at-user id="openid" />`（适配器直接使用 openid，不再反查合成 ID；未知/格式不对的 openid 会替换成「@用户」纯文字并记 WARNING，不做文本降级）。
- 生效范围：提示词/用户资料/历史/通知/档案里，已映射的用户显示 `QQ:<真实号>（ID:<完整 openid>）`，群显示 `群号:<真实群号>（ID:<完整 group_openid>）`；**未映射时显示完整 openid 字符串（`ID:<openid>`，不截断）**。好友/群黑白名单、回复黑名单只认管理员命令写入的 trusted 映射；agent 写入的映射只影响展示，不参与访问控制。管理员权限只认 trusted 用户映射。映射只影响展示与身份解析，不改资料存储主键。
- **超级管理员**：`chat.admin_accounts` **默认留空，必须由部署者在配置/面板显式设置**，配置里可填**真实 QQ 号（数字）或官方 openid 字符串**（与 `sub_admin_accounts` 一致）；填 openid 时该通道的号主直接命中权限，无需再 `/linkqq`；填真实 QQ 号时，官方通道的号主需要先由管理员用 `/linkqq` 建立 trusted 映射，权限判定才能命中。`/linkqq` 写入超管 QQ 的映射只允许超管本人操作；`/unlinkqq`、`/unlinkgroup` 仅超级管理员可用。
- **解绑**：机器人通道页提供「解绑官方机器人」，删除本机扫码凭据并断开；配置里显式填写的 AppID/AppSecret 优先于扫码落盘的凭据，热重载不会因为配置留空而丢掉环境变量里的凭据。
- 存储：`data/user_qq_map.json`（原子写；新版 local ID 为文本——OneBot 数字串或官方 openid；旧格式的合成号 key 在迁移脚本里改写）。映射是人工维护的，系统**不会**根据昵称/头像等猜测，也不会自动建立跨通道会话关联。

## 身份判定与账号

- 判定只在**连接建立后**进行：对每条已连接通道调用 `get_version_info`，`app_name` 为 `NeoBot-QQOfficial` 即官方通道；未连接不判定、不猜测。双待下每条通道各有一份判定结果（通道、账号、昵称）。
- **双通道路由**：已通过 `/linkgroup` 建立群号映射、且 OneBot 与官方 bot 都在线的群，官方通道的群消息会去重交给 OneBot 处理；但明确 @ 官方机器人的消息不参与去重，仍按官方通道正常回复/触发命令。@ 判定由适配器按官方 API 契约给出权威结论 `mentioned_self`（见下一条），app 侧统一走 `is_addressed_to_bot`。回复默认发 OneBot，OneBot 连接不可用时自动回落到官方通道（Conversation ID 会按映射换成官方的 group_openid）。
- **双待模式下两个机器人 QQ 号都通过工具/API 获取**（`get_login_info` 等），**不读 `[bot].account`**：两个号不同，不能用一个配置值代表。消息自带 `self_id`（即对应通道的机器人号），自我发言判断、提示词、命令 @ 判定都按消息级账号处理。
- 单通道模式保留旧行为：`[bot].account = 0` 时连接后用 API 自动回填运行期配置；`[bot].official_mode` 仍可强制官方/非官方行为。
- 官方通道的官方行为：@ 判定按官方 API 契约——`GROUP_AT_MESSAGE_CREATE` 事件本身即表示用户在群里 @ 了机器人（`content` 已去掉 @ 前缀，不看 uin/at 段/mentions），按必回并触发群命令；`GROUP_MESSAGE_CREATE`（群全量消息）先按 `content` 里的 `<@!bot_openid>` / `<@bot_openid>` / `<qqbot-at-user id="bot_openid">`，或 `mentions`/`msg_elements` 中 `bot=true` 且 id 等于机器人 openid 判定。平台在群场景可能把 @机器人 记成群 `member_openid`（与 READY 的 `d.user.id` 不同，2026-11-12 线上实测），此时若 `mentions` 里 `bot=true` 的 id 出现在正文 @ 标记中，也会判为被 @（`source=bot_mention`）：机器人昵称（READY 的 `username` 或 `/users/@me` 的 `nickname`）已知时优先按昵称匹配，否则要求该标记在正文开头或为唯一候选，只记一次 WARNING。引用消息（`message_type=103`）的 `msg_elements` 是原消息，不作为 @ 来源。未命中且无兜底证据时权威结论是「未 @」，按普通群消息走意愿概率。机器人 openid 取自 READY 的 `d.user.id`；READY 缺 `user.id` 只记一次 WARNING（RESUMED 缺 user 不告警），全量消息仍可用昵称/mention 兜底。适配器把结论写入消息模型 `mentioned_self`（True/False；非官方为 None），映射时输出「官方消息 @ 判定」日志：`event_type` / `message_id` / `group_openid` / `sender_id` / `mentioned_self` / `source`（`event_type`｜`content`｜`mentions`｜`bot_mention`｜`none`）/ `bot_openid` / `self_id` / `content_at_ids` / `bot_mention_ids` / `bot_mention_names`。app 侧统一由 `is_addressed_to_bot` 消费，命令/@必回/已映射群去重/睡眠/提示词不再按通道名、uin/self_id、at qq=0 猜。提示词会注入官方机器人的能力边界；双待下只有官方通道的回复会注入该说明。
- **提示词口径**：官方通道的 system 提示词最前面追加「当前你是使用官方渠道搭建的QQ机器人,所以你看不到QQ号和群号,只看得到QQ ID和群ID,」；同一轮提示词（system 与上下文块）里的「QQ号」「群号」统一改称「QQ ID」「群 ID」。

## 热重载

| 改动 | 生效方式 |
|---|---|
| 面板切换模式 / 改 `[adapter].mode` + 重载 | 可同时运行的适配器门面原地增删通道；未变化的通道不重启，不软重启运行期 |
| `qq_appid` / `qq_client_secret` 等 | 热重载：只重启官方后端（重新取 token/连网关） |
| OneBot 反向 WS 地址/端口/token | 热重载：只重启 OneBot 后端，失败回滚 |
| `[bot].official_mode`、`[bot].account` | 热重载：身份服务按新配置重新判定/回填，队列同步 |
| 扫码绑定 / 重新扫码 / 连续登录失败自动重扫码 | 运行期完成；新凭据成功后才切换连接，失败保留旧连接 |

通道增删会断开被移除的那条连接；两条通道同时运行时，单条断开只影响它自己。发送期间若目标通道不可用会返回明确失败。

## 官方通道的能力与限制

- **连续登录失败自动重新扫码**：连续 3 次明确鉴权失败（获取 access token 返回 HTTP 401/403 或业务错误码 `10004/100007/100016`，获取网关地址返回 HTTP 401/403）后停止用旧凭据自动重连：日志明确提示「连续 3 次登录失败，需要重新扫码登录」，面板「机器人通道」页与终端自动给出新的扫码二维码。扫码落盘的凭据会被删除；AppID/AppSecret 来自配置/环境变量时不会静默删除，只提示检查配置或清空后扫码。绑定成功后用新凭据重连；成功连接（READY/RESUMED）后失败计数清零。瞬时故障不计入这 3 次：`429/5xx`、网络异常、token 接口限频错误码 `100001`、网关 `4004` token 失效（只自动刷新 token 重连）、普通网络断开、会话失效（`4006/4007/4009`）、限频（`4008`）与 `4914/4915`。
- **被动回复窗口**：群消息 5 分钟内最多回复 5 条，单聊 60 分钟内最多 4 条。超限/过期直接失败并写 info 日志，不再自动转主动消息；后台通知/定时任务等没有被动窗口的场景显式使用主动消息（`proactive`），失败同样只写日志/返回工具错误。
- **文本**：普通文本一律按纯文本发送（msg_type=0），不渲染 Markdown；需要 Markdown 时显式使用 `send_official_markdown`（官方 Markdown 卡片），需要 Markdown 图片时显式使用 `send_long_reply`（我们自己的图片渲染）。
- **发送侧 @ 用户**：必须通过 `send_official_markdown` 的官方 Markdown 卡片内嵌 `@` 发送（普通文本不支持 @）：卡片 `content` 里只放行 `<qqbot-at-user id="openid" />`（openid 直接使用；格式非法/无法解析时适配器替换成「@用户」纯文字并记 WARNING）；`@全体成员` 只能由 `at_everyone=true` 生成（仅群聊、每群每天 1 次、需机器人是群管理员），指令按钮只能由 `commands` 数组生成。正文里手写的 `<qqbot-at-everyone />`、`<qqbot-cmd-*/>`、`<@...>` 会被全角化成普通文字（工具回执带 `neutralized` 计数）；普通文本（msg_type=0）同样清理这些标签，不会真的 @ 全体或伪造按钮。
- **图片/语音**：按官方富媒体协议先上传拿 `file_info`，再以 `msg_type=7` + `media` 发送。NeoBot 的图片/语音/文件消息段会附带本地路径 `local_path`，官方通道优先读取本地文件走分片上传，不依赖本机文件服务器 URL（QQ 拉不到 127.0.0.1/局域网地址）；base64/data/file URL 走原路径；http(s) URL 只走官方 URL 转存，不做下载后分片回退。
- **工具可见性**：官方通道隐藏并拒绝 OneBot 专属工具/技能（拍一拍、QQ 表情回应/搜索、onebot 任意 API、好友管理/合并转发、历史消息查询、跨聊天历史查询、头像解析）。发图用 `emoji_numbers`/`send_long_reply`（Markdown 图片），发语音用 `speak`，需要 Markdown 卡片时用 `send_official_markdown`，群管理用 `official_group_manage`（仅官方真实接口）。
- **收消息**：文本、图片附件、语音 ASR/`voice_wav_url`、引用消息、`mentions` 里的被 @ 用户、`member_role`；群全量消息需要平台权限，默认只收 @ 消息；群成员加入/退出、入群申请、好友增删、机器人入群/退群、群消息接收开启/关闭、单聊主动消息开关、订阅授权状态会映射为 OneBot notice/request。
- **白名单接口**：官方有群信息/群成员/群黑名单/批量移除接口，但多数需要内邀白名单；无权限时返回明确 failed（11253），不再 `ok + 空数据`。没有好友列表/群列表；没有历史消息接口；`get_msg` 只查最近约 200 条本地缓存。
- **动作能力**：撤回群/单聊消息（2 分钟）、群禁言/解除禁言（最长 30 天）、群成员批量移除、入群申请审批、群信息/群成员/机器人群内状态已接入；群黑名单与成员管理白名单接口按官方 11253 返回明确失败。好友管理、合并转发、频道/子频道等官方无等价接口。失败只写日志并返回工具错误，不把错误文本发进聊天流。
- **openid 是官方通道的本地 ID**：官方只给用户/群的 openid（字符串），NeoBot 直接把它作为该通道的用户/群主键（会话键、存储、工具参数都是文本）。提示词/资料/历史里官方 ID 统一显示为**完整** `ID:<openid>`（不截断，便于复制核对）；提示词里仍沿用「QQ ID / 群 ID」的说法。旧版本派生的 13 位合成号只在迁移期经 `data/qqbot/identities.json` 反查（`decode`），不再分配新合成号；迁移完成后该文件只作只读备份。单聊 `user_openid` 与群聊 `member_openid` 是不同场景 ID，同一人可能对应两个 openid；官方默认不保证跨场景/跨 AppID 唯一，真正的跨场景统一只能靠人工 `/linkqq` 真实 QQ，或平台特批的 `union_openid`。
- **ID 类型与主键**：OneBot 通道的 user_id/group_id 仍是 int（协议原样），官方通道是 openid 字符串；插件公开 API、面板、内置插件数据库都接受两者（本地 ID 一律按文本持久化）。插件可以直接把 `IncomingEvent.user_id` 当 str/int 原值使用，禁止再 `int(openid)`。
- **同一个 QQ 群在两条通道下是两条会话**：OneBot 用真实群号，官方用 group_openid（字符串）。查过官方文档后确认没有可靠的关联方法：
  - 群信息接口 `GET /v2/groups/{group_openid}/info` 只返回 group_openid、群名称、简介、分类、标签、成员数，不返回 QQ 群号；
  - 官方「唯一身份机制」明确写「不同的 bot(AppID) 获取到的用户 openid、群 openid、频道 openid 均不相同」，同一个群在不同 AppID 下连 openid 都不同；
  - OpenAPI 里没有 group_openid → QQ 群号 / user_openid → QQ 号 的转换接口。

  因此只按人工 `/linkgroup` 映射关联合法群：已映射且两通道都在线时，官方群消息去重交给 OneBot（显式 @ 官方机器人的消息除外，仍按官方通道处理），回复默认优先 OneBot，OneBot 不可用回落官方；显式 `channel` 不被静默改投。
- **非目标**：QQ 频道/频道私信、Webhook 模式、流式消息、消息 `keyboard` 字段（模板/自定义键盘）、ARK、互动回调；Markdown 卡片只支持内嵌 `<qqbot-at-user>` 与由 `at_everyone`/`commands` 结构化参数生成的 `qqbot-at-everyone`/`qqbot-cmd-enter`/`qqbot-cmd-input` 标签，不支持手写这些标签。

## 从合成号迁移到 openid（旧数据）

- **为什么迁移**：合成号只是 13 位派生的显示视图，无法表达完整 openid；现在官方通道的主键就是 openid 字符串，插件与存储直接读原值。
- **数据位置**：`data/qqbot/identities.json`（openid ↔ 旧合成号，迁移期只读反查源）、`data/user_qq_map.json`（真实 QQ/群号 ↔ 本地 ID 的人工映射）、本体数据库 `data/neobot.db`（会话/消息/档案/定时任务/跨聊天记录里的本地 ID 都是文本，按 `identities.json` 改写旧值）。
- **自动迁移**：升级后首次启动时，`user_data`/`group_data`/`messages`/`memories`/`archive_memories`/`archive_snapshots`/`cross_chat_sessions`/`model_usage_records` 里的旧合成号会按 `identities.json` 自动改写成 openid（单个 SQLite 事务、可重复执行；`_build_storage` 在 schema 迁移前已写 `data/db_backup/` 快照；失败只记 WARNING 不阻塞启动，下次启动重试）；有迁移或跳过时汇总一条 INFO（迁移条数、跳过条数，有迁移时附各表条数），无迁移无跳过不记日志。
- **冲突处理**：若目标 openid 行已存在（典型：迁移后又从旧备份恢复），保留新旧两份数据、逐条只记 DEBUG 并跳过该条，不删除旧数据，需要人工核对合并；结束时的 INFO 汇总会带跳过条数（只要冲突还在，每次启动会出现这一条 INFO，不再逐条 WARNING 刷屏）；头像文件（`data/avatars/<旧合成号>.png`）不随迁移改名，下次出面会重新拉取并产生孤儿文件。
- **插件私有库**：`streaming_parser` 的 `group_id` 已从 BigInteger 迁移为 TEXT（插件库 Migration v2，旧数字群号自动 CAST）；`minigame` 的用户 ID 列加宽到 128 并接受 openid（Migration v3）；其它插件按自己的迁移版本随插件升级执行。
- **面板**：机器人/活跃用户页面显示**完整** openid（`ID:<openid>`）；openid 不是 QQ 号，页面不再为它请求 qlogo 头像，也不把它拼进 `nk=` 参数。
- **备份**：迁移前请同时备份 `data/neobot.db`、`data/qqbot/`、`data/user_qq_map.json` 和各插件数据目录（插件库在主数据库快照之外）。恢复旧备份后，旧合成号仍可经 `identities.json` 反查使用一个发布周期；迁移完成后不要立即删除 `identities.json`。

## 排查

- **官方 @ 判定排查**：搜索日志 `官方消息 @ 判定`，字段 `event_type` / `message_id` / `group_openid` / `sender_id` / `mentioned_self` / `source`（`event_type`｜`content`｜`mentions`｜`none`）/ `bot_openid` / `self_id` / `content_at_ids` / `bot_mention_ids`。`GROUP_AT_MESSAGE_CREATE` 恒为 `mentioned_self=true`；群全量消息未命中时先看 `content_at_ids`/`bot_mention_ids` 是否出现、以及 `bot_openid` 是否为空（READY/RESUMED 未给 `user.id` 时会告警）。
- **已连接但 @ 命令 / 必回不触发**：先确认进程确实已重启并运行修复后的代码（editable 安装时 `neobot --version` 可能仍显示旧安装元数据，不能只看版本号；发布包部署则需更新构建后重启）。再看上面日志的 `source`：若 `source=none` 且 `bot_openid` 为空，说明官方平台把这条 @ 当作群全量消息投递、且 READY/RESUMED 没给机器人 openid —— 此时全量消息无法判定 @，应让群使用 `GROUP_AT_MESSAGE_CREATE`（群 @ 消息事件）或补齐开放平台权限；若正文无任何 `@` 标记且 `mentions` 不含机器人，按契约无法判定，属平台事件能力限制。另：同一 `msg_id` 的 `GROUP_AT` 与 `GROUP_MESSAGE_CREATE` 双事件按「id → 是否被 @」记录去重，允许一次「未 @ → 被 @」升级：全量事件先到（未 @）时，后到的 @ 事件不会被误丢，命令与 @ 必回仍会触发；代价是同一句话可能进入上下文两次（已知取舍）。队列「最新消息为@你的内容」提示同样使用 `mentioned_self` 权威结论（uin 未解析、无可用 at 段时也能标出）。
- **日志出现「连续 3 次登录失败，需要重新扫码登录」**：官方通道已停止用旧凭据重连，面板与终端会自动出现新二维码——用手机 QQ 重新扫码即可；来自扫码的旧凭据已删除，来自配置/环境变量的 AppID/AppSecret 不会被改动，请检查配置或清空配置后重新扫码。
- **只有一条通道在线**：面板「机器人通道」页分别显示两条通道；官方未绑定会显示二维码，OneBot 未连接会显示监听地址。另一条离线不影响这条。
- **双待下账号显示「未获取（连接后自动读取）」**：该通道尚未连接或身份解析未完成；连接成功后会自动从 API 获取两个不同的机器人 QQ 号。
- **显式 `channel` 发送失败**：目标通道未启用/未连接，或该会话只存在于另一条通道；换默认 auto 或检查面板状态。
- **扫码后仍不连接**：看日志里的 token/网关错误与 close code：`4004` 刷新 token 重连、`4006/4007/4009` 清会话重连、`4008` 限频退避、`4914/4915` 机器人离线/封禁（停止重连）。
- **没收到群消息**：官方默认只推送 @ 机器人的群消息；群全量消息需要在开放平台申请权限。
- **图片/语音/文件发送失败**：看是否超过单文件上限、触发每日上传配额（错误码 40093002）或本地文件已被清理；日志会带中文原因。官方通道读本地文件分片上传，「上传官方富媒体失败：上传URL错误」通常是旧版把本机文件服务器 URL 交给 QQ 转存导致的，升级并重启后不再出现。

## 凭据与安全

- 官方 AppSecret 只写在 config.toml / `.env` / 扫码生成的 `data/qqbot/credentials.json`（0600、原子写）；**不会写进日志**。
- 扫码绑定的中间密钥只用于本次解密，不落盘。
- 不要把 `.env`、凭据文件或真实 openid 提交进仓库。
