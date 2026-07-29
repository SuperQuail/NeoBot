"use strict";

const state = {
  csrf: null,
  role: "debug",
  currentPage: "overview",
  config: [],
  changes: new Map(),
  logSource: null,
  previewTimer: null,
  passwordFile: "<NeoBot 数据目录>/console/auth.json",
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;").replaceAll("'", "&#039;");

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (state.csrf && !["GET", "HEAD"].includes(options.method || "GET")) headers.set("X-CSRF-Token", state.csrf);
  const response = await fetch(path, {credentials: "same-origin", ...options, headers});
  const type = response.headers.get("content-type") || "";
  const payload = type.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    if (response.status === 401 && !path.includes("/auth/")) showAuth();
    throw new Error(payload.error || `请求失败 (${response.status})`);
  }
  return payload;
}

function toast(message, error = false) {
  const item = document.createElement("div");
  item.className = `toast${error ? " error" : ""}`;
  item.textContent = message;
  $("#toast-region").append(item);
  setTimeout(() => item.remove(), 4200);
}

function formatBytes(bytes) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = Number(bytes || 0), index = 0;
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1; }
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}

function formatDuration(seconds) {
  const total = Math.max(0, Number(seconds || 0));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days) return `${days}天 ${hours}小时`;
  if (hours) return `${hours}小时 ${minutes}分`;
  return `${minutes}分 ${Math.floor(total % 60)}秒`;
}

async function initialize() {
  updateClock();
  setInterval(updateClock, 1000);
  try {
    const status = await api("/api/auth/status");
    state.role = status.role;
    state.csrf = status.csrf_token;
    configureRole();
    if (status.authenticated) enterApp();
    else configureAuth(status);
  } catch (error) {
    $("#auth-title").textContent = "控制台暂时不可用";
    $("#auth-description").textContent = error.message;
  }
}

function configureRole() {
  const admin = state.role === "admin";
  $("#auth-role-chip").textContent = admin ? "LOCAL ADMIN" : "DEBUG CONSOLE";
  $("#console-edition").textContent = admin ? "Local Admin" : "Debug Console";
  $$(".admin-only").forEach((item) => item.hidden = !admin);
}

function configureAuth(status) {
  const form = $("#auth-form");
  state.passwordFile = status.password_file || state.passwordFile;
  $("#password-file-path").textContent = state.passwordFile;
  $("#recovery-password-file").textContent = state.passwordFile;
  $("#forgot-password").hidden = !status.configured;
  form.hidden = false;
  if (!status.configured) {
    $("#auth-title").textContent = "创建控制台密码";
    $("#auth-description").textContent = "这是首次访问。请设置至少 12 位、包含三类字符的强密码。";
    $("#password").autocomplete = "new-password";
    $("#confirmation-field").hidden = false;
    $("#confirmation").required = true;
    $("#auth-submit").textContent = "设置密码并进入";
    form.dataset.mode = "setup";
  } else {
    $("#auth-title").textContent = "欢迎回来";
    $("#auth-description").textContent = state.role === "admin"
      ? "验证密码后进入本机管理员控制台。"
      : "验证密码后查看 NeoBot 的实时运行状态。";
    form.dataset.mode = "login";
  }
}

$("#auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorNode = $("#auth-error");
  errorNode.textContent = "";
  const mode = event.currentTarget.dataset.mode;
  const payload = {password: $("#password").value};
  if (mode === "setup") payload.confirmation = $("#confirmation").value;
  const button = $("#auth-submit");
  button.disabled = true;
  try {
    const result = await api(`/api/auth/${mode}`, {method: "POST", body: JSON.stringify(payload)});
    state.csrf = result.csrf_token;
    $("#password").value = "";
    $("#confirmation").value = "";
    enterApp();
  } catch (error) {
    errorNode.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

function showAuth() {
  if (state.logSource) state.logSource.close();
  if (state.previewTimer) {
    clearInterval(state.previewTimer);
    state.previewTimer = null;
  }
  $("#app-view").hidden = true;
  $("#auth-view").hidden = false;
  api("/api/auth/status").then(configureAuth).catch(() => {});
}

async function enterApp() {
  $("#auth-view").hidden = true;
  $("#app-view").hidden = false;
  await loadPage("overview");
}

function updateClock() {
  $("#clock").textContent = new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(new Date());
}

const titles = {
  overview: "运行总览", preview: "运行预览", services: "服务健康", logs: "实时日志", tasks: "异步任务",
  debug: "调试记录", diagnostics: "诊断报告", config: "配置中心",
  secrets: "密钥保险箱",
};

$$(".nav-item").forEach((button) => button.addEventListener("click", async () => {
  await loadPage(button.dataset.page);
  $(".sidebar").classList.remove("open");
}));

async function loadPage(page) {
  if (state.logSource && page !== "logs") { state.logSource.close(); state.logSource = null; }
  if (state.previewTimer && page !== "preview") {
    clearInterval(state.previewTimer);
    state.previewTimer = null;
  }
  state.currentPage = page;
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.page === page));
  $$(".page").forEach((item) => item.classList.toggle("active", item.id === `page-${page}`));
  $("#page-title").textContent = titles[page] || "Console";
  try {
    const loaders = {
      overview: loadOverview, preview: loadPreview, services: loadServices, logs: loadLogs, tasks: loadTasks,
      debug: loadDebugFiles, diagnostics: loadDiagnostics, config: loadConfig,
      secrets: loadSecrets,
    };
    if (loaders[page]) await loaders[page]();
  } catch (error) {
    toast(error.message, true);
  }
}

