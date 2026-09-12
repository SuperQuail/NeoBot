// ScheduledTasks.test.tsx —— 定时任务页：列表、启停、删除、新建表单校验
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import ScheduledTasks from '../pages/ScheduledTasks';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';
import type { ScheduledTasksPayload } from '../api/types';

vi.mock('../api/endpoints.js', () => ({
  api: { scheduledTasks: vi.fn(), scheduledTaskAction: vi.fn() },
}));

const scheduledTasks = vi.mocked(api.scheduledTasks);
const scheduledTaskAction = vi.mocked(api.scheduledTaskAction);

const PAYLOAD: ScheduledTasksPayload = {
  ok: true,
  available: true,
  editable: true,
  tasks: [
    {
      task_id: 't-1',
      title: '喝水提醒',
      detail: '每个小时喝一杯',
      recurrence: 'daily',
      state: 'active',
      enabled: true,
      start_at: '2026-01-01 09:00',
      end_at: '2026-01-01 09:10',
      start_at_local: '2026-01-01T09:00',
      end_at_local: '2026-01-01T09:10',
      next_run: '2026-01-02 09:00',
      bindings: [{ kind: 'group', id: '888' }],
      one_shot_notification: true,
      completed_windows: 0,
    },
    {
      task_id: 't-2',
      title: '生日祝福',
      recurrence: 'yearly',
      state: 'disabled',
      enabled: false,
      next_run: '',
      bindings: [{ kind: 'private', id: '10001' }],
      one_shot_notification: false,
    },
  ],
};

beforeEach(() => {
  clearQueries();
  vi.clearAllMocks();
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  scheduledTaskAction.mockResolvedValue({
    ok: true,
    data: { message: '已执行' },
    error: null,
    status: 200,
  });
});

describe('ScheduledTasks', () => {
  it('渲染任务行与关键字段', async () => {
    scheduledTasks.mockResolvedValue(PAYLOAD);
    render(<ScheduledTasks />);

    expect(await screen.findByText('喝水提醒')).toBeInTheDocument();
    expect(screen.getByText('每个小时喝一杯')).toBeInTheDocument();
    expect(screen.getByText('2026-01-02 09:00')).toBeInTheDocument();
    expect(screen.getByText('群 888')).toBeInTheDocument();
    expect(screen.getByText('私聊 10001')).toBeInTheDocument();
    expect(screen.getByText('一次性')).toBeInTheDocument();
    expect(screen.getByText('持续')).toBeInTheDocument();
  });

  it('停用按钮调用 set_state 并刷新列表', async () => {
    scheduledTasks.mockResolvedValue(PAYLOAD);
    render(<ScheduledTasks />);
    await screen.findByText('喝水提醒');

    fireEvent.click(screen.getAllByRole('button', { name: '停用' })[0]);

    await waitFor(() =>
      expect(scheduledTaskAction).toHaveBeenCalledWith({
        action: 'set_state',
        task_uuid: 't-1',
        state: 'disabled',
      }),
    );
    // 列表刷新（初次加载 + 操作后各一次）
    await waitFor(() => expect(scheduledTasks.mock.calls.length).toBeGreaterThan(1));
  });

  it('停用的任务显示启用按钮', async () => {
    scheduledTasks.mockResolvedValue(PAYLOAD);
    render(<ScheduledTasks />);
    await screen.findByText('生日祝福');

    fireEvent.click(screen.getByRole('button', { name: '启用' }));

    await waitFor(() =>
      expect(scheduledTaskAction).toHaveBeenCalledWith({
        action: 'set_state',
        task_uuid: 't-2',
        state: 'active',
      }),
    );
  });

  it('删除需要确认后调用 delete', async () => {
    scheduledTasks.mockResolvedValue(PAYLOAD);
    render(<ScheduledTasks />);
    await screen.findByText('喝水提醒');

    fireEvent.click(screen.getAllByRole('button', { name: '删除' })[0]);

    await waitFor(() =>
      expect(scheduledTaskAction).toHaveBeenCalledWith({ action: 'delete', task_uuid: 't-1' }),
    );
  });

  it('新建表单校验必填项，通过后提交 create', async () => {
    scheduledTasks.mockResolvedValue(PAYLOAD);
    render(<ScheduledTasks />);
    await screen.findByText('喝水提醒');

    fireEvent.click(screen.getByRole('button', { name: /新建任务/ }));
    fireEvent.click(screen.getByRole('button', { name: /^保存$/ }));

    expect(await screen.findByText('标题不能为空')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '开会提醒' } });
    fireEvent.change(screen.getByLabelText('绑定 ID 1'), { target: { value: '888' } });
    fireEvent.click(screen.getByRole('button', { name: /^保存$/ }));

    await waitFor(() => {
      const body = scheduledTaskAction.mock.calls.at(-1)?.[0];
      expect(body?.action).toBe('create');
      expect(body?.title).toBe('开会提醒');
      expect(body?.bindings).toEqual([{ kind: 'group', id: '888' }]);
    });
  });

  it('无管理权限时禁用新建', async () => {
    scheduledTasks.mockResolvedValue({ ...PAYLOAD, editable: false });
    render(<ScheduledTasks />);
    await screen.findByText('喝水提醒');

    expect(screen.getByRole('button', { name: /新建任务/ })).toBeDisabled();
    expect(screen.getAllByRole('button', { name: '删除' })[0]).toBeDisabled();
  });

  it('管理器未启用时显示不可用态', async () => {
    scheduledTasks.mockResolvedValue({
      ok: true,
      available: false,
      tasks: [],
      error: '定时任务管理器未启用',
    });
    render(<ScheduledTasks />);

    expect(await screen.findByText('定时任务不可用')).toBeInTheDocument();
    expect(screen.getByText('定时任务管理器未启用')).toBeInTheDocument();
  });
});
