import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import System from '../pages/System';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';
import { useAuthGate } from '../auth/AuthContext';
import { infoBar } from '../notifications/infoBar';
import { POLL } from '../data/queryKeys';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../auth/AuthContext', () => ({ useAuthGate: vi.fn() }));
vi.mock('../notifications/infoBar', () => ({ infoBar: vi.fn(), notify: vi.fn() }));

vi.mock('../api/endpoints', () => ({
  api: {
    services: vi.fn().mockResolvedValue({ items: [] }),
    tasks: vi.fn().mockResolvedValue({ scheduled: [], background: [] }),
    statsUsage: vi.fn().mockResolvedValue({ items: [], totals: {} }),
    system: vi.fn().mockResolvedValue({}),
    powerStatus: vi.fn(),
    standbyEnter: vi.fn(),
    resume: vi.fn(),
    reboot: vi.fn(),
    setStandbyOnebot: vi.fn(),
    restart: vi.fn(),
    shutdownProcess: vi.fn(),
    plugins: vi.fn().mockResolvedValue({ items: [], manage_enabled: true }),
    extensions: vi.fn().mockResolvedValue({ items: [] }),
  },
}));

beforeEach(() => {
  clearQueries();
  vi.clearAllMocks();
  vi.mocked(api.services).mockResolvedValue({ items: [] });
  vi.mocked(api.tasks).mockResolvedValue({ scheduled: [], background: [] });
  vi.mocked(api.system).mockResolvedValue({});
  vi.mocked(api.statsUsage).mockResolvedValue({
    available: true,
    items: [],
    totals: { calls: 0, cost_cny: 0, input_tokens: 0, output_tokens: 0 },
  });
  vi.mocked(api.powerStatus).mockResolvedValue({ available: true, state: 'running', standby: false });
  vi.mocked(api.plugins).mockResolvedValue({ items: [], manage_enabled: true });
  vi.mocked(api.extensions).mockResolvedValue({ items: [] });
  vi.mocked(useAuthGate).mockReturnValue({ canManage: true, setupRequired: false, refresh: async () => {} });
});

it('服务按区域分页，任务切换与完整详情保持可访问', async () => {
  const description = '用于验证完整服务说明不会因单屏布局被丢失。'.repeat(12);
  vi.mocked(api.powerStatus).mockResolvedValue({ available: true, state: 'running', standby: false });
  vi.mocked(api.services).mockResolvedValue({
    items: Array.from({ length: 7 }, (_, index) => ({
      name: `服务 ${index + 1}`,
      description,
      available: true,
    })),
  });
  vi.mocked(api.tasks).mockResolvedValue({
    background: [{ task_id: 'memory-summary', pipeline_key: 'private:1001', status: 'running' }],
    scheduled: [
      {
        task_id: 'daily-summary',
        name: '每日归档',
        next_run: '2026-10-27 09:00',
        cron: '0 9 * * *',
        status: 'scheduled',
      },
    ],
  });
  render(<System />);
  expect(await screen.findByText('服务 1')).toBeInTheDocument();
  expect(screen.queryByText('服务 4')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '宿主服务下一页' }));
  fireEvent.click(screen.getByRole('button', { name: /服务 4/ }));
  const details = screen.getByRole('dialog', { name: '服务 4' });
  expect(within(details).getByText(description)).toBeInTheDocument();
  fireEvent.click(within(details).getByRole('button', { name: '关闭对话框' }));
  fireEvent.click(screen.getByRole('button', { name: /后台任务 1/ }));
  expect(screen.getByText('memory-summary')).toBeInTheDocument();
  expect(screen.getByText('private:1001')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /定时任务 1/ }));
  fireEvent.click(screen.getByRole('button', { name: /每日归档/ }));
  expect(within(screen.getByRole('dialog', { name: '每日归档' })).getByText('0 9 * * *')).toBeInTheDocument();
});

it('任务来源失败显示服务返回的原因，不误报为空闲', async () => {
  vi.mocked(api.tasks).mockResolvedValue({
    background: [],
    scheduled: [],
    background_error: '绘图服务读取失败',
    scheduled_error: '计划任务查询失败',
  });
  render(<System />);
  await screen.findByText('运行时已启动。');
  fireEvent.click(screen.getByRole('button', { name: /后台任务 0/ }));
  expect(await screen.findByText('绘图服务读取失败')).toBeInTheDocument();
  expect(screen.queryByText('当前没有后台任务')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /定时任务 0/ }));
  expect(screen.getByText('计划任务查询失败')).toBeInTheDocument();
});

