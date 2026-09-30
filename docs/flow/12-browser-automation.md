---
flow: 12-browser-automation
covers:
  - app/src/neobot_app/browser/
  - app/src/neobot_app/runtime/browser_lifecycle.py
verified_against: 99836cd
verified_hash: 34bfa260e6b9
---

# 12 浏览器自动化：DrissionPage 会话管理 · 动作集 · per-chat-flow 生命周期

## 范围

本图覆盖 **agent-browser 这条浏览器链路**（面向"点网页"，不是"搜网页"）：

* `browser/agent_browser/manager.py`（2262 行）：`BrowserManager` —— Chromium 启动与重建、
  可执行文件解析、实例注册表、页面/标签页、100+ 个动作方法、截图/录屏、Cookie/Storage/状态持久化；
* `browser/agent_browser/actions.py`（828 行）：`AgentBrowser` —— 薄封装层，统一
  `{"success": bool, "timestamp": ...}` 结果协议；
* `browser/agent_browser/snapshot.py`（210 行）：可访问性快照与 `@eN` 引用解析；
* `browser/__init__.py`（364 行）：`BrowserAgentWrapper`（懒启动 + 后台共享锁）与
  `BrowserScreenshotBackend`（给 `ScreenshotService` 用的 Port 后端）；
* `runtime/browser_lifecycle.py`（185 行）：`BrowserLifecycleManager` —— 每个聊天流一份
  `last_access / held_until / tab_ids`，60s 后台循环回收空闲流。

**不画什么**（边界要记牢）：

| 内容 | 去哪张图 |
|---|---|
| `skills/browser_skill.py`、`browser_network_skill.py`、`browser_video_skill.py` 的工具表与 `{skill}__{tool}` 路由 | 06 工具与技能 |
| `bootstrap/_runtime.py:121 build_browser_components` 的装配细节、`application.start/stop` 的 S11/停机步 | 01 启动装配 |
| `reply/tools.py:1041` 往技能参数里注入 `pipeline_key` 的过程 | 03b 回复管线工具面 |
| `ScreenshotService` 的 HTML 准备、字体/图片等待、`html_card` 降级 | 13 渲染与卡片 |
| `web_search/browser_channel.py`（Playwright 独立驱动） | 10 联网搜索 |

**两条浏览器链路必须分清**（同仓不共用代码、不共用进程）：

| | 本图（agent-browser） | 10 图（browser_channel） |
|---|---|---|
| 驱动 | DrissionPage 的 `ChromiumPage` | Playwright `async_playwright` |
| 可执行文件 | `_find_chrome_binary()`：`CHROME_PATH` → Playwright Chromium → 系统 Chrome/Edge | `_resolve_chromium()`：只认 `%LOCALAPPDATA%/ms-playwright`，优先 `chrome-headless-shell` |
| 会话 | 持久化 user_data_dir（`DATA_DIR/browser`）+ cookies.json | 每次 launch 新 context，无 profile |
| 用途 | 模型可见的 `browser__*` 工具、HTML 截图 | Bing 第三级回退检索 |
| 失败语义 | 方法吞异常返回 `success: False` | `available()` 为假就跳过本级 |

**spec / 直觉与现实的差异**（本图逐条落到节点上，详见「易错点」）：

1. 文档（`docs/04-功能文档/浏览器.md`）说 `browser_video` 是"视频获取（解析网页中的视频地址）"，
   实现是 **GIF 录屏**（`record_start/stop/restart`），没有任何视频地址解析。
2. `agent.browser.data_dir`（默认 `./data/browser/`）**是死配置**：`build_browser_components`
   用的是全局 `DATA_DIR / "browser"`（`bootstrap/__init__.py:856`）；同理 `headless`/`port`
   在 `AgentBrowser` schema 里根本不存在，只靠 `getattr(cfg, "headless", True)` 回落。
3. `neobot open_web` 手动登录写的是 `DATA_DIR/browser/profiles/manual_login`，而运行时
   Chromium 的 user_data_dir 就是 `DATA_DIR/browser` —— 两者不是同一个 profile，
   「登录一次后续复用」并没有实现。
4. `BrowserLifecycleManager.hold()` / `release()` / `is_held()` / `active_flow_count` 全仓
   **只有测试调用**，没有任何技能或面板暴露 hold —— 「保活 2 小时」是死路径。
5. `BrowserSkill._check_lifecycle` 调用了 **不存在** 的 `BrowserLifecycleManager.should_auto_close()`；
   该方法自身零调用点，所以现在不炸。

## 流程

```mermaid
flowchart TD
    A["build_browser_components / bootstrap/_runtime.py:121"] --> B{"agent.browser.enabled?"}
    B -- 否 --> B1["UnavailableScreenshots：render/save 抛 ScreenshotUnavailable"]
    B -- 是 --> C{"_find_chrome_binary() 命中?"}
    C -- 否 --> C1["_auto_install_chromium: playwright install chromium，timeout 300s"]
    C1 --> C2{"再查仍为空?"}
    C2 -- 是 --> B1
    C2 -- 否 --> D
    C -- 是 --> D["BrowserLifecycleManager + BrowserAgentWrapper + ScreenshotService 装配"]
    D --> E["技能调用 browser__* / browser_network__* / browser_video__*"]
    E --> F["Skill.execute：operation_lock 串行 + lifecycle.touch(pipeline_key)"]
    F --> G["BrowserAgentWrapper._ensure：_init_lock 内懒建 AgentBrowser 并 start()"]
    G --> H{"AgentBrowser._started?"}
    H -- 否 --> H1["BrowserManager.start：杀残留 → 3 次重试 → 恢复 cookies"]
    H -- 是 --> I
    H1 --> I["分发到 manager 的动作方法 / manager.py:364-2262"]
    I --> J{"动作是否需要活页面?"}
    J -- 是 --> K["_ensure_page：读 page.url 探活 / manager.py:350"]
    K -- 抛异常 --> K1["close() + start() 整机重启，最多再试 3 次"]
    K -- 正常 --> L
    K1 --> L["执行动作，返回 dict(success=...)"]
    L --> M{"动作内部异常?"}
    M -- 是 --> M1["catch 成 success=False + error 文本；不冒泡"]
    M -- 否 --> N
    M1 --> N["技能层包成 {ok: ...} JSON 文本回灌模型"]
    N --> O{"该聊天流有登记的 tab_id?"}
    O -- 是 --> P["_switch_to_flow_tab 切回本流标签页 + 刷新 last_access"]
    O -- 否 --> Q
    P --> Q["后台每 60s：空闲 600s 的流 → _close_flow_tabs 关标签页 → 丢掉流状态"]
    N -.-> R["停机：_persist_state → quit(timeout=3) → Windows 再补 taskkill /F"]
```

