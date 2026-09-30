---
flow: 11-minigame
covers:
  - app/src/neobot_app/builtin_plugins/minigame/
verified_against: f610088
verified_hash: 64272780cb2c
---

# 11 小游戏：命令/关键词/工具三入口 · 认人窗口 · 积分账户 · 卡片渲染与降级

## 范围

**画什么**：`app/src/neobot_app/builtin_plugins/minigame/` 这一整个插件 ——
`__init__.py` 的三条入站路径（`/mg` 命令、关键词意图、`minigame__*` 工具）、
`service.py` 的六张表与积分账户写入语义、`games/*.py` 四个玩法的判据与阈值、
`themes.py` / `avatars.py` 的卡片主题与头像注入、文件末尾四个对外能力
（`points.get` / `points.add` / `points.rank` / `points.describe`）。

**不画什么**（指向相邻图）：

| 相邻内容 | 去哪张图 |
|---|---|
| 卡片渲染器本体（HTML 模板、slot/marker 注入、Chromium 截图端口） | 13-render-cards |
| 插件加载 / 热重载 / 能力调用机制（`require_plugin` / `handle.call`） | 08-plugins（08b-plugin-runtime） |
| 命令注册、权限树、群聊需被 @ 才走命令 | 17-commands |
| 头像存储本体（`avatar_store` 服务） | 20-avatar-files |
| 被 @ 时跳过等待的关键词快照 | 02b-willing-probability |

**spec 与现实的三处差异**（都在 `docs/04-功能文档/小游戏.md` 末尾登记为 WIP）：

1. **工具通道不发卡**：7 个工具都只返回文本，没有「已渲染好卡片、请发给用户」的句柄；
   全仓库 grep `minigame__card` 为 0 命中 —— 这个工具**不存在**，发卡只在命令入口发生。
2. `/mg help` 与 `/mg help <游戏>` 直接返回纯文本、不出图（`help_command`:873）。
3. `bottle_show_sender_id` 读得到但**未接线**，普通瓶一律显示 QQ 号（`config.py:36`）。

## 流程

```mermaid
flowchart TD
    subgraph 入口层
        A["/mg 或 /游戏 命令"] --> B["handle_command｜__init__.py:532"]
        K0["群聊正文命中 KEYWORDS（9 个词）"] --> K1["on_keyword｜__init__.py:925"]
        T0["agent 调用 minigame__ 前缀工具"] --> T1["_tool_bottle_write 等 7 个｜__init__.py:1033-1162"]
    end
    B --> C["remember_interaction｜:381<br/>写 _latest 认人记录"]
    C --> D{"首个子命令是什么?"}
    D -- "stop / rank / 积分 / help" --> E["stop_command :630 · rank_command :816<br/>points_text :645 · help_command :873"]
    D -- "玩法 id / 名字 / 别名" --> F["find_game｜games/__init__.py:172 → run_game :609"]
    D -- "其余一律" --> G["natural_language_fallback :614<br/>sync_reply=True，不执行动作"]
    T1 --> H{"resolve_user :409 认出用户?"}
    H -- 否 --> H1["NEED_IDENTITY_HINT :450"]
    H -- 是 --> I["tool_request :422<br/>GameRequest(command_ctx=None)"]
    F --> J["Game.run / write / pick / draw / submit"]
    I --> J
    J --> S["MinigameService｜service.py:51<br/>mg_profile · mg_bottle · mg_daily<br/>mg_checkin · mg_fortune · mg_record"]
    J --> R{"command_ctx 非空?"}
    R -- 是 --> R1["render_card :337 → HTML 转 PNG"]
    R1 -- "拿到 png" --> R2["send_card :345 发回原会话"]
    R1 -. "端口不可用 / 失败 / 超时 20s" .-> R3["build_card_text 纯文本回落"]
    R -- 否 --> R4["工具只回文本 → 模型转述，不出图"]
    K1 --> K2["emit_intent :978 → ctx.agent_reply<br/>预激活 minigame_ 玩法技能包"]
    G --> AG["interaction_background :472<br/>事实 + 提示词交主管线"]
    R3 --> AG
```

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant CMD as CommandsService
    participant RT as MinigamePlugin
    participant GM as Game 玩法
    participant SVC as MinigameService
    participant DB as minigame.db
    participant AG as 回复管线 Agent

    CMD->>RT: handle_command(command_ctx)（群聊需先被 @）
    RT->>RT: remember_interaction 写 _latest
    alt 确定性分支 stop / rank / 积分 / help
        RT-->>CMD: 文本（不经渲染、不改状态）
    else 玩法分支
        RT->>GM: run(GameRequest)
        GM->>SVC: daily_plays / add_bottle / apply_points / checkin …
        SVC->>DB: 单条 SQL + 事务，时间列写 ISO 字符串
        DB-->>SVC: 行数据 / rowcount
        SVC-->>GM: dict（不足时用 insufficient 表达，不抛）
        GM->>RT: render_card(html, timeout=20.0)
        RT-->>GM: png 或 None（永不抛异常）
        GM-->>CMD: None=已自行发图 / 文本=纯文本回落
        GM->>RT: interaction_background 拼「事实 + 提示词」
        RT->>AG: sync_reply=True 触发一次回复（非阻塞本轮命令）
    else 自然语言 / 格式错
        RT->>AG: interaction_background，不执行任何游戏动作
    end
    Note over RT,AG: 工具通道没有入站事件，只能靠 _latest 认人（TTL 300s）
