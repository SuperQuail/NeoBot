"""面板里的机器人通道页：OneBot / QQ 官方双通道状态、模式切换与官方扫码绑定。

页面与脚本挂在面板同一端口、同一 base_path 下（走 DashboardWebExtension 扩展点，
不改 React 构建）。OneBot 与官方机器人可以同时运行，页面同时展示两条通道的
连接与账号；二维码由官方适配器的 QrBindFlow 生成，页面轮询 /api/qqbot/status
展示。接口仍由面板鉴权中间件保护。

为什么脚本单独一个响应而不是内联：面板统一下发 CSP（script-src 'self'），
内联 <script> 会被浏览器拦掉，所以照 B站扫码页的做法把 JS 放在同源路径里。
"""

from __future__ import annotations

from aiohttp import web

PATH = "/qqbot"
"""挂载前缀（不含面板 base_path）。"""


class QQBotPageExtension:
    """机器人通道页（协议见 dashboard/web_extension.py）。"""

    name = "qqbot"

    @property
    def prefixes(self) -> tuple[str, ...]:
        return (PATH,)

    @property
    def auth_prefixes(self) -> tuple[str, ...]:
        # 通道、账号与扫码状态只给已登录面板的人看（页面和脚本一起挡在会话后面）
        return (PATH,)

    async def handle_request(self, request: web.Request, path: str) -> web.StreamResponse | None:
        if path == PATH:
            # 目录形式访问，保证页面里的相对路径以 /qqbot/ 为基准
            return web.Response(status=302, headers={"Location": request.path + "/"})
        if path in {f"{PATH}/", f"{PATH}/index.html"}:
            return web.Response(
                text=PAGE_HTML,
                content_type="text/html",
                headers={"Cache-Control": "no-store"},
            )
        if path == f"{PATH}/client.js":
            return web.Response(
                text=PAGE_SCRIPT,
                content_type="application/javascript",
                headers={"Cache-Control": "no-store"},
            )
        return None


PAGE_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>机器人通道 · NeoBot 面板</title>
<style>
:root { color-scheme: light; --canvas: #f6fcff; --panel: #fff; --inset: #eef9ff;
  --ink: #1f3a4d; --secondary: #526e80; --line: #d2e5f0; --brand: #0369a1;
  --brand-hover: #075985; --brand-soft: #e0f2fe; --danger: #b43c36;
  --shadow: 0 12px 40px rgba(15, 34, 56, .06); }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; padding: 28px 20px; background: var(--canvas);
  color: var(--ink); font: 14px/1.65 system-ui, -apple-system, "PingFang SC",
  "Microsoft YaHei", sans-serif; -webkit-font-smoothing: antialiased; }
main { width: min(100%, 860px); margin: 0 auto; }
.page-nav { display: flex; align-items: center; justify-content: space-between;
  gap: 16px; padding: 0 2px 20px; }
.wordmark { display: flex; align-items: center; gap: 9px; font-size: 14px; font-weight: 650; }
.wordmark span { display: grid; place-items: center; width: 29px; height: 29px;
  border: 1px solid var(--line); border-radius: 7px; background: var(--brand-soft);
  color: var(--brand); font-size: 15px; }
h1 { margin: 0 0 6px; font-size: 24px; line-height: 1.35; font-weight: 650; letter-spacing: -.02em; }
.intro { margin: 0 0 18px; color: var(--secondary); font-size: 13px; }
.notice { margin: 0 0 16px; padding: 10px 14px; border: 1px solid var(--line);
  border-radius: 7px; background: var(--inset); font-size: 13px; }