主干三句话：**装配只做对象、不启浏览器**（`_ensure` 才懒启动）；**所有动作的失败都收敛成
`success: False` 的 dict**（只有截图 Port 会抛 `ScreenshotError`）；**会话归属靠
`pipeline_key`→`tab_ids` 映射**，回收是 60s 轮询而不是引用计数。

## 时序

```mermaid
sequenceDiagram
    autonumber
    participant SK as BrowserSkill 等三个技能
    participant BW as BrowserAgentWrapper
    participant AB as AgentBrowser
    participant BM as BrowserManager
    participant CH as Chromium 进程
    participant LM as BrowserLifecycleManager
    participant SS as ScreenshotService

    SK->>BW: execute：先拿 operation_lock（跨聊天流串行）
    SK->>LM: touch(pipeline_key) + _switch_to_flow_tab
    SK->>BW: 具体动作（navigate / click / screenshot ...）
    BW->>AB: _ensure()（_init_lock 内，首次建实例）
    AB->>BM: start()——浏览器没起才走，venv 里可能耗时数秒
    BM->>CH: ChromiumPage(ChromiumOptions)，失败重试 3 次，间隔 1.5s
    BM->>BM: _restore_persisted_state：只回灌 cookies，不回灌 localStorage
    AB-->>BW: manager 就绪
    BW->>BM: 转发动作（每个动作再 _notify_lifecycle —— 当前是 pass）
    BM->>CH: CDP / run_js / DrissionPage 调用（多数经 asyncio.to_thread）
    CH-->>BM: 结果或异常
    BM-->>SK: dict(success, ...)；异常在这里被吞成 error 字段
    Note over SK,BM: 单次动作失败不致命；只有 _ensure_page 探活失败会整机重启
    SS->>BM: render()：持同一把 operation_lock + asyncio.timeout(30s 默认)
    BM->>CH: _open_temporary_page → setDocumentContent → Page.captureScreenshot
    BM-->>SS: ScreenshotResult；失败抛 ScreenshotError/ScreenshotTimeout
    Note over SS,BM: 截图链路是唯一会把异常抛给调用方的入口（html_card 侧再降级）
    LM->>BM: 每 60s：对空闲流 list_tabs → close_tab（经 set_close_callback）
    Note over LM,BM: 空闲判定只认 last_access，且没有生产代码调用 hold()，保活永不生效
```

## 细节

<details>
### 三层对象：谁负责懒启动、谁负责锁、谁负责真实浏览器

```mermaid
flowchart TD
    A["BrowserAgentWrapper / browser/__init__.py:43"] --> A1["_data_dir / _headless / _port / _browser_path 来自 bootstrap"]
    A1 --> A2["_init_lock：建 AgentBrowser 用"]
    A2 --> A3["_operation_lock：跨聊天流串行，透传给 BrowserManager"]
    A3 --> B["AgentBrowser / actions.py:18"]
    B --> B1["_started：只有 start() 置真、close() 置假"]
    B1 --> B2["_ensure() 用 self.__dict__.setdefault 懒建 asyncio.Lock / actions.py:69"]
    B2 --> C["BrowserManager / manager.py:154"]
    C --> C1["_page = 当前操作目标；_session_page = 浏览器根"]
    C1 --> C2["_tab_pages / _tab_labels / _init_scripts"]
    C2 --> C3["__init__ 建目录 + _cleanup_locks + _register_instance / manager.py:182-184"]
    D["BrowserScreenshotBackend / browser/__init__.py:19"] --> D1["get_manager(): _closed 为真直接抛 ScreenshotUnavailable"]
    D1 --> D2["否则 wrapper._ensure()._manager —— 截图会顺手把浏览器拉起来"]
    E["BrowserAgentWrapper.close / __init__.py:105"] --> E1["_closed=True + agent.close() + _agent=None"]
    E1 -.-> E2["但 _ensure() 无条件把 _closed 置回 False / __init__.py:96"]
    E2 -.-> E3["后果：停机后一个迟到的技能调用可静默重启 Chromium"]
```

* `_ensure()` 里 `if not self._agent._started: await self._agent.start()`，
  且启动成功后调 `lifecycle.set_browser_instance(self)`（`__init__.py:90-96`）——
  同一个 wrapper 会被重复设置成 lifecycle 的 browser 实例（bootstrap 也设过一次）。
* `BrowserAgentWrapper._notify_lifecycle()` 是 **NO-OP**（`__init__.py:113-120`），
  每个动作后都 await 它一次：注释写明「不在此自动关闭浏览器，否则标签页状态会丢」。
  别把它当有效链路找日志。
* `manager.page` 是 `assert self._page is not None` 的 property（`manager.py:306-309`），
  没启动就访问会抛 `AssertionError`（不是 `RuntimeError`）。
</details>

<details>
### 可执行文件解析与启动参数：四级回退 + 一份写死的开关表

