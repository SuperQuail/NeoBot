# 官方机器人 Markdown 卡片工具设计

> 状态：设计稿（工具已落地；术语：本工具发送的是「官方 Markdown 卡片」，不是把 Markdown 渲染成图片的「Markdown 图片」（send_long_reply））　分支：`fix/official-review`　范围：官方 QQ 机器人通道（`official`），不含频道/子频道。
> 参考：官方 [发送群消息](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_groups_group_openid_messages.post.html)、
> [发送单聊消息](https://bot.q.qq.com/wiki/develop/api-v2/autogen/api/v2_users_user_openid_messages.post.html)、
> [文本交互](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/trans/text-chain.html)、
> [Markdown 消息](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/type/markdown.html)、
> [富媒体](https://bot.q.qq.com/wiki/develop/api-v2/server-inter/message/rich-media.html)、
> [群@事件](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/group_at_message_create.html)、
> [群全量事件](https://bot.q.qq.com/wiki/develop/api-v2/autogen/event/group_message_create.html)。

## 1. 背景与目标

官方 v2 的文本消息（`msg_type=0`）只有纯文本；要标题、列表、引用、链接、内嵌 @、指令按钮，都只能发
**Markdown 消息**（`msg_type=2`）。2026-04-23 起，单聊与群聊的自定义 Markdown 已对所有机器人开放，
不需要申请模板；频道场景仍需内邀（不在本设计范围）。

现在官方通道上「文字看起来能用 Markdown」，但只是适配器把普通文本按 `qq_markdown=true` 装进
`markdown.content`（[`official/send.py`](../../packages/adapter/src/neobot_adapter/official/send.py) `_send_text`），
并不是一个可编排的发送能力：

1. `send_reply` 先按句子切分（`process_reply_text`，默认上限 300 字/12 句），多行结构被拆成多条消息，
   标题、列表、引用全被打散；超限还会触发「转图片」或默认兜底模板。
2. @ 只能通过 `mention_qqs` 放在正文**开头**（`ReplySender.build_reply_segments`），无法内嵌；
   `@全体成员` 无参数可达（`mention_qqs` 是整数列表，`all` 只能内部传）。
3. 指令按钮（`qqbot-cmd-enter`/`qqbot-cmd-input`）完全缺失。
4. 普通文本里出现的 `<qqbot-at-everyone />` 等标签会被原样装进 Markdown 发出去——见 §9 的现存缺陷。

目标：新增一个**官方通道专用**的回复工具 `send_official_markdown`，外加一份按需读取的提示词 skill，
让模型能可靠地发一条原生 Markdown 消息；不改变现有 `send_reply`/`send_long_reply` 的语义。

## 2. 官方协议事实（设计依据）

| 事实 | 结论 | 影响 |
|---|---|---|
| `msg_type=2` 时只认 `markdown.content`；`content`/`ark` 必须为空 | 一条消息只能二选一 | 新增消息段，不能靠「文本 + 开关」拼装 |
| `markdown.template_id`/`custom_template_id` 已废弃 | 只用 `content` | 不做模板消息 |
| 2026-04-23 起自定义 Markdown 单聊/群聊全量开放 | 无需权限申请 | 不设计「无权限」的用户流程 |
| 群聊 @ 用户：`<qqbot-at-user id="member_openid" />`，**仅 Markdown 消息** | 文本消息发不了 @ | @ 必须走 Markdown |
| @全体：`<qqbot-at-everyone />`，**需要机器人是群管理员，每群每自然日 1 次** | 稀缺资源 | 必须显式开关 + 本地节流 |
| 回车指令 `<qqbot-cmd-enter text="..." />`：仅 Markdown，**群聊不支持** | 群聊只能发参数指令 | 按会话类型校验 |
| 参数指令 `<qqbot-cmd-input text="..." show="..." reference="false" />`：`text` 必填，`text`/`show` 各 ≤100 字符，值需 urlencode | 不能让模型手写编码 | 工具层统一编码 |
| 官方 Markdown 格式清单：标题、加粗/斜体/删除线/下划线、链接、图片、有序/无序/嵌套列表、块引用、分割线、多行 | **没有表格、没有代码块** | 表格/代码走 `send_long_reply`（转图片） |
| 被动回复：群 5 分钟/每条消息 5 次；单聊 60 分钟/4 次；`msg_id + msg_seq` 相同会失败（适配器实际按 4/3 留一次余量） | 每发一条 Markdown 消耗一次 | 工具不拆多发，并提示额度 |
| 官方未公布 Markdown 长度上限；超限报 `40054007` | 沿用适配器 4000 字符安全线 | 超限在工具层拒绝 |
| 报错与降级相关码：`40034008`/`40034009`/`40034011`/`40034124`/`40034127`/`304036`（Markdown 相关）、`40054007`（超长）、`40054010`（不允许 URL）、`40034128`/`304103`（被动超限/过期）、`40034100`（主动频控）、`40054005`（去重） | 判定要按错误码，不只按文案 | 扩展 `_is_markdown_forbidden` |

> 私聊的 @ 能力：官方能力的表格只列了「群聊」「文字子频道」，单聊没有 @ 用户/全体。当前适配器在私聊把 @ 段
> 降级成 `@昵称` 文本（`_mention_tag`），本工具沿用同一口径：单聊拒绝 @ 标签，让模型直接写昵称。

## 3. 现状差距（代码位点）

| 位置 | 现状 | 本设计是否改 |
|---|---|---|
| `reply/tool_parts/reply_tools.py:384` `send_reply` | 文本按句切分；官方通道 @ 只能置前 | 不改 |
| `reply/tool_parts/long_reply_tools.py` `send_long_reply` | Markdown → 图片 | 不改 |
| `reply/sender.py:800` `build_reply_segments` | `at` 段固定在正文前 | 不改 |
| `official/send.py:445` `_prepare` | 只认 text/at/reply/media | **加 markdown 段** |
| `official/send.py:335` `_send_text` | 有 `force_markdown` 分支，可复用 | 复用 |
| `official/send.py:503` `_split_text` | 4000 字硬切（会切碎 Markdown） | markdown 路径不切 |
| `official/send.py:523` `_is_markdown_forbidden` | 只按文案含 markdown + 「不允许/forbidden」判定 | **扩错误码** |
| `official/send.py:488` `_strip_mention_tags` | 降级只去 @ 标签，不去指令标签 | **扩展** |
| `reply/output_guard.py` `clean_text` | 不处理 `<qqbot-*>` | 不改（在适配器兜底） |

## 4. 工具设计

### 4.1 名称与可见性

- 名称：`send_official_markdown`。不用 `send_markdown`：与「Markdown 转图片」的 `send_long_reply` 太像，
  模型会混用；显式带 `official` 也能在工具列表里自解释。
- 只在 `_official_platform=True` **且**绑定了 handler 时定义（`_define_markdown_tool`）。OneBot 事件、单通道
  OneBot 部署都看不到它；双待下 OneBot 事件看不到、官方事件看得到。
- 加入 `_SKILL_GUARD_BASE_TOOLS`（技能 `allowed-tools` 限制轮次仍可发）与 `BASIC_REPLY_TOOLS`（回执按控制流压缩），
  与 `send_reply` 同等待遇。

### 4.2 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `content` | string | 是 | Markdown 正文。允许内嵌 `<qqbot-at-user id="合成ID" />`；其余 `<qqbot-*` 标签会被转义成普通文字。上限 4000 字符 |
| `reply_to_number` | integer | 否 | 引用回复的消息编号（行首编号），语义与 `send_reply` 相同；不存在直接报错 |
| `at_everyone` | boolean | 否 | 仅群聊；为 true 时在正文最前面插入 `<qqbot-at-everyone />` 和一个空格，每群每天最多 1 次（本地节流 + 官方兜底） |
| `commands` | array | 否 | 指令按钮，追加在正文末尾。元素 `{text, show?, reference?, enter?}` |

`commands` 元素：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | string | 是 | 点击后发送/插入的文本，≤100 字符；工具负责 urlencode |
| `show` | string | 否 | 按钮上显示的文本，≤100 字符；缺省取 `text` |
| `enter` | boolean | 否 | true 生成 `qqbot-cmd-enter`（点一下直接发送）；**仅单聊**，群聊报错 |
| `reference` | boolean | 否 | 仅参数指令；插入输入框时是否带引用，默认 false |

为什么按钮走结构化参数而不是让模型写标签：需要 urlencode、要卡 100 字符、要按会话类型禁 `enter`，
也让「用户文本被抄进 content 时附带一个假按钮」变成不可能。@ 之所以允许内嵌写标签，是因为工具必须知道
@ 的位置（用户 ID 又只以合成 ID 出现在模型上下文里），而 @全体单独用参数把住。

### 4.3 校验（失败即返回 JSON，不发送）

| 规则 | 错误回执 |
|---|---|
| 非官方通道 | `错误：send_official_markdown 仅官方通道可用` |
| `content` 清洗后为空 | `错误：Markdown 内容为空` |
| `len(content) > 4000` | `错误：Markdown 内容 N 字，超过单条上限 4000；请精简后重发，或改用 send_long_reply` |
| 单聊带 `<qqbot-at-user` 或 `at_everyone` | `错误：单聊不支持 @；请直接写昵称` |
| 群聊 `at_everyone` 当天已用 | `错误：本群今天的 @全体成员已用掉（官方限制每群每天 1 次）` |
| `commands` 非数组/元素非对象 | `错误：commands 必须是对象数组` |
| `text`/`show` 超 100 字符或为空 | `错误：指令按钮文本必须在 1~100 字符内` |
| 群聊 `enter=true` | `错误：群聊不支持回车指令；请去掉 enter 或改用 send_reply` |
| `reply_to_number` 不存在 | 同 `send_reply`：`错误：消息编号 N 不存在于当前上下文中` |

校验前先跑 `clean_text`（去系统标注/思考标签），清洗后为空按空内容处理；不做句子切分。

### 4.4 回执

成功：`{"ok": true, "sent_count": 1, "summary": "已发送 1 条 Markdown 消息"}`；
被降级时补 `"degraded": "markdown->text"`（需要适配器把降级信息放进 `SendMsgResponse.message`，见 §7.2）。
失败：`{"ok": false, "error": "..."}`，与 `send_long_reply` 的既有风格一致。

## 5. 何时用 / 不用，与现有两个出口的关系

| 场景 | 用哪个 | 原因 |
|---|---|---|
| 日常聊天、一两句话 | `send_reply` | 有分句节奏、AI 检查、图片与表情入口；Markdown 对短句没有收益 |
| 要标题/列表/引用/链接/加粗，或 @ 出现在正文中间，或要指令按钮 | **`send_official_markdown`** | 原生 Markdown，不切分、不转图 |
| 要 @全体成员 | **`send_official_markdown` + `at_everyone=true`** | 唯一入口；仅群聊、每天 1 次 |
| 要表格、代码块、超长排版（>4000 或官方不支持的语法） | `send_long_reply` | 官方 Markdown 不支持表格/代码块，转图片保真 |
| 发图片/表情包 | `send_reply.emoji_numbers` / `send_long_reply` | 本工具只发一条 Markdown 消息，不夹带媒体 |
| 需要多条消息、分批说 | `send_reply` 的 `segments` | 被动回复额度按条消耗，Markdown 不做拆发 |

关系约定：

- 三者都是「对外发言出口」的平级关系，**都不结束本轮**；只有 `cancel` 结束。
- 每个 `send_official_markdown` 调用 = 一次发送 = 消耗一个被动回复额度；工具描述里明确「一轮最多 1 条」，
  避免模型把长文反复改格式重发。
- 写入自身历史时保存**去标签的可读版**（`<qqbot-at-user .../>` → `@用户`，`<qqbot-at-everyone />` → `@全体成员`，
  指令标签 → `[按钮：文本]`），否则下一轮上下文会教模型在普通 `send_reply` 里手写标签。

## 6. 示例

### 6.1 群聊：内嵌 @ + 列表 + 参数指令

工具调用：

```json
{
  "content": "## 今日签到\n\n<qqbot-at-user id=\"9000000000123\" /> 你今天还没签到。\n\n- 连续签到 **7** 天\n- 本次积分 **+50**",
  "commands": [{"text": "/签到", "show": "去签到"}]
}
```

实际请求体（`POST /v2/groups/{group_openid}/messages`）：

```json
{
  "msg_type": 2,
  "markdown": {
    "content": "## 今日签到\n\n<qqbot-at-user id=\"7A3B9C1D5E2F4A6B8C0D1E3F5A7B9C2D\" /> 你今天还没签到。\n\n- 连续签到 **7** 天\n- 本次积分 **+50**\n\n<qqbot-cmd-input text=\"%2F%E7%AD%BE%E5%88%B0\" show=\"%E5%8E%BB%E7%AD%BE%E5%88%B0\" reference=\"false\" />"
  },
  "msg_id": "ROBOT1.0_xxxxxxxx",
  "msg_seq": 3
}
```

要点：合成 ID `9000000000123` 由适配器反查成 `member_openid`；`/签到` 被工具编码成 `%2F%E7%AD%BE%E5%88%B0`。

### 6.2 群聊：@全体成员

```json
{
  "content": "今晚 **20:00** 群活动开始，记得来。",
  "at_everyone": true
}
```

生成 `<qqbot-at-everyone /> 今晚 **20:00** …`。机器人不是管理员、或当天已发过时，官方会拒绝（无权限/频控类错误，
不是专门的错误码）；工具本地也先拦一次，回执要求模型改用普通提醒。

### 6.3 单聊：回车指令

```json
{
  "content": "点下面的按钮直接发送：",
  "commands": [{"text": "/今日运势", "show": "看运势", "enter": true}]
}
```

### 6.4 拒绝与转义

- `content` 里出现用户原话 `<qqbot-at-everyone />`：工具把标签首尾的 `<>` 换成全角 `＜＞`，客户端显示为普通文字，
  `neutralized` 计数 +1；不会真的 @全体。
- 群聊 `commands: [{"text": "/x", "enter": true}]`：直接报错，不发送。
- 4220 字的内容：报错并提示改用 `send_long_reply`。

## 7. 发送链路与最小改动

### 7.1 消息段契约

在 OneBot 消息段数组里新增一种仅内部使用的段：

```python
{"type": "markdown", "data": {"content": "<最终 Markdown 文本>"}}
```

规则：**markdown 段不能与 text/at 段混用**（`_prepare` 抛 `ValueError`），可与 `reply` 段同用（用于引用）。
这样「一条消息一个 body」的官方语义在适配器里显式化，而不是靠拼接猜测。

### 7.2 改动清单

| 文件 | 改动 |
|---|---|
| `app/src/neobot_app/reply/tool_parts/markdown_tools.py`（新） | `_MarkdownToolsMixin`：`_define_markdown_tool` + `_execute_send_official_markdown` + 校验/编码/转义纯函数 |
| `reply/tool_parts/core.py` | 构造参数 `official_markdown_handler`；`definitions()` 调 `_define_markdown_tool` |
| `reply/tool_parts/dispatch.py` | `execute` 增加 `send_official_markdown` 路由 |
| `reply/tool_parts/common.py` | 两个白名单集加入新工具名 |
| `reply/tools.py` | `build_reply_toolset` 透传 handler |
| `reply/orchestrator_parts/agent_toolset.py` | 绑定 `_agent_send_markdown_handler` |
| `reply/orchestrator_parts/agent_handlers.py` | 新 handler：组装 `[reply?, markdown]` → `_send_with_timeout(..., channel="official")` → `record_self_sent_text` + `state.reply_sent=True` |
| `packages/adapter/src/neobot_adapter/official/send.py` | `_prepare` 识别 markdown 段；`send` 走 `_send_markdown`；内嵌 @ 反查；错误码降级；普通文本路径转义官方标签 |
| `app/data/skills/qq-official-markdown/SKILL.md`（新） | 提示词 skill，见 §10 |
| `app/src/neobot_app/prompt/blocks.py` | `_official_platform_note` 追加一句「需要排版/内嵌 @/按钮用 send_official_markdown，语法见技能 qq-official-markdown」 |
| `docs/04-功能文档/QQ官方机器人.md` | 实现后补一节工具说明 |

### 7.3 适配器细节

```python
# send(): 有 markdown 段时
if markdown is not None:
    if len(markdown) > _TEXT_LIMIT:
        return _failed(f"Markdown 消息 {len(markdown)} 字，超过单条上限 {_TEXT_LIMIT}")
    markdown = self._render_embedded_mentions(markdown, kind)   # 合成 ID -> openid
    try:
        official_id = await self._send_text(kind, openid, conversation.id, markdown,
                                           reply_id, timeout, force_markdown=True, split=False)
    except (OfficialApiError, OfficialAuthError) as exc:
        ...  # 见降级链
```

- `_render_embedded_mentions`：把 `<qqbot-at-user id="(\d+)" />` 里的合成 ID 用 `self._identity.openid(int(id), "user")`
  换成 openid；查不到时替换成 `@用户` 文本并记 WARNING（不让坏 ID 原样上线）。私聊里全部替换成 `@用户`。
- `at_everyone` 由工具生成标签，适配器原样透传（它无法区分合法来源，节流放在工具层）。
- `_send_text` 增加 `split: bool = True`；markdown 路径传 False（4000 已在工具/适配器入口卡住）。
- 降级：`_is_markdown_forbidden` 增加错误码集合 `{304036, 40034008, 40034009, 40034011, 40034124, 40034127}`；
  降级时用 `_strip_official_tags`（@ 标签 + 指令标签 + 全角转义）后再以 `msg_type=0` 重发一次，并让
  `SendMsgResponse.message` 带上降级说明，工具回执据此标记 `degraded`。
- 普通文本路径（`_prepare` 处理 `text` 段时）对 `<qqbot-*` 做转义——这是 §9 现存缺陷的修复点。

## 8. 失败与降级链

| 触发 | 行为 | 模型看到 |
|---|---|---|
| 参数校验失败 | 不发送 | JSON error，可直接修正重试 |
| Markdown 被官方拒绝（错误码/文案） | 去标签后 `msg_type=0` 重发一次，记 WARNING | `ok=true, degraded="markdown->text"` |
| `40054007` 长度超限 | 不重发（无法安全切分） | error：改用 `send_long_reply` |
| `40054010` 不允许发送 URL | 不自动删链接（会改变语义），返回明确错误 | error：去掉链接或改用 `send_long_reply` |
| 被动额度用尽/过期（`40034128`/`304103`） | 适配器既有行为：转主动推送，每会话告警一次 | `ok`（额度信息不保证可见） |
| 主动推送被拒/机器人离线 | 返回 failed | error：本轮不要重试，别再发 |
| 内嵌 @ 的合成 ID 查不到 | 替换成 `@用户` | `ok`，日志 WARNING |
| 清洗后为空 | 不发送 | error，同 `send_reply` 的空内容提示 |

原则：**能在工具层拦的绝不发出去**；发送侧的降级只会「降级格式」，不会「改内容语义」。

## 9. 注入防护

威胁模型：`content` 会混入用户原话、网页抓取、聊天记录引用；攻击者可以让模型「复述」一段带官方标签的文本。

- **R1 标签白名单**：`content` 只放行 `<qqbot-at-user id="13位合成ID（9 开头）" />`；`<qqbot-at-everyone />`、
  `<qqbot-cmd-enter ...>`、`<qqbot-cmd-input ...>`、`<@...>`、`@everyone` 一律转义为全角文字
  （`＜qqbot-at-everyone /＞`）。「把这段话原样发出去」不再能触发 @全体或伪造按钮。
- **R2 @全体单独开关**：只能由 `at_everyone=true` 生成，仅群聊；本地按 `(群ID, 自然日)` 记录，每天 1 次；
  官方限制仍是最终权威（本地记录重启即清空，属已知限制）。
- **R3 按钮只来自结构化参数**：`commands` 的值统一 `quote(value, safe="")`；编码前先 `unquote`，
  保证「已编码的输入」不会被二次编码破坏（对 `%` 也收敛）。
- **R4 链接与图床**：`![...](url)`、`[text](url)` 只允许 `http(s)`；拒绝 `javascript:`/`data:`/
  `file:`，以及回环/内网/链路本地地址（`127.0.0.1`、`10.*`、`192.168.*`、`172.16-31.*`、`169.254.*`、
  `*.local`）。官方本来就要求公网可访问，内网 URL 只会泄漏拓扑。命中直接报错，不静默删。
- **R5 不做 HTML**：官方 Markdown 不解析 HTML，除白名单外的 `<...>` 一律转义，避免出现「看起来像标签」的残留。
- **R6 日志脱敏**：日志只记长度、标签计数、错误码，不记 `content` 全文（可能含密钥/隐私）。
- **R7 发送前清洗**：沿用 `clean_text`，防止把历史里的 `[msg_id=...]`、`编号: 名字: ` 抄进 Markdown。
- **R8 频控**：每次回复管线（一个 `ReplyToolExecutor` 实例）最多 1 次 `send_official_markdown`，避免被动额度被格式重试吃光。

### 9.1 顺带修复的现存缺陷

当前 `qq_markdown=true` 时，`send_reply` 的普通文本会原样进 `markdown.content`：
用户说「把 `<qqbot-at-everyone />` 发一遍」，模型复述 → 真的 @全体（若机器人是管理员）。
修复：`_prepare` 处理 `text` 段时调用 `_neutralize_official_tags`（R1 同一函数），
`qq_markdown` 开或关都生效。这是纯收紧，不改变任何正常文本（正常文本里不会有这些标签）。

## 10. 提示词 skill

位置：`app/data/skills/qq-official-markdown/SKILL.md`（`SkillRegistry(root=DATA_DIR/"skills").discover()` 自动发现，
按 `keywords` 命中后只注入 name+description，模型再用 `skills__read_manifest` 读全文——与本仓库
`balance-query` 同一模式，不占常驻 token）。

```markdown
---
name: qq-official-markdown
description: QQ 官方机器人 Markdown 消息的写法与限制（内嵌 @、@全体、指令按钮、格式与额度）
keywords: markdown 排版 表格 代码块 按钮 指令 @全体 富文本 官方
---
# QQ 官方机器人 Markdown

何时用 send_official_markdown：
- 需要标题/列表/引用/链接/加粗，或 @ 要出现在正文中间；
- 需要 @全体成员（仅群聊，每群每天 1 次）；
- 需要指令按钮。

何时不用：
- 日常短回复 → send_reply；
- 表格、代码块、超过 4000 字 → send_long_reply（转图片）；
- 只想 @ 一个人且 @ 在开头 → send_reply 的 mention_qqs 更省事。

content 写法：
- 支持：## 标题、**加粗**、_斜体_、~~删除线~~、> 引用、- 列表、1. 有序、[文字](https://...)、*** 分割线；
- 不支持：表格、代码块、HTML —— 需要就改 send_long_reply；
- @ 用户：<qqbot-at-user id="群成员列表里的 ID 数字" />，ID 就是聊天里显示的 ID，不要编；
- 不要手写 <qqbot-cmd-*> 或 <qqbot-at-everyone />，按钮用 commands，@全体用 at_everyone=true。

commands 示例：[{"text": "/签到", "show": "去签到"}]；回车指令只在单聊可用（enter=true）。

限制：
- 单条 ≤4000 字，一次回复里最多 1 条；
- 被动回复额度：群 5 分钟内 5 次、单聊 60 分钟内 4 次，不要用它刷屏；
- @全体需要机器人是群管理员，当天已用过就不要再试；
- 单聊不支持 @。

失败怎么办：报「超过上限」就精简或换 send_long_reply；报「Markdown 被拒」系统会自动降级纯文本并告诉你。
```

同时在 `_official_platform_note` 里加一句指路（常驻、稳定、可缓存）：

```text
需要排版、内嵌 @ 或指令按钮时用 send_official_markdown；语法与限制见技能 qq-official-markdown。
```

不设置 `allowed-tools`：该技能只提供知识，不该限制本轮工具集。

## 11. 测试要点

| 层 | 测试文件 | 用例 |
|---|---|---|
| 工具定义/可见性 | `app/tests/modules/reply/test_official_tool_visibility.py`（扩展） | official=True 时定义存在；official=False 时不定义、直接调用被拒；`allowed_tools` 限制下仍在 |
| 工具校验 | `app/tests/modules/reply/test_markdown_tool.py`（新） | 空内容、4001 字、单聊 @、群聊已用 @全体、群聊 enter、commands 非数组/超 100 字、reply_to 不存在；合法输入生成正确段 |
| 转义/编码 | 同上 | 用户文本里的三个标签被转义成全角；`％` 与已编码输入幂等；`quote(safe="")` 结果正确 |
| handler | `app/tests/modules/reply/test_tools.py`（扩展） | 发出 `[reply, markdown]`；设置 `state.reply_sent`；自身历史存去标签文本；发送失败返回 error 且不标记已回复 |
| 适配器 | `app/tests/modules/adapter/test_official_send.py`（扩展） | msg_type=2、无 content 字段、msg_id/msg_seq/message_reference；合成 ID→openid；未知 ID→`@用户`；私聊 @ 降级；>4000 直接 failed；markdown 不被 `_split_text` 切分；各错误码降级纯文本且标签被清；普通文本路径转义标签 |
| skill | `app/tests/modules/chat/test_skill_registry.py` 或新用例 | SKILL.md 能被 discover；frontmatter name/description/keywords 合规；不影响 allowed-tools |
| 集成 | `app/tests/modules/reply/test_dual_identity.py` 附近（扩展） | 双通道官方事件可见、OneBot 事件不可见；markdown 发送显式走 official，不因映射改投 OneBot |

回归重点：现有 `send_reply` 在官方通道的 Markdown 行为不变（除新增标签转义）；OneBot 通道完全无变化。

## 12. 非目标

- 内嵌键盘（`keyboard`）、Markdown 模板（`template_id`/`custom_template_id`）、流式消息、ARK/图文卡片。
- 频道/子频道、`<#channel_id>`、`<emoji:id>`。
- 在 Markdown 里内嵌图片（`![...]` 需要公网图床或 `qqbot-media://` 上传）——留作后续；第一阶段只做文本排版、@ 与按钮。
- 自动拆多条 Markdown 消息、自动 URL 删除、自动把 @ 换成昵称。
- 列表/表格语法降级转换（表格交给 `send_long_reply`）。

## 13. 风险与待确认

1. **长度上限**：官方未公布 Markdown 单条长度；沿用 4000 是经验值，若官方实际更小，错误码 `40054007` 会兜底，
   但工具层应把该错误翻译成「改用 send_long_reply」而不是重试。
2. **@全体节流**：本地按天计数只在单进程内有效，重启/多实例会重置；权威仍是官方限制，本地只防手滑。
3. **降级判定**：`_is_markdown_forbidden` 目前依赖文案，新增错误码覆盖后仍可能漏；漏判的结果是发送失败，
   不是发错消息，可接受。
4. **被动额度不可见**：适配器转主动推送时不回报额度，模型可能以为还有被动额度；工具描述已提示「一轮最多 1 条」。
5. **私聊 @**：官方不支持，工具直接拒绝；若后续官方开放，需同步改 `_mention_tag` 与校验。
6. **命名**：`send_official_markdown` 一旦上线就是模型可见契约，改名需要同步 skill 与文档。

## 14. 验收口径

- 群聊一条调用能产出「标题 + 列表 + 内嵌 @ + 参数按钮」的 `msg_type=2` 请求，客户端渲染正常；
- 用户复述 `<qqbot-at-everyone />` 不会触发真 @；
- 4001 字内容被拒绝且提示指向 `send_long_reply`；
- 官方拒绝 Markdown 时降级为纯文本一次，标签不残留；
- OneBot 通道工具列表与行为零变化；
- `uv run pytest -m "not browser and not network and not slow and not llm"` 全绿。
