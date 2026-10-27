import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import TaskStatusList, { TaskDetails } from '../components/TaskStatusList';

describe('任务状态展示', () => {
  it('读取真实任务、待处理数和来源错误，不把字段数当作任务数', () => {
    const snapshot = {
      active_task: { task_id: 'draw-1', status: 'drawing' },
      solver_has_active_task: false,
      solver_recent_tasks: [
        { task_id: 'solve-1', status: 'failed', error: '模型连接中断', question: '分析本周计划' },
      ],
      background_notifications_pending: 3,
      scheduled_task_notifications_pending: 0,
      background_notifications_by_source: { drawing: 2, scheduled_task: 1 },
      cooldown_remaining_seconds: 75,
      notification_error: '通知状态暂不可读',
      extension_data: { unfamiliar: '完整保留' },
    };
    const { container } = render(<TaskStatusList snapshot={snapshot} />);
    expect(screen.getByText('正在绘图')).toBeInTheDocument();
    expect(screen.getByText('draw-1', { selector: 'h4' })).toBeInTheDocument();
    expect(screen.getByText('待处理通知').nextElementSibling).toHaveTextContent('3 条');
    expect(screen.getByText('待发送提醒').nextElementSibling).toHaveTextContent('0 条');
    expect(screen.getByText('绘图冷却').nextElementSibling).toHaveTextContent('1 分 15 秒');
    expect(screen.getByText('模型连接中断')).toBeInTheDocument();
    expect(screen.getByText('通知服务状态读取失败')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    const raw = container.querySelector('details')!;
    expect(raw).not.toHaveAttribute('open');
    fireEvent.click(within(raw).getByText('原始数据'));
    expect(raw).toHaveAttribute('open');
    expect(within(raw).getByText(/"unfamiliar": "完整保留"/)).toBeInTheDocument();
  });

  it('仅呈现明确的进度与已运行时长，未知状态保持原文', () => {
    const { rerender } = render(
      <TaskDetails
        value={{
          name: '归档',
          status: 'external-stage',
          progress: { completed: 3, total: 12 },
          elapsed_seconds: 90,
          created_at: 100,
        }}
      />,
    );
    expect(screen.getByText('external-stage')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: '任务进度' })).toHaveAttribute('value', '25');
    expect(screen.getByText('3 / 12')).toBeInTheDocument();
    expect(screen.getByText('1 分 30 秒')).toBeInTheDocument();
    rerender(<TaskDetails value={{ task_id: 'no-progress', created_at: 100, progress: 0.5 }} />);
    expect(screen.getByText('状态未提供')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.queryByText('已运行')).not.toBeInTheDocument();
  });

  it('未知任务来源可查看原始数据，不显示虚构的正常或完成状态', () => {
    render(
      <TaskStatusList snapshot={{ custom_provider: { metadata: 'waiting-for-input', name: 'custom' } }} />,
    );
    expect(screen.getByText('暂未提供可识别的任务摘要')).toBeInTheDocument();
    expect(screen.getByText(/"waiting-for-input"/)).toBeInTheDocument();
    expect(screen.queryByText('已完成')).not.toBeInTheDocument();
  });

  it('通用命名任务展示真实状态、待处理数和完成数量', () => {
    render(
      <TaskStatusList
        snapshot={{
          memory_summary: { status: 'waiting', pending: 12 },
          custom_job: { name: '整理资料', state: 'running', completed: 2, total: 8 },
        }}
      />,
    );
    const memory = within(screen.getByRole('region', { name: '记忆总结' }));
    expect(memory.getByRole('heading', { name: '记忆总结' })).toBeInTheDocument();
    expect(memory.getByText('等待中')).toBeInTheDocument();
    expect(memory.getByText('待处理').nextElementSibling).toHaveTextContent('12');
    expect(memory.queryByRole('progressbar')).not.toBeInTheDocument();
    const custom = within(screen.getByRole('region', { name: 'custom_job' }));
    expect(custom.getByRole('heading', { name: '整理资料' })).toBeInTheDocument();
    expect(custom.getByRole('progressbar')).toHaveAttribute('value', '25');
    expect(custom.getByText('2 / 8')).toBeInTheDocument();
    expect(screen.queryByText('暂未提供可识别的任务摘要')).not.toBeInTheDocument();
  });
});