```mermaid
flowchart TD
    A["_find_chrome_binary / manager.py:105"] --> B{"CHROME_PATH 环境变量?"}
    B -- 有 --> Z["直接返回"]
    B -- 无 --> C["_playwright_chromium_path / manager.py:86"]
    C --> C1["Win: ms-playwright/chromium-*/chrome-win/chrome.exe"]
    C --> C2["Linux: chrome-linux 或 chrome-linux64"]
    C --> C3["macOS: chrome-mac/Chromium.app/..."]
    C1 --> C4["sorted()[−1] 取字典序最后一个"]
    C4 --> D{"命中?"}
    D -- 是 --> Z
    D -- 否 --> E["系统候选列表"]
    E --> E1["Windows: which(msedge)/which(chrome) 插到最前"]
    E1 --> E2["再试 Program Files 的 Chrome / Chromium / Edge 与 LOCALAPPDATA"]
    E2 --> E3["Linux/macOS 固定路径"]
    E3 --> F{"存在?"}
    F -- 是 --> Z
    F -- 否 --> G["返回空串 → bootstrap 走自动下载或降级"]
    H["_make_options / manager.py:271"] --> H1["set_browser_path / set_user_data_path / local_port"]
    H1 --> H2["--disable-blink-features=AutomationControlled"]
    H2 --> H3["ignore_certificate_errors(True) + set_load_mode(eager) + --no-sandbox"]
    H3 --> H4{"headless?"}
    H4 -- 是 --> H5["co.headless(True) + 伪装 UA Chrome/120 + --disable-gpu"]
    H4 -- 否 --> H6["--start-maximized/--window-size=1280,800 + 9 个 GPU 与后台节能开关"]
```

**实测（本机 `%LOCALAPPDATA%/ms-playwright`）**：同时存在 `chromium-1148/chrome-win/chrome.exe`
与 `chromium-1223/chrome-win64/chrome.exe`，而 `_playwright_chromium_path()` 的 Windows glob
只认 `chrome-win`，所以自动检测拿到的是**旧构建 r1148**；`chrome-win64` 那一份永远匹配不到。
同理 `sorted(candidates)[-1]` 是按字符串排序，`chromium-999` 会排在 `chromium-1000` 之后，
"取最新 revision" 只在位数相同时成立。

文档写"Chrome > Edge > Chromium"，实际 Windows 上 `shutil.which("msedge")` 被 `insert(0)`
到最前，**PATH 里有 Edge 就用 Edge**；而 Playwright Chromium 又整体优先于系统 Chrome。
</details>

<details>
### 启动、探活与整机重建：3 次重试与"任何异常都重启"

```mermaid
flowchart TD
    A["BrowserManager.start / manager.py:239"] --> B["_kill_orphaned_chrome / manager.py:198"]
    B --> B1{"Windows 且无其它存活实例?"}
    B1 -- 否 --> C
    B1 -- 是 --> B2["psutil 扫 cmdline 含该 user_data_dir 的 chrome 进程 kill + wait(3)"]
    B2 --> C["attempt = 0"]
    C --> D["asyncio.to_thread(_start_sync): ChromiumPage(ChromiumOptions)"]
    D --> E["记 _chrome_pid（取不到就 None）"]
    E --> F["读 page.url 探活 → _restore_persisted_state()"]
    F --> G{"成功?"}
    G -- 是 --> Z["返回"]
    G -- 否 --> H{"attempt < 2?"}
    H -- 是 --> H1["sleep(1.5) + quit 旧 session_page + 清 _page/_session_page → 重试"]
    H1 --> D
    H -- 否 --> H2["第 3 次仍失败：异常向上抛"]
    I["_ensure_page / manager.py:350"] --> I1["try: _ = page.url"]
    I1 --> I2{"抛异常?"}
    I2 -- 是 --> I3["close() + start() —— 整机重建"]
    I2 -- 否 --> I4["返回当前 page"]
    I3 --> I4
    J["close / manager.py:311"] --> J1["录制中先 _recording_stop（丢帧不落盘）"]
    J1 --> J2["_tab_pages.clear() → _persist_state()"]
    J2 --> J3["session_page.quit(timeout=3, force=False)"]
    J3 --> J4["Windows: psutil wait(5) 后【无条件】taskkill /F /PID"]
    J4 --> J5["_unregister_instance + _page/_session_page 置 None"]
```

* `except (PageDisconnectedError, Exception)` 中 `Exception` 已覆盖前者，元组写法是冗余的；
  真正后果是**任何**探活异常（含页面正在跳转）都会触发 close+start，重建期间该流的标签页全丢。
* `_MAX_RETRIES = 2` / `_RETRY_INTERVAL = 1.0`（`manager.py:37-38`）**没有任何读取点**；
  真正生效的是 `start()` 里写死的 `range(3)` 与 `sleep(1.5)`。
  `bugfixes/fix(12)/fallback-inventory.md:61` 记的"导航 = DrissionPage retry=1 + 自研 2 次"与本图实测不符：
  导航路径只有 `page.get(timeout=15, retry=1, interval=1)` 一层。
* `close()` 的注释写"仅在进程残留时才强制终止"，代码里 `if self._chrome_pid:` 紧接着就 taskkill，
  **没有判断进程是否已退出** —— 正常退出也会多跑一次 `taskkill /F`（失败被吞）。
* 实例注册表是弱引用（`manager.py:47-83`），只用来让 `_kill_orphaned_chrome` 判断
  "这个 user_data_dir 是否还有别的活实例"；`launch_headed` 会换一个新 `BrowserManager`，
  旧实例尚未被 GC 时新实例会误判"还有同伴"从而跳过残留清理。
</details>

<details>
### 动作集与选择器解析：一个 `_find_element` 吃掉五种写法

