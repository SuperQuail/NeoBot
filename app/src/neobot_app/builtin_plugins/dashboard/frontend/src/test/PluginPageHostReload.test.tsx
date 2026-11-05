import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/endpoints';
import type { PluginSurfacePayload } from '../api/types';
import { clearQueries, setQueryData } from '../data/queryCore';
import { QK } from '../data/queryKeys';
import Plugins from '../pages/Plugins';
import type { PluginViewSurface } from '../pages/plugins/pluginViewBridge';

vi.mock('../auth/AuthContext', () => ({ useAuthGate: () => ({ canManage: true }) }));
vi.mock('../notifications/infoBar', () => ({ infoBar: vi.fn(), notify: vi.fn() }));
vi.mock('../components/TomlEditor', () => import('./mocks/TomlEditor'));
vi.mock('../api/endpoints', () => ({
  api: {
    plugins: vi.fn(),
    pluginConfig: vi.fn(),
    pluginConfigSave: vi.fn(),
    pluginSurface: vi.fn(),
    pluginViews: vi.fn(),
    pluginAction: vi.fn(),
  },
}));

const view = {
  id: 'editor',
  title: '业务页面',
  entry: 'web/index.html',
  anchors: [],
  url: '/plugins-ui/demo/editor/?revision=one',
};
const surface: PluginViewSurface = {
  available: true,
  state: 'loaded',
  source: 'runtime',
  permissions: ['read', 'manage'],
  contract: {
    schema_version: 1,
    plugin: { name: 'demo' },
    config: { type: 'object' },
    actions: [
      { id: 'save', title: '保存记录', permission: 'manage', input_schema: null, output_schema: null },
    ],
    resources: [],
    guides: [],
    views: [view],
  },
};
function publish(value: PluginSurfacePayload) {
  act(() => setQueryData(QK.pluginSurface('demo'), value));
}
async function mount() {
  render(<Plugins />);
  await userEvent.click(await screen.findByRole('tab', { name: '插件页面' }));
  return screen.findByTitle<HTMLIFrameElement>('业务页面');
}
async function connect(frame: HTMLIFrameElement) {
  const source = frame.contentWindow!;
  const messages: Array<Record<string, unknown>> = [];
  vi.spyOn(source, 'postMessage').mockImplementation((message) => {
    messages.push(message);
  });
  let sequence = 0;
  let session = '';
  const request = async (method: string, params: unknown = {}) => {
    const requestId = String(++sequence);
    act(() =>
      window.dispatchEvent(
        new MessageEvent('message', {
          source,
          data: {
            channel: 'neobot-plugin-view',
            version: 1,
            kind: 'request',
            requestId,
            session,
            method,
            params,
          },
        }),
      ),
    );
    await waitFor(() => expect(messages.some((value) => value.requestId === requestId)).toBe(true));
    return messages.find((value) => value.requestId === requestId)!;
  };
  session = String((await request('ready')).session);
  return request;
}

beforeEach(() => {
  vi.clearAllMocks();
  clearQueries();
  vi.mocked(api.plugins).mockResolvedValue({
    manage_enabled: true,
    hot_reload: true,
    items: [{ id: 'demo', name: 'demo', status: 'loaded', enabled: true, hot_reload: true }],
  });
  vi.mocked(api.pluginConfig).mockResolvedValue({
    ok: true,
    status: 200,
    error: null,
    data: { config: {}, schema: [], form_supported: true, revision: '00000000000000000000000000000001' },
  });
  vi.mocked(api.pluginSurface).mockResolvedValue({ ok: true, status: 200, error: null, data: surface });
  vi.mocked(api.pluginViews).mockResolvedValue({
    ok: true,
    status: 200,
    error: null,
    data: { ok: true, items: [view] },
  });
});

describe('插件页面宿主的契约热更新边界', () => {
  it.each(['删除最后一页', '契约暂时不可用'] as const)('暂停期间%s保留窗口，恢复后才删除', async (kind) => {
    const frame = await mount();
    await userEvent.click(screen.getByRole('tab', { name: '配置表单' }));
    publish({ ...surface, contract: kind === '删除最后一页' ? { ...surface.contract, views: [] } : null });
    expect(screen.getByTitle('业务页面')).toBe(frame);
    expect(screen.getByRole('tab', { name: '插件页面' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: '插件页面' }));
    await waitFor(() => expect(screen.queryByTitle('业务页面')).not.toBeInTheDocument());
    expect(screen.queryByRole('tab', { name: '插件页面' })).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '配置表单' })).toHaveAttribute('aria-selected', 'true');
  });

  it('聚焦页面收到删除声明时保留窗口，焦点回到宿主后删除', async () => {
    const frame = await mount();
    act(() => frame.focus());
    publish({ ...surface, contract: { ...surface.contract, views: [] } });
    expect(screen.getByTitle('业务页面')).toBe(frame);
    expect(frame).toHaveFocus();
    act(() => screen.getByRole('tab', { name: '插件页面' }).focus());
    expect(screen.queryByTitle('业务页面')).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: '插件页面' })).not.toBeInTheDocument();
  });

  it('保留暂态不可用的聚焦窗口时立即阻止业务写入，恢复契约仍使用原窗口', async () => {
    const frame = await mount();
    const request = await connect(frame);
    act(() => frame.focus());
    publish({ ...surface, contract: null, available: false, permissions: [] });
    expect(screen.getByTitle('业务页面')).toBe(frame);
    expect(await request('action', { id: 'save', values: {} })).toMatchObject({
      error: { code: 'view_suspended' },
    });
    expect(await request('saveConfig', { values: {}, revision: 'old' })).toMatchObject({
      error: { code: 'view_suspended' },
    });
    expect(api.pluginAction).not.toHaveBeenCalled();
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
    publish(surface);
    expect(screen.getByTitle('业务页面')).toBe(frame);
    expect(await request('getConfig')).toMatchObject({ result: { config: {} } });
  });
});
