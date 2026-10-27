// ScheduledTasks.test.tsx —— 定时任务页：列表、启停、删除、新建表单校验
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { confirmAction } from '../components/ui/ConfirmDialog';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import ScheduledTasks from '../pages/ScheduledTasks';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';
import type { ScheduledTasksPayload } from '../api/types';

vi.mock('../components/ui/ConfirmDialog', () => ({ confirmAction: vi.fn() }));

vi.mock('../api/endpoints', () => ({
  api: { scheduledTasks: vi.fn(), scheduledTaskAction: vi.fn() },
}));

const scheduledTasks = vi.mocked(api.scheduledTasks);
const scheduledTaskAction = vi.mocked(api.scheduledTaskAction);
let restoreMedia: (() => void) | undefined;

function mockCompactViewport() {
  const listeners = new Set<() => void>();
  const media = {
    matches: true,
    media: '(max-width: 740px)',
    addEventListener: (_type: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_type: string, listener: () => void) => listeners.delete(listener),
  };
  const original = window.matchMedia;
  const spy = vi
    .spyOn(window, 'matchMedia')
    .mockImplementation((query) =>
      query === media.media ? (media as unknown as MediaQueryList) : original(query),
    );
  restoreMedia = () => spy.mockRestore();
  return (compact: boolean) =>
    act(() => {
      media.matches = compact;
      listeners.forEach((listener) => listener());
    });
}

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
  vi.mocked(confirmAction).mockResolvedValue(true);
  scheduledTaskAction.mockResolvedValue({
    ok: true,
    data: { message: '已执行' },
    error: null,
    status: 200,
  });
});

