# 官方机器人 Markdown 卡片工具设计

> 状态：已实现（2026-11-11 补全 at_everyone / commands / 注入转义 / 普通文本清理；发送失败一律明确返回错误，**不自动降级**）　分支：`fix/official-review`　范围：官方 QQ 机器人通道（`official`），不含频道/子频道。
> 术语：本工具发送的是「官方 Markdown 卡片」，不是把 Markdown 渲染成图片的「Markdown 图片」（send_long_reply）。
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

> 说明：本节与 §3 描述的是设计时的旧实现；其中 `qq_markdown`/`_send_text`/`_is_markdown_forbidden` 已在
> 0fce4ab5 重构中移除（普通文本固定纯文本、失败不再降级），当前实现见 §4/§7。

现在官方通道上「文字看起来能用 Markdown」，但只是适配器把普通文本按 `qq_markdown=true` 装进
`markdown.content`（[`official/send.py`](../../packages/adapter/src/neobot_adapter/official/send.py) `_send_text`），
并不是一个可编排的发送能力：

1. `send_reply` 先按句子切分（`process_reply_text`，默认上限 300 字/12 句），多行结构被拆成多条消息，
   标题、列表、引用全被打散；超限还会触发「转图片」或默认兜底模板。
2. @ 只能通过 `mention_qqs` 放在正文**开头**（`ReplySender.build_reply_segments`），无法内嵌；
   `@全体成员` 无参数可达（`mention_qqs` 是整数列表，`all` 只能内部传）。
3. 指令按钮（`qqbot-cmd-enter`/`qqbot-cmd-input`）没有结构化入口（2026-11-11 已补）。
4. 普通文本里出现的 `<qqbot-at-everyone />` 等标签会被原样装进 Markdown 发出去——见 §9（2026-11-11 已修）。

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
| 参数指令 `<qqbot-cmd-input text="..." show="..." reference="false" />`：`text` 必填，`text`/`show` 各 ≤100 字符，值需 urlencode | 不能让模型手写编码 | 工具校验长度、适配器统一编码 |
| 官方 Markdown 格式清单：标题、加粗/斜体/删除线/下划线、链接、图片、有序/无序/嵌套列表、块引用、分割线、多行 | **没有表格、没有代码块** | 表格/代码走 `send_long_reply`（转图片） |
| 被动回复：群 5 分钟/每条消息 5 次；单聊 60 分钟/4 次；`msg_id + msg_seq` 相同会失败（适配器实际按 4/3 留一次余量） | 每发一条 Markdown 消耗一次 | 工具不拆多发，并提示额度 |
| 官方未公布 Markdown 长度上限；超限报 `40054007` | 沿用适配器 4000 字符安全线 | content 超限工具层拒绝；拼装后的最终文本由适配器再卡一次 |
| 报错与降级相关码：`40034008`/`40034009`/`40034011`/`40034124`/`40034127`/`304036`（Markdown 相关）、`40054007`（超长）、`40054010`（不允许 URL）、`40034128`/`304103`（被动超限/过期）、`40034100`（主动频控）、`40054005`（去重） | 判定要按错误码，不只按文案 | 0fce4ab5 起不降级：按错误码原样返回明确失败 |

> 私聊的 @ 能力：官方能力的表格只列了「群聊」「文字子频道」，单聊没有 @ 用户/全体。工具层在单聊直接拒绝
> content 里的 `<qqbot-at-user` 与 `at_everyone`，让模型直接写昵称；适配器兜底把单聊内嵌 @ 替换成「@用户」普通文字。

## 3. 实现前的现状差距（已全部处理）

| 位置 | 现状 | 本设计是否改 |
|---|---|---|
| `reply/tool_parts/reply_tools.py:384` `send_reply` | 文本按句切分；官方通道 @ 只能置前 | 不改 |
| `reply/tool_parts/long_reply_tools.py` `send_long_reply` | Markdown → 图片 | 不改 |
| `reply/sender.py:800` `build_reply_segments` | `at` 段固定在正文前 | 不改 |
| `official/send.py:445` `_prepare` | 只认 text/at/reply/media | **加 markdown 段** |
| `official/send.py:335` `_send_text` | 有 `force_markdown` 分支，可复用 | 复用 |
| `official/send.py:503` `_split_text` | 4000 字硬切（会切碎 Markdown） | markdown 路径不切 |
| `official/send.py` `_is_markdown_forbidden` | 只按文案含 markdown + 「不允许/forbidden」判定 | 已随 0fce4ab5 移除（不再降级） |
| `official/send.py` `_strip_mention_tags` | 降级只去 @ 标签，不去指令标签 | 已被 `neutralize_official_tags` 取代 |
| `reply/output_guard.py` `clean_text` | 不处理 `<qqbot-*>` | 不改（在适配器兜底） |

