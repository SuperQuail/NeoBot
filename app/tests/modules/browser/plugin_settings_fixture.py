"""真实浏览器使用的最小插件设置页，只调用公开 SDK。"""

SETTINGS_PAGE = """<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>数值设置</title>
<link rel="stylesheet" href="_ui.css"><script src="_sdk.js"></script>
<script defer src="app.js"></script></head>
<body>
<section id="value-settings" class="nb-view nb-stack">
  <label for="value">数值</label><input id="value" name="value" type="number" min="1" value="1">
  <button id="save" type="button">保存数值</button>
  <button id="refresh" type="button">读取数值</button>
  <p>已保存数值：<output id="result" aria-label="已保存数值">尚未读取</output></p>
</section>
</body></html>
"""

SETTINGS_SCRIPT = """(() => {
  const sdk = window.NeoBotPlugin;
  const input = document.getElementById('value');
  const save = document.getElementById('save');
  const refresh = document.getElementById('refresh');
  let context;
  let pending = false;

  function updateControls() {
    const readable = context?.available && !context.suspended && !pending;
    const writable = readable && context.permissions.includes('manage');
    input.disabled = !writable;
    save.disabled = !writable;
    refresh.disabled = !readable;
    document.body.dataset.suspended = String(!!context?.suspended);
    document.body.dataset.mode = context?.mode || '';
  }

  async function readValues() {
    const rows = await sdk.action('list');
    document.getElementById('result').textContent = rows.map(row => row.value).join(', ');
  }

  async function run(task) {
    pending = true;
    updateControls();
    try {
      await task();
    } catch (error) {
      await sdk.notify({title: '数值操作未完成', message: error.message, tone: 'err'});
    } finally {
      pending = false;
      updateControls();
    }
  }

  save.addEventListener('click', () => void run(async () => {
    await sdk.action('set', {value: Number(input.value)});
    await readValues();
    await sdk.notify({title: '数值已保存', tone: 'ok'});
  }));
  refresh.addEventListener('click', () => void run(readValues));
  sdk.registerAnchor('value', document.getElementById('value-settings'));
  sdk.onContext(next => {
    context = next;
    updateControls();
  });
  void sdk.ready().then(async next => {
    context = next;
    updateControls();
    if (context.available && !context.suspended) await run(readValues);
    document.body.dataset.ready = 'true';
  });
})();
"""