```mermaid
flowchart TD
    A["_find_element(selector) / manager.py:509"] --> B{"以 @e 开头?"}
    B -- 是 --> B1["snapshot.get_element_by_ref_sync：重跑采集再按 selector 找"]
    B -- 否 --> C{"含 :has-text(...)?"}
    C -- 是 --> C1["剥掉伪类先按 CSS 找；找不到再按 text= 找"]
    C -- 否 --> D{"含逗号?"}
    D -- 是 --> D1["逐个候选 CSS 试探，返回第一个命中"]
    D -- 否 --> E{"带 tag:/css:/text:/xpath:/@ 前缀?"}
    E -- 是 --> E1["原样交给 DrissionPage"]
    E -- 否 --> E2["补 css: 前缀查找"]
    E2 --> F{"仍未命中?"}
    F -- 是 --> F1["去掉符号字符，按长度>1 的词逐个 text= 模糊回退"]
    F -- 否 --> Z["返回元素"]
    F1 --> Z
    G["click / manager.py:559"] --> G1["index>0：page.eles(css)[index]，越界直接报错"]
    G1 --> G2["阶段1 el.click()（抛异常才算失败）"]
    G2 --> G3["_click_detected：URL 变化 / 元素脱离 DOM / tab 数增加"]
    G3 --> G4["阶段2 JS 派发 mousedown+mouseup+click"]
    G4 --> G5["阶段3 closest(a,button,[onclick],[role=button],...) 再派发"]
    G5 --> G6["阶段4 仅当元素是 a 标签才 location.href 跳转"]
    G6 --> G7["无论是否生效，都返回 success=True / manager.py:649"]
```

* **`_find_element` 支持 `text=` 与模糊回退，所以"选择器写错"经常表现为点到了别的元素**，
  而不是报"未找到元素"。`click` 返回的 `match_count` 是 CSS 匹配数，可以用来交叉验证。
* 输入类动作的 JS 回退：`type_text`（`manager.py:791`）在 `el.input()` 抛异常时用 JS 赋值，
  并**额外派发 Enter 的 keydown/keyup**；`press_key('Enter')`（`manager.py:819`）还会
  `form.dispatchEvent(submit)` + 点 submit 按钮 —— 一次输入失败可能顺手提交表单。
* `execute_js`（`manager.py:478`）：语句模式结果为空或含 `SyntaxError`/`Uncaught`，
  且脚本里没有 `return ` 时，会再用 `as_expr=True` 跑一次，两次都失败返回空串。
* `dblclick`（`764`）、`hover`（`942`）、`select_option`（`919`）等都直接透传 DrissionPage，
  失败一律 `{"success": False, "error": str(e)}`；`check`/`uncheck` 先读 `el.checked` 再决定是否点击。
* `upload_file`（`1009`）先 `Path(filepath).resolve()` + `exists()`，**没有任何沙箱或目录白名单**。
</details>

<details>
### 标签页与流归属：`index` 的两套口径与隔离标签页

```mermaid
flowchart TD
    A["new_tab / manager.py:1626"] --> A1["记 tab_ids_before → _session_page.new_tab(url) → sleep(0.2)"]
    A1 --> A2["差集里第一个新 id → activate_tab + 写 _tab_pages + _page 指向它"]
    A2 --> A3["返回 title；失败 success=False"]
    B["new_tab_label / manager.py:1645"] --> B1["直接取 tab_ids[-1] 作为新标签 id"]
    B1 -.-> B2["只保证取到最后一个 id，不保证是刚建的那个"]
    C["list_tabs / manager.py:1698"] --> C1["Target.getTargets 过滤 type in (page, webview)"]
    C1 --> C2["且 targetId 必须在 _browser.tab_ids 里"]
    C2 --> C3["index 是【过滤后】的下标；active 比对 page.tab_id"]
    D["switch_tab / close_tab / manager.py:1657,1725"] --> D1["用【未过滤】的 _browser.tab_ids 下标取 id"]
    D1 -.-> D2["两套下标在存在非 page 目标时会错位"]
    E["_open_temporary_page / manager.py:1566"] --> E1["原页面留存 → new_tab(None) → activate → _page 换成临时页"]
    E1 --> E2["失败：Target.closeTarget + 恢复原 tab + 重新抛出"]
    F["_close_temporary_page / manager.py:1607"] --> F1["closeTarget → 清 _tab_pages → activate 原 tab → _page 复位"]
    G["close_tab 关掉当前页"] --> G1["tab_ids 仍 >1 时激活 remaining[0] 并同步 _page"]
```

* 技能侧用 `list_tabs()` 的 `index` 再调 `switch_tab/close_tab`（`browser_skill.py:264-275`），
  所以上面那条"两套下标"的差异会直接落到**关错标签页**上；目前只在存在非 page 目标时出现。
* `_tab_pages` 只缓存"曾经激活过"的 tab；`switch_tab` 命中缓存就复用对象，否则 `get_tab()` 现取。
* `close()` 只清 `_tab_pages`，**不清 `_tab_labels`**；`close_tab` 才会按 id 删标签名。
* 截图链路专用：`ScreenshotService.render` 全程持 `operation_lock`，用临时标签页 +
  `Page.setDocumentContent` 注入 HTML，**不污染当前页面**（`screenshot.py:223-278`）。
</details>

<details>
### per-chat-flow 生命周期：touch / 空闲回收 / 空壳回收 / 关闭回调

```mermaid
flowchart TD
    A["reply/tools.py:1040 注入 pipeline_key = kind:id"] --> B["三个浏览器技能的 _run_tool 都先 touch + 切流标签页"]
    B --> C["touch / browser_lifecycle.py:88"]
    C --> C1{"该流已有状态?"}
    C1 -- 否 --> C2["建 _FlowState：last_access=now、held_until=None、tab_ids=空集"]
    C1 -- 是 --> C3["只刷新 last_access"]
    C2 --> D["browser__open：diff list_tabs 找新 tab → track_tab_open"]
    D --> D1["track_tab_open = touch + tab_ids.add（只登记第一个新 tab）"]
    E["_auto_close_loop / browser_lifecycle.py:197"] --> E1["每 60s 醒一次"]
    E1 --> E2["_get_idle_flows：有 tab_ids 且未 hold 且 now−last_access ≥ 600s"]
    E2 --> E3{"_on_close_flow 已注册?"}
    E3 -- 是 --> E4["bootstrap 的 _close_flow_tabs：list_tabs 映射 id→index 后逐个 close_tab"]
    E3 -- 否 --> E5["什么都不做，仅丢状态"]
    E4 --> E6["pop 该流状态"]
    E5 --> E6
    E6 --> E7["_get_stale_flow_ids：无 tab_ids 且超时的空壳一并 pop"]
    F["hold / browser_lifecycle.py:106"] --> F1["held_until = now + min(minutes 或 120, 120min)"]
    F1 -.-> F2["全仓无生产调用者：只有 app/tests/modules/runtime/test_browser_wait.py"]
    G["reset_flow / browser_lifecycle.py:134"] --> G1["技能 close 成功或流内无标签页时调用"]
    H["stop / browser_lifecycle.py:187"] --> H1["cancel 后台任务并 await（CancelledError 吞掉）"]
```

