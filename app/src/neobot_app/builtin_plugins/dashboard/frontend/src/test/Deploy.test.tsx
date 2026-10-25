import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { api } from '../api/endpoints';
import type { DeployStatus } from '../api/types';
import Deploy from '../pages/Deploy';

vi.mock('../api/endpoints', () => ({
  api: {
    deployStatus: vi.fn(),
    config: vi.fn(),
    configSave: vi.fn(),
    envSave: vi.fn(),
    deployOneBotToken: vi.fn(),
  },
}));
vi.mock('../components/Toast', () => ({ toast: vi.fn() }));

const ok = <T,>(data: T) => ({ ok: true, data, error: null, status: 200 });

const status = (values: DeployStatus['values'] = {}): DeployStatus => ({
  steps: [],
  values,
  defaults: { bot_account: '0', bot_nick_name: 'Neo Bot', bot_data: '示例人设' },
  revision: 3,
  env_revision: 8,
  ready: false,
});

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  vi.mocked(api.deployStatus).mockResolvedValue(ok(status()));
  vi.mocked(api.envSave).mockResolvedValue(ok({ revision: 9, message: '密钥已保存' }));
});

describe('快捷部署表单', () => {
  it('保存密钥后不覆盖尚未保存的身份/人设草稿', async () => {
    render(<Deploy />);
    const account = await screen.findByPlaceholderText(/例如 123456789/);
    fireEvent.change(account, { target: { value: '10001' } });
    fireEvent.change(screen.getByPlaceholderText('Neo Bot'), { target: { value: '测试机器人' } });
    fireEvent.change(screen.getByPlaceholderText(/你是群里的老群友/), { target: { value: '我是测试人设' } });
    fireEvent.change(screen.getByPlaceholderText('sk-…'), { target: { value: 'sk-test' } });

    fireEvent.click(screen.getByRole('button', { name: /保存密钥/ }));

    await waitFor(() => expect(api.envSave).toHaveBeenCalled());
    await waitFor(() => expect(api.deployStatus).toHaveBeenCalledTimes(2));
    expect(account).toHaveValue('10001');
    expect(screen.getByPlaceholderText('Neo Bot')).toHaveValue('测试机器人');
    expect(screen.getByPlaceholderText(/你是群里的老群友/)).toHaveValue('我是测试人设');
  });

  it('保存并重载后回填服务端返回的值', async () => {
    vi.mocked(api.config).mockResolvedValue(ok({ revision: 3, config: { bot: {}, chat: {} } }));
    vi.mocked(api.configSave).mockResolvedValue(ok({ revision: 4, config: { bot: {}, chat: {} } }));
    render(<Deploy />);
    const account = await screen.findByPlaceholderText(/例如 123456789/);
    fireEvent.change(account, { target: { value: '10001' } });
    vi.mocked(api.deployStatus).mockResolvedValue(ok(status({ bot_account: '10001', bot_nick_name: '服务端昵称' })));

    fireEvent.click(screen.getByRole('button', { name: /保存并重载/ }));

    await waitFor(() => expect(api.configSave).toHaveBeenCalled());
    await waitFor(() => expect(account).toHaveValue('10001'));
    expect(screen.getByPlaceholderText('Neo Bot')).toHaveValue('服务端昵称');
    expect(sessionStorage.getItem('neobot.deploy.draft.v1')).toBeNull();
  });

  it('切到其它页面（组件卸载）再回来时恢复未保存草稿', async () => {
    const view = render(<Deploy />);
    const account = await screen.findByPlaceholderText(/例如 123456789/);
    fireEvent.change(account, { target: { value: '10001' } });
    fireEvent.change(screen.getByPlaceholderText('Neo Bot'), { target: { value: '草稿昵称' } });
    fireEvent.change(screen.getByPlaceholderText(/你是群里的老群友/), { target: { value: '草稿人设' } });
    await waitFor(() => expect(sessionStorage.getItem('neobot.deploy.draft.v1')).toBeTruthy());

    // 模拟路由跳转：组件卸载后重新挂载，服务端仍是旧值（空）
    view.unmount();
    render(<Deploy />);

    expect(await screen.findByDisplayValue('10001')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Neo Bot')).toHaveValue('草稿昵称');
    expect(screen.getByPlaceholderText(/你是群里的老群友/)).toHaveValue('草稿人设');
    expect(screen.getByText(/已恢复上次未保存/)).toBeInTheDocument();
  });
});