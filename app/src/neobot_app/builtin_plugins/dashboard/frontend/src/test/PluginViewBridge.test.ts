import { describe, expect, it, vi } from 'vitest';
import { createPluginViewBridge } from '../pages/plugins/pluginViewBridge';
import type { PluginSurfaceContract } from '../api/types';
import type { PluginViewContext } from '../pages/plugins/pluginViewBridge';

const contract: PluginSurfaceContract = {
  schema_version: 1,
  plugin: { name: 'demo' },
  config: null,
  resources: [],
  guides: [],
  actions: [{ id: 'save', title: '保存', permission: 'manage', input_schema: null, output_schema: null }],
  views: [{ id: 'editor', title: '编辑', entry: 'web/index.html', anchors: ['save'] }],
};

function fixture(mode: 'live' | 'demo' = 'live') {
  const definition = structuredClone(contract);
  const frame = {} as Window;
  const posted: unknown[] = [];
  const run = vi.fn().mockResolvedValue({ ok: true, result: { saved: true } });
  const context: PluginViewContext = {
    pluginId: 'demo',
    viewId: 'editor',
    mode,
    permissions: ['manage'],
    available: true,
    theme: {},
    reducedMotion: false,
    language: 'zh-CN',
  };
  const notify = vi.fn();
  const navigate = vi.fn();
  const anchors = vi.fn();
  const resize = vi.fn();
  const reveal = vi.fn();
  const getConfig = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    error: null,
    data: {
      revision: '00000000000000000000000000000004',
      config: { note: '已屏蔽敏感字段的配置' },
      source: '不能桥接源码',
      path: '不能桥接磁盘路径',
    },
  });
  const saveConfig = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    error: null,
    data: { revision: '00000000000000000000000000000005', config: { note: '新配置' }, applied: true },
  });
  const bridge = createPluginViewBridge({
    source: () => frame,
    post: (message) => posted.push(message),
    contract: () => definition,
    context: () => context,
    demo: () => ({ actions: { save: { saved: 'synthetic' } }, config: { note: '合成配置' } }),
    run,
    notify,
    navigate,
    anchors,
    resize,
    reveal,
    configuration: () => {
      if (context.mode === 'demo') return { mode: 'demo', values: { note: '合成配置' } };
      return { mode: 'live', access: { get: getConfig, save: saveConfig } };
    },
    session: 'session-test',
  });
  const send = (method: string, params: unknown = {}, source = frame, session = 'session-test') =>
    bridge.receive({
      source,
      data: {
        channel: 'neobot-plugin-view',
        version: 1,
        kind: 'request',
        requestId: `${method}-${posted.length}`,
        method,
        params,
        session,
      },
    } as MessageEvent);
  return {
    bridge,
    run,
    posted,
    frame,
    send,
    context,
    notify,
    navigate,
    anchors,
    resize,
    reveal,
    getConfig,
    saveConfig,
    definition,
  };
}

