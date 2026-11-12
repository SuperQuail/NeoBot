# 发送工具历史记录审计（草稿）

> 任务：task-15。只读审计 + 独立测试，不改核心发送实现。
> 测试文件：`app/tests/modules/reply/test_tool_history_audit.py`
> 结论时间：2026-11-11，分支 fix/official-review（含工作区中另一子代理的 tool_call 元数据实现）。

## 1. 审计问题

各种对外发送工具在**发送成功后**是否把「工具调用 + 结果 + 自己发过的东西」写回聊天队列，
使回复管线因寿命耗尽 / 挂起恢复 / 软重启而重置后，`role_messages` 仍能重建出：

1. 真实工具名（send_reply / speak / send_long_reply / send_official_markdown）；
2. 当时的工具参数（emoji_numbers / caption / image_path / content）；
3. 产物索引（图片 temp 图库 id、file 路径、音频文件）；
4. 稳定的 tool_call_id（负合成 message_id），不破坏前缀缓存。

## 2. 路径清单（当前工作区实现）

| 工具 / 路径 | 发送入口 | 写自队列 | 写库（软重启） | role_messages 重建 | 断链点 |
|---|---|---|---|---|---|
| send_reply 文字 | `ReplySender.send_reply` → `_emit_self_sent_text` → `record_self_sent_text` | ✅ 每条实际发出的文本（自动切分逐条） | ✅ 仅 text（event_id=self:<负id>） | ✅ send_reply(text=...) + ok 回执 | 软重启后只剩文本（见 §3.2） |
| send_reply 图片 / 表情包 | 同上 Phase A → `_emit_self_sent_image` | ✅ 写「索引文本」`[图片:<tmp_id> file:<path>]`，非图片本体 | ✅ 索引文本 | ✅ send_reply(emoji_numbers=[n]) + image_index 回执 | 队列里没有 image 段；模型需自己用 tmp_id 再引用 |
| speak | `_agent_speak_handler` → `_send_with_timeout` → `record_self_sent_voice` | ✅ `[语音:file:...] <原文>` | ✅ 索引文本 | ✅ speak(text=...) + file_index 回执 | 软重启后同理退化 |
| send_long_reply | `_agent_send_long_reply_handler`（caption + send_image） | ✅ caption（仅成功）+ Markdown 图片索引（仅成功，见修复） | ✅ 索引文本 | ✅ send_long_reply(caption/image_path) | caption 与图片是两条独立历史 |
| send_official_markdown | `_agent_send_official_markdown_handler` → `ReplySender.send_official_markdown` | ✅ 原始 Markdown 文本 | ✅ | ✅ send_official_markdown(content=...) | 线上是 official_markdown 段，历史只有文本 |
| 后台通知（hub 镜像） | `BackgroundNotificationHub._mirror_to_message_queue` → `record_notification` → `push_notification` | ✅ 低权重 NotificationEntry | ❌（不需） | ✅ user 块 `[通知:<source>] <content>` | `mirror=False` 的通知与 `event.background_content` 仍是瞬时 |
| 表情回应 / 戳一戳 / 撤回 | handlers → `push_reaction/push_poke/push_notice` | ✅ 非消息条目 | ❌ | ✅ 独立 user 块 | 与发送工具无关 |
| 非发送工具（list_emojis、image_context、绘图、解析…） | 工具执行后 `_record_tool_call_history` | ✅ compact TOOL_CALL 条目（完整 args/result 保留） | ✅ `MessageData.tool_call_json` | ✅ assistant.tool_calls(arguments={}) + tool `{"ok":...}` | 显示只到工具名/成败；完整数据供面板/审计 |

## 3. 已验证契约（测试通过）

### 3.1 写回与重建
- 文字成功：队列消息 id 为负合成 id、`self_id == user_id == 事件 bot_account`；
  重建为 send_reply(text) + `{"ok": true}` 配对，call_id 稳定为 `history_<负id>`。
