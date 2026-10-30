import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/endpoints';
import type { ConfigDocument, Result } from '../api/types';
import { clearQueries } from '../data/queryCore';
import { POLL } from '../data/queryKeys';
import Plugins from '../pages/Plugins';

vi.mock('../auth/AuthContext', () => ({ useAuthGate: () => ({ canManage: true }) }));
vi.mock('../notifications/infoBar', () => ({ infoBar: vi.fn(), notify: vi.fn() }));
vi.mock('../components/TomlEditor', () => import('./mocks/TomlEditor'));
vi.mock('../api/endpoints', () => ({
  api: {
    plugins: vi.fn(),
    pluginConfig: vi.fn(),
    pluginConfigSave: vi.fn(),
    pluginSurface: vi.fn(),
  },
}));

const document: ConfigDocument = {
  revision: '00000000000000000000000000000001',
  config: { note: '原值' },
  form_supported: true,
  schema: [{ name: 'note', path: ['note'], kind: 'scalar', type: 'str' }],
};
const updated: ConfigDocument = {
  ...document,
  schema: [...document.schema!, { name: 'extra', path: ['extra'], kind: 'scalar', type: 'str' }],
};
function ok<T>(data: T): Result<T> {
  return { ok: true, status: 200, error: null, data };
}
async function tick() {
  await act(async () => vi.advanceTimersByTimeAsync(POLL.pluginSurface));
}
async function mount() {
  await act(async () => {
    render(<Plugins />);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  clearQueries();
  vi.mocked(api.plugins).mockResolvedValue({
    manage_enabled: true,
    hot_reload: true,
    items: [{ id: 'demo', name: 'demo', status: 'loaded', enabled: true, hot_reload: true }],
  });
  vi.mocked(api.pluginSurface).mockResolvedValue(
    ok({
      contract: null,
      available: true,
      state: 'loaded',
      permissions: ['read', 'manage'],
      source: 'runtime',
    }),
  );
  vi.mocked(api.pluginConfig).mockResolvedValue(ok(document));
});
afterEach(() => vi.useRealTimers());

describe('插件配置契约热更新', () => {
  it('代码重载只改变 schema、未改变配置 revision 时也同步新表单', async () => {
    await mount();
    expect(screen.queryByRole('textbox', { name: 'extra' })).not.toBeInTheDocument();
    vi.mocked(api.pluginConfig).mockResolvedValue(ok(updated));
    await tick();
    expect(screen.getByRole('textbox', { name: 'extra' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'note' })).toHaveValue('原值');
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
  });

  it('输入焦点与未保存草稿均保留原表单，不因新 schema 丢失输入', async () => {
    await mount();
    const input = screen.getByRole('textbox', { name: 'note' });
    act(() => input.focus());
    vi.mocked(api.pluginConfig).mockResolvedValue(ok(updated));
    await tick();
    expect(api.pluginConfig).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('textbox', { name: 'note' })).toBe(input);
    fireEvent.change(input, { target: { value: '尚未保存' } });
    act(() => input.blur());
    await tick();
    expect(screen.getByRole('textbox', { name: 'note' })).toBe(input);
    expect(input).toHaveValue('尚未保存');
    expect(screen.queryByRole('textbox', { name: 'extra' })).not.toBeInTheDocument();
  });

  it('新 schema 在途读取期间开始输入，旧响应不能覆盖草稿', async () => {
    await mount();
    let finish!: (value: Result<ConfigDocument>) => void;
    vi.mocked(api.pluginConfig).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    await tick();
    const input = screen.getByRole('textbox', { name: 'note' });
    fireEvent.change(input, { target: { value: '请求途中输入' } });
    await act(async () => finish(ok(updated)));
    expect(screen.getByRole('textbox', { name: 'note' })).toBe(input);
    expect(input).toHaveValue('请求途中输入');
    expect(screen.queryByRole('textbox', { name: 'extra' })).not.toBeInTheDocument();
  });
});