* `held_until` 的过期是**惰性**清零：`is_held`（`71`）与 `_get_idle_flows`（`151`）各自判一次；
  `_get_stale_flow_ids` 则要求 `now < held_until` 才算"还持有"。
* 回收是"先回调再 pop"，回调里的异常被 `except Exception: pass` 吞掉（`209`）——
  关标签页失败时**流状态照样被丢弃**，那些标签页从此不再被自动回收。
* `track_tab_close` 全仓只有测试调用；生产路径关标签页后靠 `reset_flow` 或 60s 循环兜底。
* `BrowserSkill._check_lifecycle`（`browser_skill.py:95`）调用不存在的 `should_auto_close()`：
  该方法没有任何调用点，所以 AttributeError 至今没被触发；接回去之前必须补这个方法。
</details>

<details>
### 截图三条链路：legacy JPEG / Port capture / 标注截图

```mermaid
flowchart TD
    A["manager.screenshot / manager.py:1492"] --> A1{"full_page?"}
    A1 -- 是 --> A2["body.scrollWidth/Height 做 clip，取不到回落 1280x720"]
    A1 -- 否 --> A3["无 clip：当前视口"]
    A2 --> A4["Page.captureScreenshot format=jpeg quality=85"]
    A3 --> A4
    A4 --> A5{"传了 path?"}
    A5 -- 是 --> A6["mkdir + write_bytes（内容是 JPEG）"]
    A5 -- 否 --> A7["只返回 bytes"]
    B["manager.capture(ScreenshotOptions) / manager.py:1417"] --> B1["_apply_temporary_capture_metrics：只有与现况不同才下发 CDP override"]
    B1 --> B2{"mode"}
    B2 -- element --> B3["querySelector + rect；找不到或面积 0 → ScreenshotTargetNotFound"]
    B2 -- viewport --> B4["用当前视口矩形"]
    B2 -- full_page --> B5["用 documentElement/body 的最大滚动尺寸"]
    B3 --> B6["args: format / quality / transparent / captureBeyondViewport / clip.scale=1"]
    B4 --> B6
    B5 --> B6
    B6 --> B7["base64 解码 + PIL 读像素尺寸 → ScreenshotResult"]
    B7 --> B8["finally：恢复上一次 metrics（有 override 就还原，没有就 clear）"]
    C["screenshot_annotated / manager.py:1525"] --> C1["page.get_screenshot(full_page=True) 存 annotated_*.png"]
    C1 --> C2["elements_data 里 rect 恒为空 dict / manager.py:1545"]
    C2 -.-> C3["画不出任何编号：名不副实的标注截图"]
    D["ScreenshotService.render / screenshot.py:204"] --> D1["operation_lock + asyncio.timeout(默认 30s)"]
    D1 --> D2["_open_temporary_page → setDocumentContent → 字体/图片等待 → capture"]
    D2 --> D3["超时→ScreenshotTimeout；其它→ScreenshotError；finally 收尾失败也可能抛"]
```

* 三条链路的**格式口径不同**：legacy 固定 JPEG q85；Port 走 `ScreenshotOptions`（默认
  `format=png, quality=90, scale=1.0`，`transparent=True` 与 JPEG 互斥，
  width/height 必须成对且 1..16384，scale 限 0.25..4 —— `contracts/ports/screenshot.py:94-129`）。
* `_apply_temporary_capture_metrics` 只在"请求尺寸/scale 与页面现况不同"时才动 CDP；
  `_device_metrics_override`（`set_viewport`/`set_device` 写的）会被当作"上一个状态"原样还原。
* `actions.shot()`（`actions.py:616`）文件名是 `.png` 但写进去的是 `screenshot()` 的 **JPEG 字节**；
  且没有生产调用点（技能里的 `shot` 走的是 `screenshot()` + PIL 转 PNG，`browser_skill.py:463-473`）。
* 停机时 `application._cleanup_browser_artifacts`（`application.py:511`）删
  `screenshots/*.jpg|png`、`annotated_*.png`、`recording_*.gif`，**不删** `cookies.json` 与
  `browser_state.json`。
</details>

<details>
### 录屏：0.5s 一帧、600 帧上限、GIF 固定 500ms

```mermaid
flowchart TD
    A["record_start / manager.py:2186"] --> A1["_recording_lock 内"]
    A1 --> A2{"_recording 已为真?"}
    A2 -- 是 --> A3["success=False: 已在录制中"]
    A2 -- 否 --> A4["_ensure_page → _recording=True → 清帧列表"]
    A4 --> A5["_record_path = 传入路径 或 user_data_dir/recording_时间戳.gif"]
    A5 --> A6["create_task(_record_loop)，返回 output 路径"]
    B["_record_loop / manager.py:2244"] --> B1["while _recording: screenshot() 得 JPEG 字节"]
    B1 --> B2{"帧数 > 600?"}
    B2 -- 是 --> B3["pop(0) 丢最旧的一帧"]
    B2 -- 否 --> B4["sleep(0.5)"]
    B3 --> B4
    B4 --> B1
    B1 -.-> B5["CancelledError → break；其它异常 → sleep(1) 后继续"]
    C["record_stop / manager.py:2201"] --> C1["_recording=False + cancel task"]
    C1 --> C2{"有帧?"}
    C2 -- 否 --> C3["success=True frames=0 path 空串"]
    C2 -- 是 --> C4["PIL 逐帧打开 → save(gif, duration=500, loop=0, optimize=False)"]
    C4 --> C5{"扩展名不是 .gif?"}
    C5 -- 是 --> C6["改名为同名 .gif 再写"]
    C4 -. ImportError .-> C7["只写 路径.json 记录帧数"]
    D["record_restart / manager.py:2258"] --> D1["录制中先 record_stop 再 record_start"]
    E["close() 且正在录制"] --> E1["_recording_stop：直接丢帧，不落盘"]
```

