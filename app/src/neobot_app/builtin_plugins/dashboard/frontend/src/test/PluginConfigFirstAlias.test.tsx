import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import Plugins from '../pages/Plugins';
import { api } from '../api/endpoints';
import type { ConfigDocument } from '../api/types';
import { getPath } from '../utils/paths';

vi.mock('../notifications/infoBar', () => ({
  infoBar: vi.fn(),
  notify: vi.fn(),
  closeInfoBarDetails: vi.fn(),
}));
vi.mock('../components/TomlEditor', () => import('./mocks/TomlEditor'));
vi.mock('../auth/AuthContext', () => ({ useAuthGate: () => ({ canManage: true }) }));
vi.mock('../api/endpoints', () => ({
  api: { plugins: vi.fn(), pluginConfig: vi.fn(), pluginSurface: vi.fn(), pluginConfigSave: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.plugins).mockResolvedValue({
    console_plugin: 'dashboard',
    manage_enabled: true,
    hot_reload: true,
    items: [
      {
        id: 'demo',
        name: 'demo',
        version: '1.0',
        official: false,
        source: 'third_party',
        status: 'loaded',
        enabled: true,
        manageable: true,
        hot_reload: true,
      },
    ],
  });
  vi.mocked(api.pluginSurface).mockResolvedValue({
    ok: true,
    status: 200,
    error: null,
    data: { contract: null, available: false, state: 'loaded', permissions: ['read'], source: 'none' },
  });
});

describe('插件首次配置的输入别名', () => {
  it('扩容后继续编辑另一负别名仍提交对应的最后一项', async () => {
    const document: ConfigDocument = {
      revision: 'negative-alias',
      config: { payload: [{ a: 10 }] },
      form_supported: true,
      schema: [
        {
          name: 'last',
          path: ['payload', -1, 'a'],
          label: '最后一项',
          kind: 'scalar',
          type: 'int',
          value: 10,
        },
        {
          name: 'previous',
          path: ['payload', -2, 'b'],
          label: '前一项',
          kind: 'scalar',
          type: 'int',
          value: 20,
        },
      ],
    };
    vi.mocked(api.pluginConfig).mockResolvedValue({ ok: true, status: 200, error: null, data: document });
    vi.mocked(api.pluginConfigSave).mockResolvedValue({ ok: true, status: 200, error: null, data: document });
    render(<Plugins />);
    fireEvent.change(await screen.findByRole('spinbutton', { name: /前一项/ }), { target: { value: '25' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: /最后一项/ }), { target: { value: '15' } });
    fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));
    await waitFor(() => expect(api.pluginConfigSave).toHaveBeenCalled());
    expect(vi.mocked(api.pluginConfigSave).mock.calls[0][1].config).toEqual({
      payload: [{ b: 25 }, { a: 15 }],
    });
  });
  it.each([0, 2, -1, -2])('空配置中的数组下标 %s 可编辑并提交真实表单', async (index) => {
    const path = ['payload', index, 'entry'];
    const document: ConfigDocument = {
      revision: 'first-config',
      config: {},
      form_supported: true,
      schema: [
        { name: 'interval', path, label: '间隔秒数', kind: 'scalar', type: 'int', default: 60, value: 60 },
      ],
    };
    vi.mocked(api.pluginConfig).mockResolvedValue({ ok: true, status: 200, error: null, data: document });
    vi.mocked(api.pluginConfigSave).mockResolvedValue({ ok: true, status: 200, error: null, data: document });
    render(<Plugins />);
    fireEvent.change(await screen.findByRole('spinbutton', { name: /间隔秒数/ }), {
      target: { value: '15' },
    });
    fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));
    await waitFor(() => expect(api.pluginConfigSave).toHaveBeenCalled());
    const [name, body] = vi.mocked(api.pluginConfigSave).mock.calls[0];
    expect(name).toBe('demo');
    expect(getPath(body.config, path)).toBe(15);
    const serialized = JSON.parse(JSON.stringify(body.config));
    expect(getPath(serialized, path)).toBe(15);
    expect(serialized.payload).not.toContain(null);
    expect(serialized).not.toHaveProperty('interval');
  });
});