async function loadPreview() {
  const data = await api("/api/runtime-preview");
  $("#preview-time").textContent = new Date(data.server_time).toLocaleString("zh-CN");
  $("#chat-preview").innerHTML = data.chats.length ? data.chats.map((chat) => `
    <details class="preview-card">
      <summary><strong>${chat.kind === "group" ? "群聊" : "私聊"} ${escapeHtml(chat.key)}</strong><small>${chat.last_time ? new Date(chat.last_time).toLocaleString("zh-CN") : "—"}</small></summary>
      <div>${chat.messages.map((message) => `<div class="timeline-row"><time>${message.time ? new Date(message.time).toLocaleTimeString("zh-CN") : "—"}</time><strong>${escapeHtml(message.sender)}</strong><p>${escapeHtml(message.content)}</p></div>`).join("")}</div>
    </details>`).join("") : `<div class="empty-state">当前消息队列中没有聊天记录。</div>`;
  $("#ai-preview").innerHTML = data.ai_calls.length ? data.ai_calls.map((call) => `
    <details class="preview-card">
      <summary><strong>${escapeHtml(call.target || call.event_id || "AI 调用")}</strong><small>${new Date(call.captured_at).toLocaleString("zh-CN")}</small></summary>
      <div class="io-block"><h4>输入</h4><pre>${escapeHtml(JSON.stringify(call.input, null, 2))}</pre><h4>输出</h4><pre>${escapeHtml(JSON.stringify(call.output, null, 2))}</pre></div>
    </details>`).join("") : `<div class="empty-state">尚未捕获到本次启动后的 AI 调用。</div>`;
  $("#background-preview").innerHTML = data.background.length ? `<table><thead><tr><th>类型</th><th>任务</th><th>内容</th><th>状态</th></tr></thead><tbody>${data.background.map((item) =>
    `<tr><td>${escapeHtml(item.type)}</td><td>${escapeHtml(item.name)}</td><td>${escapeHtml(item.detail || "")}</td><td class="${item.status === "running" || item.status === "drawing" ? "ok" : "warn"}">${escapeHtml(item.status)}</td></tr>`
  ).join("")}</tbody></table>` : `<div class="empty-state">当前没有可展示的后台工作。</div>`;
  if ($("#live-preview").checked && !state.previewTimer && state.currentPage === "preview") {
    state.previewTimer = setInterval(() => {
      if (state.currentPage === "preview") loadPreview().catch((error) => toast(error.message, true));
    }, 3000);
  }
}

$("#live-preview").addEventListener("change", () => {
  if (!$("#live-preview").checked && state.previewTimer) {
    clearInterval(state.previewTimer);
    state.previewTimer = null;
  } else if (state.currentPage === "preview") {
    loadPreview().catch((error) => toast(error.message, true));
  }
});