* 600 帧 × 0.5s ≈ **5 分钟**上限，与 `browser_video_skill` 的提示语一致；
  每帧都是完整 JPEG（quality 85），内存里最多压 600 份字节，长录屏是明显的内存开销。
* 帧间隔靠 `sleep(0.5)` 串行排队，截图本身耗时会让实际帧率低于 2fps，
  GIF 仍按 500ms/帧回放 —— 录出来的动作比真实更快。
* `record_stop` 里 `out_path` 取自 `self._record_path`：`record_start` 之后又 `record_restart`
  会重写该字段，最后一次的路径才是落盘位置。
</details>

<details>
### 每一层阈值总表：从技能到 CDP 的数字

```mermaid
flowchart TD
    A["技能/模型一次工具调用"] --> A1["operation_lock 串行，无超时上限（等待即排队）"]
    A1 --> B["actions.navigate 等正文：最多 16 次 × 0.5s = 8s，text_length>200 提前退出"]
    B --> C["manager._navigate: page.get(timeout=15, retry=1, interval=1)"]
    C --> D["BrowserManager.start: 3 次尝试，失败间隔 1.5s"]
    D --> E["close: quit(timeout=3) → Windows psutil wait(5) → taskkill timeout=5"]
    F["wait(condition, value, timeout=20)"] --> F1["selector/text：DrissionPage wait，timeout 秒"]
    F1 --> F2["url：每秒轮询，最多 timeout 次"]
    F2 --> F3["fn：每 0.5s 轮询，最多 timeout 次（约为 timeout/2 秒）"]
    F3 --> F4["timeout 条件：value 截到 0..30，默认 2；数字首参同样截 0..30"]
    G["截图"] --> G1["legacy：JPEG q85，无超时参数"]
    G1 --> G2["Port capture：RenderOptions.timeout 默认 30s（上层 asyncio.timeout）"]
    H["录屏"] --> H1["帧间隔 0.5s，帧上限 600"]
    I["生命周期"] --> I1["扫描间隔 60s，空闲阈值 auto_close_idle_seconds 默认 600s"]
    I1 --> I2["hold 上限 120min（无生产调用者）"]
    J["Chrome 下载"] --> J1["playwright install chromium，subprocess timeout=300s（仅未命中可执行文件时）"]
```

* `auto_close_idle_seconds` 在 `bootstrap/_runtime.py:154` 被整除成分钟并 `max(...,1)`，
  所以配置 30 秒实际是 **60 秒**粒度。
* 技能的 `operation_lock` 是进程级共享锁（三个技能 + 截图共用），
  单次慢动作（如 `wait` 30s）会**阻塞所有聊天流**的浏览器调用 —— 这是设计上的取舍，不是 bug。
* `_navigate` 的 15s 与 `actions.navigate` 的 8s 等待是**串联**的：最坏 23s 才返回。
</details>

<details>
### 网络拦截 / Cookie / Storage / 状态持久化：谁真的落盘

```mermaid
flowchart TD
    A["network_route / manager.py:1919"] --> A1["page.listen.start(url_pattern)（同步调用，占事件循环）"]
    A1 --> A2{"abort=True?"}
    A2 -- 是 --> A3["page.listen.wait() —— 无超时，没有匹配请求就永久卡住"]
    A2 -- 否 --> A4["只启动监听"]
    A3 --> A5["mock_body 参数被完全忽略：没有 mock 能力"]
    A4 --> A5
    B["network_unroute / manager.py:1931"] --> B1["page.listen.stop()（忽略 url_pattern）"]
    C["network_requests / manager.py:1940"] --> C1["listen.steps() 逐条映射 url/method/status"]
    D["save_cookies / load_cookies / manager.py:1830,1836"] --> D1["user_data_dir/cookies.json"]
    D1 --> D2["load 逐条 page.set.cookies，异常吞；返回条数"]
    E["_persist_state / manager.py:2091"] --> E1["cookies + localStorage + url + ts → browser_state.json"]
    E1 --> E2["close() 前调用；_page 为 None 直接返回"]
    F["_restore_persisted_state / manager.py:2112"] --> F1["start() 成功后调用"]
    F1 -.-> F2["只回灌 cookies，localStorage 不恢复（与 state_load 不对称）"]
    G["state_save / state_load / manager.py:2046,2064"] --> G1["同一份 JSON 可显式读写，localStorage 逐键 setItem"]
    H["storage_* / manager.py:1962-2016"] --> H1["run_js 拼 f-string：key 未转义，value 走 json.dumps"]
    I["cookies_set_curl / manager.py:1883"] --> I1["JSON 数组 或 Netscape 7 列 TSV"]
```

* `listen.*` 与 `page.cookies()` 是少数**没有进 `asyncio.to_thread`** 的调用；
  `listen.wait()` 无超时是明确的挂起风险（技能工具 `network_route(abort=True)` 可直达）。
* `clear_cookies`（`1870`）用 JS 逐条置过期，**改不到 HttpOnly cookie**，
  与 `page.set.cookies`/`cookies.json` 是两套作用域。
* `get_console_logs`（`2128`）、`get_page_errors`（`2148`）、`dialog_status`（`1154`）读的是
  `window.__consoleLogs` / `window.__pageErrors` / `window.__alertActive`，
  **全仓没有任何地方安装这些采集器**（`add_init_script` 也没被调用）
  → 三个工具的返回值恒为""/false，是"永远没日志"的观测黑洞。
