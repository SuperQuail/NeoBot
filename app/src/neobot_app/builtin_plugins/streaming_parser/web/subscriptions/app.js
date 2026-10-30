/* 页面只通过宿主桥接调用声明动作，不持有登录凭据。 */
(() => {
  const sdk = window.NeoBotPlugin;
  const $ = (id) => document.getElementById(id);
  const fallbackError = "操作暂时未完成，请稍后重试。";
  let context;
  let pending = false;
  let preview;
  let previewKey = "";
  let originalSize = false;
  let previewMode = "image";
  let groupSettings;
  let exampleVersion = 0;
  const settingIds = {
    card_style: "settings-style",
    ai_reply_live: "settings-ai-live",
    ai_reply_live_end: "settings-ai-end",
    default_push_live: "settings-push-live",
    default_push_live_end: "settings-push-end",
  };
  let groups = [];
  let items = [];
  let latestStep;
  let initialized = false;
  let refreshTimer;
  let reportedHealthError = "";
  let reportedBackgroundError = "";
  const disposers = [];
  const selectSync = new Map();
  const selection = () => ({
    group_id: Number($("group_id").value),
    target: $("target-input").value.trim(),
  });
  const key = () =>
    JSON.stringify([
      selection(),
      groupSettings &&
        Object.keys(settingIds).map((field) => groupSettings[field]),
    ]);
  const canManage = () =>
    context?.available &&
    !context.suspended &&
    context.mode !== "demo" &&
    context.permissions.includes("manage");

  function updateControls() {
    const available =
      !!context?.available && !context.suspended && context.mode !== "demo";
    document.querySelectorAll("button,input,select").forEach((node) => {
      node.disabled = pending || !available;
    });
    $("subscribe").disabled = pending || !canManage() || previewKey !== key();
    document.querySelectorAll("[data-manage]").forEach((node) => {
      node.disabled = pending || !canManage();
    });
    const groupReady =
      available &&
      canManage() &&
      groupSettings?.group_id === selection().group_id;
    for (const id of Object.values(settingIds))
      $(id).disabled = pending || !groupReady;
    $("save-settings").disabled =
      pending || !groupReady || (!settingsDirty() && !groupSettings?.inherited);
    $("reset-settings").disabled = pending || !available || !settingsDirty();
    if (settingsDirty()) {
      $("show-preview").disabled = true;
      $("subscribe").disabled = true;
    }
    $("preview-image").disabled = !preview;
    $("preview-text").disabled = !preview;
    if (!context?.available) $("health").textContent = "插件未运行";
    for (const sync of selectSync.values()) sync();
  }

  function showError(error) {
    // 进入演示时宿主会暂停隐藏页面，这是预期的请求中断。
    if (error.code === "view_suspended") return;
    sdk.notify({
      title: "操作未完成",
      message: error.message || fallbackError,
      tone: "err",
    });
  }

  async function run(task, background = false) {
    if (pending) return;
    // 后台读取不能临时禁用正在操作的控件，否则浏览器会移走焦点。
    const focusedControl =
      document.hasFocus() &&
      document.activeElement?.matches(
        "input,select,textarea,button,[contenteditable='true']",
      );
    if (background && focusedControl) return;
    pending = true;
    updateControls();
    try {
      await task();
    } catch (error) {
      const message = error.message || fallbackError;
      if (!background || message !== reportedBackgroundError) showError(error);
      if (background) reportedBackgroundError = message;
    } finally {
      pending = false;
      updateControls();
    }
  }

  async function action(name, values = {}) {
    return sdk.action("subscriptions." + name, values);
  }

  function requireSelection() {
    const value = selection();
    if (!value.group_id) throw new Error("先选择接收通知的群。");
    if (!value.target) throw new Error("粘贴直播间链接或输入房间号。");
    return value;
  }

  function invalidate() {
    preview = undefined;
    previewKey = "";
    $("identity").textContent = "房间号、短号和 uid: 写法也可以。";
    $("confirmation").hidden = true;
    $("preview-empty").hidden = false;
    $("preview-canvas").hidden = true;
    $("preview-style").textContent = "未预览";
    $("preview-zoom").hidden = true;
    $("preview-copy").hidden = true;
    $("preview-copy").textContent = "";
    updateControls();
  }

  async function loadGroups() {
    const result = await action("groups");
    groups = result.items;
    const current = $("group_id").value;
    $("group_id").replaceChildren(new Option("请选择接收群", ""));
    groups.forEach((group) =>
      $("group_id").add(new Option(group.name, String(group.group_id))),
    );
    if (groups.some((group) => String(group.group_id) === current))
      $("group_id").value = current;
    $("group-hint").hidden = groups.length > 0;
    $("group-hint").textContent = "机器人尚未加入群，加群后刷新。";
    updateListFilter();
    renderRows();
  }

  function showTarget(target) {
    $("identity").textContent =
      `${target.name || "未命名主播"} · 房间 ${target.room_id}`;
  }

  function sizePreview() {
    if (!preview) return;
    const scale = originalSize
      ? 1
      : Math.min(
          1,
          $("preview-canvas").clientWidth / 720,
          $("preview-canvas").clientHeight / 900,
        );
    $("card").style.transform = `scale(${scale})`;
    $("preview-stage").style.width = `${Math.ceil(720 * scale)}px`;
    $("preview-stage").style.height = `${Math.ceil(900 * scale)}px`;
    $("preview-zoom").textContent = originalSize ? "适应宽度" : "查看原始大小";
  }

  function showPreview(result) {
    preview = result;
    previewKey = key();
    $("card").srcdoc = result.html;
    $("preview-empty").hidden = true;
    $("preview-canvas").hidden = false;
    $("preview-style").textContent = `实际模板 · ${result.style}`;
    $("preview-copy").textContent = result.fallback_text;
    $("preview-zoom").hidden = false;
    showTarget(result.target);
    const group = groups.find((item) => item.group_id === selection().group_id);
    $("confirmation").textContent =
      `将通知发到「${group?.name || selection().group_id}」，监听「${result.target.name}」。`;
    $("confirmation").hidden = false;
    showPreviewMode(previewMode);
  }

  function showPreviewMode(mode) {
    previewMode = mode;
    $("preview-image").setAttribute("aria-pressed", String(mode === "image"));
    $("preview-text").setAttribute("aria-pressed", String(mode === "text"));
    $("preview-canvas").hidden = !preview || mode !== "image";
    $("preview-copy").hidden = !preview || mode !== "text";
    $("preview-zoom").hidden = !preview || mode !== "image";
    if (preview && mode === "image") sizePreview();
  }

  function settingValues() {
    return Object.fromEntries(
      Object.entries(settingIds).map(([field, id]) => [
        field,
        field === "card_style" ? $(id).value : $(id).checked,
      ]),
    );
  }

  function settingsDirty() {
    if (!groupSettings) return false;
    const values = settingValues();
    return Object.keys(settingIds).some(
      (field) => values[field] !== groupSettings[field],
    );
  }

  function applySettings(value) {
    groupSettings = value;
    if (preview && previewKey !== key()) invalidate();
    for (const [field, id] of Object.entries(settingIds)) {
      if (field === "card_style") $(id).value = value[field];
      else $(id).checked = value[field];
    }
    $("settings-origin").textContent = value.inherited
      ? "继承全局默认"
      : "已保存本群设置";
    updateControls();
  }

  function clearSettings() {
    groupSettings = undefined;
    $("settings-style").value = "random";
    for (const [field, id] of Object.entries(settingIds)) {
      if (field !== "card_style") $(id).checked = false;
    }
    $("settings-origin").textContent = "先选择接收群";
    updateControls();
  }

  async function loadSettings() {
    const groupId = selection().group_id;
    if (!groupId) {
      clearSettings();
      return;
    }
    $("settings-origin").textContent = "正在读取本群设置…";
    try {
      const value = await sdk.action("groups.settings.get", {
        group_id: groupId,
      });
      if (selection().group_id === groupId) applySettings(value);
    } catch (error) {
      if (selection().group_id === groupId)
        $("settings-origin").textContent = "读取未完成，请刷新接收群";
      throw error;
    }
  }

  function changeGroup() {
    if (context.mode === "demo") return;
    if (settingsDirty()) {
      $("group_id").value = String(groupSettings.group_id);
      selectSync.get($("group_id"))?.();
      void sdk.notify({ title: "先保存或放弃本群设置的修改", tone: "info" });
      return;
    }
    clearSettings();
    invalidate();
    void run(loadSettings);
  }

  async function saveSettings() {
    const value = await sdk.action("groups.settings.update", {
      group_id: selection().group_id,
      ...settingValues(),
    });
    applySettings(value);
    invalidate();
    void sdk.notify({ title: "本群通知设置已保存", tone: "ok" });
  }

  function updateListFilter() {
    const selected = $("list-filter").value;
    const choices = new Map(
      groups.map((group) => [group.group_id, group.name]),
    );
    for (const row of items) {
      if (!choices.has(row.group_id))
        choices.set(row.group_id, String(row.group_id));
    }
    $("list-filter").replaceChildren(new Option("全部群", ""));
    for (const [id, label] of choices)
      $("list-filter").add(new Option(label, String(id)));
    $("list-filter").value = choices.has(Number(selected)) ? selected : "";
    selectSync.get($("list-filter"))?.();
  }

  function showHealth(health) {
    let status;
    if (health.error) status = "检查异常";
    else if (!health.running) status = "轮询未运行";
    else if (!health.subscriptions) status = "暂无订阅";
    else if (!health.checked_at) status = "等待首次检查";
    else status = "监听中";
    $("health").textContent = status;
    const checked = health.checked_at
      ? new Date(health.checked_at).toLocaleTimeString()
      : "尚未检查";
    $("checked").textContent =
      `${health.subscriptions} 条订阅 · 最近检查 ${checked}`;
    $("health-success").textContent = health.success_at
      ? new Date(health.success_at).toLocaleString()
      : "尚无成功检查";
    $("health-counts").textContent =
      `${health.watched_rooms ?? 0} 个房间 · 成功 ${health.checked ?? 0} · 失败 ${health.failed ?? 0}`;
    $("health-message").textContent = health.message || "暂无监听说明";
    // 后台轮询只在出现新错误时提示，避免每次刷新重复打扰。
    if (health.error && health.error !== reportedHealthError)
      sdk.notify({
        title: "直播间检查未完成",
        message: health.error,
        tone: "warn",
      });
    reportedHealthError = health.error;
  }

  async function toggleSubscription(row, field, next) {
    const result = await action("toggle", {
      group_id: row.group_id,
      room_id: row.room_id,
      push_live: field === "push_live" ? next : row.push_live,
      push_live_end: field === "push_live_end" ? next : row.push_live_end,
    });
    row.push_live = result.item.push_live;
    row.push_live_end = result.item.push_live_end;
    sdk.notify({ title: "推送开关已更新", tone: "ok" });
  }

  function switchBox(row, field, title) {
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = row[field];
    input.dataset.manage = "";
    input.setAttribute(
      "aria-label",
      `${row.name || row.room_id} ${title}（群 ${row.group_id}）`,
    );
    input.addEventListener("change", () => {
      const next = input.checked;
      void run(() => toggleSubscription(row, field, next)).finally(renderRows);
    });
    return input;
  }

  async function removeSubscription(item) {
    const result = await action("remove", {
      group_id: item.group_id,
      room_id: item.room_id,
    });
    if (!result.removed) throw new Error("这条订阅已不存在，请刷新列表。");
    items = items.filter((value) => value !== item);
    renderRows();
    if (context.mode !== "demo") await refresh();
    sdk.notify({ title: "已取消监听", tone: "ok" });
  }

  function subscriptionRow(item) {
    const row = document.createElement("tr");
    const group = groups.find((value) => value.group_id === item.group_id);
    const identity = document.createElement("td");
    const name = document.createElement("strong");
    name.textContent = item.name || `房间 ${item.room_id}`;
    const room = document.createElement("span");
    room.className = "row-meta";
    room.textContent = `房间 ${item.room_id}${item.uid ? ` · UID ${item.uid}` : ""}`;
    identity.append(name, room);
    const receiver = document.createElement("td");
    receiver.textContent = group?.name || String(item.group_id);
    const status = document.createElement("td");
    const live = document.createElement("span");
    live.textContent =
      item.live_status == null
        ? "未检查"
        : { 0: "未开播", 1: "直播中", 2: "轮播中" }[item.live_status] || "未知";
    const checked = document.createElement("span");
    checked.className = "row-meta";
    checked.textContent = item.checked_at
      ? new Date(item.checked_at).toLocaleString()
      : "尚未检查";
    status.append(live, checked);
    row.append(identity, receiver, status);
    for (const [field, title] of [
      ["push_live", "开播通知"],
      ["push_live_end", "下播通知"],
    ]) {
      const cell = document.createElement("td");
      cell.append(switchBox(item, field, title));
      row.append(cell);
    }
    const cell = document.createElement("td");
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "nb-quiet nb-danger";
    remove.dataset.manage = "";
    remove.textContent = "取消监听";
    remove.setAttribute("aria-label", `取消监听 ${item.name}`);
    remove.addEventListener(
      "click",
      () => void run(() => removeSubscription(item)),
    );
    cell.append(remove);
    row.append(cell);
    return row;
  }

  function renderRows() {
    const groupId = Number($("list-filter").value);
    const rows = groupId
      ? items.filter((item) => item.group_id === groupId)
      : items;
    $("rows")
      .querySelector("tbody")
      .replaceChildren(...rows.map(subscriptionRow));
    $("rows").hidden = !rows.length;
    $("list-empty").hidden = !!rows.length;
    updateControls();
  }

  async function refresh() {
    items = (await action("list")).items;
    updateListFilter();
    renderRows();
    showHealth(await action("health"));
    reportedBackgroundError = "";
  }

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    if (
      !initialized ||
      context.mode !== "live" ||
      !context.available ||
      context.suspended
    )
      return;
    refreshTimer = setTimeout(async () => {
      if (!pending) await run(refresh, true);
      scheduleRefresh();
    }, 5000);
  }

  async function playExample(step) {
    if (step.mode !== "demo" || !step.target.startsWith("view.subscriptions."))
      return;
    const version = ++exampleVersion;
    const target = step.target.split(".").slice(2).join(".");
    const sample = step.example || {};
    const values = {
      group_id: Number(sample.group_id || 0),
      target: sample.target || "",
    };
    const needsPreview = [
      "preview",
      "start",
      "status",
      "settings",
      "health-panel",
    ].includes(target);
    const [resolved, card, health, settings] = await Promise.all([
      target === "target" && values.target
        ? action("resolve", { target: values.target })
        : null,
      needsPreview ? action("preview", values) : null,
      action("health"),
      values.group_id
        ? sdk.action("groups.settings.get", { group_id: values.group_id })
        : null,
    ]);
    if (version !== exampleVersion) return;
    // 每一步重建独立快照；后退和重播不能沿用后面章节已经填写或创建的内容。
    $("group_id").value = values.group_id ? String(values.group_id) : "";
    $("target-input").value = values.target;
    $("list-filter").value = "";
    items = Array.isArray(sample.items) ? sample.items : [];
    clearSettings();
    invalidate();
    if (settings) applySettings(settings);
    if (resolved) showTarget(resolved);
    if (card) showPreview(card);
    updateListFilter();
    renderRows();
    showHealth({
      ...health,
      subscriptions: items.length,
      watched_rooms: new Set(items.map((item) => item.room_id)).size,
      checked_at: items.length ? health.checked_at : null,
      success_at: items.length ? health.success_at : null,
      checked: items.length ? health.checked : 0,
      message: items.length
        ? health.message
        : "尚未添加订阅，按顺序填写上方表单。",
    });
    updateControls();
  }

  function updateContext(next) {
    const resume =
      (context.suspended || !context.available) &&
      next.available &&
      !next.suspended;
    context = next;
    updateControls();
    if (resume && next.mode === "live") void run(loadInitialData, true);
    scheduleRefresh();
  }

  function updateGuideStep(step) {
    latestStep = step;
    if (initialized) void playExample(step).catch(showError);
  }

  async function resolveTarget() {
    const value = requireSelection();
    showTarget(await action("resolve", { target: value.target }));
  }

  async function previewSelection() {
    const values = requireSelection();
    invalidate();
    showPreview(await action("preview", values));
  }

  async function subscribeSelection() {
    if (previewKey !== key())
      throw new Error("接收群或链接已变化，请重新预览。");
    const result = await action("create", requireSelection());
    if (context.mode === "demo") {
      items = [result.item];
      renderRows();
      showHealth(await action("health"));
    } else {
      await refresh();
    }
    sdk.notify({
      title: result.created ? "已开始监听" : "已更新监听信息",
      tone: "ok",
    });
  }

  function setupCustomSelect(select) {
    if (!select || select.dataset.customSelectInitialized) return () => {};
    select.dataset.customSelectInitialized = "true";

    const isSmall = select.classList.contains("field-control-sm");
    const wrapper = document.createElement("div");
    wrapper.className = `select-control-wrapper ${isSmall ? "select-control-sm" : ""}`;

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = `select-control ${isSmall ? "select-control-sm" : ""}`;
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    trigger.dataset.state = "closed";

    const valueSpan = document.createElement("span");
    valueSpan.className = "select-control-value";

    const iconSpan = document.createElement("span");
    iconSpan.className = "select-control-icon";
    iconSpan.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
        <path fill-rule="evenodd" d="M1.646 4.646a.5.5 0 0 1 .708 0L8 10.293l5.646-5.647a.5.5 0 0 1 .708.708l-6 6a.5.5 0 0 1-.708 0l-6-6a.5.5 0 0 1 0-.708z"/>
      </svg>`;

    trigger.append(valueSpan, iconSpan);

    const menu = document.createElement("div");
    menu.className = "select-control-menu";
    menu.setAttribute("role", "listbox");
    menu.hidden = true;

    const optionsContainer = document.createElement("div");
    optionsContainer.className = "select-control-options";
    menu.appendChild(optionsContainer);

    select.parentNode.insertBefore(wrapper, select);
    wrapper.appendChild(select);
    wrapper.appendChild(trigger);
    wrapper.appendChild(menu);

    select.classList.add("select-hidden-native");

    function closeMenu() {
      if (menu.hidden) return;
      menu.hidden = true;
      trigger.setAttribute("aria-expanded", "false");
      trigger.dataset.state = "closed";
    }

    function openMenu() {
      if (trigger.disabled || !menu.hidden) return;
      document.querySelectorAll(".select-control-menu").forEach((m) => {
        if (m !== menu) {
          m.hidden = true;
          const parentTrigger = m.parentElement?.querySelector(".select-control");
          if (parentTrigger) {
            parentTrigger.setAttribute("aria-expanded", "false");
            parentTrigger.dataset.state = "closed";
          }
        }
      });
      menu.hidden = false;
      trigger.setAttribute("aria-expanded", "true");
      trigger.dataset.state = "open";

      const checked = optionsContainer.querySelector('[data-state="checked"]');
      if (checked) checked.scrollIntoView({ block: "nearest" });
    }

    function sync() {
      trigger.disabled = select.disabled;
      if (select.disabled) closeMenu();
      const selectedOption =
        select.options[select.selectedIndex] || select.options[0];
      const text = selectedOption ? selectedOption.text : "";
      valueSpan.textContent = text;
      valueSpan.title = text;

      optionsContainer.replaceChildren();
      Array.from(select.options).forEach((opt) => {
        const isChecked = opt.value === select.value;
        const item = document.createElement("div");
        item.className = "select-control-option";
        item.setAttribute("role", "option");
        item.dataset.value = opt.value;
        if (isChecked) item.dataset.state = "checked";
        if (opt.disabled) item.dataset.disabled = "true";

        const label = document.createElement("span");
        label.className = "select-control-option-text";
        label.textContent = opt.text;
        item.appendChild(label);

        if (isChecked) {
          const check = document.createElement("span");
          check.className = "select-control-check";
          check.innerHTML = `
            <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
              <path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z"/>
            </svg>`;
          item.appendChild(check);
        }

        item.addEventListener("click", (e) => {
          e.stopPropagation();
          if (opt.disabled) return;
          if (select.value !== opt.value) {
            select.value = opt.value;
            select.dispatchEvent(new Event("change", { bubbles: true }));
          }
          closeMenu();
          sync();
        });

        optionsContainer.appendChild(item);
      });
    }

    trigger.addEventListener("click", (e) => {
      e.stopPropagation();
      if (menu.hidden) openMenu();
      else closeMenu();
    });

    const onPointerDown = (e) => {
      if (!wrapper.contains(e.target)) closeMenu();
    };
    document.addEventListener("pointerdown", onPointerDown);

    const onKeyDown = (e) => {
      if (e.key === "Escape") closeMenu();
    };
    wrapper.addEventListener("keydown", onKeyDown);

    // 原生 select 的属性由 DOM 管理；业务更新后显式同步，避免覆盖平台访问器。
    selectSync.set(select, sync);

    const observer = new MutationObserver(() => sync());
    observer.observe(select, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["disabled"],
    });

    select.addEventListener("change", () => sync());
    sync();

    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      wrapper.removeEventListener("keydown", onKeyDown);
      observer.disconnect();
      selectSync.delete(select);
    };
  }

  async function loadInitialData() {
    try {
      await loadGroups();
      if (!settingsDirty()) await loadSettings();
    } finally {
      // 群目录依赖机器人连接，读取失败也不能阻止管理本地已有订阅。
      if (context.mode !== "demo") await refresh();
    }
  }

  async function start() {
    context = await sdk.ready();
    for (const id of [
      "group",
      "target",
      "preview",
      "start",
      "status",
      "settings",
      "health-panel",
    ]) {
      disposers.push(sdk.registerAnchor(id, $(id)));
    }
    for (const id of ["group_id", "settings-style", "list-filter"]) {
      const el = $(id);
      if (el) disposers.push(setupCustomSelect(el));
    }
    disposers.push(sdk.onContext(updateContext));
    disposers.push(sdk.onGuideStep(updateGuideStep));
    $("group_id").addEventListener("change", changeGroup);
    $("target-input").addEventListener("input", invalidate);
    $("reload-groups").addEventListener(
      "click",
      () => void run(loadInitialData),
    );
    $("resolve").addEventListener("click", () => void run(resolveTarget));
    $("show-preview").addEventListener(
      "click",
      () => void run(previewSelection),
    );
    $("preview-zoom").addEventListener("click", () => {
      originalSize = !originalSize;
      sizePreview();
    });
    $("subscribe").addEventListener(
      "click",
      () => void run(subscribeSelection),
    );
    $("refresh").addEventListener("click", () => void run(refresh));
    $("list-filter").addEventListener("change", renderRows);
    $("preview-image").addEventListener("click", () =>
      showPreviewMode("image"),
    );
    $("preview-text").addEventListener("click", () => showPreviewMode("text"));
    for (const id of Object.values(settingIds))
      $(id).addEventListener("change", () => {
        if (context.mode === "demo") return;
        invalidate();
        $("settings-origin").textContent = settingsDirty()
          ? "有未保存的本群设置"
          : groupSettings?.inherited
            ? "继承全局默认"
            : "已保存本群设置";
      });
    $("save-settings").addEventListener("click", () => void run(saveSettings));
    $("reset-settings").addEventListener("click", () => {
      if (groupSettings) applySettings(groupSettings);
    });
    const observer = new ResizeObserver(sizePreview);
    observer.observe($("preview-canvas"));
    disposers.push(() => observer.disconnect());
    updateControls();
    if (context.available && !context.suspended) await run(loadInitialData);
    initialized = true;
    if (latestStep) await playExample(latestStep);
    showPreviewMode(previewMode);
    disposers.push(() => clearTimeout(refreshTimer));
    scheduleRefresh();
  }

  window.addEventListener(
    "pagehide",
    () => disposers.forEach((dispose) => dispose()),
    { once: true },
  );
  void start().catch(showError);
})();