async function loadOverview() {
  const data = await api("/api/overview");
  const running = data.status === "running";
  $("#hero-status").innerHTML = `
    <div><p class="eyebrow">RUNTIME STATUS</p>
      <h3>${running ? "NeoBot 正在稳定运行" : "NeoBot 正在启动"}</h3>
      <p>进程 ${escapeHtml(data.pid)} · 已运行 ${escapeHtml(formatDuration(data.uptime_seconds))} · ${escapeHtml(data.platform)}</p>
    </div><div class="status-orbit" aria-hidden="true"><span></span><i></i></div>`;
  const metrics = [
    ["运行时间", formatDuration(data.uptime_seconds), "当前进程生命周期"],
    ["活动任务", data.tasks, "asyncio 未完成任务"],
    ["群聊队列", data.queues.group.entries, `${data.queues.group.conversations} 个会话`],
    ["私聊队列", data.queues.friend.entries, `${data.queues.friend.conversations} 个会话`],
  ];
  $("#metric-grid").innerHTML = metrics.map(([label, value, note]) =>
    `<article class="metric-card"><p>${escapeHtml(label)}</p><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`
  ).join("");
  $("#disk-chart").innerHTML = `
    <div class="disk-legend"><span>已用 ${formatBytes(data.disk.used)}</span><span>${data.disk.percent}%</span></div>
    <div class="progress-track"><div class="progress-fill" style="width:${Math.min(100, data.disk.percent)}%"></div></div>
    <div class="disk-legend"><span>可用 ${formatBytes(data.disk.free)}</span><span>总计 ${formatBytes(data.disk.total)}</span></div>`;
  $("#adapter-card").innerHTML = `
    <div class="adapter-status"><div class="adapter-icon">IO</div><div>
      <strong>${escapeHtml(data.adapter.type)}</strong>
      <p>模式：${escapeHtml(data.adapter.mode)}</p>
      <small class="${data.adapter.connected ? "ok" : "warn"}">${data.adapter.connected ? "● 通道可用" : "● 等待连接"}</small>
    </div></div>`;
}

async function loadServices() {
  const data = await api("/api/services");
  $("#service-grid").innerHTML = data.services.map((service, index) => `
    <article class="service-card ${service.available ? "available" : ""}">
      <p>SERVICE / ${String(index + 1).padStart(2, "0")}</p>
      <strong>${escapeHtml(service.name)}</strong>
      <small class="${service.available ? "ok" : "warn"}">${service.available ? "AVAILABLE" : "NOT CONFIGURED"}</small>
    </article>`).join("");
}

async function loadLogs() {
  const params = new URLSearchParams({limit: "500"});
  const level = $("#log-level").value;
  const search = $("#log-search").value.trim();
  if (level) params.set("level", level);
  if (search) params.set("search", search);
  const data = await api(`/api/logs?${params}`);
  $("#log-output").textContent = data.lines.join("\n") || "暂无日志";
  scrollLogs();
  connectLogStream();
}

function connectLogStream() {
  if (state.logSource) state.logSource.close();
  if (!$("#live-logs").checked || state.currentPage !== "logs") return;
  state.logSource = new EventSource("/api/logs/stream", {withCredentials: true});
  state.logSource.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    const output = $("#log-output");
    if (output.textContent === "暂无日志" || output.textContent === "等待日志数据…") output.textContent = "";
    output.textContent += `${output.textContent ? "\n" : ""}${payload.line}`;
    const lines = output.textContent.split("\n");
    if (lines.length > 2000) output.textContent = lines.slice(-2000).join("\n");
    scrollLogs();
  };
}
function scrollLogs() { if ($("#live-logs").checked) $("#log-output").scrollTop = $("#log-output").scrollHeight; }
$("#log-level").addEventListener("change", loadLogs);
$("#log-search").addEventListener("input", debounce(loadLogs, 300));
$("#live-logs").addEventListener("change", connectLogStream);
$("#clear-log-view").addEventListener("click", () => $("#log-output").textContent = "");

async function loadTasks() {
  const data = await api("/api/tasks");
  $("#task-table").innerHTML = `<table><thead><tr><th>任务名称</th><th>协程</th><th>状态</th></tr></thead><tbody>${
    data.tasks.map((task) => `<tr><td>${escapeHtml(task.name)}</td><td><code>${escapeHtml(task.coroutine)}</code></td>
      <td class="${task.done ? "warn" : "ok"}">${task.cancelled ? "CANCELLED" : task.done ? "DONE" : "RUNNING"}</td></tr>`).join("")
  }</tbody></table>`;
}

async function loadDebugFiles() {
  const data = await api("/api/debug-files");
  $("#debug-file-grid").innerHTML = data.files.length ? data.files.map((file) => `
    <div class="file-row"><strong>${escapeHtml(file.path)}</strong><span>${formatBytes(file.size)}</span>
    <span>${new Date(file.modified_at).toLocaleString("zh-CN")}</span></div>`).join("")
    : `<div class="empty-state">暂无调试记录。可在配置中开启 debug.enabled 后生成记录。</div>`;
}

async function loadDiagnostics() {
  const data = await api("/api/diagnostics");
  const cards = [
    ["运行时", data.runtime], ["队列", data.queues], ["路径检查", data.paths],
    ["安全配置摘要", data.configuration], ["最近错误", data.recent_errors],
  ];
  $("#diagnostic-grid").innerHTML = cards.map(([title, value]) =>
    `<article class="diagnostic-card"><h3>${escapeHtml(title)}</h3><pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre></article>`
  ).join("");
}