```

## 细节

<details>
### 三条入口如何汇到同一个 service

```mermaid
flowchart TD
    A["/mg 玩法 参数｜__init__.py:532 命令入口"] --> B["command_request :584<br/>GameRequest(command_ctx=ctx)"]
    C["minigame__ 工具｜:1024-1162"] --> D["tool_request :422<br/>GameRequest(command_ctx=None)"]
    E["关键词 on_keyword :925"] --> F["只 emit_intent :978，不执行动作"]
    B --> G["find_game｜games/__init__.py:172<br/>按 id / name / alias 匹配"]
    G --> H["Game.run｜games/__init__.py:157"]
    D --> I["Game.write / pick / do_checkin / draw / submit"]
    H --> J["request.service = MinigameService｜service.py:51"]
    I --> J
    J --> K["同一个插件库 minigame.db（六张表）"]
    H --> L["request.runtime = MinigamePlugin<br/>提供 rng :293 / monotonic :290 / avatars"]
    I --> L
    L --> M["pick_card_theme :301 / render_card :337 / send_card :345"]
    K --> N["daily_plays :240 · apply_points :182 · add_bottle :268"]
    F --> O["模型下一轮自己选工具，回到 C 的路径"]
```

三条入口共用同一个 `GameRequest` 与同一个 `MinigameService` 实例：
`MinigamePlugin.load`:243 只构造一次 service，工具与命令都从 `_runtime()`:1014 拿同一个
单例插件对象（模块级 `_instance = MinigamePlugin()`:1011）。
唯一的结构差异是 `command_ctx`：它是「能不能发图」的总开关（`None` = 工具通道）。
关键词入口**刻意不执行任何动作**（R14/D11），只把控制权交回主管线。
</details>

<details>
### 工具通道认人：_latest 单槽 + 300 秒窗口

```mermaid
flowchart TD
    A["remember_interaction :381"] --> A1["写 _latest = user_id / user_name / kind<br/>conversation_id / game / at=monotonic"]
    A1 --> A2["调用方：handle_command :538、on_keyword :939"]
    B["latest_interaction :401"] --> C{"_latest 为空?"}
    C -- 是 --> C1["返回 None"]
    C -- 否 --> D{"monotonic - at 大于 300.0?"}
    D -- 是 --> D1["返回 None（过期，但**不清理** _latest）"]
    D -- 否 --> D2["返回记录"]
    E["resolve_user :409"] --> F{"显式 user_id 非空?"}
    F -- 是 --> F1["以参数为准；昵称仅在记录同号时补"]
    F -- 否 --> G{"记录有效?"}
    G -- 否 --> G1["返回空串 → NEED_IDENTITY_HINT :450"]
    G -- 是 --> G2["用记录里的 user_id / user_name"]
    H["tool_request :422"] --> I{"uid 为空?"}
    I -- 是 --> I1["返回 None：工具回引导文案，不写库"]
    I -- 否 --> I2["kind / conversation_id 取记录<br/>缺失回落 group / 空串"]
    D2 --> E
