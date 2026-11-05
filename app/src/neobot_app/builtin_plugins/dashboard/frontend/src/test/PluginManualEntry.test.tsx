import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '../api/endpoints';
import type { PluginSurfacePayload, Result } from '../api/types';
import type { PluginViewSurface } from '../pages/plugins/pluginViewBridge';
import { clearQueries } from '../data/queryCore';
import { infoBar } from '../notifications/infoBar';
import PluginManualEntry from '../pages/plugins/PluginManualEntry';

vi.mock('../api/endpoints', () => ({
  api: {
    pluginSurface: vi.fn(),
    pluginViews: vi.fn(),
    pluginAction: vi.fn(),
    pluginConfig: vi.fn(),
    pluginConfigSave: vi.fn(),
  },
}));
vi.mock('../notifications/infoBar', () => ({ infoBar: vi.fn() }));

function ok<T>(data: T): Result<T> {
  return { ok: true, status: 200, error: null, data };
}
function surface(): PluginViewSurface {
  return {
    available: true,
    state: 'running',
    source: 'runtime',
    permissions: ['read', 'manage'],
    contract: {
      schema_version: 1,
      plugin: { name: 'demo', version: '1.0' },
      config: null,
      actions: [
        {
          id: 'save',
          title: '保存数值',
          permission: 'manage',
          input_schema: { type: 'object', properties: { count: { type: 'integer', default: 1 } } },
          output_schema: null,
        },
        { id: 'ready', title: '检查设置', permission: 'read', input_schema: null, output_schema: null },
      ],
      resources: [
        { id: 'items', title: '记录', list_action: 'ready', columns: [{ key: 'name', title: '名称' }] },
      ],
      guides: [
        {
          id: 'first',
          title: '首次使用',
          completion_action: 'ready',
          steps: [
            { target: 'action.save', text: '先填写一个数值。', chapter: '填写数值', example: { count: 3 } },
            {
              target: 'resource.items',
              text: '再查看记录说明。',
              chapter: '了解记录',
              example: { name: '样例记录' },
            },
          ],
          demo: { actions: { save: { saved: true }, ready: { completed: true } } },
        },
      ],
    },
  };
}
async function open() {
  const entry = await screen.findByRole('button', { name: '使用说明' });
  await waitFor(() => expect(entry).toBeEnabled());
  await userEvent.click(entry);
  return entry;
}

beforeEach(() => {
  vi.clearAllMocks();
  clearQueries();
  vi.mocked(api.pluginSurface).mockResolvedValue(ok(surface()));
});