## 4. 工具设计

### 4.1 名称与可见性

- 名称：`send_official_markdown`。不用 `send_markdown`：与「Markdown 转图片」的 `send_long_reply` 太像，
  模型会混用；显式带 `official` 也能在工具列表里自解释。
- 只在 `_official_platform=True` **且**绑定了 handler 时定义（`_define_official_markdown_tool`）。OneBot 事件、单通道
  OneBot 部署都看不到它；双待下 OneBot 事件看不到、官方事件看得到。
- 加入 `_SKILL_GUARD_BASE_TOOLS`（技能 `allowed-tools` 限制轮次仍可发）与 `BASIC_REPLY_TOOLS`（回执按控制流压缩），
  与 `send_reply` 同等待遇；计划审批（plan mode）下与 `send_reply` 一样属于安全工具。
- 每个 `ReplyToolExecutor`（一条回复管线）最多成功发送 1 条；第二次调用直接返回错误，避免模型反复改格式重发。

### 4.2 参数

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `content` | string | 是 | Markdown 正文。允许内嵌 `<qqbot-at-user id="openid" />`；其余 `<qqbot-*` 标签会被转义成普通文字。上限 4000 字符 |
| `reply_to_number` | integer | 否 | 引用回复的消息编号（行首编号），语义与 `send_reply` 相同；不存在直接报错 |
| `at_everyone` | boolean | 否 | 仅群聊；为 true 时在正文最前面插入 `<qqbot-at-everyone />` 和一个空格，每群每天最多 1 次（本地节流 + 官方兜底） |
| `commands` | array | 否 | 指令按钮，追加在正文末尾。元素 `{text, show?, reference?, enter?}` |

`commands` 元素：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | string | 是 | 点击后发送/插入的文本，≤100 字符；适配器拼标签时统一 urlencode |
| `show` | string | 否 | 按钮上显示的文本，≤100 字符；缺省取 `text` |
| `enter` | boolean | 否 | true 生成 `qqbot-cmd-enter`（点一下直接发送）；**仅单聊**，群聊报错 |
| `reference` | boolean | 否 | 仅参数指令；插入输入框时是否带引用，默认 false |

为什么按钮走结构化参数而不是让模型写标签：需要 urlencode、要卡 100 字符、要按会话类型禁 `enter`，
也让「用户文本被抄进 content 时附带一个假按钮」变成不可能。@ 之所以允许内嵌写标签，是因为工具必须知道
@ 的位置（官方用户 ID 以完整 openid 出现在模型上下文里），而 @全体单独用参数把住。

分层：工具负责校验与转义（content 里除内嵌 `@用户` 外的官方标签全角化，`neutralized` 计数写回回执）；
`at_everyone`/`commands` 作为结构化参数经 handler → sender → 适配器消息段透传，**由适配器按官方协议拼装**
（`<qqbot-at-everyone /> ` 前置、指令标签追加末尾、值统一 `quote(unquote(v), safe="")`）。这样适配器不必猜
content 里的标签来源，用户/模型复述的标签永远不会被当成真 @/真按钮执行。

### 4.3 校验（失败即返回 JSON，不发送）

所有校验失败统一回执 `{"ok": false, "error": "错误：..."}`（与 `send_long_reply` 同风格），不发送任何消息。

