// Plugins 页面回归测试 —— 列表分组、选中态、按钮可用性
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Plugins from '../pages/Plugins';
import { api } from '../api/endpoints';

vi.mock('../api/endpoints.js', () => ({
  api: {
    plugins: vi.fn(),
    pluginConfig: vi.fn(),
    pluginConfigSave: vi.fn(),
    pluginToggle: vi.fn(),
    pluginReload: vi.fn(),
    pluginUpdate: vi.fn(),
    pluginUninstall: vi.fn(),
    pluginInstall: vi.fn(),
    pluginsCheckUpdates: vi.fn(),
    pluginsProxySave: vi.fn(),
  },
}));

const PLUGIN_LIST = {
  console_plugin: 'dashboard',
  manage_enabled: true,
  hot_reload: true,
  proxy: { mode: 'system', description: '跟随系统' },
  items: [
    {
      id: 'dashboard',
      name: 'dashboard',
      version: '1.0.0',
      official: true,
      source: 'official',
      status: 'loaded',
      enabled: true,
      manageable: false,
      hot_reload: false,
      config_hot_reload: true,
      description: '网页面板',
    },
    {
      id: 'memo',
      name: 'memo',
      version: '0.2.0',
      official: false,
      source: 'third_party',
      status: 'disabled',
      enabled: false,
      manageable: true,
      hot_reload: true,
      description: '记忆插件',
    },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.plugins).mockResolvedValue(PLUGIN_LIST);
  // 配置详情保持在加载中，聚焦列表与工具栏行为
  vi.mocked(api.pluginConfig).mockImplementation(() => new Promise(() => {}));
});

describe('Plugins 页面', () => {
  it('按状态分组渲染插件，并默认选中第一个运行中的插件', async () => {
    render(<Plugins />);

    // 「dashboard」同时出现在列表项与右侧编辑器标题里，用 heading 定位编辑器
    expect(await screen.findByRole('heading', { name: 'dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /运行中/ })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /已停用/ })).toBeInTheDocument();

    const selected = await screen.findByRole('button', { current: true });
    expect(within(selected).getByText('dashboard')).toBeInTheDocument();
  });

  it('展示来源筛选与搜索框', async () => {
    render(<Plugins />);

    await screen.findByRole('heading', { name: 'dashboard' });
    expect(screen.getByRole('button', { name: '全部' })).toHaveClass('active');
    expect(screen.getByRole('button', { name: '官方' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '第三方' })).toBeInTheDocument();
    expect(screen.getByLabelText('搜索插件')).toBeInTheDocument();
  });

  it('搜索无结果时给出空状态', async () => {
    const user = userEvent.setup();
    render(<Plugins />);

    const search = await screen.findByLabelText('搜索插件');
    await user.type(search, '不存在的插件');

    expect(await screen.findByText('没有匹配的插件')).toBeInTheDocument();
  });

  it('配置未就绪时保存/重载按钮禁用，面板自身不允许热重载', async () => {
    render(<Plugins />);

    await screen.findByRole('heading', { name: 'dashboard' });

    // dashboard 是面板自身（console_plugin），不允许热重载
    expect(screen.getByRole('button', { name: '重载插件' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /保存并重载/ })).toBeDisabled();
    // 配置详情尚未返回，底部状态应提示等待配置
    expect(screen.getByText('等待配置')).toBeInTheDocument();
  });
});