```

`INTERACTION_TTL_SECONDS = 300.0`（`__init__.py:72`）只作用于**工具通道认人**：
工具调用没有入站事件，这是唯一的身份来源。它和成语接龙的 60 秒步时限、
签到的自然日边界**没有任何关系**（三个不同时钟：monotonic / 本地日期 / 无）。
`_latest` 是**全局单槽**（不按用户、不按会话分桶）：A 用户刚说完话、B 用户的
agent 会话再调工具，认到的是 A —— 所以工具参数里才有可选的 `user_id` / `user_name`。
</details>

<details>
### 积分账户 apply_points：不足整笔不生效

```mermaid
flowchart TD
    A["points.add 能力｜__init__.py:1236（装饰器 :1235）"] --> B["_points_user_id :1177<br/>必须数字 QQ 且长度不超过 32"]
    B --> C["_points_int :1187<br/>bool 与 1.5 一律 ValueError"]
    C --> D["adjust_points :683"]
    D --> E{"abs(delta) 超过 points_max_delta 默认 100000?"}
    E -- 是 --> E1["抛 ValueError（参数错才用异常）"]
    E -- 否 --> F{"points_allow_external_write 默认 True?"}
    F -- 否 --> F1["ok=False reason=disabled applied=0<br/>score 回当前余额"]
    F -- 是 --> G["service.apply_points｜service.py:182"]
    G --> H["ensure_profile :124<br/>INSERT … ON CONFLICT DO NOTHING"]
    H --> I{"delta == 0?"}
    I -- 是 --> I1["applied=0 且不碰 updated_at"]
    I -- 否 --> J{"delta 小于 0 且 allow_negative=False?"}
    J -- 是 --> K["UPDATE 追加 AND score + :delta 大于等于 0"]
    J -- 否 --> L["UPDATE 无条件"]
    K --> M["_run :115 返回 rowcount"]
    L --> M
    M --> N{"rowcount 为 0 且是受限扣分?"}
    N -- 是 --> N1["insufficient=True applied=0<br/>profile 未被改动"]
    N -- 否 --> N2["applied=delta<br/>best_score = MAX(旧值, 新值)"]
```

* 判据全在 SQL 里：`score + :delta >= 0` 是 WHERE 条件，因此**并发下也扣不成负数**，
  不需要额外锁；影响行数为 0 就是 `insufficient`。
* `play` / `win` 也写在这条 UPDATE 里，所以**失败整笔不生效时场次、胜场都不累加**。
* `add_score`:151 没有这个保护（它只被本插件用正分调用）：传负分可以把余额写成负数 ——
  其它插件**不要**绕过 `points.add` 直接调它。
* `best_score` 只升不降（`MAX(旧值, score + delta)`），扣分不会回退历史最高分。
* 返回体里 `delta` 是「请求值」、`applied` 是「实际生效值」，余额不足时两者不等，调用方看 `ok`。
</details>

<details>
### 签到：自然日边界、连续附加与并发幂等

```mermaid
flowchart TD
    A["/mg 签到 或 minigame__checkin"] --> B["CheckinGame.do_checkin｜games/checkin.py:135"]
    B --> C["service.checkin｜service.py:424"]
    C --> D["day = today() :89 → 本地自然日 YYYY-MM-DD"]
    D --> E{"mg_checkin 已有当日行?"}
    E -- 是 --> E1["already=True<br/>base=落库 score、bonus=0"]
    E -- 否 --> F["base = rng.randint(low, high)<br/>默认 1-10；high 小于 low 时交换"]
    F --> G{"昨天的签到行存在?"}
    G -- 是 --> G1["streak = 昨天 streak + 1"]
    G -- 否 --> G2["streak = 1（断签归零，无补签）"]
    G1 --> H["bonus = min( (streak-1) × checkin_streak_bonus, cap )<br/>默认每天 +1、上限 +5"]
    G2 --> H
    H --> I["score = base + bonus"]
    I --> J["_claim_checkin :505 占位与加分同一事务"]
    J --> K{"INSERT mg_checkin 的 rowcount 为 1?"}
    K -- 否 --> K1["并发已被占：本次不加分<br/>按对方落库结果返回 already=True"]
    K -- 是 --> L["同事务 INSERT mg_profile + UPDATE score"]
    L --> M["_checkin_result :485<br/>already / score / streak / base / bonus / total / day"]