.notice.is-error { border-color: var(--danger); color: var(--danger); }
.mode-bar { display: flex; flex-wrap: wrap; gap: 10px; margin: 0 0 18px; }
.mode-bar button.is-selected { font-weight: 700; outline: 2px solid var(--ink); outline-offset: 2px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
.card { padding: 22px; border: 1px solid var(--line); border-radius: 10px; background: var(--panel);
  box-shadow: var(--shadow); }
.card.is-active { border-color: var(--brand); }
.card-head { display: flex; align-items: flex-start; justify-content: space-between;
  gap: 12px; margin-bottom: 6px; }
h2 { margin: 0; font-size: 17px; font-weight: 650; }
.badge { flex: none; padding: 2px 9px; border: 1px solid var(--line); border-radius: 999px;
  background: var(--inset); color: var(--secondary); font-size: 12px; white-space: nowrap; }
.badge.is-active { border-color: var(--brand); background: var(--brand-soft); color: var(--brand); }
.desc { margin: 0 0 14px; color: var(--secondary); font-size: 13px; }
dl { margin: 0 0 16px; display: grid; gap: 10px; }
dl > div { display: grid; grid-template-columns: 96px 1fr; gap: 10px; align-items: baseline; }
dt { color: var(--secondary); font-size: 12px; }
dd { margin: 0; font-size: 13px; overflow-wrap: anywhere; }
.fine { margin: 6px 0 0; color: var(--secondary); font-size: 12px; overflow-wrap: anywhere; }
.fine.is-error { color: var(--danger); }
.qr-box { width: 200px; height: 200px; margin: 4px auto 10px; padding: 10px;
  border: 1px solid var(--line); border-radius: 7px; background: #fff;
  display: grid; place-items: center; overflow: hidden; }
.qr-box svg, .qr-box img { display: block; width: 100%; height: 100%; }
.qr-box.is-empty { color: #526e80; font-size: 12px; text-align: center; padding: 20px; }
.bind-url { margin: 0 0 12px; text-align: center; }
.bind-url a { color: var(--brand); font-size: 13px; }
.row { display: flex; flex-wrap: wrap; gap: 10px; }
button { min-height: 40px; padding: 8px 18px; border: 1px solid transparent; border-radius: 6px;
  background: var(--brand); color: #fff; font: inherit; font-weight: 550; cursor: pointer;
  transition: background-color .15s ease, transform .15s ease; }
button:hover:not(:disabled) { background: var(--brand-hover); }
button:active:not(:disabled) { transform: translateY(1px); }
button:disabled { background: var(--inset); border-color: var(--line);
  color: var(--secondary); cursor: not-allowed; }
button.ghost { background: transparent; border-color: var(--line); color: var(--brand); }
.status { min-height: 22px; margin: 18px 2px 0; color: var(--secondary); font-size: 13px;
  overflow-wrap: anywhere; }
.status.is-error { color: var(--danger); }
a { color: var(--secondary); font-size: 12px; text-decoration: none; }
a:focus-visible, button:focus-visible { outline: 2px solid var(--brand); outline-offset: 3px; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { color-scheme: dark; --canvas: #0f2238; --panel: #19304c; --inset: #122a43;
    --ink: #e7f6ff; --secondary: #9cb7cb; --line: #2a3d5e; --brand: #7dd3fc;
    --brand-hover: #bae6fd; --brand-soft: #143c5a; --danger: #ffaaa2; --shadow: 0 12px 40px rgba(0, 0, 0, .18); }
  :root:not([data-theme="light"]) button:not(:disabled) { color: #0f2238; }
}
:root[data-theme="dark"] { color-scheme: dark; --canvas: #0f2238; --panel: #19304c; --inset: #122a43;
  --ink: #e7f6ff; --secondary: #9cb7cb; --line: #2a3d5e; --brand: #7dd3fc;
  --brand-hover: #bae6fd; --brand-soft: #143c5a; --danger: #ffaaa2; --shadow: 0 12px 40px rgba(0, 0, 0, .18); }
:root[data-theme="dark"] button:not(:disabled) { color: #0f2238; }
@media (max-width: 640px) { body { padding: 24px 14px; } .card { padding: 18px; }
  dl > div { grid-template-columns: 84px 1fr; } .mode-bar button { flex: 1; } }
@media (prefers-reduced-motion: reduce) { button { transition: none; } }
/* 嵌在面板内容区（React 路由里的 iframe）时去掉自己的页头和留白，避免双层导航 */
html.is-embedded body { padding: 2px; background: transparent; }
html.is-embedded .page-nav, html.is-embedded h1 { display: none; }
html.is-embedded main { width: 100%; max-width: none; }
</style>
</head>
<body>
<main>
  <nav class="page-nav" aria-label="页面导航">
    <div class="wordmark"><span aria-hidden="true">N</span>NeoBot</div>
    <a href="../">返回面板</a>
  </nav>
  <h1>机器人通道</h1>
  <p class="intro">OneBot 与官方机器人可以同时运行。切换模式会热重载适配器，不重启进程。</p>
  <p id="notice" class="notice" hidden></p>
  <section class="mode-bar" aria-label="通道模式">
    <button id="mode-onebot" type="button" data-mode="onebot">仅 OneBot</button>
    <button id="mode-official" type="button" data-mode="official">仅官方机器人</button>
    <button id="mode-dual" type="button" data-mode="dual">双通道并行</button>
  </section>
  <section class="cards">
    <article id="card-onebot" class="card" aria-labelledby="title-onebot">
      <div class="card-head">
        <h2 id="title-onebot">OneBot 框架</h2>
        <span id="badge-onebot" class="badge">未启用</span>
      </div>
      <p class="desc">通过 NapCat / LLOneBot 等框架的反向 WebSocket 接入。</p>
      <dl>
        <div><dt>连接</dt><dd id="link-onebot">—</dd></div>
        <div><dt>账号</dt><dd id="account-onebot">—</dd></div>
        <div><dt>反向 WS 地址</dt><dd id="onebot-addr">—</dd></div>
        <div><dt>access token</dt><dd id="onebot-token">—</dd></div>
      </dl>
    </article>
    <article id="card-official" class="card" aria-labelledby="title-official">
      <div class="card-head">
        <h2 id="title-official">QQ 官方机器人</h2>
        <span id="badge-official" class="badge">未启用</span>
      </div>
      <p class="desc">内嵌官方协议，扫码绑定后由 NeoBot 直接连接，不需要框架进程。</p>
      <dl>
        <div><dt>连接</dt><dd id="link-official">—</dd></div>
        <div><dt>账号</dt><dd id="account-official">—</dd></div>
        <div><dt>AppID</dt><dd id="official-appid">—</dd></div>
      </dl>
      <div id="bind-box" hidden>
        <div id="qr" class="qr-box is-empty">等待绑定二维码…</div>
        <p class="bind-url"><a id="bind-link" href="#" target="_blank" rel="noopener" hidden>打开绑定链接</a></p>
        <p id="bind-hint" class="fine"></p>
        <p id="bind-error" class="fine is-error" hidden></p>
      </div>
      <div class="row">
        <button id="rebind" class="ghost" type="button">重新扫码绑定</button>
        <button id="unbind" class="ghost" type="button">解绑官方机器人</button>
      </div>
    </article>
  </section>
  <p id="status" class="status" role="status">读取状态…</p>
</main>
<script src="client.js" defer></script>
</body>
</html>
"""

PAGE_SCRIPT = """(function () {
  "use strict";
  try {
    var theme = window.localStorage.getItem("neobot-dashboard-theme");
    if (theme === "light" || theme === "dark") {
      document.documentElement.setAttribute("data-theme", theme);
    }
  } catch (error) { /* 浏览器禁用存储时跟随系统主题。 */ }
  if (/(?:^|[?&])embed=1(?:&|$)/.test(window.location.search)) {
    document.documentElement.classList.add("is-embedded");
  }

  var API = "../api/qqbot/";
  var MODES = { onebot: "仅 OneBot", official: "仅官方机器人", dual: "双通道并行", local: "本地适配器" };
  var PHASES = {
    idle: "尚未开始绑定",
    pending: "等待扫码…",
    success: "绑定成功",
    expired: "二维码已过期，请点「重新扫码绑定」",
    error: "绑定失败"
  };
  var csrf = "";
  var timer = 0, busy = false, canManage = false, currentMode = "";

  function el(id) { return document.getElementById(id); }

  function setStatus(text, isError) {
    var node = el("status");
    node.textContent = text;
    node.classList.toggle("is-error", !!isError);
  }

  function setNotice(text, isError) {
    var node = el("notice");
    node.hidden = !text;
    node.textContent = text || "";
    node.classList.toggle("is-error", !!isError);
  }

  function modeLabel(mode) { return MODES[mode] || mode || "未知模式"; }

  function channelOf(state, name) {
    var fallback = {
      name: name, label: name, active: false, connected: false, account: 0,
      nickname: "", app_id: "",
      bind: { phase: "idle", url: "", svg: "", expires_at: 0, error: "" },
      onebot: { host: "", port: 0, token_set: false }
    };
    var list = state.channels || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i] && list[i].name === name) {
        var item = list[i];
        return {
          name: name, label: item.label || name, active: !!item.active,
          connected: !!item.connected, account: item.account || 0,
          nickname: item.nickname || "", app_id: item.app_id || "",
          bind: item.bind || fallback.bind, onebot: item.onebot || fallback.onebot
        };
      }
    }
    return fallback;
  }

  function accountText(channel) {
    var name = channel.nickname || "";
    var account = channel.account || 0;
    if (name && account) { return name + "（" + account + "）"; }
    if (name) { return name; }
    if (account) { return String(account); }
    return channel.active ? "未获取（连接后自动读取）" : "—";
  }

  function onebotAddress(info) {
    if (!info || !info.host || !info.port) {
      return "未配置（config.toml [adapter].reverse_ws_host / port）";
    }
    var wildcard = info.host === "0.0.0.0" || info.host === "::";
    var host = wildcard ? "127.0.0.1" : info.host;
    return "ws://" + host + ":" + info.port + (wildcard ? "（监听 " + info.host + "）" : "");
  }

  function renderModeBar(mode, switching) {
    var names = ["onebot", "official", "dual"];
    for (var i = 0; i < names.length; i++) {
      var name = names[i];
      var button = el("mode-" + name);
      if (!button) { continue; }
      button.classList.toggle("is-selected", mode === name);
      button.setAttribute("aria-pressed", mode === name ? "true" : "false");
      button.disabled = switching || !canManage;
    }
  }

  function renderChannel(channel, mode) {
    var name = channel.name;
    var active = !!channel.active;
    el("card-" + name).classList.toggle("is-active", active);
    var badge = el("badge-" + name);
    badge.textContent = active
      ? (channel.connected ? "运行中 · 已连接" : "运行中 · 未连接")
      : (mode === "local" ? "未启用（local 模式）" : "未启用");
    badge.classList.toggle("is-active", active);
    el("link-" + name).textContent = active
      ? (channel.connected ? "已连接" : "未连接（等待连接或扫码绑定）")
      : "未启用";
    el("account-" + name).textContent = accountText(channel);
  }

  function renderBind(official) {
    var box = el("bind-box");
    var bind = official.bind || {};
    var phase = bind.phase || "idle";
    // 重新扫码时 phase 先回到 pending：即使已连接/已有账号也要重新露出二维码
    var binding = phase === "pending" || phase === "expired" || phase === "error";
    var bound = !binding && (phase === "success" || !!official.account || (official.active && official.connected));
    if (bound) { box.hidden = true; return; }
    box.hidden = false;

    var qr = el("qr");
    var link = el("bind-link");
    var hint = el("bind-hint");
    var error = el("bind-error");
    link.hidden = true;
    error.hidden = true;
    hint.textContent = "";

    if (!official.active) {
      qr.className = "qr-box is-empty";
      qr.textContent = "未启用：把模式切到「仅官方机器人」或「双通道并行」后可扫码绑定";
      return;
    }
    if (!canManage) {
      qr.className = "qr-box is-empty";
      qr.textContent = "需要管理权限才能扫码绑定";
      return;
    }

    var svg = bind.svg || "";
    if (svg) {
      qr.className = "qr-box";
      qr.innerHTML = svg;
    } else {
      qr.className = "qr-box is-empty";
      qr.textContent = PHASES[phase] || "等待绑定二维码…";
    }
    hint.textContent = svg
      ? "打开手机 QQ 扫码，并在手机上确认绑定。"
      : (phase === "idle" ? "官方适配器正在启动；若二维码没有出现，请点「重新扫码绑定」。" : (PHASES[phase] || ""));
    if (bind.url) {
      link.hidden = false;
      link.href = bind.url;
    }
    if (bind.error) {
      error.hidden = false;
      error.textContent = bind.error;
    }
  }

  function render(state) {
    var mode = state.mode || "";
    var power = state.power || {};
    var switching = busy || !!state.switching;
    currentMode = mode;

    var summary = "当前模式：" + modeLabel(mode);
    if (power.standby) { summary += "｜待机中"; }
    if (state.switching) { summary += "｜正在热重载…"; }
    setStatus(summary);

    var onebot = channelOf(state, "onebot");
    var official = channelOf(state, "official");
    renderModeBar(mode, switching);
    renderChannel(onebot, mode);
    renderChannel(official, mode);

    el("onebot-addr").textContent = onebotAddress(onebot.onebot);
    el("onebot-token").textContent = onebot.onebot && onebot.onebot.token_set
      ? "已设置"
      : "未设置（监听非回环地址时任何主机都可注入事件）";
    el("official-appid").textContent = official.app_id
      || "未配置（config.toml [adapter].qq_appid 或 .env NEOBOT_QQ_APPID）";
    renderBind(official);
    el("rebind").disabled = switching || !canManage || !official.active;
    el("unbind").disabled = switching || !canManage || !official.active;
  }

  async function readJson(response) {
    var payload = {};
    try { payload = await response.json(); } catch (error) { payload = {}; }
    if (!response.ok || payload.ok === false) {
      var failure = new Error(payload.error || ("HTTP " + response.status));
      failure.status = response.status;
      throw failure;
    }
    return payload;
  }

  function stopPolling() {
    if (timer) { window.clearTimeout(timer); timer = 0; }
  }

  function schedule(ms) {
    stopPolling();
    timer = window.setTimeout(tick, ms);
  }

  function handleFailure(error) {
    if (error.status === 401) {
      stopPolling();
      setStatus("请先登录网页面板，再刷新本页。", true);
      return;
    }
    setStatus("读取状态失败：" + error.message, true);
  }

  async function refresh() {
    var state = await readJson(await fetch(API + "status", { cache: "no-store" }));
    render(state);
    return state;
  }

  async function tick() {
    try {
      var state = await refresh();
      schedule(state.switching ? 1000 : 3000);
    } catch (error) {
      handleFailure(error);
      schedule(5000);
    }
  }

  async function post(path, body) {
    return readJson(await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify(body || {})
    }));
  }

  async function switchMode(mode) {
    if (busy || mode === currentMode) { return; }
    busy = true;
    setNotice("");
    setStatus("正在切换到「" + modeLabel(mode) + "」…（热重载中，请稍候）");
    try {
      await post("switch", { mode: mode });
      busy = false;
      setNotice("已提交切换到「" + modeLabel(mode) + "」，正在等待适配器就绪…", false);
      schedule(500);
    } catch (error) {
      busy = false;
      if (error.status === 401) { handleFailure(error); return; }
      setNotice("切换失败：" + error.message, true);
      schedule(3000);
    }
  }

  async function rebind() {
    if (busy) { return; }
    busy = true;
    setNotice("");
    setStatus("正在重新开始扫码绑定…");
    try {
      await post("bind/rebind", {});
      busy = false;
      setNotice("已重新开始绑定，二维码生成后本页会自动刷新。", false);
      schedule(1000);
    } catch (error) {
      busy = false;
      if (error.status === 401) { handleFailure(error); return; }
      setNotice(
        error.status === 503
          ? "当前适配器不支持扫码绑定（请先把模式切到「仅官方机器人」或「双通道并行」）。"
          : "重新绑定失败：" + error.message,
        true
      );
      schedule(3000);
    }
  }

  async function main() {
    try {
      var me = await readJson(await fetch("../api/auth/me", { cache: "no-store" }));
      csrf = me.csrf_token || "";
      canManage = !!me.can_manage;
      if (!canManage) {
        setNotice("当前会话没有管理权限：可以查看通道状态，但不能切换模式或重新绑定。", true);
      }
      await tick();
    } catch (error) {
      handleFailure(error);
    }
  }

  var modes = ["onebot", "official", "dual"];
  for (var i = 0; i < modes.length; i++) {
    (function (mode) {
      el("mode-" + mode).addEventListener("click", function () { switchMode(mode); });
    })(modes[i]);
  }
  async function unbind() {
    if (busy) { return; }
    if (!window.confirm("解绑后会删除本机保存的官方机器人凭据并断开连接；确定继续？")) { return; }
    busy = true;
    setNotice("");
    setStatus("正在解绑官方机器人…");
    try {
      await post("bind/unbind", {});
      busy = false;
      setNotice("已解绑。可在配置里填写 AppID/AppSecret，或重新扫码绑定。", false);
      schedule(1000);
    } catch (error) {
      busy = false;
      if (error.status === 401) { handleFailure(error); return; }
      setNotice(
        error.status === 503
          ? "当前适配器不支持解绑（请先把模式切到「仅官方机器人」或「双通道并行」）。"
          : "解绑失败：" + error.message,
        true
      );
      schedule(3000);
    }
  }

  el("rebind").addEventListener("click", function () { rebind(); });
  el("unbind").addEventListener("click", function () { unbind(); });
  main();
})();
"""
