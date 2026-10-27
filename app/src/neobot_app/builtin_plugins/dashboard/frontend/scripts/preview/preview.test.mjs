import assert from 'node:assert/strict';
import { once } from 'node:events';
import { test } from 'node:test';
import { createPreviewServer } from './server.mjs';
import { DEFAULT_PORT, PREVIEW_HOST } from './http.mjs';

async function fixture(t, scenario = 'default') {
  const server = createPreviewServer({ scenario });
  server.listen(0, PREVIEW_HOST);
  await once(server, 'listening');
  t.after(
    () =>
      new Promise((resolve) => {
        server.closeAllConnections();
        server.close(resolve);
      }),
  );
  const base = 'http://' + PREVIEW_HOST + ':' + server.address().port;
  return async (path, { method = 'GET', body, headers = {}, authenticated = true, csrf = true } = {}) => {
    const response = await fetch(base + path, {
      method,
      headers: {
        ...(authenticated ? { 'x-token': 'preview-token' } : {}),
        ...(csrf ? { 'x-csrf-token': 'preview-csrf' } : {}),
        ...headers,
      },
      ...(body === undefined ? {} : { body: typeof body === 'string' ? body : JSON.stringify(body) }),
      signal: AbortSignal.timeout(5000),
    });
    const type = response.headers.get('content-type') || '';
    const data = type.includes('application/json') ? await response.json() : await response.text();
    return { status: response.status, headers: response.headers, data };
  };
}

test('authentication, cookies, CSRF and readonly gates retain their ordering', async (t) => {
  assert.equal(DEFAULT_PORT, 18881);
  const request = await fixture(t);
  assert.equal((await request('/__preview', { authenticated: false })).data.memory_only, true);
  assert.equal((await request('/api/auth/status', { authenticated: false })).data.configured, true);
  assert.equal((await request('/api/overview', { authenticated: false })).status, 401);
  assert.equal((await request('/api/auth/login', { authenticated: false })).status, 405);
  assert.equal(
    (await request('/api/auth/login', { method: 'POST', body: { password: 'wrong' }, authenticated: false }))
      .status,
    403,
  );
  const login = await request('/api/auth/login', {
    method: 'POST',
    body: { password: 'neobot-demo' },
    authenticated: false,
    csrf: false,
  });
  assert.equal(login.status, 200);
  assert.match(login.headers.get('set-cookie'), /HttpOnly; SameSite=Lax/);
  const cookie = login.headers.get('set-cookie').split(';')[0];
  assert.equal(
    (await request('/api/auth/me', { authenticated: false, headers: { cookie } })).data.authenticated,
    true,
  );
  assert.equal((await request('/api/config/reload', { method: 'POST', csrf: false })).status, 403);
  assert.equal(
    (await request('/__preview/scenario', { method: 'POST', body: { scenario: 'readonly' } })).status,
    200,
  );
  assert.equal((await request('/api/auth/me')).data.can_manage, false);
  assert.equal((await request('/api/config/reload', { method: 'POST' })).status, 403);
  assert.equal((await request('/api/config')).status, 200);
  assert.equal(
    (await request('/__preview/scenario', { method: 'POST', body: { scenario: 'invalid' } })).status,
    400,
  );
  assert.equal(
    (await request('/__preview/scenario', { method: 'POST', body: { scenario: 'default' } })).status,
    200,
  );
  const logout = await request('/api/auth/logout', { method: 'POST', csrf: false });
  assert.equal(logout.status, 200);
  assert.match(logout.headers.get('set-cookie'), /Max-Age=0/);
});