</details>

<details>
### 安全边界：能碰到什么、哪些防线不存在

```mermaid
flowchart TD
    A["进程参数 / manager.py:278-303"] --> A1["--no-sandbox：渲染进程不再隔离"]
    A1 --> A2["ignore_certificate_errors(True)：证书错误放行"]
    A2 --> A3["关闭 AutomationControlled + 伪装桌面 Chrome UA"]
    B["凭据注入"] --> B1["set_credentials: Basic base64 → Network.setExtraHTTPHeaders"]
    B1 --> B2["全浏览器生效，无域名白名单，凭据进页面请求头"]
    B2 --> B3["set_headers 可加任意请求头"]
    C["代码注入"] --> C1["execute_js / storage_* / add_init_script"]
    C1 --> C2["addScriptToEvaluateOnNewDocument 跨导航常驻"]
    D["文件进出"] --> D1["upload_file：resolve + exists 即可，无沙箱白名单"]
    D1 --> D2["截图/录屏产物写 user_data_dir（DATA_DIR/browser）"]
    E["访问范围"] --> E1["无域名/协议黑名单；file:// 与内网地址同样可达"]
    E1 --> E2["无代理配置项：browser/ 下 proxy 零命中"]
    F["会话数据"] --> F1["cookies.json / browser_state.json 明文落盘"]
    F1 --> F2["手动登录目录 DATA_DIR/browser/profiles/manual_login 与运行时 user_data_dir 不是同一个 profile"]
    G["隔离点"] --> G1["os.environ['CHROME_PATH'] 可指定任意可执行文件"]
    G1 --> G2["_kill_orphaned_chrome 按 cmdline 含 user_data_dir 匹配后 kill（仅 Windows）"]
```

* 唯一"能访问什么"的判据来自上层：模型能不能调 `browser__*` 由技能注册与白名单决定（见 06 图）；
  **浏览器自身不做任何 URL 裁决**。
* `_kill_orphaned_chrome` 的匹配条件是 `user_data_dir.lower() in cmdline.lower()`，
  同机若有两个 NeoBot 实例用**同一**数据目录，弱引用注册表能挡住误杀；用**不同**目录则互不影响。
* 录屏/截图产物在停机时被删（`application.py:511`），但 `cookies.json`、`browser_state.json`、
  Chromium 自己的 profile 目录都会保留 —— 想彻底清会话要手删 `DATA_DIR/browser`。
</details>

<details>
### 与 agent-browser CLI / CDP 的关系：三条互不相通的入口

```mermaid
flowchart TD
    A["进程内链路（本图主干）"] --> A1["DrissionPage ChromiumPage(ChromiumOptions)"]
    A1 --> A2["run_cdp 直发 CDP：Page.captureScreenshot / Emulation.* / Network.* / Target.*"]
    A1 --> A3["run_js / page.ele / page.listen 走 DrissionPage 自己的封装"]
    B["manager.connect(port) / manager.py:375"] --> B1["ChromiumPage(addr_or_opts='127.0.0.1:port') 接管已开浏览器"]
    B1 -.-> B2["无生产调用点，只在 actions.info 的说明里列出"]
    C["neobot open_web / cli.py:328"] --> C1["自己 new 一套 ChromiumOptions，有头 + data/browser/profiles/manual_login"]
    C1 -.-> C2["与运行时的 user_data_dir 不同，会话不共享"]
    D["scripts/open_browser.bat / .sh"] --> D1["playwright open --profile-dir=... 加上目标 URL"]
    D1 -.-> D2["playwright CLI 只有 --user-data-dir：--profile-dir 是未知选项，脚本必然报错退出"]
    E["10 图 browser_channel"] --> E1["Playwright 独立 launch，不 import neobot_app.browser"]
    F["_auto_install_chromium / bootstrap/_runtime.py:21"] --> F1["python -m playwright install chromium，仅装浏览器、不建会话"]
```

* 全仓没有任何地方调用 agent-browser 的 **Node CLI**：`agent-browser` 指的是本包目录名
  （`browser/agent_browser/`），不是外部命令；真正调 CDP 的是 `page.run_cdp(...)`。
* `actions.AgentBrowser.info()`（`actions.py:898`）列出的动作清单是**全量 API**，
  其中 `connect / launch_headed / pushstate / frame / screenshot_annotated / highlight_element /
  create_tab / state_save / set_credentials / set_headers` 等**没有任何技能暴露**，
  模型看不到；读清单时别把它当成可用工具表。
</details>

## 关键状态