| 规则 | 错误回执 |
|---|---|
| 非官方通道 | `错误：send_official_markdown 仅在官方机器人通道可用` |
| 本轮已成功发过 1 条 | `错误：本轮回复已发送过 1 条官方 Markdown 卡片；同一轮最多 1 条，请不要重复发送` |
| `content` 缺失/为空 | `错误：Markdown 内容为空` |
| `content` 清洗后为空 | `错误：Markdown 内容清洗后为空，请只提供正文，不要带系统标注或思考草稿` |
| `len(content) > 4000` | `错误：Markdown 内容 N 字，超过单条上限 4000；请精简后重发，或改用 send_long_reply` |
| content 含代码块 | `错误：官方 Markdown 不支持代码块，请改用 send_long_reply` |
| content 含非官方 `<...>`（HTML 等） | `错误：Markdown 中出现了不支持的标签：<...>；官方 Markdown 不解析 HTML...` |
| content 含不安全链接 | `错误：链接只允许 http(s)：...` / `错误：不允许发送内网/本机链接：...` |
| 单聊带 `<qqbot-at-user` | `错误：单聊不支持 @；请直接写昵称，去掉 <qqbot-at-user> 标签` |
| 单聊 `at_everyone=true` | `错误：单聊不支持 @全体成员；请直接写提醒并去掉 at_everyone` |
| `at_everyone` 非布尔 | `错误：at_everyone 必须是布尔值` |
| 群聊 `at_everyone` 当天已用 | `错误：本群今天的 @全体成员已用掉（官方限制每群每天 1 次）；请改用普通提醒` |
| `commands` 非数组/元素非对象 | `错误：commands 必须是对象数组` |
| `text`/`show` 超 100 字符或为空 | `错误：指令按钮文本必须在 1~100 字符内` |
| 群聊 `enter=true` | `错误：群聊不支持回车指令；请去掉 enter 或改用 send_reply` |
| `reply_to_number` 不存在 | 同 `send_reply`：`错误：消息编号 N 不存在于当前上下文中` |

校验前先跑 `clean_text`（去系统标注/思考标签），清洗后为空按空内容处理；不做句子切分。
content 里除内嵌 `<qqbot-at-user id="..."/>`（字符集 `[A-Za-z0-9_-]{1,128}`）外的官方标签（`<qqbot-at-everyone />`、
`<qqbot-cmd-*/>`、`<@...>`）**全角化**为普通文字并计入回执 `neutralized`，不报错、不发送原标签。

### 4.4 回执

成功：`{"ok": true, "sent_count": 1, "summary": "已发送 1 条官方 Markdown 消息"}`；
content 里有标签被全角化时补 `"neutralized": N`。
失败：`{"ok": false, "error": "..."}`，与 `send_long_reply` 的既有风格一致。
**没有 `degraded` 字段**：发送失败不降级（见 §8），模型看到的是明确错误，需要自己修正参数或告知用户。

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
  指令标签 → `[按钮：文本]`），否则下一轮上下文会教模型在普通 `send_reply` 里手写标签；工具调用参数里
  的 content 也是转义后的版本，`at_everyone`/`commands` 保留结构化形式。

## 6. 示例

### 6.1 群聊：内嵌 @ + 列表 + 参数指令

工具调用：