```

幂等的**唯一判据是 INSERT 的 rowcount**，不是事务外读到的 `existing` ——
后者正是「并发重复记账」的历史根因（`service.py:508-512` 的注释）。
随机源是注入的 `rng`（与抽签共用同一个 `random.Random` 实例，种子可测）。
返回值里的 `streak` 与 `score` 永远是**落库事实**，即使本次是重复签到。
</details>

<details>
### 抽签：档位权重、当日幂等与未知 key 回落

```mermaid
flowchart TD
    A["/mg 抽签 或 minigame__fortune"] --> B["FortuneGame.draw｜games/fortune.py:187"]
    B --> C{"mg_fortune 当日已有行?"}
    C -- 是 --> C1["reused=True：读库，不重抽不改动"]
    C -- 否 --> D{"fortune_include_bad_luck?"}
    D -- 是 --> D1["七档：5/15/25/30/25 + 小凶 8 + 凶 3，权重和 111"]
    D -- 否 --> D2["五档：5/15/25/30/25，权重和 100"]
    D1 --> E["pick_level :63<br/>point = rng.random() × total<br/>累计权重首次超过 point 即命中"]
    D2 --> E
    E --> F["draw_fortune｜service.py:601<br/>INSERT … ON CONFLICT DO NOTHING → SELECT"]
    F --> G["level_for :58 按落库 result_key 取档"]
    C1 --> G
    G --> H{"result_key 未知或为空?"}
    H -- 是 --> H1["回落「平」｜fortune.py:60<br/>绝不抛异常"]
    H -- 否 --> H2["用落库 result_text"]
    H1 --> I["卡片主题缓存键 user_id:day<br/>同一天重发风格一致"]
    H2 --> I
    I --> J["sync_reply=True 交 agent 组织文案<br/>抽签不产生任何积分变动"]
```

权重是**插件常量**（`fortune.py:34-46`），只有「是否含凶兆」可配。
末档兜底是 `table[-1]`（七档时是「凶」），与 `level_for` 的回落档「平」**不是同一个**：
落库 key 损坏时永远显示「平」，不会突然变成「凶」。
随机源是 `request.runtime.rng()`，与签到、接龙目标共用一个实例。
</details>

<details>
### 排行榜、流水与清理节流

```mermaid
flowchart TD
    A["/mg rank [页码]｜__init__.py:816"] --> B{"token 非空且非数字，或数字小于 1?"}
    B -- 是 --> B1["rank_format_fallback :857<br/>sync_reply=True 交 agent 追问页码"]
    B -- 否 --> C["page = token 或 1"]
    C --> D["service.leaderboard :679｜RANK_PAGE_SIZE=10"]
    D --> E["SELECT … ORDER BY score DESC, updated_at ASC<br/>LIMIT / OFFSET"]
    E --> F{"rows 为空?"}
    F -- 是 --> F1["固定文案：排行榜还没有数据"]
    F -- 否 --> G["文本：序号 + user_id + 分数<br/>再追加本群榜"]
    G --> H["group_leaderboard :694<br/>SUM(mg_record.score) GROUP BY user_id，LIMIT 5，无分页"]
    I["points.rank 能力 :1263"] --> J{"conversation_id 非空?"}
    J -- 是 --> J1["scope=group，total=返回行数（不是总人数）"]
    J -- 否 --> J2["scope=global，page_size 限 1-100"]
    K["add_record :627"] --> L["_maybe_cleanup :650"]
    L --> M{"本进程第一次调用?"}
    M -- 是 --> M1["只记 _last_cleanup_at，不清理"]
    M -- 否 --> N{"距上次不足 3600s?"}
    N -- 是 --> N1["跳过"]
    N -- 否 --> N2["cleanup_records :667<br/>DELETE created_at 早于 now - record_keep_days"]