it('系统用量范围保持数字参数并支持键盘选择', async () => {
  render(<System />);
  const range = screen.getByRole('combobox', { name: '系统用量时间范围' });
  await act(async () => {
    fireEvent.keyDown(range, { key: 'ArrowDown' });
  });
  const option = screen.getByRole('option', { name: '最近 7 天' });
  await act(async () => {
    option.focus();
    fireEvent.keyDown(option, { key: 'Enter' });
  });
  await waitFor(() => expect(api.statsUsage).toHaveBeenCalledWith(168));
  expect(range).toHaveTextContent('最近 7 天');
});

it('停止仍在进行时禁止软启动和连接切换，但保留进程重启入口', async () => {
  vi.mocked(api.powerStatus).mockResolvedValue({
    available: true,
    state: 'stopping',
    phase: 'stopping',
    standby: true,
    transition: true,
    reason: '清理仍在进行',
    connect_onebot: true,
  });
  render(<System />);
  expect(await screen.findByText('正在停止')).toBeInTheDocument();
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: '运行设置' }));
  });
  expect(screen.getByRole('button', { name: '启动运行' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '进入待机' })).toBeDisabled();
  expect(screen.getByRole('checkbox', { name: /待机时保持 OneBot 连接/ })).toBeDisabled();
  expect(screen.getByRole('button', { name: '重启进程' })).toBeEnabled();
});

it('只读会话禁用运行操作和原因输入，保留状态与资源查看', async () => {
  vi.mocked(useAuthGate).mockReturnValue({ canManage: false, setupRequired: false, refresh: async () => {} });
  vi.mocked(api.powerStatus).mockResolvedValue({
    available: true,
    state: 'running',
    standby: false,
    connect_onebot: true,
  });
  vi.mocked(api.system).mockResolvedValue({ hostname: 'preview-workstation', cpu_percent: 12.4 });
  render(<System />);
  expect(await screen.findByText('12.4%')).toBeInTheDocument();
  expect(screen.getByText(/^当前会话只读/)).toBeInTheDocument();
  expect(screen.getByRole('combobox', { name: '系统用量时间范围' })).toBeEnabled();
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: '运行设置' }));
  });
  expect(screen.getByPlaceholderText('例如：维护模型配置中')).toBeDisabled();
  expect(screen.getByRole('button', { name: '修改密码' })).toBeDisabled();
  expect(screen.getByRole('checkbox', { name: /待机时保持 OneBot 连接/ })).toBeDisabled();
  for (const name of ['进入待机', '软重启运行', '重启进程', '关闭 NeoBot']) {
    const button = screen.getByRole('button', { name });
    expect(button).toBeDisabled();
    fireEvent.click(button);
  }
  [api.standbyEnter, api.resume, api.reboot, api.setStandbyOnebot, api.restart, api.shutdownProcess].forEach(
    (action) => expect(action).not.toHaveBeenCalled(),
  );
});

it.each([null, {}, { available: false }])(
  '运行状态缺失或不可用时不显示运行中，也不允许运行操作：%j',
  async (state) => {
    vi.mocked(api.powerStatus).mockResolvedValue(state);
    render(<System />);
    await waitFor(() => expect(screen.queryByText('正在读取运行状态')).not.toBeInTheDocument());
    expect(screen.queryByText('运行中')).not.toBeInTheDocument();
    expect(
      screen.getByText(state?.available === false ? '待机服务不可用' : '运行状态待确认'),
    ).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '运行设置' }));
    });
    expect(screen.getByRole('button', { name: '进入待机' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '软重启运行' })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: /待机时保持 OneBot 连接/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: '重启进程' })).toBeEnabled();
  },
);

it('运行操作拒绝走错误提示；后续操作成功不会继续显示旧错误', async () => {
  vi.mocked(api.standbyEnter).mockResolvedValue({
    ok: false,
    data: null,
    error: '当前状态不允许进入待机',
    status: 409,
  });
  vi.mocked(api.setStandbyOnebot).mockResolvedValue({
    ok: true,
    data: { message: '已更新连接设置' },
    error: null,
    status: 200,
  });
  render(<System />);
  await screen.findByText('运行中');
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: '运行设置' }));
  });
  const dialog = screen.getByRole('dialog', { name: '运行设置' });
  fireEvent.click(within(dialog).getByRole('button', { name: '进入待机' }));
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('当前状态不允许进入待机');
  expect(dialog.querySelector('.inline-alert--success')).toBeNull();
  fireEvent.click(within(dialog).getByRole('checkbox', { name: /待机时保持 OneBot 连接/ }));
  await waitFor(() =>
    expect(infoBar).toHaveBeenCalledWith(
      expect.objectContaining({
        title: '已更新 OneBot 连接设置',
        tone: 'ok',
      }),
    ),
  );
  expect(infoBar).toHaveBeenCalledTimes(1);
  expect(dialog.querySelector('.inline-alert--success')).toBeNull();
  expect(within(dialog).queryByRole('alert')).not.toBeInTheDocument();
});

