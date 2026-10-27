import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import StarshipToggle from '../components/StarshipToggle';
import { api } from '../api/endpoints';
import { clearQueries, getQuerySnapshot } from '../data/queryCore';
import { QK } from '../data/queryKeys';

vi.mock('../api/endpoints', () => ({
  api: { plugins: vi.fn(), extensions: vi.fn(), pluginToggle: vi.fn() },
}));

const disabledPlugins = {
  manage_enabled: true,
  items: [{ name: 'starship', official: true, enabled: false, status: 'disabled' }],
};
const enabledPlugins = {
  manage_enabled: true,
  items: [{ name: 'starship', official: true, enabled: true, status: 'loaded' }],
};
const mounted = { items: [{ name: 'starship', panel: { path: '/game/', title: 'NeoBot 星舰' } }] };

beforeEach(() => {
  clearQueries();
  vi.clearAllMocks();
  vi.mocked(api.plugins).mockResolvedValue(disabledPlugins);
  vi.mocked(api.extensions).mockResolvedValue({ items: [] });
  vi.mocked(api.pluginToggle).mockResolvedValue({
    ok: true,
    status: 200,
    error: null,
    data: { message: 'ok' },
  });
});

describe('StarshipToggle', () => {
  it('明确提交目标状态，读回运行与扩展状态后更新开关和入口缓存', async () => {
    const user = userEvent.setup();
    render(<StarshipToggle />);
    const toggle = await screen.findByRole('switch', { name: '启用星舰' });
    await waitFor(() => expect(toggle).toBeEnabled());
    expect(toggle).not.toBeChecked();
    vi.mocked(api.plugins).mockResolvedValue(enabledPlugins);
    vi.mocked(api.extensions).mockResolvedValue(mounted);

    await user.click(toggle);
    await waitFor(() => expect(toggle).toBeChecked());
    expect(api.pluginToggle).toHaveBeenCalledWith('starship', { enabled: true, expected_enabled: false });
    expect(await screen.findByText('星舰已加载，入口已注册。')).toBeInTheDocument();
    expect(getQuerySnapshot(QK.extensions).data).toEqual(mounted);

    vi.mocked(api.plugins).mockResolvedValue(disabledPlugins);
    vi.mocked(api.extensions).mockResolvedValue({ items: [] });
    await user.click(toggle);
    await waitFor(() => expect(toggle).not.toBeChecked());
    expect(api.pluginToggle).toHaveBeenLastCalledWith('starship', { enabled: false, expected_enabled: true });
    expect(await screen.findByText('星舰已卸载，入口已移除。游戏数据已保留。')).toBeInTheDocument();
    expect(getQuerySnapshot(QK.extensions).data).toEqual({ items: [] });
  });

  it('只读权限禁用开关，不发出修改', async () => {
    const user = userEvent.setup();
    render(<StarshipToggle readOnly />);
    const toggle = await screen.findByRole('switch', { name: '启用星舰' });
    await screen.findByText('当前会话只读，切换星舰需要管理权限。');
    expect(toggle).toBeDisabled();
    await user.click(toggle);
    expect(api.pluginToggle).not.toHaveBeenCalled();
  });

  it('服务端管理权限关闭时禁用开关', async () => {
    vi.mocked(api.plugins).mockResolvedValue({ ...disabledPlugins, manage_enabled: false });
    render(<StarshipToggle />);
    expect(await screen.findByText('当前会话只读，切换星舰需要管理权限。')).toBeInTheDocument();
    expect(screen.getByRole('switch', { name: '启用星舰' })).toBeDisabled();
  });

  it('加载失败保留后端真实选择，显示错误而不报告已启用', async () => {
    const user = userEvent.setup();
    render(<StarshipToggle />);
    const toggle = await screen.findByRole('switch', { name: '启用星舰' });
    await waitFor(() => expect(toggle).toBeEnabled());
    vi.mocked(api.pluginToggle).mockResolvedValue({
      ok: false,
      status: 400,
      error: '依赖加载失败',
      data: null,
    });
    vi.mocked(api.plugins).mockResolvedValue({
      manage_enabled: true,
      items: [{ name: 'starship', enabled: true, status: 'error', error: '依赖加载失败' }],
    });

    await user.click(toggle);
    expect(await screen.findByRole('alert')).toHaveTextContent('依赖加载失败');
    expect(toggle).toBeChecked();
    expect(screen.getByText('启用异常')).toBeInTheDocument();
    expect(screen.queryByText('星舰已加载，入口已注册。')).not.toBeInTheDocument();
  });

  it('接口成功但扩展未挂载也不伪装启用成功', async () => {
    const user = userEvent.setup();
    render(<StarshipToggle />);
    const toggle = await screen.findByRole('switch', { name: '启用星舰' });
    await waitFor(() => expect(toggle).toBeEnabled());
    vi.mocked(api.plugins).mockResolvedValue(enabledPlugins);
    await user.click(toggle);
    expect(await screen.findByRole('alert')).toHaveTextContent('插件运行状态尚未符合请求');
    expect(screen.queryByText('星舰已加载，入口已注册。')).not.toBeInTheDocument();
  });

  it('状态读取失败时不能切换，重试成功后恢复', async () => {
    const user = userEvent.setup();
    vi.mocked(api.plugins).mockResolvedValue(null);
    render(<StarshipToggle />);
    expect(await screen.findByRole('alert')).toHaveTextContent('无法读取星舰状态');
    expect(screen.getByRole('switch', { name: '启用星舰' })).toBeDisabled();
    vi.mocked(api.plugins).mockResolvedValue(disabledPlugins);
    await user.click(screen.getByRole('button', { name: '重试读取' }));
    await waitFor(() => expect(screen.getByRole('switch', { name: '启用星舰' })).toBeEnabled());
  });
});