| 状态 | 谁置位 | 谁清理 | 失败时停在哪 |
|---|---|---|---|
| `AgentBrowser._started` | `start()`（actions.py:38） | `close()`（actions.py:43） | `manager.start()` 三次都失败会抛穿 `_ensure`；技能层只挡 `browser_instance is None`，异常继续冒到 SkillManager 记成「工具执行失败」 |
| `BrowserAgentWrapper._closed` | `close()`（\_\_init\_\_.py:107） | `_ensure()` **无条件**置回 False（:96） | 关闭后截图抛 `ScreenshotUnavailable`；但技能调用会走 `_ensure` 静默重启 Chromium |
| `BrowserManager._page / _session_page` | `start()` 成功后（manager.py:244-245） | `close()` 置 None；`_ensure_page` 重建 | `manager.page` 断言失败抛 `AssertionError`；`_ensure_page` 捕获后整机重启 |
| `_chrome_pid` | `_start_sync`（取不到则 None） | `close()` 末尾（:345） | 取不到 pid 时跳过"等进程退出 + taskkill"整段，只 quit |
| `_tab_pages / _tab_labels` | `new_tab / switch_tab / new_tab_label` | `close_tab / close_tabs`；`close()` 只清 `_tab_pages` | 标签页被浏览器自己关掉时映射不更新，靠下一次 `switch_tab` 现取纠正 |
| `_device_metrics_override` | `set_viewport / set_device` | **没有清理点** | `capture` 只做临时覆盖并还原到它；未设置过则 `clearDeviceMetricsOverride` |
| `_recording / _recording_frames / _record_path` | `record_start` | `record_stop`（合成 GIF）、`_recording_stop`（丢帧） | 帧为空返回 `frames=0`；PIL 缺失退化成写 `.json` 帧数 |
| `_INSTANCE_REGISTRY[user_data_dir]` | `BrowserManager.__init__`（:184） | `close()`（:346） | 弱引用；实例被 GC 即消失，不清理也不泄漏 |
| `_init_scripts` | `add_init_script` | `remove_init_script` | `close()` 不清，随浏览器进程一起消失 |
| `BrowserLifecycleManager._flows[key]` | `touch / hold / track_tab_open` | `reset_flow`、60s 循环 pop、`_get_stale_flow_ids` | 关标签页回调抛异常也照样 pop（:209 吞异常）→ 标签页失联 |
| `_FlowState.held_until` | `hold()`（**无生产调用者**） | `is_held` / `_get_idle_flows` 惰性清零 | 过期即视为未持有，不影响回收 |
| `_bg_task`（生命周期循环） | `start()`（application.py:194） | `stop()`（停机 / 回滚） | `CancelledError` 直接 return；未启动时 `stop()` 是空操作 |
| `_browser_instance`（lifecycle） | `set_browser_instance`（bootstrap + wrapper 各一次） | **无清理** | 只被存起来，当前没有任何读取点 |
| `cookies.json / browser_state.json` | `save_cookies` / `_persist_state` | **无自动清理** | 停机只删截图与录屏产物（application.py:511） |

## 易错点

1. **`agent.browser.data_dir` 改了没用**：schema 里有（bot.py:1312-1315），`build_browser_components`
   却用全局 `DATA_DIR / "browser"`（bootstrap/__init__.py:856、_runtime.py:160）。
   同理 `AgentBrowser` 根本没有 `headless`/`port` 字段，`getattr(..., True/0)` 永远取默认值 ——
   想改无头/端口只能改代码。
2. **手动登录与运行时会话不是同一个 profile**：`open_web` 写
   `DATA_DIR/browser/profiles/manual_login`（cli.py:330），而运行时 Chromium 的
   `--user-data-dir` 就是 `DATA_DIR/browser`。文档「登录一次后续无头复用」在这条路径上不成立；
   真要复用只能让运行时自己有头跑一次（`launch_headed`，而它没有技能入口）。
3. **`hold()` 一族是死 API**：`hold / release / is_held / active_flow_count` 全仓只有
   `app/tests/modules/runtime/test_browser_wait.py` 调用。也就是说「保活 2 小时」永远不会发生，
   任何流只要 600s 没被 `touch` 就会被回收 —— 长任务（录屏 5 分钟上限、慢站点人工流程）要留意。
4. **`BrowserSkill._check_lifecycle` 调用不存在的方法**（browser_skill.py:98 →
   `BrowserLifecycleManager.should_auto_close`）。因为该方法自身零调用点才没炸；
   谁把它接回 `_run_tool`，谁就会立刻拿到 AttributeError。
5. **重试次数与文档不符**：`_MAX_RETRIES = 2` / `_RETRY_INTERVAL = 1.0`（manager.py:37-38）
   没有任何读取点；真实生效的是启动 `range(3)` + `sleep(1.5)`（:242-261）与导航
   `page.get(timeout=15, retry=1, interval=1)`（:360）。`fix(12)/fallback-inventory.md:61`
   把两者相加说成"导航最坏 3 次"，读图时以本图为准。
6. **`click` 几乎永远返回 `success: True`**：四阶段走完无条件返回成功（manager.py:649），
   只有"元素找不到"或"抛异常"才是失败。判断点击是否生效要看 `url` 字段与后续 `snapshot`，
   不能看 `success`。
7. **`network_route(abort=True)` 可能永久挂起**：`page.listen.wait()` 没有超时（manager.py:1924），
   且这三个方法直接同步调用 DrissionPage，会阻塞事件循环；`mock_body` 参数被完全忽略，
   工具描述里的"mock 响应体"不存在。
8. **console / page error / dialog 三个观测点是黑洞**：`get_console_logs`、`get_page_errors`、
   `dialog_status` 读 `window.__consoleLogs / __pageErrors / __alertActive`，
   全仓没有任何安装器（`add_init_script` 也无人调用）→ 恒为 `""` / `false`。
   要拿控制台日志必须自己往页面注入采集脚本。
9. **标注截图与 `shot()` 都名不副实**：`screenshot_annotated` 的 `rect` 恒为空 dict
   （manager.py:1545）所以画不出编号；`actions.shot()` 把 JPEG 字节写进 `.png` 文件名
   （actions.py:616-624），而且没有生产调用点。技能里的 `shot` 走的是另一条路。
10. **`_ensure_page` 的"任何异常都整机重启"是最大的连带影响面**（manager.py:350-356）：
    一次瞬时探活失败会 close + start，**该浏览器上所有聊天流的标签页一起消失**，
    随后各流只会在下一次 `touch` 后重新 `new_tab`。排查"我的页面怎么没了"先看这里。
11. **标签页 `index` 有两套口径**：`list_tabs` 返回的是过滤掉非 page/webview 目标后的下标，
    `switch_tab/close_tab` 用的是原始 `tab_ids` 下标（manager.py:1698-1750）。
    技能与生命周期回调都按"list_tabs 的 index → close_tab"传参，遇错位会关错页。
12. **改动连带面**（改前先想清楚）：`_find_element` 是所有元素动作的唯一入口（含模糊 `text=` 回退）；
    `list_tabs` 同时服务三个技能与生命周期回调；`operation_lock` 是进程级串行点，
    任何新增的慢动作都会拖住全部聊天流；`browser_lifecycle` 的回收阈值直接决定会话复用体验，
    且没有 `hold` 兜底可用。