- 图片/表情包：索引文本保留 temp 图库 id 与 file 路径；重建参数为 `emoji_numbers=[n]`，
  回执 `image_index` 与队列文本一致。
- speak：历史含 `[语音:file:...]` 与原文；重建为 speak 调用 + file_index 回执。
- send_long_reply：caption 与 Markdown 图片索引分别重建为 send_long_reply 调用。
- send_official_markdown：线上载荷为 official_markdown 段（channel=official），历史写原文并重建同名工具调用。
- 后台通知：镜像后下一轮 transcript 出现 `[通知:source] content` user 块。
- 发送失败：send_reply 文字/图片、send_long_reply 图片失败均不写历史（不再谎报已发送）。
- 落盘：event_id 与队列负 id 对应（`self:<负id>`），sender_id 为事件账号，供软重启补齐。
- tool_call 元数据不依赖账号集合：`user_id=0`（账号未解析）时仍能重建工具历史。
- 负 message_id 防护：`_record_reply_delivered` 遇负的 last message id 时回退
  `event.pre_reply_message_id`，last_reply_position 仍是用户消息的真实 id。
- 队列裁剪：按权重驱逐后，重建历史的 assistant.tool_calls 与 tool 回执仍一一配对。

### 3.2 软重启恢复（已实现）
`MessageData.tool_call_json` 与 `IncomingMessage.tool_call` 已持久化；`ChatStreamManager`
启动恢复时分两路：`self:` 记录还原为 MESSAGE + full tool_call（发送工具），
`tool:` 记录还原为 compact TOOL_CALL（非发送工具）；空 text 不会产生空白消息。
覆盖：`app/tests/modules/database/test_chatstream_tool_call_restore.py`。

## 4. 剩余缺口与最小修复建议

1. **MessageNumbering 暴露自身发言的负 msg_id —— 已修复**
   - `_render_numbered_line` 的 is_self 分支不再渲染 `[msg_id=...]`，与 role_messages 的 assistant 口径一致；对应测试已转为普通通过。

2. **软重启工具元数据 —— 已修复**
   - `messages.tool_call_json`（迁移 0032）+ `IncomingMessage.tool_call`；发送工具 full、非发送工具 compact 均可在启动恢复。

3. **非发送工具完整数据仅存储、compact 显示**
   - 完整 args/result 存 `QueueEntry.tool_call` 与 `MessageData.tool_call_json`；
     聊天管线只显示工具名 + 成败，避免上下文膨胀。

4. **图片/语音产物的再引用**
   - 队列里是索引文本而非图片段；image_context 支持 `tmp_xxx`/`file:` 引用，
     但需要模型自己从历史文本里取 id，没有自动把历史图片段注入视觉上下文的链路。
   - 若要增强：让 role_messages 重建时把 `image_index` 回执里的 tmp_id 作为可引用提示
     （已有回执，成本低；是否自动加载图片仍需评估上下文开销）。

## 5. 测试与验证

- 测试文件：`test_tool_history_audit.py`（13）、`test_tool_call_history.py`（17）、`test_queue_tool_call.py`（6）、`test_message_tool_call.py`（9）、`test_chatstream_tool_call_restore.py`（10）。
  覆盖：文字/图片/表情包写回与重建、speak、send_long_reply（成功/失败）、
  send_official_markdown、后台通知镜像、负 message_id 防护、账号未解析兜底、
  软重启退化、队列裁剪配对、numbering 负 id 回归（已修复）。
- 命令：`.venv/Scripts/python.exe -m pytest app/tests/modules/reply/test_tool_history_audit.py -q`
  （本会话 uv run 受沙箱限制；pytest 临时目录需本机 ACL 规避，见验证说明）。
- 未覆盖：真实 QQ 网络发送回执；`send_emoji` 旧参数名兼容路径（已并入 send_reply）；
  跨进程软重启的端到端 DB 补齐（用行为等价的消息构造验证）。