```

全球榜的 `total` 是 `mg_profile` 的**行数**，而 0 分行会被查询接口惰性创建
（`ensure_profile` 由 `get_profile` / `points` 触发），因此「查过积分」也会进榜尾。
发瓶 / 捞瓶写入 `mg_record.game_id` 的是 `bottle:send` / `bottle:pick`（`service.py:27-28`），
**不是** `bottle` —— 按玩法聚合流水时要留意这个口径。
清理只在 `add_record` 之后触发，且**进程启动后的第一个小时不清理**（A25 的 SQL 审计口径）。
</details>

<details>
### 漂流瓶发瓶：四道校验后才写库

```mermaid
flowchart TD
    A["/mg 瓶 丢 文本 或 /mg 瓶 匿名 文本"] --> B["split_head｜bottle.py:43<br/>raw_args 优先，保留正文连续空格"]
    B --> C["BottleGame.write｜bottle.py:258"]
    C --> E{"去空白后为空?"}
    E -- 是 --> E1["need_agent：未写入瓶池"]
    E -- 否 --> F{"长度超过 bottle_content_max_chars 默认 500?"}
    F -- 是 --> F1["need_agent：报超字数，未写库"]
    F -- 否 --> G{"is_pure_link :44 每段都是 URL?"}
    G -- 是 --> G1["need_agent：纯链接不能丢，未写库"]
    G -- 否 --> H{"daily_plays 已达 5（BOTTLE_SEND_DAILY_LIMIT）?"}
    H -- 是 --> H1["need_agent：额度用完，未写库"]
    H -- 否 --> I["avatars.refresh + avatars.path<br/>失败不影响发瓶"]
    I --> J["add_bottle｜service.py:268"]
    J --> K{"pool_count 已达 bottle_pool_max 默认 1000?"}
    K -- 是 --> K1["ORDER BY RANDOM LIMIT 1<br/>status 置 expired（随机转档）"]
    K -- 否 --> L["INSERT mg_bottle status=pooled"]
    K1 --> L
    L --> M["bump_daily + add_score +1 play=True<br/>add_record game_id=bottle:send"]
    M --> N["BottleCard：匿名时 sender_label=神秘的人<br/>sender_id_label 留空、头像照常"]
    N --> O{"command_ctx 非空?"}
    O -- 否 --> O1["返回纯文本卡片给模型"]
    O -- 是 --> O2["deliver_card :421<br/>出图或发图失败回 build_card_text"]
```

四道校验**都在写库之前**，命中任意一条都只走 `need_agent`（命令通道置 `sync_reply`，
工具通道返回「事实 + 提示」文本），瓶池、每日计数、积分三者一个都不动。
`add_bottle` 返回的 `archived_id` 只在真的转档成功时非空（`service.py:296`）；
注意它随后用 `ORDER BY id DESC LIMIT 1` 取新瓶 id —— 并发发瓶时这不是本条的 id。
发瓶积分 +1（`BOTTLE_SEND_SCORE`），`play=True` 让 `plays` 加 1，`wins` 不加。
</details>

<details>
### 漂流瓶捞瓶：排除、回落与 5 次重试

```mermaid
flowchart TD
    A["/mg 瓶 捞 或 minigame__bottle_pick"] --> B["BottleGame.pick｜bottle.py:352"]
    B --> C{"daily_plays 已达 5（BOTTLE_PICK_DAILY_LIMIT）?"}
    C -- 是 --> C1["need_agent：额度用完，未捞未写库"]
    C -- 否 --> D["recent_picked_senders :322<br/>最近 3 条 picked 按时间倒序后去重"]
    D --> E["pick_bottle｜service.py:342<br/>SQL 恒带 sender_id 不等于自己"]
    E --> F{"带全部排除条件抽到行?"}
    F -- 否 --> G{"excluded 非空且 fallback 为真?"}
    G -- 是 --> G1["清空排除再抽一次<br/>used_fallback=True"]
    G -- 否 --> H["bottle=None → need_agent 说明空池"]
    F -- 是 --> I["UPDATE status=picked<br/>WHERE id 匹配 AND status=pooled"]
    G1 --> I
    I --> J{"rowcount 为 1?"}
    J -- 否 --> K{"重试次数少于 5?"}
    K -- 是 --> L["重新抽一行再试（软删不会丢行）"]
    K -- 否 --> H
    J -- 是 --> M["bump_daily + add_score +1 play=True<br/>add_record game_id=bottle:pick"]
    L --> F
    M --> N["卡片：匿名瓶只显示头像与「神秘的人」<br/>used_fallback 时追加提示行"]
