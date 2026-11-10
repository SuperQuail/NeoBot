"""面板里的机器人通道页：OneBot / QQ 官方通道切换与官方扫码绑定。

页面与脚本挂在面板同一端口、同一 base_path 下（走 DashboardWebExtension 扩展点，
不改 React 构建）。二维码由官方适配器的 QrBindFlow 生成，页面轮询
/api/qqbot/status 展示；接口仍由面板鉴权中间件保护。

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
        # 通道与扫码状态只给已登录面板的人看（页面和脚本一起挡在会话后面）
        return (PATH,)

    def panel_entry(self) -> dict[str, str]:
        return {
            "title": "机器人通道",
            "path": f"{PATH}/",
            "icon": "message",
            "description": "选择 OneBot 或官方机器人通道并扫码登录",
        }

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
.intro { margin: 0 0 20px; color: var(--secondary); font-size: 13px; }
.notice { margin: 0 0 16px; padding: 10px 14px; border: 1px solid var(--line);
  border-radius: 7px; background: var(--inset); font-size: 13px; }
.notice.is-error { border-color: var(--danger); color: var(--danger); }
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
button.ghost:hover:not(:disabled) { background: var(--brand-soft); }
.status { min-height: 22px; margin: 18px 2px 0; color: var(--secondary); font-size: 13px;
  overflow-wrap: anywhere; }
.status.is-error { color: var(--danger); }
a { color: var(--secondary); font-size: 12px; text-decoration: none; }
a:hover { color: var(--brand); text-decoration: underline; text-underline-offset: 4px; }
a:focus-visible, button:focus-visible { outline: 2px solid var(--brand); outline-offset: 3px; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { color-scheme: dark; --canvas: #0f2238; --panel: #19304c;
    --inset: #122a43; --ink: #e7f6ff; --secondary: #9cb7cb; --line: #2a3d5e;
    --brand: #7dd3fc; --brand-hover: #bae6fd; --brand-soft: #143c5a; --danger: #ffaaa2;
    --shadow: 0 12px 40px rgba(0, 0, 0, .18); }
  :root:not([data-theme="light"]) button:not(:disabled) { color: #0f2238; }
}
:root[data-theme="dark"] { color-scheme: dark; --canvas: #0f2238; --panel: #19304c;
  --inset: #122a43; --ink: #e7f6ff; --secondary: #9cb7cb; --line: #2a3d5e;
  --brand: #7dd3fc; --brand-hover: #bae6fd; --brand-soft: #143c5a; --danger: #ffaaa2;
  --shadow: 0 12px 40px rgba(0, 0, 0, .18); }
:root[data-theme="dark"] button:not(:disabled) { color: #0f2238; }
@media (max-width: 640px) { body { padding: 24px 14px; } .card { padding: 18px; }
  dl > div { grid-template-columns: 84px 1fr; } .row button { flex: 1; } }
@media (prefers-reduced-motion: reduce) { button { transition: none; } }
</style>
</head>
<body>
<main>
  <nav class="page-nav" aria-label="页面导航">
    <div class="wordmark"><span aria-hidden="true">N</span>NeoBot</div>
    <a href="../">返回面板</a>
  </nav>
  <h1>机器人通道</h1>
  <p class="intro">选择 NeoBot 接入 QQ 的方式。切换会热重载适配器，不重启进程。</p>
  <p id="notice" class="notice" hidden></p>
  <section class="cards">
    <article id="card-onebot" class="card" aria-labelledby="title-onebot">
      <div class="card-head">
        <h2 id="title-onebot">OneBot 框架</h2>
        <span id="badge-onebot" class="badge">未启用</span>
      </div>
      <p class="desc">通过 NapCat / LLOneBot 等框架的反向 WebSocket 接入。</p>
      <dl>
        <div><dt>反向 WS 地址</dt><dd id="onebot-addr">—</dd></div>
        <div><dt>access token</dt><dd id="onebot-token">—</dd></div>
      </dl>
      <button id="switch-onebot" type="button" data-mode="onebot">切换到 OneBot</button>
    </article>
    <article id="card-official" class="card" aria-labelledby="title-official">
      <div class="card-head">
        <h2 id="title-official">QQ 官方机器人</h2>
        <span id="badge-official" class="badge">未启用</span>
      </div>
      <p class="desc">内嵌官方协议，扫码绑定后由 NeoBot 直接连接，不需要框架进程。</p>
      <dl>
        <div><dt>AppID</dt><dd id="official-appid">—</dd></div>
        <div><dt>绑定账号</dt><dd id="official-account">未绑定</dd></div>
      </dl>
      <div id="bind-box" hidden>
        <div id="qr" class="qr-box is-empty">等待绑定二维码…</div>
        <p class="bind-url"><a id="bind-link" href="#" target="_blank" rel="noopener" hidden>打开绑定链接</a></p>
        <p id="bind-hint" class="fine"></p>
        <p id="bind-error" class="fine is-error" hidden></p>
      </div>
      <div class="row">
        <button id="switch-official" type="button" data-mode="official">切换到官方机器人</button>
        <button id="rebind" class="ghost" type="button">重新扫码绑定</button>
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

  var API = "../api/qqbot/";
  var csrf = "";
  var timer = 0;
  var busy = false;
  var canManage = false;
  var MODES = { onebot: "OneBot 框架", official: "QQ 官方机器人", local: "本地适配器" };
  var PHASES = {
    idle: "尚未开始绑定",
    pending: "等待扫码…",
    success: "绑定成功",
    expired: "二维码已过期，请点「重新扫码绑定」",
    error: "绑定失败"
  };

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

  function modeLabel(mode) { return MODES[mode] || mode || "未知通道"; }

  function onebotAddress(info) {
    if (!info.host || !info.port) { return "未配置（config.toml [adapter].reverse_ws_host / port）"; }
    var wildcard = info.host === "0.0.0.0" || info.host === "::";
    var host = wildcard ? "127.0.0.1" : info.host;
    return "ws://" + host + ":" + info.port + (wildcard ? "（监听 " + info.host + "）" : "");
  }

  function accountText(official) {
    if (!official.bound) { return "未绑定"; }
    var name = official.nickname || "";
    var account = official.account || 0;
    if (name && account) { return name + "（" + account + "）"; }
    if (name) { return name; }
    if (account) { return String(account); }
    return "已绑定（账号信息获取中）";
  }

  function renderBind(bind, bound, mode) {
    var box = el("bind-box");
    if (bound) { box.hidden = true; return; }
    box.hidden = false;
    if (mode !== "official") {
      el("qr").className = "qr-box is-empty";
      el("qr").textContent = "切换到官方机器人通道后可扫码绑定";
      el("bind-hint").textContent = "";
      el("bind-link").hidden = true;
      el("bind-error").hidden = true;
      return;
    }
    if (!canManage) {
      el("qr").className = "qr-box is-empty";
      el("qr").textContent = "需要管理权限才能扫码绑定";
      el("bind-hint").textContent = "";
      el("bind-link").hidden = true;
      el("bind-error").hidden = true;
      return;
    }

    var phase = bind.phase || "idle";
    var svg = bind.svg || "";
    var qr = el("qr");
    if (svg && (phase === "pending" || phase === "idle")) {
      qr.className = "qr-box";
      qr.innerHTML = svg;
    } else {
      qr.className = "qr-box is-empty";
      qr.textContent = PHASES[phase] || "等待绑定二维码…";
    }

    el("bind-hint").textContent = svg ? "打开手机 QQ 扫码，并在手机上确认绑定。" : (PHASES[phase] || "");
    var link = el("bind-link");
    link.hidden = !bind.url;
    if (bind.url) { link.href = bind.url; }

    var error = el("bind-error");
    error.hidden = !bind.error;
    error.textContent = bind.error || "";
  }

  function render(state) {
    var mode = state.mode || "";
    var onebot = state.onebot || {};
    var official = state.official || {};
    var bind = state.bind || {};
    var power = state.power || {};
    var switching = busy || !!state.switching;

    var summary = "当前通道：" + modeLabel(mode) + "｜" + (state.connected ? "已连接" : "未连接");
    if (power.standby) { summary += "｜待机中"; }
    if (state.switching) { summary += "｜正在切换…"; }
    setStatus(summary);

    el("card-onebot").classList.toggle("is-active", mode === "onebot");
    el("card-official").classList.toggle("is-active", mode === "official");

    var onebotBadge = el("badge-onebot");
    onebotBadge.textContent = mode === "onebot"
      ? "当前通道 · " + (state.connected ? "已连接" : "未连接")
      : "未启用";
    onebotBadge.classList.toggle("is-active", mode === "onebot");

    var officialBadge = el("badge-official");
    officialBadge.textContent = mode === "official"
      ? "当前通道 · " + (official.bound ? "已绑定" : "未绑定")
      : (official.bound ? "已绑定" : "未启用");
    officialBadge.classList.toggle("is-active", mode === "official");

    el("onebot-addr").textContent = onebotAddress(onebot);
    el("onebot-token").textContent = onebot.token_set
      ? "已设置"
      : "未设置（监听非回环地址时任何主机都可注入事件）";
    el("official-appid").textContent = official.app_id
      || "未配置（config.toml [adapter].qq_appid 或 .env NEOBOT_QQ_APPID）";
    el("official-account").textContent = accountText(official);
    renderBind(bind, !!official.bound, mode);

    el("switch-onebot").disabled = switching || !canManage || mode === "onebot";
    el("switch-official").disabled = switching || !canManage || mode === "official";
    el("rebind").disabled = switching || !canManage;
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
    if (busy) { return; }
    busy = true;
    setNotice("");
    setStatus("正在切换到" + modeLabel(mode) + "…（热重载中，请稍候）");
    try {
      await post("switch", { mode: mode });
      setNotice("已提交切换到" + modeLabel(mode) + "，正在等待适配器就绪…", false);
      busy = false;
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
      setNotice("已重新开始绑定，二维码生成后本页会自动刷新。", false);
      busy = false;
      schedule(1000);
    } catch (error) {
      busy = false;
      if (error.status === 401) { handleFailure(error); return; }
      setNotice(
        error.status === 503
          ? "当前适配器不支持扫码绑定（请先切换到官方机器人通道）。"
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
        setNotice("当前会话没有管理权限：可以查看状态，但不能切换通道或重新绑定。", true);
      }
      await tick();
    } catch (error) {
      handleFailure(error);
    }
  }

  el("switch-onebot").addEventListener("click", function () { switchMode("onebot"); });
  el("switch-official").addEventListener("click", function () { switchMode("official"); });
  el("rebind").addEventListener("click", function () { rebind(); });
  main();
})();
"""