describe('插件页面桥接', () => {
  it('焦点滚动只接收当前内联真实页面的有效会话，暂停和演示期间不移动正文', async () => {
    const test = fixture();
    test.context.layout = 'inline';
    const rectangle = { left: 0, top: 20, width: 100, height: 44 };
    await test.send('reveal', { rectangle }, {} as Window);
    await test.send('reveal', { rectangle }, test.frame, 'expired');
    expect(test.reveal).not.toHaveBeenCalled();
    for (const invalid of [
      null,
      { ...rectangle, top: -1 },
      { ...rectangle, width: 0 },
      { ...rectangle, top: Infinity },
    ]) {
      await test.send('reveal', { rectangle: invalid });
      expect(test.posted.at(-1)).toMatchObject({ error: { code: 'invalid_rectangle' } });
    }
    await test.send('reveal', { rectangle });
    expect(test.reveal).toHaveBeenCalledTimes(1);
    expect(test.reveal).toHaveBeenLastCalledWith(rectangle);
    test.context.suspended = true;
    await test.send('reveal', { rectangle });
    test.context.suspended = false;
    test.context.mode = 'demo';
    await test.send('reveal', { rectangle });
    test.context.mode = 'live';
    test.context.layout = 'stage';
    await test.send('reveal', { rectangle });
    expect(test.reveal).toHaveBeenCalledTimes(1);
    expect(test.run).not.toHaveBeenCalled();
  });
  it('只允许当前页面会话调整内联高度，拒绝非法尺寸并限制异常高度', async () => {
    const test = fixture();
    test.context.layout = 'inline';
    await test.send('resize', { height: 250 }, {} as Window);
    await test.send('resize', { height: 250 }, test.frame, 'expired');
    expect(test.resize).not.toHaveBeenCalled();
    for (const height of [0, -1, NaN, Infinity, '300']) {
      await test.send('resize', { height });
      expect(test.posted.at(-1)).toMatchObject({ error: { code: 'invalid_height' } });
    }
    await test.send('resize', { height: 250.5 });
    expect(test.resize).toHaveBeenLastCalledWith(251);
    await test.send('resize', { height: 1000000 });
    expect(test.resize).toHaveBeenLastCalledWith(20000);
    test.context.layout = 'stage';
    test.resize.mockClear();
    await test.send('resize', { height: 250 });
    expect(test.resize).not.toHaveBeenCalled();
    expect(test.run).not.toHaveBeenCalled();
  });
  it.each(['', '0123456789abcdef0123456789abcdef'])(
    '原样保存真实配置文档的字符串版本 %j',
    async (revision) => {
      const test = fixture();
      test.definition.config = { type: 'object' };
      test.context.permissions = ['read', 'manage'];
      test.getConfig.mockResolvedValueOnce({
        ok: true,
        status: 200,
        error: null,
        data: { revision, config: { note: '当前配置' } },
      });
      await test.send('getConfig');
      const document = (test.posted.at(-1) as { result: { revision: string } }).result;
      await test.send('saveConfig', { values: { note: '保留我的修改' }, revision: document.revision });
      expect(test.saveConfig).toHaveBeenCalledWith({ note: '保留我的修改' }, revision);
      expect((test.posted.at(-1) as { error?: unknown }).error).toBeUndefined();
    },
  );

  it('不会把数字版本号当成真实配置文件版本', async () => {
    const test = fixture();
    test.definition.config = { type: 'object' };
    await test.send('saveConfig', { values: { note: '草稿' }, revision: 7 });
    expect(test.saveConfig).not.toHaveBeenCalled();
    expect(test.posted.at(-1)).toMatchObject({ error: { code: 'invalid_config' } });
  });

  it('只接受当前 iframe 和会话，握手不包含宿主凭据', async () => {
    const test = fixture();
    await test.send('ready', {}, {} as Window);
    expect(test.posted).toEqual([]);
    await test.send('ready');
    expect(test.posted).toHaveLength(1);
    expect(JSON.stringify(test.posted)).not.toMatch(/csrf|token|password/i);
    await test.send('action', { id: 'save', values: {} }, test.frame, 'wrong-session');
    expect(test.run).not.toHaveBeenCalled();
  });

  it('真实模式只调用当前插件声明且获准的动作', async () => {
    const test = fixture();
    await test.send('action', { id: 'unknown', values: {} });
    expect(test.run).not.toHaveBeenCalled();
    await test.send('action', { id: 'save', values: { value: 7 } });
    expect(test.run).toHaveBeenCalledWith(contract.actions[0], { value: 7 }, true);
    expect(test.posted.at(-1)).toMatchObject({ result: { saved: true } });
  });

  it('演示模式使用声明样例，写动作也不触发真实调用', async () => {
    const test = fixture('demo');
    await test.send('action', { id: 'save', values: { value: 9 } });
    expect(test.run).not.toHaveBeenCalled();
    expect(test.posted.at(-1)).toMatchObject({ result: { saved: 'synthetic' } });
  });

  it('页面关闭后丢弃在途响应，清理桥接会话', async () => {
    const test = fixture();
    let resolve!: (value: unknown) => void;
    test.run.mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    const request = test.send('action', { id: 'save', values: {} });
    test.bridge.dispose();
    resolve({ ok: true, result: { saved: true } });
    await request;
    expect(test.posted).toEqual([]);
    await test.send('ready');
    expect(test.posted).toEqual([]);
  });

  it('只读、停止与演示暂停期间均拒绝真实写入', async () => {
    const test = fixture();
    test.context.permissions = ['read'];
    await test.send('action', { id: 'save' });
    expect(test.posted.at(-1)).toMatchObject({ error: { code: 'permission_denied' } });
    test.context.permissions = ['manage'];
    test.context.available = false;
    await test.send('action', { id: 'save' });
    expect(test.posted.at(-1)).toMatchObject({ error: { code: 'permission_denied' } });
    test.context.available = true;
    test.context.suspended = true;
    await test.send('action', { id: 'save' });
    expect(test.posted.at(-1)).toMatchObject({ error: { code: 'view_suspended' } });
    expect(test.run).not.toHaveBeenCalled();
  });

  it('保留根模型的 null 参数，并把明确业务错误交给页面', async () => {
    const test = fixture();
    test.run.mockResolvedValueOnce({ ok: false, code: 'invalid_room', error: '直播间不存在' });
    await test.send('action', { id: 'save', values: null });
    expect(test.run).toHaveBeenCalledWith(contract.actions[0], null, true);
    expect(test.posted.at(-1)).toMatchObject({ error: { code: 'invalid_room', message: '直播间不存在' } });
  });

  it('只接收声明锚点的有限几何值，通知和导航复用宿主入口', async () => {
    const test = fixture();
    const save = { left: 10, top: 20, width: 80, height: 40 };
    await test.send('anchors', { rectangles: { save, unknown: save } });
    expect(test.anchors).toHaveBeenLastCalledWith({ save });
    await test.send('anchors', { rectangles: { save: { ...save, left: Infinity } } });
    expect(test.anchors).toHaveBeenLastCalledWith({});
    await test.send('notify', { title: '已完成', message: '一条记录', tone: 'ok' });
    expect(test.notify).toHaveBeenCalledWith({ title: '已完成', message: '一条记录', tone: 'ok' });
    await test.send('navigate', { target: 'view.editor.save' });
    expect(test.navigate).toHaveBeenCalledWith('view.editor.save');
    await test.send('navigate', { target: 'https://example.com' });
    expect(test.navigate).toHaveBeenCalledTimes(1);
    expect(test.posted.at(-1)).toMatchObject({ error: { code: 'invalid_target' } });
  });

  it('配置桥接使用同一配置文档与 revision，不把源码和磁盘路径交给页面', async () => {
    const test = fixture();
    test.definition.config = { type: 'object' };
    test.context.permissions = ['read', 'manage'];
    await test.send('getConfig');
    expect(test.getConfig).toHaveBeenCalledTimes(1);
    expect(test.posted.at(-1)).toMatchObject({
      result: { revision: '00000000000000000000000000000004', config: { note: '已屏蔽敏感字段的配置' } },
    });
    expect(JSON.stringify(test.posted)).not.toMatch(/不能桥接/);
    await test.send('saveConfig', {
      values: { note: '新配置' },
      revision: '00000000000000000000000000000004',
    });
    expect(test.saveConfig).toHaveBeenCalledWith({ note: '新配置' }, '00000000000000000000000000000004');
    await test.send('saveConfig', { values: {} });
    expect(test.saveConfig).toHaveBeenCalledTimes(1);
    expect(test.posted.at(-1)).toMatchObject({ error: { code: 'invalid_config' } });
    test.saveConfig.mockResolvedValueOnce({
      ok: false,
      status: 409,
      error: '配置已变化',
      data: { errors: [{ path: 'note', message: '请重新合并' }] },
    });
    await test.send('saveConfig', {
      values: { note: '我的草稿' },
      revision: '00000000000000000000000000000004',
    });
    expect(test.posted.at(-1)).toMatchObject({
      error: { code: 'config_conflict', status: 409, fields: [{ path: 'note', message: '请重新合并' }] },
    });
    expect(test.notify).not.toHaveBeenCalled();
  });

  it.each([
    { applied: true, title: '插件配置已保存', message: '配置已热重载', tone: 'ok' },
    {
      applied: false,
      title: '配置已保存，尚未生效',
      message: '配置已保存，需重启 NeoBot 生效',
      tone: 'warn',
    },
  ])('设置页收起后补发一次保存结果并保留生效说明：$applied', async ({ applied, title, message, tone }) => {
    const test = fixture();
    test.definition.config = { type: 'object' };
    let resolve!: (value: unknown) => void;
    test.saveConfig.mockReturnValueOnce(
      new Promise((done) => {
        resolve = done;
      }),
    );
    const values = { note: '不得进入通知的配置值' };
    const request = test.send('saveConfig', { values, revision: '原始版本' });
    expect(test.saveConfig).toHaveBeenCalledWith(values, '原始版本');
    test.bridge.dispose();
    resolve({ ok: true, status: 200, error: null, data: { config: values, applied, message } });
    await request;
    expect(test.posted).toEqual([]);
    expect(test.notify).toHaveBeenCalledTimes(1);
    expect(test.notify).toHaveBeenCalledWith({ title, message, tone });
    expect(JSON.stringify(test.notify.mock.calls)).not.toContain(values.note);
  });

  it.each([
    { ok: false, status: 409, error: '配置已被其他窗口修改', data: { config: { note: '服务端值' } } },
    { ok: false, status: 500, error: '写入配置失败', data: null },
    { ok: true, status: 200, error: null, data: null },
  ])('设置页卸载后补发一次保存失败，成功但缺少文档也不误报：$status/$ok', async (response) => {
    const test = fixture();
    test.definition.config = { type: 'object' };
    let resolve!: (value: unknown) => void;
    test.saveConfig.mockReturnValueOnce(
      new Promise((done) => {
        resolve = done;
      }),
    );
    const request = test.send('saveConfig', { values: { note: '保留的草稿' }, revision: '原始版本' });
    test.bridge.dispose();
    resolve(response);
    await request;
    expect(test.posted).toEqual([]);
    expect(test.notify).toHaveBeenCalledTimes(1);
    expect(test.notify).toHaveBeenCalledWith({
      title: '插件配置保存失败',
      message: response.error || '配置操作未完成',
      tone: 'err',
    });
    expect(JSON.stringify(test.notify.mock.calls)).not.toMatch(/保留的草稿|服务端值/);
  });

  it('设置页卸载后的配置读取不补发保存通知', async () => {
    const test = fixture();
    test.definition.config = { type: 'object' };
    test.context.permissions = ['read'];
    const request = test.send('getConfig');
    test.bridge.dispose();
    await request;
    expect(test.posted).toEqual([]);
    expect(test.notify).not.toHaveBeenCalled();
  });

  it('演示读取合成配置且拒绝保存；只读权限禁止真实保存', async () => {
    const demo = fixture('demo');
    await demo.send('getConfig');
    expect(demo.posted.at(-1)).toMatchObject({ result: { revision: '', config: { note: '合成配置' } } });
    await demo.send('saveConfig', { values: { note: '不会写入' }, revision: '' });
    expect(demo.posted.at(-1)).toMatchObject({ error: { code: 'demo_read_only' } });
    expect(demo.getConfig).not.toHaveBeenCalled();
    expect(demo.saveConfig).not.toHaveBeenCalled();
    demo.bridge.dispose();
    expect(demo.notify).not.toHaveBeenCalled();
    const live = fixture();
    live.definition.config = { type: 'object' };
    live.context.permissions = ['read'];
    await live.send('saveConfig', { values: {}, revision: '00000000000000000000000000000004' });
    expect(live.saveConfig).not.toHaveBeenCalled();
    expect(live.posted.at(-1)).toMatchObject({ error: { code: 'permission_denied' } });
  });
});