async function loadConfig(force = false) {
  if (!force && state.config.length) { renderConfig(); return; }
  const data = await api("/api/admin/config");
  state.config = data.sections;
  state.changes.clear();
  renderConfig();
  updateChangeCount();
}

function renderConfig() {
  const query = $("#config-search").value.trim().toLowerCase();
  const sections = state.config.filter((section) => {
    const text = JSON.stringify(section).toLowerCase();
    return !query || text.includes(query);
  });
  $("#config-sections").innerHTML = sections.map((section, index) => `
    <details class="config-section" ${query || index < 2 ? "open" : ""}>
      <summary><span>${escapeHtml(section.label)}</span><small>${countFields(section.children)} 项</small></summary>
      <div class="config-fields">${renderConfigChildren(section.children, 0, query)}</div>
    </details>`).join("");
  $$(".config-input").forEach((input) => input.addEventListener("change", onConfigChange));
}

function countFields(children) {
  return children.reduce((sum, item) => sum + (item.kind === "section" ? countFields(item.children) : 1), 0);
}

function renderConfigChildren(children, depth, query) {
  return children.map((field) => {
    if (field.kind === "section") {
      const content = renderConfigChildren(field.children, depth + 1, query);
      return `<h4 class="nested-heading">${escapeHtml(field.label)}</h4>${content}`;
    }
    if (query && !`${field.path} ${field.description}`.toLowerCase().includes(query)) return "";
    const changed = state.changes.has(field.path);
    return `<div class="config-field${changed ? " changed" : ""}" data-path="${escapeHtml(field.path)}">
      <div><code>${escapeHtml(field.path)}</code><p>${escapeHtml(field.description || "未提供说明")}</p></div>
      <div>${renderInput(field, changed ? state.changes.get(field.path) : field.value)}</div>
    </div>`;
  }).join("");
}

function renderInput(field, value) {
  const data = `class="config-input" data-path="${escapeHtml(field.path)}" data-kind="${field.kind}"`;
  if (!field.editable) return `<input value="${escapeHtml(value)}" disabled aria-label="${escapeHtml(field.path)}">`;
  if (field.kind === "boolean") return `<label class="boolean-control"><input type="checkbox" ${data} ${value ? "checked" : ""}><span>${value ? "已开启" : "已关闭"}</span></label>`;
  if (["integer", "number"].includes(field.kind)) return `<input type="number" ${data} value="${escapeHtml(value)}" step="${field.kind === "integer" ? "1" : "any"}">`;
  if (["list", "mapping"].includes(field.kind)) return `<input ${data} value="${escapeHtml(JSON.stringify(value))}" aria-label="${escapeHtml(field.path)}">`;
  return `<input ${data} value="${escapeHtml(value ?? "")}" aria-label="${escapeHtml(field.path)}">`;
}

function onConfigChange(event) {
  const input = event.currentTarget;
  const kind = input.dataset.kind;
  let value;
  try {
    if (kind === "boolean") value = input.checked;
    else if (kind === "integer") value = Number.parseInt(input.value, 10);
    else if (kind === "number") value = Number.parseFloat(input.value);
    else if (["list", "mapping"].includes(kind)) value = JSON.parse(input.value);
    else if (kind === "null") value = input.value || null;
    else value = input.value;
    if (["integer", "number"].includes(kind) && Number.isNaN(value)) throw new Error("请输入有效数字");
  } catch (error) {
    toast(`${input.dataset.path}: ${error.message}`, true);
    return;
  }
  state.changes.set(input.dataset.path, value);
  input.closest(".config-field").classList.add("changed");
  if (kind === "boolean") input.nextElementSibling.textContent = value ? "已开启" : "已关闭";
  updateChangeCount();
}

function updateChangeCount() {
  $("#change-count").textContent = state.changes.size;
  $("#save-config").disabled = state.changes.size === 0;
  $("#save-restart-config").disabled = state.changes.size === 0;
}

$("#config-search").addEventListener("input", debounce(renderConfig, 180));
async function saveConfig() {
  if (!state.changes.size) return;
  const updates = [...state.changes].map(([path, value]) => ({path, value}));
  const result = await api("/api/admin/config", {method: "PATCH", body: JSON.stringify({updates})});
  await loadConfig(true);
  return result;
}

$("#save-config").addEventListener("click", async () => {
  try {
    const result = await saveConfig();
    if (result) toast(`已保存 ${result.changed.length} 项配置；可使用“重启 Bot 核心”立即生效。`);
  } catch (error) { toast(error.message, true); }
  finally { updateChangeCount(); }
});