describe('插件思索说明书入口', () => {
  it('直接打开唯一播放器，不展示业务工作台或发起真实业务请求', async () => {
    render(<PluginManualEntry pluginId="demo" />);
    const entry = await open();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(screen.getByRole('dialog', { name: 'demo · 思索说明书' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: '思索章节' })).toBeInTheDocument();
    expect(screen.getByText('先填写一个数值。', { selector: '.ponder-caption p' })).toBeVisible();
    expect(screen.queryByRole('tablist', { name: '插件功能' })).not.toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: '操作与数据' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '跟着做' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '检查是否完成' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '执行 保存数值' })).not.toBeInTheDocument();
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '下一步演示' }));
    await userEvent.click(screen.getByRole('button', { name: '下一步演示' }));
    expect(api.pluginAction).not.toHaveBeenCalled();
    expect(api.pluginConfig).not.toHaveBeenCalled();
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole('button', { name: '返回配置' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(entry).toHaveFocus();
  });

  it('停用插件仍可阅读 action/resource/config 说明，不执行完成检查', async () => {
    const payload = surface();
    payload.available = false;
    payload.state = 'disabled';
    payload.source = 'package';
    payload.permissions = [];
    payload.contract.guides[0].steps.push({
      target: 'config.note',
      text: '最后阅读配置说明。',
      chapter: '配置',
    });
    vi.mocked(api.pluginSurface).mockResolvedValue(ok(payload));
    render(<PluginManualEntry pluginId="demo" />);
    await open();
    await userEvent.click(screen.getByRole('button', { name: '下一步演示' }));
    expect(screen.getByText('再查看记录说明。', { selector: '.ponder-caption p' })).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '下一步演示' }));
    expect(screen.getByText('最后阅读配置说明。', { selector: '.ponder-caption p' })).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '下一步演示' }));
    expect(api.pluginAction).not.toHaveBeenCalled();
    expect(infoBar).not.toHaveBeenCalledWith(expect.objectContaining({ title: '插件当前未运行' }));
  });

  it('多份说明只通过播放器内的选择说明切换', async () => {
    const payload = surface();
    payload.contract.guides.push({
      id: 'advanced',
      title: '更多设置',
      steps: [{ target: 'config.note', text: '阅读更多配置说明。' }],
    });
    vi.mocked(api.pluginSurface).mockResolvedValue(ok(payload));
    render(<PluginManualEntry pluginId="demo" />);
    await open();
    const selection = screen.getByRole('combobox', { name: '选择说明' });
    selection.focus();
    await userEvent.keyboard('{ArrowDown}');
    await userEvent.click(screen.getByRole('option', { name: '更多设置' }));
    expect(screen.getByText('阅读更多配置说明。', { selector: '.ponder-caption p' })).toBeVisible();
    expect(screen.getAllByRole('dialog')).toHaveLength(1);
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
    expect(api.pluginAction).not.toHaveBeenCalled();
  });

  it('没有说明时不因声明动作、资源或业务页面而显示额外入口', async () => {
    const payload = surface();
    payload.contract.guides = [];
    payload.contract.views = [{ id: 'editor', title: '业务设置', entry: 'web/index.html', anchors: [] }];
    vi.mocked(api.pluginSurface).mockResolvedValue(ok(payload));
    render(<PluginManualEntry pluginId="demo" />);
    await waitFor(() => expect(api.pluginSurface).toHaveBeenCalledWith('demo'));
    expect(screen.queryByRole('button', { name: '使用说明' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '功能与教程' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '业务设置' })).not.toBeInTheDocument();
    expect(api.pluginViews).not.toHaveBeenCalled();
    expect(api.pluginAction).not.toHaveBeenCalled();
  });

  it('没有 SDK 契约的旧插件隐藏说明书入口', async () => {
    vi.mocked(api.pluginSurface).mockResolvedValue(
      ok<PluginSurfacePayload>({
        contract: null,
        available: false,
        state: 'disabled',
        source: 'none',
        permissions: [],
      }),
    );
    render(<PluginManualEntry pluginId="legacy" />);
    await waitFor(() => expect(api.pluginSurface).toHaveBeenCalledWith('legacy'));
    expect(screen.queryByRole('button', { name: '使用说明' })).not.toBeInTheDocument();
  });

  it('读取失败只通知 InfoBar，重试后恢复说明书而非业务控件', async () => {
    vi.mocked(api.pluginSurface).mockResolvedValue({
      ok: false,
      status: 500,
      error: '暂时无法读取',
      data: null,
    });
    render(<PluginManualEntry pluginId="demo" />);
    await open();
    expect(infoBar).toHaveBeenCalledWith(expect.objectContaining({ message: '暂时无法读取', tone: 'err' }));
    expect(screen.queryByText('暂时无法读取')).not.toBeInTheDocument();
    vi.mocked(api.pluginSurface).mockResolvedValue(ok(surface()));
    await userEvent.click(screen.getByRole('button', { name: '重试读取' }));
    expect(await screen.findByRole('navigation', { name: '思索章节' })).toBeVisible();
    expect(api.pluginAction).not.toHaveBeenCalled();
  });

  it('切换插件后旧说明响应不回写新说明书', async () => {
    let finish!: (value: Result<PluginSurfacePayload>) => void;
    vi.mocked(api.pluginSurface).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const test = render(<PluginManualEntry pluginId="first" />);
    await waitFor(() => expect(api.pluginSurface).toHaveBeenCalledWith('first'));
    const next = surface();
    next.contract.guides[0].steps[0].text = '这是第二个插件的说明。';
    vi.mocked(api.pluginSurface).mockResolvedValue(ok(next));
    test.rerender(<PluginManualEntry pluginId="second" />);
    await open();
    await act(async () => finish(ok(surface())));
    expect(screen.getByRole('dialog', { name: 'second · 思索说明书' })).toBeVisible();
    expect(screen.getByText('这是第二个插件的说明。', { selector: '.ponder-caption p' })).toBeVisible();
    expect(screen.queryByText('先填写一个数值。', { selector: '.ponder-caption p' })).not.toBeInTheDocument();
  });
});