```

排除表是「SQL 先 LIMIT 3 行、再 Python 去重」，所以**实际排除的不同发送者可能少于 3 个**。
回落路径只去掉「最近 3 位发送者」，**仍然排除自己**。
捞瓶无冷却：连捞只受每日 5 次限制。
第 5 次重试仍被并发抢走时会返回 `bottle=None`，用户看到的是「空池」——
池子可能并不空，这是并发下的已知语义。
</details>

<details>
### 成语接龙对局态：进程内字典的生命周期

```mermaid
flowchart TD
    A["/mg 成语接龙 [词]｜chengyu.py:276 或工具 chengyu_submit :400"] --> B["active_session :219<br/>查 chengyu_sessions[conversation_id]"]
    B --> C{"字典里有会话?"}
    C -- 否 --> D["submit 回「先开一局」，不记分"]
    C -- 是 --> E{"finished 为真?"}
    E -- 是 --> D
    E -- 否 --> F{"now - last_submit_at 超过 step_timeout_seconds 默认 60?"}
    F -- 是 --> F1["close_session :230 reason=timeout<br/>从字典 pop"]
    F -- 否 --> G["返回会话"]
    G --> H["submit：words.append + participants.add<br/>last_submit_at = monotonic"]
    H --> I["add_score +1 play=True + add_record game_id=chengyu"]
    I --> J{"steps 达到 target 默认 3-10?"}
    J -- 是 --> J1["额外 +target 分 win=True<br/>close_session reason=reached"]
    J -- 否 --> K{"steps 达到 max_steps 默认 10?"}
    K -- 是 --> K1["close_session reason=steps_exhausted<br/>不扣分"]
    K -- 否 --> L["返回进度「第 k/N 条」"]
    M["/mg stop → stop :363 / can_stop :381"] --> N{"发起者本人或持有 PERM_SUB_ADMIN?"}
    N -- 否 --> N1["固定文案：只有发起者或次级管理员"]
    N -- 是 --> N2["close_session reason=stopped<br/>note_session_closed :369 留痕"]
```

* 会话态**只在内存**（`MinigamePlugin.chengyu_sessions`:203），`unload`:273 清空；重启即无局。
* 超时**不是定时器**：只有下一次有人交互时 `active_session` 才发现过期并关局；
  没人再来，这条会话就一直躺在字典里。
* `submit` **不校验内容**（是否成语、接不接得上、是否重复全交 AI），也不校验提交者是不是参与者 ——
  `participants` 只记录、从不参与判定与计分。
* 命令入口报一个词时也只出「待判定」卡片并请 AI 判定；AI 不调工具就**什么都没记**。
* `can_stop` 里「工具通道（`command_ctx is None`）一律放行」的分支目前**没有调用方**：
  没有 stop 工具，`stop` 只被命令路径调用。
</details>

<details>
### 卡片渲染：主题选择、20 秒超时与三种降级

```mermaid
flowchart TD
    A["pick_card_theme :301"] --> B{"cache_key 非空且命中 _theme_memo?"}
    B -- 是 --> B1["直接返回记住的主题"]
    B -- 否 --> C["resolve_theme｜themes.py:512"]
    C --> D{"theme_mode?"}
    D -- fixed --> D1["用配置 theme，留空用 default_theme :507"]
    D -- random --> D2["候选池过滤 is_registered 后 rng.randrange"]
    D1 --> E{"候选主题已注册?"}
    D2 --> E
    E -- 否 --> E1["回落 default"]
    E -- 是 --> F["写 memo：上限 64，超出 pop 最早插入项"]
    F --> G["日志「小游戏卡片主题：玩法 X，模式 Y，本次使用 Z」"]
    G --> H["build_card_html｜bottle.py:109 / checkin.py:46<br/>fortune.py:99 / chengyu.py:98"]
    H --> I["render_card :337 → render_card_image<br/>timeout=20.0"]
    I --> J{"screenshots 端口可用?"}
    J -- 否 --> J1["返回 None：降级"]
    J -- 是 --> K["逐级尝试 element/full_page × 等字体/不等字体"]
    K --> L{"拿到渲染数据?"}
    L -- 否 --> J1
    L -- 是 --> M["send_card :345 按 kind 构造 group/private 事件"]
    M --> N{"发送成功?"}
    N -- 否 --> J1
    N -- 是 --> N1["bottle/chengyu 返回 None：不再发重复文本"]