test('password edits are validated and isolated to one in-memory fixture', async (t) => {
  const request = await fixture(t);
  const password = {
    current_password: 'neobot-demo',
    new_password: 'demo-password-2',
    confirm: 'demo-password-2',
  };
  for (const body of [
    { ...password, current_password: 1 },
    { ...password, confirm: 'mismatch' },
    { ...password, new_password: 'short', confirm: 'short' },
    { ...password, new_password: ' demo-password ', confirm: ' demo-password ' },
  ])
    assert.equal((await request('/api/auth/password', { method: 'POST', body })).status, 400);
  assert.equal(
    (
      await request('/api/auth/password', {
        method: 'POST',
        body: { ...password, current_password: 'incorrect' },
      })
    ).status,
    403,
  );
  const changed = await request('/api/auth/password', { method: 'POST', body: password });
  assert.equal(changed.data.reauthenticate, true);
  assert.match(changed.headers.get('set-cookie'), /Max-Age=0/);
  assert.equal(
    (await request('/api/auth/login', { method: 'POST', body: { password: 'neobot-demo' } })).status,
    403,
  );
  assert.equal(
    (await request('/api/auth/login', { method: 'POST', body: { password: password.new_password } })).status,
    200,
  );
  const fresh = await fixture(t);
  assert.equal(
    (await fresh('/api/auth/login', { method: 'POST', body: { password: 'neobot-demo' } })).status,
    200,
  );
});

test('all scenarios preserve workspace shapes and do not reset memory on switching', async (t) => {
  const request = await fixture(t);
  const reads = [
    '/api/overview',
    '/api/bots',
    '/api/bot/detail',
    '/api/system',
    '/api/services',
    '/api/tasks',
    '/api/extensions',
    '/api/logs',
    '/api/series/messages',
    '/api/series/latency',
    '/api/stats/api-calls',
    '/api/stats/active-users',
    '/api/series/usage',
    '/api/stats/usage',
    '/api/stats/usage/records?detail=1&limit=20',
    '/api/config',
    '/api/config/env',
    '/api/config/models',
    '/api/config/billing',
    '/api/plugins',
    '/api/plugins/dashboard/config',
    '/api/prompts',
    '/api/analysis/prompts',
    '/api/chat-flows',
    '/api/chat-flows/detail',
    '/api/chat-flows/prompts',
    '/api/chat-flows/prompt?seq=1',
    '/api/archives',
    '/api/archives/items?table=user_profile',
    '/api/archives/item?table=user_profile&key=user:100002',
    '/api/archives/snapshots?table=user_profile&key=user:100002',
    '/api/archives/snapshot?id=1',
    '/api/scheduled-tasks',
    '/api/admin/power',
    '/api/deploy/status',
  ];
  for (const scenario of ['default', 'long', 'empty', 'readonly']) {
    await request('/__preview/scenario', { method: 'POST', body: { scenario } });
    for (const path of reads) {
      const result = await request(path);
      assert.equal(result.status, 200, scenario + ' ' + path + ': ' + JSON.stringify(result.data));
      assert.equal(result.headers.get('x-neobot-preview'), 'fictional-memory-only');
    }
    const prompts = (await request('/api/prompts')).data;
    assert.equal(prompts.sections.length, scenario === 'empty' ? 0 : scenario === 'long' ? 36 : 26);
    const plugins = (await request('/api/plugins')).data;
    assert.equal(plugins.items.length, scenario === 'empty' ? 0 : 7);
    assert.equal(plugins.manage_enabled, scenario !== 'readonly');
    const config = (await request('/api/config')).data;
    assert.equal(config.config.models.registry.length, scenario === 'long' ? 8 : 3);
  }
});