async function restartCore() {
  if (!confirm("将完整关闭并重新创建 Bot 核心。记忆保存可能很久，页面会持续等待且不会判定超时。是否继续？")) return false;
  const initialResponse = await fetch("/healthz", {cache: "no-store", credentials: "same-origin"});
  const initialHealth = initialResponse.ok ? await initialResponse.json() : {};
  const dialog = $("#restart-dialog");
  $("#restart-status").textContent = "正在提交重启请求…";
  dialog.showModal();
  try {
    await api("/api/admin/restart", {method: "POST"});
  } catch (error) {
    dialog.close();
    throw error;
  }
  $("#restart-status").textContent = "正在等待核心完成关闭流程…";
  let observedOffline = false;
  while (true) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    try {
      const response = await fetch("/healthz", {cache: "no-store", credentials: "same-origin"});
      if (!response.ok) throw new Error("console unavailable");
      const health = await response.json();
      if (
        (initialHealth.instance && health.instance !== initialHealth.instance)
        || (!initialHealth.instance && observedOffline)
      ) {
        $("#restart-status").textContent = "新核心已启动，正在刷新控制台…";
        location.reload();
        return true;
      }
    } catch (_) {
      observedOffline = true;
      $("#restart-status").textContent = "核心正在保存记忆并关闭；将持续等待，不设超时…";
    }
  }
}

$("#restart-core").addEventListener("click", () => restartCore().catch((error) => toast(error.message, true)));
$("#save-restart-config").addEventListener("click", async () => {
  try {
    const result = await saveConfig();
    if (result) await restartCore();
  } catch (error) { toast(error.message, true); }
});

async function loadSecrets() {
  const data = await api("/api/admin/environment");
  $("#secret-grid").innerHTML = data.variables.length ? data.variables.map((item) => `
    <div class="secret-row">
      <strong>${escapeHtml(item.key)}</strong>
      <span class="${item.configured ? "ok" : "warn"}">${item.configured ? "已配置" : "未配置"}</span>
      <code>${escapeHtml(item.preview || "—")}</code>
      <div class="secret-actions">
        <button class="secondary-button edit-secret" data-key="${escapeHtml(item.key)}">替换</button>
        <button class="danger-button delete-secret" data-key="${escapeHtml(item.key)}">移除</button>
      </div>
    </div>`).join("") : `<div class="empty-state">环境变量文件中还没有可管理的变量。</div>`;
  $$(".edit-secret").forEach((button) => button.addEventListener("click", () => openSecretDialog(button.dataset.key)));
  $$(".delete-secret").forEach((button) => button.addEventListener("click", () => deleteSecret(button.dataset.key)));
}

function openSecretDialog(key = "") {
  $("#secret-key").value = key;
  $("#secret-key").readOnly = Boolean(key);
  $("#secret-value").value = "";
  $("#secret-dialog").showModal();
  setTimeout(() => (key ? $("#secret-value") : $("#secret-key")).focus(), 50);
}
$("#add-secret").addEventListener("click", () => openSecretDialog());
$$(".dialog-close").forEach((button) => button.addEventListener("click", () => $("#secret-dialog").close()));
$("#secret-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const key = $("#secret-key").value.trim();
  const value = $("#secret-value").value;
  try {
    await api(`/api/admin/environment/${encodeURIComponent(key)}`, {method: "PUT", body: JSON.stringify({value})});
    $("#secret-dialog").close();
    toast(`${key} 已安全保存；重启后完全生效。`);
    await loadSecrets();
  } catch (error) { toast(error.message, true); }
});
async function deleteSecret(key) {
  if (!confirm(`确定移除环境变量 ${key}？此操作会立即写入 .env。`)) return;
  try {
    await api(`/api/admin/environment/${encodeURIComponent(key)}`, {method: "DELETE"});
    toast(`${key} 已移除`);
    await loadSecrets();
  } catch (error) { toast(error.message, true); }
}

$("#logout-button").addEventListener("click", async () => {
  try { await api("/api/auth/logout", {method: "POST"}); } catch (_) {}
  state.csrf = null;
  showAuth();
});
$("#refresh-button").addEventListener("click", () => loadPage(state.currentPage));
$("#mobile-menu").addEventListener("click", () => $(".sidebar").classList.toggle("open"));
$("#forgot-password").addEventListener("click", () => $("#forgot-dialog").showModal());
$$(".forgot-close").forEach((button) => button.addEventListener("click", () => $("#forgot-dialog").close()));

function debounce(fn, delay) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay); };
}

initialize();
