import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import Deploy from '../pages/Deploy';
import { api } from '../api/endpoints';
import { useAuthGate } from '../auth/AuthContext';
import type { DeployStatus } from '../api/types';
import { notify } from '../notifications/infoBar';
import { POLL } from '../data/queryKeys';
import { DEPLOY_DRAFT_KEY } from '../pages/deploy/deployDraftStorage';

vi.mock('../auth/AuthContext', () => ({ useAuthGate: vi.fn() }));
vi.mock('../notifications/infoBar', () => ({ notify: vi.fn() }));
vi.mock('../api/endpoints', () => ({
  api: {
    deployStatus: vi.fn(),
    config: vi.fn(),
    configSave: vi.fn(),
    envSave: vi.fn(),
    deployOneBotToken: vi.fn(),
  },
}));

const deployment: DeployStatus = {
  revision: '00000000000000000000000000000001',
  env_revision: '00000000000000000000000000000001',
  ready: true,
  values: {
    bot_account: '100000001',
    bot_nick_name: '演示机器人',
    alias_name: ['小演示'],
    bot_data: '演示人设',
    admin_accounts: ['100000002'],
    group_chat_chance: 0.3,
  },
  onebot: {
    url_local: 'ws://127.0.0.1:9980/onebot',
    url_lan: 'ws://192.0.2.10:9980/onebot',
    token: 'preview-token',
    token_enabled: true,
  },
  steps: [
    { key: 'bot_identity', done: true, required: true },
    { key: 'persona', done: true, required: true },
    { key: 'platform_key', done: true, required: true },
    { key: 'admin', done: true, required: false },
    { key: 'onebot', done: true, required: true },
  ],
};

const success = { ok: true, status: 200, error: null, data: {} };
const goTo = (label: string) => fireEvent.click(screen.getByRole('tab', { name: new RegExp(label) }));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function renderWithPolling() {
  vi.useFakeTimers();
  await act(async () => {
    render(<Deploy />);
  });
}

async function advancePolling(periods = 1) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(POLL.editor * periods);
  });
}

afterEach(() => {
  vi.useRealTimers();
});

beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  vi.mocked(useAuthGate).mockReturnValue({ canManage: true, setupRequired: false, refresh: async () => {} });
  vi.mocked(api.deployStatus).mockResolvedValue({
    ...success,
    data: deployment,
  });
  vi.mocked(api.config).mockResolvedValue({
    ...success,
    data: {
      revision: '00000000000000000000000000000007',
      config: {
        bot: { account: '100000001', nick_name: '演示机器人', untouched: 'identity-option' },
        chat: { admin_accounts: ['100000002'], group_chat_chance: 0.3, untouched: 'chat-option' },
        adapter: { enabled: true },
      },
    },
  });
  vi.mocked(api.configSave).mockResolvedValue(success);
  vi.mocked(api.envSave).mockResolvedValue(success);
  vi.mocked(api.deployOneBotToken).mockResolvedValue(success);
});