test('config revisions, form/source values and cross-workspace reads share the same memory', async (t) => {
  const request = await fixture(t);
  const doc = (await request('/api/config')).data;
  doc.config.bot.nick_name = '内存中的演示名称';
  const saved = await request('/api/config', {
    method: 'POST',
    body: { revision: doc.revision, config: doc.config },
  });
  assert.equal(saved.data.revision, doc.revision + 1);
  assert.equal(
    (await request('/api/config', { method: 'POST', body: { revision: doc.revision, config: doc.config } }))
      .status,
    409,
  );
  assert.equal((await request('/api/bots')).data[0].nickname, '内存中的演示名称');
  assert.equal((await request('/api/deploy/status')).data.values.bot_nick_name, '内存中的演示名称');
  const rendered = await request('/api/prompts/preview', {
    method: 'POST',
    body: { template: '{bot_name} / {missing}' },
  });
  assert.equal(rendered.data.rendered, '内存中的演示名称 / {missing}');
  assert.deepEqual(rendered.data.unresolved, ['missing']);
  const source = saved.data.source.replace('内存中的演示名称', 'TOML 演示名称');
  const sourceSaved = await request('/api/config', {
    method: 'POST',
    body: { revision: saved.data.revision, mode: 'toml', source },
  });
  assert.equal(sourceSaved.data.config.bot.nick_name, 'TOML 演示名称');
  assert.equal(
    sourceSaved.data.schema[0].fields.find((item) => item.name === 'nick_name').value,
    'TOML 演示名称',
  );
  await request('/__preview/scenario', { method: 'POST', body: { scenario: 'empty' } });
  await request('/__preview/scenario', { method: 'POST', body: { scenario: 'default' } });
  assert.equal((await request('/api/config')).data.config.bot.nick_name, 'TOML 演示名称');
});

test('plugin revisions and guarded starship toggles keep extensions synchronized', async (t) => {
  const request = await fixture(t);
  assert.deepEqual((await request('/api/extensions')).data.items, []);
  assert.equal((await request('/api/preview/starship/')).status, 404);
  const doc = (await request('/api/plugins/dashboard/config')).data;
  assert.equal(doc.schema.find((item) => item.name === 'greeting').value, doc.config.greeting);
  const saved = await request('/api/plugins/dashboard/config', {
    method: 'POST',
    body: {
      revision: doc.revision,
      mode: 'toml',
      source: 'enabled = false\ngreeting = "演示新值"\nmax_items = 8\nnotify_admin = false',
    },
  });
  assert.equal(saved.data.config.greeting, '演示新值');
  assert.equal(saved.data.schema.find((item) => item.name === 'enabled').value, false);
  assert.equal(
    (
      await request('/api/plugins/dashboard/config', {
        method: 'POST',
        body: { revision: doc.revision, config: {} },
      })
    ).status,
    409,
  );
  assert.equal((await request('/api/plugins/starship/toggle')).status, 405);
  assert.equal(
    (await request('/api/plugins/starship/toggle', { method: 'POST', body: { enabled: 'true' } })).status,
    400,
  );
  const enabled = await request('/api/plugins/starship/toggle', {
    method: 'POST',
    body: { enabled: true, expected_enabled: false },
  });
  assert.equal(enabled.data.state, 'running');
  assert.equal((await request('/api/extensions')).data.items[0].name, 'starship');
  assert.equal((await request('/api/preview/starship/')).status, 200);
  assert.equal(
    (
      await request('/api/plugins/starship/toggle', {
        method: 'POST',
        body: { enabled: false, expected_enabled: false },
      })
    ).status,
    409,
  );
  assert.equal((await request('/api/plugins/starship/toggle', { method: 'POST' })).data.state, 'unloaded');
  assert.deepEqual((await request('/api/extensions')).data.items, []);
});