afterEach(() => {
  restoreMedia?.();
  restoreMedia = undefined;
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

  it('取消删除时保留任务且不发送写请求', async () => {
    scheduledTasks.mockResolvedValue(PAYLOAD);
    vi.mocked(confirmAction).mockResolvedValue(false);
    render(<ScheduledTasks />);
    await screen.findByText('喝水提醒');
    fireEvent.click(screen.getAllByRole('button', { name: '删除' })[0]);
    await waitFor(() => expect(confirmAction).toHaveBeenCalled());
    expect(scheduledTaskAction).not.toHaveBeenCalled();
    expect(screen.getByText('喝水提醒')).toBeInTheDocument();
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

  it('编辑表单由固定操作区提交，保留时间、通知策略与多个绑定', async () => {
    scheduledTasks.mockResolvedValue(PAYLOAD);
    render(<ScheduledTasks />);
    await screen.findByText('喝水提醒');
    fireEvent.click(screen.getAllByRole('button', { name: '编辑' })[0]);

    const form = screen.getByRole('form', { name: '定时任务表单' });
    const saveButton = screen.getByRole('button', { name: /^保存$/ }) as HTMLButtonElement;
    expect(form).not.toContainElement(saveButton);
    expect(saveButton.form).toBe(form);
    expect(screen.getByLabelText('标题')).toHaveValue('喝水提醒');
    expect(screen.getByLabelText('提醒内容')).toHaveValue('每个小时喝一杯');

    fireEvent.change(screen.getByLabelText('重复方式'), { target: { value: 'weekly' } });
    fireEvent.change(screen.getByLabelText('开始时间'), { target: { value: '2026-01-08T10:00' } });
    fireEvent.change(screen.getByLabelText('结束时间'), { target: { value: '2026-01-08T10:30' } });
    fireEvent.click(screen.getByRole('checkbox', { name: /每个触发窗口只通知一次/ }));
    fireEvent.click(screen.getByRole('button', { name: '添加绑定' }));
    fireEvent.change(screen.getByLabelText('绑定类型 2'), { target: { value: 'private' } });
    fireEvent.change(screen.getByLabelText('绑定 ID 2'), { target: { value: '10001' } });
    fireEvent.click(saveButton);

    await waitFor(() =>
      expect(scheduledTaskAction).toHaveBeenCalledWith({
        action: 'update',
        task_uuid: 't-1',
        title: '喝水提醒',
        detail: '每个小时喝一杯',
        recurrence: 'weekly',
        start_at: '2026-01-08T10:00',
        end_at: '2026-01-08T10:30',
        one_shot_notification: false,
        bindings: [
          { kind: 'group', id: '888' },
          { kind: 'private', id: '10001' },
        ],
      }),
    );
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('提交期间锁定表单和关闭操作，失败后保留草稿供继续编辑', async () => {
    scheduledTasks.mockResolvedValue(PAYLOAD);
    let completeAction!: (result: Awaited<ReturnType<typeof api.scheduledTaskAction>>) => void;
    scheduledTaskAction.mockReturnValueOnce(
      new Promise((resolve) => {
        completeAction = resolve;
      }),
    );
    render(<ScheduledTasks />);
    await screen.findByText('喝水提醒');
    fireEvent.click(screen.getAllByRole('button', { name: '编辑' })[0]);
    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '保留这份草稿' } });
    fireEvent.click(screen.getByRole('button', { name: /^保存$/ }));

    expect(screen.getByRole('button', { name: '提交中…' })).toBeDisabled();
    expect(screen.getByLabelText('标题')).toBeDisabled();
    expect(screen.getByRole('button', { name: '添加绑定' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '关闭对话框' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '取消' })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(scheduledTaskAction).toHaveBeenCalledTimes(1);

    completeAction({ ok: false, data: null, error: '请稍后重试', status: 409 });
    await waitFor(() => expect(screen.getByLabelText('标题')).toBeEnabled());
    expect(screen.getByLabelText('标题')).toHaveValue('保留这份草稿');
    expect(screen.getByRole('button', { name: /^保存$/ })).toBeEnabled();
    expect(screen.getByRole('button', { name: '关闭对话框' })).toBeEnabled();
  });

  it('窄屏使用任务卡片展示全部字段，多绑定可展开且操作无需横向滚动', async () => {
    mockCompactViewport();
    const task = {
      ...PAYLOAD.tasks![0],
      title: '项目例会与本周进度同步提醒',
      detail: '讨论本周进度。\n请带上需要协作的事项。',
      bindings: [
        { kind: 'group', id: '888' },
        { kind: 'private', id: '10001' },
        { kind: 'group', id: '1234567890123456789012345678901234567890' },
        { kind: 'private', id: '10002' },
      ],
    };
    scheduledTasks.mockResolvedValue({ ...PAYLOAD, tasks: [task] });
    render(<ScheduledTasks />);

    const card = await screen.findByRole('article', { name: task.title });
    const content = within(card);
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByText('左右滑动查看完整任务')).not.toBeInTheDocument();
    expect(content.getByText(/讨论本周进度/)).toHaveTextContent('请带上需要协作的事项。');
    expect(content.getByText('2026-01-01 09:00')).toBeInTheDocument();
    expect(content.getByText('2026-01-01 09:10')).toBeInTheDocument();
    expect(content.getByText('2026-01-02 09:00')).toBeInTheDocument();
    expect(content.getByText('每天')).toBeInTheDocument();
    expect(content.getByText('每个窗口一次')).toBeInTheDocument();
    expect(content.getByText('888')).toBeVisible();
    expect(content.getByText(task.bindings[2].id)).not.toBeVisible();
    fireEvent.click(content.getByText('其余 2 个绑定'));
    expect(content.getByText(task.bindings[2].id)).toBeVisible();
    expect(content.getByText('10002')).toBeVisible();

    fireEvent.click(content.getByRole('button', { name: '编辑' }));
    expect(screen.getByLabelText('标题')).toHaveValue(task.title);
    expect(screen.getByLabelText('绑定 ID 4')).toHaveValue('10002');
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    fireEvent.click(content.getByRole('button', { name: '停用' }));
    await waitFor(() => expect(scheduledTaskAction).toHaveBeenCalledTimes(1));
    expect(scheduledTaskAction).toHaveBeenLastCalledWith({
      action: 'set_state',
      task_uuid: 't-1',
      state: 'disabled',
    });

    await waitFor(() => expect(content.getByRole('button', { name: '删除' })).toBeEnabled());
    vi.mocked(confirmAction).mockResolvedValueOnce(false);
    fireEvent.click(content.getByRole('button', { name: '删除' }));
    await waitFor(() => expect(confirmAction).toHaveBeenCalledTimes(1));
    expect(scheduledTaskAction).toHaveBeenCalledTimes(1);
    fireEvent.click(content.getByRole('button', { name: '删除' }));
    await waitFor(() =>
      expect(scheduledTaskAction).toHaveBeenLastCalledWith({ action: 'delete', task_uuid: 't-1' }),
    );
  });

  it('窄屏卡片遵守只读权限，切换桌面布局后保留编辑中的草稿', async () => {
    const setCompact = mockCompactViewport();
    scheduledTasks.mockResolvedValue(PAYLOAD);
    const { unmount } = render(<ScheduledTasks />);
    const card = await screen.findByRole('article', { name: '喝水提醒' });
    fireEvent.click(within(card).getByRole('button', { name: '编辑' }));
    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '旋转屏幕后保留' } });
    setCompact(false);
    expect(screen.getByLabelText('标题')).toHaveValue('旋转屏幕后保留');
    fireEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.queryByRole('article')).not.toBeInTheDocument();
    unmount();

    clearQueries();
    scheduledTasks.mockResolvedValue({ ...PAYLOAD, editable: false });
    setCompact(true);
    render(<ScheduledTasks />);
    const readonlyCard = await screen.findByRole('article', { name: '喝水提醒' });
    for (const label of ['编辑', '停用', '删除']) {
      expect(within(readonlyCard).getByRole('button', { name: label })).toBeDisabled();
    }
    expect(screen.getByRole('button', { name: /新建任务/ })).toBeDisabled();
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