```

**三种降级要分清**：

| 玩法 | 渲染或发送失败时用户看到什么 |
|---|---|
| 漂流瓶 | `deliver_card` 返回 `build_card_text`，由命令通道当固定文本发出 |
| 成语接龙 | `deliver_card` 的返回值被 `run` / `stop` **丢弃**，用户只看到 agent 组织的那句话 |
| 签到 / 抽签 | 命令通道根本不调 `build_card_text`：只出图，文案一律由 agent 说 |

主题随机源是独立的 `_theme_rng`（`__init__.py:210`），**不消耗**玩法随机数
（签到分数 / 抽签档位 / 接龙目标）。`_theme_memo` 是 FIFO（`pop(next(iter(...)))`），不是 LRU。
签到 / 抽签用 `user_id:day` 作 cache_key，所以当天重复请求是同一张图；漂流瓶与接龙不缓存。
</details>

<details>
### 跨插件积分能力：四个接口的契约与错误语义

```mermaid
flowchart TD
    A["其它插件 require_plugin('minigame')"] --> B["handle.call('points.get' / 'points.add' / 'points.rank' / 'points.describe')"]
    B --> C["points.get :1223 → points_snapshot :661"]
    C --> C1["score/best_score/plays/wins 来自 mg_profile<br/>streak/checked_in_today 来自**今天**的 mg_checkin"]
    B --> D["points.add :1236 → adjust_points :683"]
    D --> D1{"入参非法?"}
    D1 -- 是 --> D2["抛 ValueError：缺 user_id / delta 非整数<br/>超 points_max_delta / 布尔写成别的词"]
    D1 -- 否 --> D3{"余额不足且未开 allow_negative?"}
    D3 -- 是 --> D4["ok=False reason=insufficient applied=0"]
    D3 -- 否 --> D5{"总开关 points_allow_external_write?"}
    D5 -- 否 --> D6["ok=False reason=disabled"]
    D5 -- 是 --> D7["ok=True applied=delta score=新余额"]
    B --> E["points.rank :1263 → points_rank :756"]
    E --> E1{"page_size 超出 1-100 或 page 小于 1?"}
    E1 -- 是 --> E2["抛 ValueError"]
    E1 -- 否 --> E3["scope=global 或 group（group 时 total=行数）"]
    B --> F["points.describe :1280<br/>api=minigame.points / version=1 / capabilities / max_delta"]
    D7 --> G["_log_points :806：成功 info、被拒 warning"]