```json
{
  "content": "## 今日签到\n\n<qqbot-at-user id=\"7A3B9C1D5E2F4A6B8C0D1E3F5A7B9C2D\" /> 你今天还没签到。\n\n- 连续签到 **7** 天\n- 本次积分 **+50**",
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

要点：`<qqbot-at-user id="...">` 里的 openid 直接透传（旧 13 位合成号只在迁移期经只读映射反查）；
`/签到` 由适配器按 `quote(unquote(v), safe="")` 编码成 `%2F%E7%AD%BE%E5%88%B0`。

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
  `neutralized` 计数 +1；不会真的 @全体。`<qqbot-cmd-enter ...>`、`<qqbot-cmd-input ...>`、`<@...>` 同理。
- 只想 @全体时用 `at_everyone=true`（仅群聊）：适配器在正文最前拼 `<qqbot-at-everyone /> `，并在发送前校验
  机器人是群管理员；本地按「群 openid + 本地自然日」节流，每天 1 次。
- 群聊 `commands: [{"text": "/x", "enter": true}]`：直接报错，不发送；单聊才允许回车指令。
- `<script>` 这类非官方 `<...>`：直接报错，不发送（官方 Markdown 不解析 HTML）。
- 4220 字的内容：报错并提示改用 `send_long_reply`；不安全链接（`javascript:`/内网地址等）同样直接报错。

## 7. 发送链路与最小改动

### 7.1 消息段契约

在 OneBot 消息段数组里新增一种仅内部使用的段：

```python
{"type": "official_markdown", "data": {
    "content": "<用户/模型提供的 Markdown 正文>",
    "at_everyone": True,            # 可选：结构化参数，只有真值时才带
    "commands": [{"text": ..., "show": ..., "enter": ..., "reference": ...}],  # 可选
}}
```

规则：**结构化字段只能由工具层生成**；content 里的同名标签一律全角化。适配器按官方协议拼装最终文本
（`<qqbot-at-everyone /> ` 前置、指令标签 urlencode 后追加末尾），**markdown 段不能与 text/at/富媒体段混用**
（`_prepare` 抛 `_SendFailure`），可与 `reply` 段同用（用于引用）。这样「一条消息一个 body」的官方语义在适配器里
显式化，而不是靠拼接猜测。

### 7.2 改动清单

| 文件 | 改动 |
|---|---|
| `app/src/neobot_app/reply/tool_parts/official_tools.py` | 工具定义（content/reply_to_number/at_everyone/commands）；校验、链接检查、标签全角化、@全体节流、一轮 1 条限流、回执 |
| `app/src/neobot_app/reply/tool_parts/dispatch.py` | `execute` 路由 + 计划审批（plan mode）安全工具集 |
| `app/src/neobot_app/reply/tool_parts/common.py` | `_SKILL_GUARD_BASE_TOOLS` 与 `BASIC_REPLY_TOOLS` 加入新工具名 |
| `app/src/neobot_app/reply/sender.py` | `send_official_markdown` 透传 `at_everyone`/`commands`（结构化消息段） |
| `app/src/neobot_app/reply/orchestrator_parts/agent_handlers.py` | handler：转发结构化参数 → `record_self_sent_text`（写可读文本 + 结构化工具参数）+ `state.reply_sent=True` |
| `packages/adapter/src/neobot_adapter/official/send.py` | `_prepare` 识别 `official_markdown` 段与结构化字段；`_send_markdown` 拼装/转义/管理员校验/不切分；普通文本路径转义官方标签 |
| `app/src/neobot_app/skills/official_markdown_guide.py` | 内置技能文档（写入 `app/data/skills/qq-official-markdown/SKILL.md`），见 §10 |
| `app/src/neobot_app/prompt/blocks.py` | `_official_platform_note` 指路一句「需要排版/内嵌 @/按钮用 send_official_markdown，语法见技能」 |
| `docs/04-功能文档/QQ官方机器人.md` | 工具说明（由 Lead 统一更新） |

### 7.3 适配器细节

```python
# _send_markdown(): 拿到 _Prepared（markdown + at_everyone + commands）后
content = self._render_markdown_mentions(str(prepared.markdown or ""), kind)  # 校验/透传 openid
content, neutralized = neutralize_official_tags(content, allow_at_user=True)   # 其余官方标签全角化
if prepared.at_everyone:
    content = f"<qqbot-at-everyone /> {content}"
for tag in _command_tags(kind, prepared.commands):   # quote(unquote(v), safe="")
    content = f"{content}\n\n{tag}"
if len(content) > _TEXT_LIMIT:
    raise _SendFailure(f"Markdown 消息 {len(content)} 字，超过单条上限 {_TEXT_LIMIT}")
if prepared.at_everyone:
    await self._assert_can_at_everyone(openid)       # bot_state.member_role ∈ {admin, owner}
