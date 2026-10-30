import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/endpoints';
import type { ConfigDocument, PluginAction, PluginActionPayload, Result } from '../api/types';
import type { PluginActionHandlers } from '../pages/plugins/pluginProps';
import { usePluginSettingsAccess } from '../pages/plugins/usePluginSettingsAccess';

vi.mock('../api/endpoints', () => ({
  api: { pluginAction: vi.fn(), pluginConfig: vi.fn(), pluginConfigSave: vi.fn() },
}));

const readAction: PluginAction = {
  id: 'items.list',
  title: '查看记录',
  permission: 'read',
  input_schema: null,
  output_schema: null,
};
const writeAction: PluginAction = { ...readAction, id: 'items.add', title: '添加记录', permission: 'manage' };
const configDocument: ConfigDocument = {
  revision: '00000000000000000000000000000007',
  config: { note: '服务端保存结果' },
  schema: [],
};

function ok<T>(data: T): Result<T> {
  return { ok: true, status: 200, error: null, data };
}

function setup(overrides: Partial<Parameters<typeof usePluginSettingsAccess>[0]> = {}) {
  const act = vi.fn<PluginActionHandlers['act']>().mockImplementation(async (_key, request) => request());
  const applyDocument = vi.fn<PluginActionHandlers['applyDocument']>();
  const options = { pluginId: 'demo', canWrite: true, blocked: false, act, applyDocument, ...overrides };
  return { ...renderHook(() => usePluginSettingsAccess(options)), act, applyDocument };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.pluginAction).mockResolvedValue(ok({ ok: true, result: [{ id: 1 }] }));
  vi.mocked(api.pluginConfig).mockResolvedValue(ok(configDocument));
  vi.mocked(api.pluginConfigSave).mockResolvedValue(ok(configDocument));
});

describe('独立插件设置的共享访问边界', () => {
  it('读取动作和配置直接读取 API，不占父写入锁或回写编辑文档', async () => {
    const { result, act, applyDocument } = setup({ canWrite: false, blocked: true });
    const values = { limit: 20 };
    expect(await result.current.run(readAction, values)).toEqual({ ok: true, result: [{ id: 1 }] });
    expect(await result.current.configAccess.get()).toEqual(ok(configDocument));
    expect(api.pluginAction).toHaveBeenCalledWith('demo', 'items.list', values);
    expect(api.pluginConfig).toHaveBeenCalledWith('demo');
    expect(act).not.toHaveBeenCalled();
    expect(applyDocument).not.toHaveBeenCalled();
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
  });

  it.each(['operate', 'manage'] as const)('%s 动作等待父锁执行，并由页面负责反馈', async (permission) => {
    const { result, act } = setup();
    let release!: () => void;
    const ready = new Promise<void>((resolve) => {
      release = resolve;
    });
    act.mockImplementationOnce(async (_key, request) => {
      await ready;
      return request();
    });
    const action = { ...writeAction, permission };
    const values = { title: '新记录' };
    const pending = result.current.run(action, values);
    expect(act).toHaveBeenCalledWith('action:items.add', expect.any(Function), '添加记录', false);
    expect(api.pluginAction).not.toHaveBeenCalled();
    release();
    expect(await pending).toEqual({ ok: true, result: [{ id: 1 }] });
    expect(api.pluginAction).toHaveBeenCalledTimes(1);
    expect(api.pluginAction).toHaveBeenCalledWith('demo', 'items.add', values);
  });

  it.each([
    { canWrite: false, blocked: false },
    { canWrite: true, blocked: true },
  ])('权限或编辑状态不允许写入时拒绝动作和配置保存：%j', async (options) => {
    const { result, act, applyDocument } = setup(options);
    expect(await result.current.run(writeAction, { title: '不应提交' })).toMatchObject({
      ok: false,
      code: 'action_busy',
    });
    expect(await result.current.configAccess.save({ note: '不应覆盖' }, '')).toMatchObject({
      ok: false,
      status: 409,
      data: null,
    });
    expect(act).not.toHaveBeenCalled();
    expect(api.pluginAction).not.toHaveBeenCalled();
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
    expect(applyDocument).not.toHaveBeenCalled();
  });

  it.each(['', '00000000000000000000000000000007', 'opaque-revision/v2'])(
    '配置保存原样传递 revision %j 并应用成功文档',
    async (revision) => {
      const { result, act, applyDocument } = setup();
      const values = { note: '页面草稿', nested: { enabled: false } };
      const response = ok(configDocument);
      vi.mocked(api.pluginConfigSave).mockResolvedValueOnce(response);
      expect(await result.current.configAccess.save(values, revision)).toBe(response);
      expect(act).toHaveBeenCalledWith('view-config', expect.any(Function), '配置已保存', false);
      expect(api.pluginConfigSave).toHaveBeenCalledTimes(1);
      expect(api.pluginConfigSave).toHaveBeenCalledWith('demo', {
        mode: 'form',
        config: values,
        revision,
        reload: true,
      });
      expect(applyDocument).toHaveBeenCalledTimes(1);
      expect(applyDocument).toHaveBeenCalledWith(configDocument);
      expect(api.pluginConfig).not.toHaveBeenCalled();
    },
  );

  it('409 配置冲突原样交给页面，保留字段和版本，不回写或自动重试', async () => {
    const { result, act, applyDocument } = setup();
    const response: Result<ConfigDocument> = {
      ok: false,
      status: 409,
      error: '配置已经被其他窗口修改',
      data: {
        revision: 'server-revision',
        config: { note: '较新的服务端值' },
        errors: [{ path: 'note', message: '请重新核对配置' }],
      },
    };
    vi.mocked(api.pluginConfigSave).mockResolvedValueOnce(response);
    expect(await result.current.configAccess.save({ note: '页面原草稿' }, 'old-revision')).toBe(response);
    expect(act).toHaveBeenCalledTimes(1);
    expect(api.pluginConfigSave).toHaveBeenCalledTimes(1);
    expect(api.pluginConfig).not.toHaveBeenCalled();
    expect(applyDocument).not.toHaveBeenCalled();
  });

  it('动作错误保留服务端的 code 和字段诊断', async () => {
    const { result } = setup();
    const payload: PluginActionPayload = {
      ok: false,
      code: 'invalid_input',
      error: '输入无效',
      fields: [{ path: ['title'], type: 'string_too_short' }],
    };
    vi.mocked(api.pluginAction).mockResolvedValueOnce({
      ok: false,
      status: 422,
      error: '输入无效',
      data: payload,
    });
    expect(await result.current.run(writeAction, { title: '' })).toBe(payload);
  });

  it('父锁忙碌时动作返回 null，配置保存返回 409，均不发起 API', async () => {
    const { result, act, applyDocument } = setup();
    act.mockResolvedValue(undefined);
    expect(await result.current.run(writeAction, { title: '等待处理' })).toBeNull();
    expect(await result.current.configAccess.save({ note: '等待处理' }, '')).toEqual({
      ok: false,
      status: 409,
      data: null,
      error: '另一项操作正在执行',
    });
    expect(act).toHaveBeenCalledTimes(2);
    expect(api.pluginAction).not.toHaveBeenCalled();
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
    expect(applyDocument).not.toHaveBeenCalled();
  });
});