describe('Deploy 分步配置', () => {
  it('离开页面再回来恢复非敏感草稿，待填密钥不落存储', async () => {
    const view = render(<Deploy />);
    fireEvent.change(await screen.findByDisplayValue('演示机器人'), { target: { value: '跨页草稿昵称' } });
    goTo('人设');
    fireEvent.change(screen.getByDisplayValue('演示人设'), { target: { value: '跨页草稿人设' } });
    goTo('供应商');
    fireEvent.change(screen.getByPlaceholderText('sk-…'), { target: { value: 'sk-pending' } });
    await waitFor(() => expect(sessionStorage.getItem(DEPLOY_DRAFT_KEY)).toContain('跨页草稿昵称'));
    expect(sessionStorage.getItem(DEPLOY_DRAFT_KEY)).not.toContain('sk-pending');
    view.unmount();
    render(<Deploy />);
    expect(await screen.findByDisplayValue('跨页草稿昵称')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '放弃草稿' })).toBeEnabled();
    goTo('人设');
    expect(screen.getByDisplayValue('跨页草稿人设')).toBeInTheDocument();
    goTo('供应商');
    expect(screen.getByPlaceholderText('sk-…')).toHaveValue('');
  });

  it('成功保存配置后清除跨页草稿，下一次进入读取服务端值', async () => {
    const view = render(<Deploy />);
    fireEvent.change(await screen.findByDisplayValue('演示机器人'), { target: { value: '已保存昵称' } });
    await waitFor(() => expect(sessionStorage.getItem(DEPLOY_DRAFT_KEY)).toContain('已保存昵称'));
    vi.mocked(api.deployStatus).mockResolvedValue({
      ...success,
      data: { ...deployment, values: { ...deployment.values, bot_nick_name: '已保存昵称' } },
    });
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '保存并应用' })).toBeDisabled());
    expect(sessionStorage.getItem(DEPLOY_DRAFT_KEY)).toBeNull();
    view.unmount();
    render(<Deploy />);
    expect(await screen.findByDisplayValue('已保存昵称')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '放弃草稿' })).not.toBeInTheDocument();
  });

  it('回复意愿校验留在对应字段，不重复发送全局通知', async () => {
    render(<Deploy />);
    await screen.findByDisplayValue('演示机器人');
    goTo('管理员');
    const chance = screen.getByRole('spinbutton', { name: '群聊回复意愿系数' });
    fireEvent.change(chance, { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));
    expect(chance).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('群聊回复意愿应为 0 到 1 之间的数值。');
    expect(api.configSave).not.toHaveBeenCalled();
    expect(notify).not.toHaveBeenCalled();
    fireEvent.change(chance, { target: { value: '0.5' } });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('只改昵称时保留服务器最新的多个管理员、别名与回复意愿', async () => {
    vi.mocked(api.config).mockResolvedValue({
      ...success,
      data: {
        revision: '00000000000000000000000000000009',
        config: {
          bot: {
            account: '100000001',
            nick_name: '演示机器人',
            alias_name: ['服务器新别名'],
            bot_data: '服务器新人设',
          },
          chat: { admin_accounts: ['100000002', '100000003'], group_chat_chance: 0.8 },
        },
      },
    });
    render(<Deploy />);
    fireEvent.change(await screen.findByDisplayValue('演示机器人'), { target: { value: '新的昵称' } });
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));
    await waitFor(() => expect(api.configSave).toHaveBeenCalled());
    expect(api.configSave).toHaveBeenCalledWith({
      revision: '00000000000000000000000000000009',
      mode: 'form',
      reload: true,
      config: {
        bot: {
          account: '100000001',
          nick_name: '新的昵称',
          alias_name: ['服务器新别名'],
          bot_data: '服务器新人设',
        },
        chat: { admin_accounts: ['100000002', '100000003'], group_chat_chance: 0.8 },
      },
    });
  });

  it('只展示当前步骤，前后导航和直接切换都保留草稿', async () => {
    render(<Deploy />);
    const nickname = await screen.findByDisplayValue('演示机器人');
    expect(screen.queryByDisplayValue('演示人设')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '保存并应用' })).toBeDisabled();
    fireEvent.change(nickname, { target: { value: '新的昵称' } });
    expect(screen.getByRole('tab', { name: /身份.*未保存/ })).toHaveAttribute('aria-selected', 'true');
    fireEvent.click(screen.getByRole('button', { name: '下一步' }));
    expect(screen.getByDisplayValue('演示人设')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/机器人设定/), { target: { value: '新的说话方式' } });
    fireEvent.click(screen.getByRole('button', { name: '上一步' }));
    expect(screen.getByDisplayValue('新的昵称')).toBeInTheDocument();
    goTo('人设');
    expect(screen.getByDisplayValue('新的说话方式')).toBeInTheDocument();
    expect(api.configSave).not.toHaveBeenCalled();
    expect(api.envSave).not.toHaveBeenCalled();
  });

  it('只读会话禁用字段与写入，仍可查看和复制连接信息', async () => {
    vi.mocked(useAuthGate).mockReturnValue({
      canManage: false,
      setupRequired: false,
      refresh: async () => {},
    });
    render(<Deploy />);
    expect(await screen.findByDisplayValue('演示机器人')).toBeDisabled();
    expect(screen.getByDisplayValue('100000001')).toBeDisabled();
    expect(screen.getByDisplayValue('小演示')).toBeDisabled();
    goTo('人设');
    expect(screen.getByDisplayValue('演示人设')).toBeDisabled();
    goTo('供应商');
    expect(screen.getByPlaceholderText('sk-…')).toBeDisabled();
    goTo('管理员');
    expect(screen.getByDisplayValue('100000002')).toBeDisabled();
    expect(screen.getByRole('spinbutton')).toBeDisabled();
    expect(screen.getByRole('slider')).toBeDisabled();
    goTo('连接');
    expect(screen.getByText(/^当前会话只读/)).toBeInTheDocument();
    for (const name of ['保存并应用', '重新生成 token']) {
      const button = screen.getByRole('button', { name });
      expect(button).toBeDisabled();
      fireEvent.click(button);
    }
    expect(screen.getAllByRole('button', { name: '复制' })).toHaveLength(3);
    screen.getAllByRole('button', { name: '复制' }).forEach((button) => expect(button).toBeEnabled());
    expect(screen.getByText('ws://127.0.0.1:9980/onebot')).toBeInTheDocument();
    expect(api.configSave).not.toHaveBeenCalled();
    expect(api.envSave).not.toHaveBeenCalled();
    expect(api.deployOneBotToken).not.toHaveBeenCalled();
  });

  it('统一保存草稿与密钥，使用最新配置修订号并保留无关字段', async () => {
    render(<Deploy />);
    fireEvent.change(await screen.findByDisplayValue('演示机器人'), { target: { value: ' 新的昵称 ' } });
    fireEvent.change(screen.getByDisplayValue('小演示'), { target: { value: '小玄、玄天, Neo' } });
    goTo('人设');
    fireEvent.change(screen.getByDisplayValue('演示人设'), { target: { value: '新的说话方式' } });
    goTo('供应商');
    fireEvent.change(screen.getByPlaceholderText('sk-…'), { target: { value: ' sk-test ' } });
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));
    await waitFor(() => expect(screen.getByRole('button', { name: '保存并应用' })).toBeDisabled());
    expect(api.configSave).toHaveBeenCalledWith({
      revision: '00000000000000000000000000000007',
      mode: 'form',
      reload: true,
      config: {
        bot: {
          account: '100000001',
          nick_name: '新的昵称',
          alias_name: ['小玄', '玄天', 'Neo'],
          bot_data: '新的说话方式',
          untouched: 'identity-option',
        },
        chat: { admin_accounts: ['100000002'], group_chat_chance: 0.3, untouched: 'chat-option' },
        adapter: { enabled: true },
      },
    });
    expect(api.envSave).toHaveBeenCalledWith({
      updates: { DeepSeek_APIKey: 'sk-test', DeepSeek_URL: 'https://api.deepseek.com' },
      deletes: [],
      revision: '00000000000000000000000000000001',
      reload: true,
    });
    expect(screen.getByPlaceholderText('sk-…')).toHaveValue('');
    goTo('人设');
    expect(screen.getByDisplayValue('新的说话方式')).toBeInTheDocument();
  });

  it('部分保存失败时保留未保存密钥，重试不重复写入已保存配置', async () => {
    vi.mocked(api.envSave).mockResolvedValueOnce({
      ok: false,
      status: 409,
      error: '密钥修订冲突',
      data: null,
    });
    render(<Deploy />);
    fireEvent.change(await screen.findByDisplayValue('演示机器人'), { target: { value: '新的昵称' } });
    goTo('供应商');
    fireEvent.change(screen.getByPlaceholderText('sk-…'), { target: { value: 'sk-retry' } });
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));
    await waitFor(() => expect(notify).toHaveBeenCalledWith('配置已保存；密钥修订冲突', 'err'));
    expect(screen.queryByText('操作未完成')).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: '保存并应用' })).toBeEnabled());
    expect(screen.getByPlaceholderText('sk-…')).toHaveValue('sk-retry');
    expect(screen.getByRole('tab', { name: /身份.*已配置/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));
    await waitFor(() => expect(screen.getByPlaceholderText('sk-…')).toHaveValue(''));
    expect(api.configSave).toHaveBeenCalledTimes(1);
    expect(api.envSave).toHaveBeenCalledTimes(2);
  });

  it('生成连接令牌后的状态读取不会重置其他步骤的未保存输入', async () => {
    render(<Deploy />);
    fireEvent.change(await screen.findByDisplayValue('演示机器人'), { target: { value: '待保存的昵称' } });
    goTo('供应商');
    fireEvent.change(screen.getByPlaceholderText('sk-…'), { target: { value: 'sk-pending' } });
    goTo('连接');
    expect(screen.getByRole('button', { name: '重新生成 token' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: '重新生成 token' }));
    await waitFor(() => expect(api.deployStatus).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByRole('button', { name: '重新生成 token' })).toBeEnabled());
    expect(screen.queryByRole('button', { name: '刷新' })).not.toBeInTheDocument();
    goTo('身份');
    expect(screen.getByDisplayValue('待保存的昵称')).toBeInTheDocument();
    goTo('供应商');
    expect(screen.getByPlaceholderText('sk-…')).toHaveValue('sk-pending');
    expect(api.deployOneBotToken).toHaveBeenCalledWith({ revision: '00000000000000000000000000000001' });
    expect(api.configSave).not.toHaveBeenCalled();
    expect(api.envSave).not.toHaveBeenCalled();
  });

  it('配置保存失败保留草稿，并阻止后续密钥写入', async () => {
    vi.mocked(api.configSave).mockResolvedValueOnce({
      ok: false,
      status: 409,
      error: '配置已变更，请重试',
      data: null,
    });
    render(<Deploy />);
    fireEvent.change(await screen.findByDisplayValue('演示机器人'), { target: { value: '保留这个昵称' } });
    goTo('供应商');
    fireEvent.change(screen.getByPlaceholderText('sk-…'), { target: { value: 'sk-pending' } });
    fireEvent.click(screen.getByRole('button', { name: '保存并应用' }));
    await waitFor(() => expect(notify).toHaveBeenCalledWith('配置已变更，请重试', 'err'));
    expect(screen.getByPlaceholderText('sk-…')).toHaveValue('sk-pending');
    goTo('身份');
    expect(screen.getByDisplayValue('保留这个昵称')).toBeInTheDocument();
    expect(api.envSave).not.toHaveBeenCalled();
  });

  it('步骤导航支持方向键，并保持单一焦点入口', async () => {
    render(<Deploy />);
    await screen.findByDisplayValue('演示机器人');
    const identityTab = screen.getByRole('tab', { name: /身份/ });
    identityTab.focus();
    fireEvent.keyDown(identityTab, { key: 'ArrowRight' });
    const personaTab = screen.getByRole('tab', { name: /人设/ });
    expect(personaTab).toHaveFocus();
    expect(personaTab).toHaveAttribute('aria-selected', 'true');
    expect(identityTab).toHaveAttribute('tabindex', '-1');
  });

  it('干净表单自动同步服务端与草稿基线，不显示页头刷新或周期通知', async () => {
    await renderWithPolling();
    expect(api.deployStatus).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: '刷新' })).not.toBeInTheDocument();
    vi.mocked(api.deployStatus).mockResolvedValue({
      ...success,
      data: {
        ...deployment,
        revision: '00000000000000000000000000000002',
        values: { ...deployment.values, bot_nick_name: '服务端新昵称' },
      },
    });
    await advancePolling();
    expect(api.deployStatus).toHaveBeenCalledTimes(2);
    expect(screen.getByDisplayValue('服务端新昵称')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '保存并应用' })).toBeDisabled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(notify).not.toHaveBeenCalled();
  });

  it('普通草稿与待填密钥均暂停自动读取，恢复干净后继续', async () => {
    await renderWithPolling();
    fireEvent.change(screen.getByDisplayValue('演示机器人'), { target: { value: '未保存昵称' } });
    await advancePolling(2);
    expect(api.deployStatus).toHaveBeenCalledTimes(1);
    expect(screen.getByDisplayValue('未保存昵称')).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue('未保存昵称'), { target: { value: '演示机器人' } });
    goTo('供应商');
    fireEvent.change(screen.getByPlaceholderText('sk-…'), { target: { value: 'sk-pending' } });
    await advancePolling(2);
    expect(api.deployStatus).toHaveBeenCalledTimes(1);
    expect(screen.getByPlaceholderText('sk-…')).toHaveValue('sk-pending');
    fireEvent.change(screen.getByPlaceholderText('sk-…'), { target: { value: '' } });
    await advancePolling();
    expect(api.deployStatus).toHaveBeenCalledTimes(2);
    expect(api.envSave).not.toHaveBeenCalled();
    expect(notify).not.toHaveBeenCalled();
  });

  it('自动请求发出后开始编辑，会丢弃旧回包并保留昵称、密钥和原基线', async () => {
    await renderWithPolling();
    const pending = deferred<Awaited<ReturnType<typeof api.deployStatus>>>();
    vi.mocked(api.deployStatus).mockReturnValueOnce(pending.promise);
    await advancePolling();
    expect(api.deployStatus).toHaveBeenCalledTimes(2);
    const nickname = screen.getByDisplayValue('演示机器人');
    expect(nickname).toBeEnabled();
    fireEvent.change(nickname, { target: { value: '请求途中输入' } });
    goTo('供应商');
    fireEvent.change(screen.getByPlaceholderText('sk-…'), { target: { value: 'sk-in-flight' } });
    await act(async () => {
      pending.resolve({
        ...success,
        data: {
          ...deployment,
          revision: '00000000000000000000000000000099',
          values: { ...deployment.values, bot_nick_name: '迟到的服务器值' },
          onebot: { ...deployment.onebot, url_local: 'ws://late.invalid/onebot' },
        },
      });
    });
    expect(screen.getByPlaceholderText('sk-…')).toHaveValue('sk-in-flight');
    fireEvent.change(screen.getByPlaceholderText('sk-…'), { target: { value: '' } });
    goTo('连接');
    expect(screen.getByText('ws://127.0.0.1:9980/onebot')).toBeInTheDocument();
    expect(screen.queryByText('ws://late.invalid/onebot')).not.toBeInTheDocument();
    goTo('身份');
    expect(screen.getByDisplayValue('请求途中输入')).toBeInTheDocument();
    fireEvent.change(screen.getByDisplayValue('请求途中输入'), { target: { value: '演示机器人' } });
    expect(screen.getByRole('button', { name: '保存并应用' })).toBeDisabled();
    expect(notify).not.toHaveBeenCalled();
  });

  it('自动请求途中启动生成令牌时丢弃旧包，忙碌期间暂停轮询', async () => {
    await renderWithPolling();
    const pendingStatus = deferred<Awaited<ReturnType<typeof api.deployStatus>>>();
    const pendingToken = deferred<Awaited<ReturnType<typeof api.deployOneBotToken>>>();
    vi.mocked(api.deployStatus)
      .mockReturnValueOnce(pendingStatus.promise)
      .mockResolvedValueOnce({
        ...success,
        data: { ...deployment, onebot: { ...deployment.onebot, token: 'newly-generated-token' } },
      });
    vi.mocked(api.deployOneBotToken).mockReturnValueOnce(pendingToken.promise);
    await advancePolling();
    goTo('连接');
    fireEvent.click(screen.getByRole('button', { name: '重新生成 token' }));
    await act(async () => {
      pendingStatus.resolve({
        ...success,
        data: { ...deployment, onebot: { ...deployment.onebot, token: 'stale-token' } },
      });
    });
    expect(screen.queryByText('stale-token')).not.toBeInTheDocument();
    await advancePolling(2);
    expect(api.deployStatus).toHaveBeenCalledTimes(2);
    await act(async () => {
      pendingToken.resolve(success);
    });
    expect(api.deployStatus).toHaveBeenCalledTimes(3);
    expect(screen.getByText('newly-generated-token')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重新生成 token' })).toBeEnabled();
  });

  it('读取失败保留重试，出现草稿后移除重试并暂停自动更新', async () => {
    const failure = { ok: false, status: 503, error: '演示读取失败', data: null };
    vi.mocked(api.deployStatus).mockResolvedValueOnce(failure);
    await renderWithPolling();
    expect(screen.getByRole('alert')).toHaveTextContent('演示读取失败');
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '重新读取' }));
    });
    expect(screen.getByDisplayValue('演示机器人')).toBeInTheDocument();
    vi.mocked(api.deployStatus).mockResolvedValueOnce(failure);
    await advancePolling();
    expect(screen.getByRole('button', { name: '重新读取' })).toBeEnabled();
    fireEvent.change(screen.getByDisplayValue('演示机器人'), { target: { value: '错误后的草稿' } });
    expect(screen.queryByRole('button', { name: '重新读取' })).not.toBeInTheDocument();
    await advancePolling(2);
    expect(api.deployStatus).toHaveBeenCalledTimes(3);
    expect(screen.getByDisplayValue('错误后的草稿')).toBeInTheDocument();
    expect(notify).not.toHaveBeenCalled();
  });
});