# 之后一次性 POST msg_type=2，不切分、不降级
```

- `_render_markdown_mentions`：`<qqbot-at-user id="..." />` 里的值现在就是 openid，直接校验字符集后透传；
  格式非法或无法解析时替换成 `@用户` 文本并记 WARNING（不让坏 ID 原样上线）。单聊没有 @ 能力，全部替换成 `@用户`。
- `neutralize_official_tags`：`@user` 之外（`at-everyone`/`cmd-*`/`<@...>`）的官方标签首尾 `<>` 换全角，
  返回转义个数；日志只记数量（R6）。
- `at_everyone`/`commands` 只能来自结构化段字段：content 里手写的同名标签会被上一步全角化。@全体节流在工具层，
  适配器负责最终的管理员校验（官方限制仍是权威）。
- markdown 段整体走一次 POST，`msg_type=2`+`markdown.content`；**没有** `_split_text`、**没有** `_is_markdown_forbidden` 降级、
  **没有** 转主动推送。
- 普通文本路径（`_send_plain`）发 `msg_type=0` 前也跑 `neutralize_official_tags`（全量），把 `<qqbot-*`/`<@...>`
  全角化——这是 §9.1 现存缺陷的修复点，与 Markdown 开关无关。

## 8. 失败与降级

**本工具没有降级链**：0fce4ab5 起官方通道统一「发送失败不降级、明确返回错误」，本工具不再重新引入
「Markdown 被拒 → 改发纯文本」。一次调用只有两种结果：发出 1 条 `msg_type=2`，或返回 failed 且什么都不发。

| 触发 | 行为 | 模型看到 |
|---|---|---|
| 参数校验失败（含标签/链接/指令） | 不发送 | JSON error，可直接修正重试 |
| Markdown 被官方拒绝（错误码/文案） | 不重发、不改发纯文本，只记 info 日志 | error：发送失败 + 官方原因；修正参数或告知用户无法发送 |
| `40054007` 长度超限 | 不切分、不重发 | error：精简或改用 `send_long_reply` |
| `40054010` 不允许发送 URL | 不自动删链接（会改变语义） | error：去掉链接或改用 `send_long_reply` |
| 被动额度用尽/过期（`40034128`/`304103`） | 不转主动推送，直接 failed（既有行为） | error：本轮不要再重试 |
| 主动推送被拒/机器人离线 | 返回 failed | error：本轮不要重试，别再发 |
| @全体不是管理员/无法确认权限 | 适配器在发送前直接 failed | error：告知用户当前不能 @全体 |
| 内嵌 @ 的 openid 非法/缺失 | 适配器替换成 `@用户` 文本并记 WARNING（工具层对非法标签是直接全角化） | `ok`，日志 WARNING |
| 清洗后为空 | 不发送 | error，同 `send_reply` 的空内容提示 |

原则：**能在工具层拦的绝不发出去**；发送侧不再改写内容形态或降级到另一种消息类型。

## 9. 注入防护

威胁模型：`content` 会混入用户原话、网页抓取、聊天记录引用；攻击者可以让模型「复述」一段带官方标签的文本。

- **R1 标签白名单**：`content` 只放行 `<qqbot-at-user id="openid" />`（id 为 `[A-Za-z0-9_-]{1,128}`，非空）；
  `<qqbot-at-everyone />`、`<qqbot-cmd-enter ...>`、`<qqbot-cmd-input ...>`、`<@...>` 一律全角化成普通文字
  （`＜qqbot-at-everyone /＞`）并在回执里带 `neutralized` 计数。「把这段话原样发出去」不再能触发 @全体或伪造按钮。
  裸文本 `@everyone` 不是官方协议标签、客户端不会执行，按普通文字处理。
- **R2 @全体单独开关**：只能由 `at_everyone=true` 生成，仅群聊；本地按 `(群ID, 本地自然日)` 记录，每天 1 次；
  官方限制仍是最终权威（本地记录重启即清空，属已知限制）。适配器发送前再校验机器人是群管理员。
- **R3 按钮只来自结构化参数**：`commands` 的值由适配器统一 `quote(unquote(value), safe="")` 编码后再拼标签，
  已编码的输入不会被二次编码破坏（对 `%` 也收敛）；模型手写的 `<qqbot-cmd-*>` 在工具层就被全角化。
- **R4 链接与图床**：`![...](url)`、`[text](url)` 只允许 `http(s)`；拒绝 `javascript:`/`data:`/
  `file:`，以及回环/内网/链路本地地址（`127.0.0.0/8`、`10.*`、`192.168.*`、`172.16-31.*`、`169.254.*`、
  `localhost`、`*.local`）。官方本来就要求公网可访问，内网 URL 只会泄漏拓扑。命中直接报错，不静默删。
- **R5 不做 HTML**：官方 Markdown 不解析 HTML；除官方协议标签外的 `<...>`（如 `<script>`）在工具层直接报错
  不发送（比转义更明确），适配器 Markdown 路径对官方标签再兜底全角化一次。
- **R6 日志脱敏**：日志只记长度、标签计数、错误码，不记 `content` 全文（可能含密钥/隐私）。
- **R7 发送前清洗**：沿用 `clean_text`，防止把历史里的 `[msg_id=...]`、`编号: 名字: ` 抄进 Markdown。
- **R8 频控**：每次回复管线（一个 `ReplyToolExecutor` 实例）最多成功发送 1 次 `send_official_markdown`，
  失败不消耗配额，避免被动额度被格式重试吃光。

### 9.1 顺带修复的现存缺陷（已修）

官方通道普通文本（`msg_type=0`）以前会把用户原话里的 `<qqbot-*` 标签原样发出去；若后续任何路径把它装进
Markdown，就会被客户端真的执行。修复：`_send_plain` 在切分/发送前调用 `neutralize_official_tags`（R1 同一函数），
`<qqbot-*`/`<@...>` 全部全角化成普通文字并记 info 日志（只记数量）。这是纯收紧，不改变正常文本
（正常文本里不会有这些标签）。

## 10. 提示词 skill

位置：`app/data/skills/qq-official-markdown/SKILL.md`（`SkillRegistry(root=DATA_DIR/"skills").discover()` 自动发现，
按 `keywords` 命中后只注入 name+description，模型再用 `skills__read_manifest` 读全文——与本仓库
`balance-query` 同一模式，不占常驻 token）。

```markdown
---
name: qq-official-markdown
description: 官方 QQ 机器人 Markdown 卡片与内嵌 @/指令按钮的写法（仅 official 通道，按需读取）
keywords: markdown 卡片 官方机器人 标题 列表 引用 按钮 指令 @ 群通知
---
# 官方 QQ 机器人 Markdown 卡片