```

契约的分界：**可预期的业务结果一律用返回值**（`ok` / `reason`），
**参数或环境错误才抛异常**（`ValueError`；插件未加载时 `require_service`:654 抛 `RuntimeError`）。
`points.get` 的 `streak` 语义容易误读：它读的是**今天**那一行，
所以「昨天连签 5 天、今天还没签」查到的是 `streak=0` 且 `checked_in_today=false`。
写入口只有 `points.add` 一个，且**不对模型暴露**（没有加减积分的工具）。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `_latest` 认人记录 | `remember_interaction`:381（命令 :538、关键词 :939） | 无人清理，只被下一次覆盖；过期只在读时判定 | `resolve_user` 认不出人 → 工具回 `NEED_IDENTITY_HINT`，不写库 |
| `_theme_memo` 主题记忆 | `pick_card_theme`:301（带 cache_key 时） | 超过 64 条 pop 最早插入项；`unload`:275 | 主题解析失败回落 `default`，不影响出图 |
| `chengyu_sessions` 对局态 | `start_session`:343 | `close_session`:230（timeout / reached / steps_exhausted / stopped）与 `unload`:273 | 过期只在有人再次交互时惰性关局；关局后字典无该会话 |
| `_closed_sessions` 关局留痕 | `note_session_closed`:369 | **无人清理**（`unload` 也不清），纯内存 | 只影响内存占用，不落库、不影响玩法 |
| `_keyword_hits` | `on_keyword`:946 | **无人清理** | 仅测试与观测用 |
| `mg_daily.plays` | `bump_daily`:247 | 跨日自然失效（主键含 day） | 达到 5 次时不写库、转 `need_agent` |
| `mg_checkin` 当日名额 | `_claim_checkin`:505 的 INSERT rowcount=1 | 跨日新行（旧行保留） | rowcount=0 表示并发已被占，本次不加分 |
| `mg_fortune` 当日结果 | `draw_fortune`:601（ON CONFLICT DO NOTHING） | 跨日重抽 | 已存在只读库重发，绝不覆盖 |
| `mg_bottle.status` | `add_bottle`:298 写 pooled；`pick_bottle`:382 写 picked；池满转档写 expired:293 | 没有任何 DELETE | 全程软删；捞取并发冲突重试 5 次后回「空池」 |
| `mg_profile.score` | `add_score`:151 / `apply_points`:182 / `_claim_checkin`:551 | 只由 `points.add` 的负 delta 减少 | 扣分不足整笔不生效（`insufficient`） |
| 卡片 PNG | `render_card`:337，一次一图 | 无状态 | 返回 `None` → 纯文本或交 agent（见表） |

## 易错点

* **300 秒是「工具认人窗口」，不是对局时限**：`INTERACTION_TTL_SECONDS`:72 只影响
  「工具调用认哪个用户」；对局时限是 `chengyu_step_timeout_seconds`（60 秒）。
  两者都过期时表现完全不同：前者回引导文案，后者关局并留痕 `timeout`。
* **`_latest` 是全局单槽**：多用户/多群并发用工具时会串人。要精确定位必须显式传 `user_id`；
  显式传了 id 但没传名字时，昵称只在「记录同号」的情况下才补。
* **每日上限 5 + 5 是模块常量**（`service.py:31-32`），不是配置项 ——
  想改额度只能改代码，面板里找不到。
* **上限判定是 check-then-act**：`daily_plays` 读 → 之后才 `bump_daily` 写，
  并发发瓶/捞瓶可以越过 5 次（签到用 INSERT rowcount 做到了真幂等，瓶子没有）。
* **`add_bottle` 的新瓶 id 是「表里 id 最大的行」**（`service.py:319`），
  并发下可能取到别人的 id；它只用于内部返回值，不参与业务判断，但不要拿它当审计依据。
* **`apply_points` 与 `add_score` 语义不同**：前者是给外部的安全写入口（整笔生效/整笔不生效），
  后者无任何保护；本插件内部一律用 `add_score`，因为它只写正分。
* **`streak` 在查询接口里等于「今天签到行的 streak」**：今天没签到就是 0，
  哪怕昨天已经连签 5 天；不要把它当成「历史最长连续」。
* **抽签权重和不是 100**：开凶兆后是 111，`pick_level` 用累计权重比较，本身没问题；
  但 `level_for` 的未知 key 回落是「平」，不是档位表最后一档「凶」。
* **成语接龙超时不主动关局**：没有定时器，`active_session` 只在被调用时判过期；
  `_closed_sessions` 与 `_keyword_hits` 只增不减，长跑进程里是缓慢的内存增长。
* **`deliver_card` 的纯文本回落有两个消费口径**：漂流瓶会把它发给用户，
  成语接龙把它丢掉（用户只看到 agent 的话）。改这块时别把「有返回值」当成「用户看得到」。
* **签到 / 抽签的命令通道不发降级文本**：渲染失败时用户只看到 agent 的回复，
  这是刻意的（`games/checkin.py:195`、`games/fortune.py:230` 的 `sync_reply` 语义），
  不要照抄 `bottle` 的降级写法以为它坏了。
* **`/mg help` 不出图**、`/mg help <未知玩法>` 回固定文案（`help_command`:873），
  这是唯一一处「格式错却不走 agent 追问」的分支 —— 与 `rank` / 玩法的处理哲学不一致（W4）。
* **排行榜与流水的口径**：全球榜排序是 `score DESC, updated_at ASC`（并列时先修改的在前）；
  本群榜是 `SUM(mg_record.score)`，而发瓶/捞瓶写的 `game_id` 是 `bottle:send` / `bottle:pick`。
  `points.rank` 传 `conversation_id` 时 `total` 是本次返回行数，不是该群总人数。
* **群聊里 `/mg` 必须先 @bot**（`commands/service.py:158`），否则命令不会被消费 ——
  「命令没反应」的第一排查点在这里，不在本插件。
* **命令返回 `None` 表示「已自行发图，不要再发文本」**（`commands/service.py:207`）：
  漂流瓶成功出图时走的就是这条；把返回值改成空串会让用户收到一条空消息。
* **关局理由只有内存留痕**（`timeout` / `stopped` / `reached` / `steps_exhausted`），
  不写数据库；要统计「多少局超时」需要先把它落库。