it.each([
  { apiName: 'restart' as const, title: '重启进程', confirm: '确认重启' },
  { apiName: 'shutdownProcess' as const, title: '关闭 NeoBot', confirm: '确认关闭' },
])('$title 请求被拒绝时保留确认弹窗并在弹窗中显示错误', async ({ apiName, title, confirm }) => {
  vi.mocked(api[apiName]).mockResolvedValue({ ok: false, data: null, error: '没有执行权限', status: 403 });
  render(<System />);
  await screen.findByText('运行中');
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: '运行设置' }));
  });
  fireEvent.click(screen.getByRole('button', { name: title }));
  fireEvent.click(screen.getByRole('button', { name: confirm }));
  const dialog = screen.getByRole('dialog', { name: title });
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('没有执行权限');
  expect(within(dialog).getByRole('button', { name: confirm })).toBeEnabled();
  expect(dialog.querySelector('.inline-alert--success')).toBeNull();
});

it('重启响应没有确认数据时不报告已请求成功', async () => {
  vi.mocked(api.restart).mockResolvedValue({ ok: true, data: null, error: null, status: 200 });
  render(<System />);
  await screen.findByText('运行中');
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: '运行设置' }));
  });
  fireEvent.click(screen.getByRole('button', { name: '重启进程' }));
  fireEvent.click(screen.getByRole('button', { name: '确认重启' }));
  expect(
    await within(screen.getByRole('dialog', { name: '重启进程' })).findByRole('alert'),
  ).toHaveTextContent('未收到操作成功确认');
  expect(screen.queryByText('已请求重启进程')).not.toBeInTheDocument();
  expect(infoBar).not.toHaveBeenCalled();
});

it('用量不可用时以未知显示总量，不伪装成零消耗', async () => {
  vi.mocked(api.statsUsage).mockResolvedValue({ available: false, error: '数据库未连接' });
  render(<System />);
  expect(await screen.findByText('用量数据库不可用：数据库未连接')).toBeInTheDocument();
  const usage = screen.getByRole('region', { name: '系统模型用量' });
  expect(within(usage).queryByText('¥0.0000')).not.toBeInTheDocument();
  expect(usage.querySelector('.system-usage-summary')).toHaveTextContent(
    '总花费—调用次数—输入 / 输出 Token— / —',
  );
});

it('自动刷新失败后保留参考数据、禁用未知运行操作并保留重试入口', async () => {
  vi.useFakeTimers();
  try {
    vi.mocked(api.system).mockResolvedValueOnce({ hostname: '已读取主机', cpu_percent: 12.4 });
    let resolvePower: ((value: Awaited<ReturnType<typeof api.powerStatus>>) => void) | undefined;
    vi.mocked(api.powerStatus)
      .mockResolvedValueOnce({ available: true, state: 'running', standby: false })
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolvePower = resolve;
          }),
      );
    render(<System />);
    await act(async () => {});
    vi.mocked(api.system).mockResolvedValueOnce(null);
    expect(screen.queryByRole('button', { name: '刷新' })).not.toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL.system);
    });
    await act(async () => resolvePower?.(null));
    expect(screen.getByText('部分系统状态暂时无法读取')).toBeInTheDocument();
    expect(screen.getByText('已读取主机')).toBeInTheDocument();
    expect(screen.getByText('12.4%')).toBeInTheDocument();
    expect(screen.getByText('运行状态待确认')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重试读取' })).toBeEnabled();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '运行设置' }));
    });
    expect(screen.getByRole('button', { name: '软重启运行' })).toBeDisabled();
  } finally {
    vi.useRealTimers();
  }
});

it('修改密码入口放在运行设置，取消后返回设置，关闭设置时焦点返回页头', async () => {
  render(
    <MemoryRouter>
      <System />
    </MemoryRouter>,
  );
  await screen.findByText('运行中');
  expect(screen.queryByRole('button', { name: '修改密码' })).not.toBeInTheDocument();
  const settingsButton = screen.getByRole('button', { name: '运行设置' });
  settingsButton.focus();
  await act(async () => {
    fireEvent.click(settingsButton);
  });
  const dialog = screen.getByRole('dialog', { name: '运行设置' });
  expect(within(dialog).getByRole('region', { name: '面板安全' })).toBeInTheDocument();
  await act(async () => {
    fireEvent.click(within(dialog).getByRole('button', { name: '修改密码' }));
  });
  expect(screen.queryByRole('dialog', { name: '运行设置' })).not.toBeInTheDocument();
  const password = screen.getByRole('dialog', { name: '修改面板密码' });
  expect(within(password).getByLabelText('当前密码')).toHaveFocus();
  await act(async () => {
    fireEvent.click(within(password).getByRole('button', { name: '取消' }));
  });
  expect(screen.getByRole('dialog', { name: '运行设置' })).toBeInTheDocument();
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: '关闭对话框' }));
  });
  await waitFor(() => expect(settingsButton).toHaveFocus());
});