普通 send_reply 只发送纯文本，不会渲染 Markdown，也不能真正 @ 用户。只有需要标题、列表、引用、
链接、内嵌 @、@全体成员或指令按钮时，才调用 send_official_markdown（官方 Markdown 卡片）；
需要把 Markdown 渲染成图片用 send_long_reply，两者不是一回事。

## content 写法（只放行内嵌 @）

- 支持：## 标题、**加粗**、_斜体_、~~删除线~~、> 引用、- 列表、1. 有序、[文字](https://...)、*** 分割线；
- 不支持：表格、代码块、HTML；需要就改 send_long_reply（转图片）。
- @ 用户：<qqbot-at-user id="openid" />，openid 见群友资料里的完整用户 ID，不要编；单聊不支持 @，直接写昵称。
- 不要手写 <qqbot-at-everyone /> 或 <qqbot-cmd-*>：这类标签会被工具转义成普通文字。
  @全体成员用 at_everyone=true（仅群聊，每群每天 1 次，机器人必须是群管理员）；
  指令按钮用 commands 数组（工具会生成 qqbot-cmd-enter/qqbot-cmd-input 标签）。

## commands 示例

[{"text": "/签到", "show": "去签到"}]：text 必填、text/show 各 ≤100 字符；
单聊可加 "enter": true（点一下直接发送），群聊不支持 enter；reference 只对参数指令生效。

## 限制

- 单条 ≤4000 字，一次回复里最多 1 条；
- 被动回复额度：群 5 分钟内 5 次、单聊 60 分钟内 4 次，不要用它刷屏；
- 链接只允许 http(s)；javascript:/data:/file: 与回环/内网地址会被拒绝；
- @全体需要机器人是群管理员，当天已用过就不要再试；单聊不支持 @。