test('archive snapshots, prompt edits, scheduled tasks and power actions stay in memory', async (t) => {
  const request = await fixture(t);
  const key = { table: 'user_profile', key: 'user:100002' };
  const query = '?table=user_profile&key=user:100002';
  const row = (await request('/api/archives/item' + query)).data;
  assert.equal(
    (
      await request('/api/archives/item', {
        method: 'PUT',
        body: { ...key, version: row.version - 1, value: '冲突' },
      })
    ).status,
    409,
  );
  const saved = await request('/api/archives/item', {
    method: 'PUT',
    body: { ...key, version: row.version, value: '演示正文'.repeat(80), tags: ['演示'] },
  });
  const compressed = await request('/api/archives/summarize', {
    method: 'POST',
    body: { ...key, target_chars: 200 },
  });
  assert.equal(compressed.data.status, 'running');
  assert.equal(
    (await request('/api/archives/summarize?task_id=' + compressed.data.task_id)).data.status,
    'done',
  );
  const snapshots = (await request('/api/archives/snapshots' + query)).data.items;
  assert.equal(snapshots.length, 1);
  assert.equal('value' in snapshots[0], false);
  assert.equal(
    (await request('/api/archives/snapshot?id=' + snapshots[0].id)).data.snapshot.value,
    saved.data.value,
  );
  const current = (await request('/api/archives/item' + query)).data;
  assert.equal(
    (await request('/api/archives/item', { method: 'DELETE', body: { ...key, version: current.version } }))
      .status,
    200,
  );
  assert.equal((await request('/api/archives/item' + query)).status, 404);
  await request('/api/prompts/save', {
    method: 'POST',
    body: { section: 'private_chat', path: 'template', value: '新模板' },
  });
  assert.equal(
    (await request('/api/prompts')).data.sections.find((item) => item.name === 'private_chat').keys[0].value,
    '新模板',
  );
  await request('/api/prompts/reset', {
    method: 'POST',
    body: { section: 'private_chat', path: 'template' },
  });
  assert.equal(
    (await request('/api/prompts')).data.sections.find((item) => item.name === 'private_chat').keys[0]
      .overridden,
    false,
  );
  await request('/api/chat-flows/prompts/clear', { method: 'POST' });
  assert.deepEqual((await request('/api/chat-flows/prompts')).data.items, []);
  await request('/api/scheduled-tasks/action', {
    method: 'POST',
    body: { action: 'create', title: '虚构新任务', start_at: '2026-10-27T15:00' },
  });
  const task = (await request('/api/scheduled-tasks')).data.tasks.find((item) => item.title === '虚构新任务');
  assert.ok(task);
  await request('/api/scheduled-tasks/action', {
    method: 'POST',
    body: { action: 'delete', task_uuid: task.task_id },
  });
  assert.equal((await request('/api/scheduled-tasks')).data.tasks.length, 2);
  await request('/api/admin/standby', { method: 'POST', body: { reason: '演示' } });
  assert.equal((await request('/api/overview')).data.online, false);
  await request('/api/admin/resume', { method: 'POST' });
  assert.equal((await request('/api/overview')).data.online, true);
});

test('static assets remain allowlisted and Bilibili login stays a fictional state machine', async (t) => {
  const request = await fixture(t);
  const image = await request('/image/icon.webp', { authenticated: false });
  assert.equal(image.status, 200);
  assert.equal(image.headers.get('content-type'), 'image/webp');
  for (const path of ['/image/auth.json', '/image/%2e%2e%2fauth.json', '/image/icon.webp/extra'])
    assert.equal((await request(path, { authenticated: false })).status, 404);
  assert.equal((await request('/bilibili/login', { authenticated: false })).status, 200);
  assert.equal((await request('/bilibili/login.js', { authenticated: false })).status, 200);
  assert.equal((await request('/bilibili/login', { method: 'POST', authenticated: false })).status, 405);
  assert.equal((await request('/api/bilibili/login/status', { authenticated: false })).status, 401);
  await request('/api/bilibili/login/start', { method: 'POST' });
  const states = [];
  for (let index = 0; index < 4; index++)
    states.push((await request('/api/bilibili/login/status')).data.state);
  assert.deepEqual(states, ['pending', 'scanned', 'scanned', 'expired']);
  const success = await request('/api/bilibili/login/start', { method: 'POST', body: { state: 'success' } });
  assert.equal(success.data.logged_in, true);
  assert.equal(success.data.qr_url, '');
  assert.equal((await request('/not-an-api')).status, 404);
  assert.equal((await request('/api/config', { method: 'POST', body: '{' })).status, 400);
  assert.equal(
    (await request('/api/config', { method: 'POST', body: 'x'.repeat(1024 * 1024 + 1) })).status,
    400,
  );
});
