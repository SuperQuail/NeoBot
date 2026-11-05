import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Plugins from '../pages/Plugins';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';

const auth = vi.hoisted(() => ({ canManage: false }));
vi.mock('../auth/AuthContext', () => ({ useAuthGate: () => auth }));
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

beforeEach(() => {
  vi.clearAllMocks();
  clearQueries();
  auth.canManage = false;
  vi.mocked(api.plugins).mockResolvedValue({
    manage_enabled: true,
    items: [{ name: 'demo', version: '1.0', status: 'loaded', enabled: true }],
  });
  vi.mocked(api.pluginConfig).mockResolvedValue({
    ok: true,
    status: 200,
    error: null,
    data: { config: {}, schema: [], revision: '00000000000000000000000000000001', form_supported: true },
  });
  vi.mocked(api.pluginSurface).mockResolvedValue({
    ok: true,
    status: 200,
    error: null,
    data: {
      available: true,
      state: 'loaded',
      source: 'runtime',
      permissions: ['read'],
      contract: {
        schema_version: 1,
        plugin: { name: 'demo' },
        config: null,
        actions: [
          {
            id: 'items.create',
            title: '添加订阅',
            permission: 'manage',
            input_schema: {},
            output_schema: {},
          },
        ],
        resources: [],
        guides: [{ id: 'start', title: '入门', steps: [{ target: 'config.note', text: '填写备注。' }] }],
      },
    },
  });
});

it('只读插件编辑器仍可阅读说明，不提供业务操作入口或自动读取资源', async () => {
  render(<Plugins />);
  await userEvent.click(await screen.findByRole('button', { name: '使用说明' }));
  expect(await screen.findByRole('dialog', { name: 'demo · 思索说明书' })).toBeVisible();
  expect(screen.queryByRole('button', { name: '执行 添加订阅' })).not.toBeInTheDocument();
  expect(screen.queryByRole('tab', { name: '操作与数据' })).not.toBeInTheDocument();
  expect(api.pluginAction).not.toHaveBeenCalled();
  expect(api.pluginConfigSave).not.toHaveBeenCalled();
});

it.each(['逐字输入', '首次原生输入'])(
  '%s 后打开和关闭说明书保留原配置草稿、输入节点及保存基线',
  async (inputMode) => {
    auth.canManage = true;
    vi.mocked(api.pluginConfig).mockResolvedValue({
      ok: true,
      status: 200,
      error: null,
      data: {
        config: { note: '已保存' },
        revision: '00000000000000000000000000000012',
        form_supported: true,
        schema: [{ name: 'note', path: ['note'], kind: 'scalar', type: 'str', value: '已保存' }],
      },
    });
    render(<Plugins />);
    const input = await screen.findByRole('textbox', { name: 'note' });
    if (inputMode === '首次原生输入') {
      fireEvent.input(input, { target: { value: '未保存的备注' } });
    } else {
      await userEvent.clear(input);
      await userEvent.type(input, '未保存的备注');
    }
    expect(screen.getByText('有未保存的修改')).toBeInTheDocument();
    const entry = screen.getByRole('button', { name: '使用说明' });
    await waitFor(() => expect(entry).toBeEnabled());
    await userEvent.click(entry);
    expect(screen.getByText('填写备注。', { selector: '.ponder-caption p' })).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: '返回配置' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'note' })).toBe(input);
    expect(input).toHaveValue('未保存的备注');
    expect(screen.getByText('有未保存的修改')).toBeInTheDocument();
    expect(api.pluginConfig).toHaveBeenCalledTimes(1);
    expect(api.pluginConfigSave).not.toHaveBeenCalled();
    expect(api.pluginAction).not.toHaveBeenCalled();
    expect(entry).toHaveFocus();
  },
);

it('原配置编辑器按当前草稿显示恢复图标，恢复默认不改保存基线或自动保存', async () => {
  auth.canManage = true;
  vi.mocked(api.pluginConfig).mockResolvedValue({
    ok: true,
    status: 200,
    error: null,
    data: {
      config: { note: '已保存的自定义备注' },
      revision: '00000000000000000000000000000013',
      form_supported: true,
      schema: [
        {
          name: 'note',
          path: ['note'],
          kind: 'scalar',
          type: 'str',
          value: '已保存的自定义备注',
          default: '默认备注',
        },
      ],
    },
  });
  render(<Plugins />);
  const input = await screen.findByRole('textbox', { name: 'note' });
  expect(screen.getByText('配置与文件同步')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '恢复默认' })).toBeEnabled();

  await userEvent.clear(input);
  await userEvent.type(input, '默认备注');
  expect(screen.queryByRole('button', { name: '恢复默认' })).not.toBeInTheDocument();
  expect(screen.getByText('有未保存的修改')).toBeInTheDocument();
  await userEvent.clear(input);
  await userEvent.type(input, '新的草稿');
  await userEvent.click(screen.getByRole('button', { name: '恢复默认' }));
  expect(screen.getByRole('textbox', { name: 'note' })).toBe(input);
  expect(input).toHaveValue('默认备注');
  expect(input).toHaveFocus();
  expect(screen.queryByRole('button', { name: '恢复默认' })).not.toBeInTheDocument();
  expect(screen.getByText('有未保存的修改')).toBeInTheDocument();

  await userEvent.clear(input);
  await userEvent.type(input, '已保存的自定义备注');
  expect(screen.getByText('配置与文件同步')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '恢复默认' })).toBeEnabled();
  expect(api.pluginConfig).toHaveBeenCalledTimes(1);
  expect(api.pluginConfigSave).not.toHaveBeenCalled();
  expect(api.pluginAction).not.toHaveBeenCalled();
});