失败怎么办：发送失败是真实失败，不会自动降级成纯文本；按错误修正参数，或告诉用户暂时无法发送。
```

> 文案以 `app/src/neobot_app/skills/official_markdown_guide.py` 的 `_DOCUMENT` 为准（启动/重载时写入技能目录）。

同时在 `_official_platform_note` 里加一句指路（常驻、稳定、可缓存）：

```text
需要排版、内嵌 @ 或指令按钮时用 send_official_markdown；语法与限制见技能 qq-official-markdown。
```

不设置 `allowed-tools`：该技能只提供知识，不该限制本轮工具集。

## 11. 测试要点

| 层 | 测试文件 | 用例（均已通过） |
|---|---|---|
| 工具定义/可见性 | `app/tests/modules/reply/test_official_tool_visibility.py` | official=True 时定义存在；official=False 时不定义、直接调用被拒 |
| 工具校验 | `app/tests/modules/reply/test_markdown_tool.py`（新） | 空内容、4001 字、代码块、非官方标签、不安全链接、单聊 @/@全体、群聊已用 @全体、群聊 enter、commands 非数组/超 100 字、reply_to 不存在、at_everyone 非布尔、非官方通道 |
| 转义/编码 | 同上 | `<qqbot-at-everyone />`/`<qqbot-cmd-*/>`/`<@...>` 全角化且 `neutralized` 计数正确；`@user` 原样保留；`https` 链接放行 |
| 结构化参数/节流 | 同上 | at_everyone 透传 + 每群每天 1 次、换群可发；commands 透传；单聊 enter 可用；一轮第 2 条被拒；失败不消耗配额；历史可读文本/tool_arguments |
| handler | `app/tests/modules/reply/test_tool_history_audit.py`/`test_tool_history_rebuild.py` | 发出 `official_markdown` 段；`state.reply_sent`；历史存可读文本并重建同名工具调用 |
| 适配器 | `app/tests/modules/adapter/test_official_send.py`（扩展） | msg_type=2、无 content 字段、msg_id/msg_seq/message_reference；content 里只有内嵌 @ 能上线（其余官方标签全角化）；结构化 at_everyone 前置 + 管理员校验；commands urlencode 追加；单聊 enter 失败；单聊 @ 文本化；非法 ID→`@用户`；>4000 直接 failed 不切分；普通文本路径转义官方标签 |
| skill | `app/tests/modules/skills/test_official_markdown_guide.py` | SKILL.md 能被注册；frontmatter name/description/keywords 合规；不设 allowed-tools |

回归重点：现有 `send_reply` 在官方通道仍只发纯文本（只是新增标签转义）；OneBot 通道完全无变化。

## 12. 非目标

- 内嵌键盘（`keyboard`）、Markdown 模板（`template_id`/`custom_template_id`）、流式消息、ARK/图文卡片。
- 频道/子频道、`<#channel_id>`、`<emoji:id>`。
- 在 Markdown 里内嵌图片（`![...]` 需要公网图床或 `qqbot-media://` 上传）——留作后续；第一阶段只做文本排版、@ 与按钮。
- 自动拆多条 Markdown 消息、自动 URL 删除、自动把 @ 换成昵称。
- 列表/表格语法降级转换（表格交给 `send_long_reply`）。

## 13. 风险与待确认

1. **长度上限**：官方未公布 Markdown 单条长度；沿用 4000 是经验值，若官方实际更小，错误码 `40054007` 会兜底。
   工具回执会带上官方原因，由模型改用 `send_long_reply` 或精简，不自动重试。
2. **@全体节流**：本地按天计数只在单进程内有效，重启/多实例会重置；权威仍是官方限制，本地只防手滑。
3. **发送失败语义**：本工具不降级，官方拒绝/额度用尽都直接返回失败；模型可能仍想再试一次，工具描述已提示
   「失败就修正参数或告知用户」，并且一轮最多 1 条成功发送（失败不消耗配额）。
4. **私聊 @**：官方不支持，工具直接拒绝、适配器兜底文本化；若后续官方开放，需同步改校验与 `_render_markdown_mentions`。
5. **命名**：`send_official_markdown` 一旦上线就是模型可见契约，改名需要同步 skill 与文档。
6. **链接校验**：只做静态字符串校验（scheme + 主机名/IP），不做 DNS 解析；`http://example.com` 解析到内网
   这类情况拦不住，但官方要求公网可访问，实际风险低。

## 14. 验收口径

- 群聊一条调用能产出「标题 + 列表 + 内嵌 @ + 参数按钮」的 `msg_type=2` 请求，客户端渲染正常；
- 用户复述 `<qqbot-at-everyone />` / `<qqbot-cmd-*/>` / `<@...>` 只会得到全角化文字（回执带 `neutralized`），不会真 @；
- `at_everyone=true` 仅在群聊、每群每天 1 次、管理员校验通过时生效；
- 单聊 `enter` 指令可用，群聊同参数直接报错不发送；
- 4001 字内容被拒绝且提示指向 `send_long_reply`；不安全链接、HTML 标签直接拒绝；
- 官方拒绝 Markdown 时**不降级**，返回明确错误（不再改发纯文本）；
- OneBot 通道工具列表与行为零变化；
- `uv run pytest -m "not browser and not network and not slow and not llm"` 全绿。
