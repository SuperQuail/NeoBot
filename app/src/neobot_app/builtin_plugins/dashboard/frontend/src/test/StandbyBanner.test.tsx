// StandbyBanner 回归测试 —— 待机状态展示、时长格式化与一键启动运行
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import StandbyBanner, { formatDuration } from '../components/StandbyBanner';
import { api } from '../api/endpoints';
import { clearQueries } from '../data/queryCore';

vi.mock('../api/endpoints.js', () => ({
  api: { powerStatus: vi.fn(), resume: vi.fn() },
}));

const powerStatus = vi.mocked(api.powerStatus);
const resume = vi.mocked(api.resume);

beforeEach(() => {
  clearQueries();
});

describe('formatDuration', () => {
  it('未知或 0 秒显示占位符', () => {
    expect(formatDuration()).toBe('—');
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(0)).toBe('—');
  });

  it('按小时 / 分钟 / 秒分段', () => {
    expect(formatDuration(45)).toBe('45 秒');
    expect(formatDuration(125)).toBe('2 分 5 秒');
    expect(formatDuration(3725)).toBe('1 小时 2 分');
  });
});

describe('StandbyBanner', () => {
  it('运行中不渲染任何内容', async () => {
    powerStatus.mockResolvedValue({ ok: true, available: true, state: 'running', standby: false });
    const { container } = render(<StandbyBanner />);

    await waitFor(() => expect(powerStatus).toHaveBeenCalled());
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('清理未完成时展示真实阶段且禁止再次启动', async () => {
    powerStatus.mockResolvedValue({
      ok: true, available: true, state: 'stopping', phase: 'stopping',
      standby: true, transition: true, reason: '停止超时：清理仍在进行',
    });
    render(<StandbyBanner />);
    expect(await screen.findByText('Bot 正在停止')).toBeInTheDocument();
    expect(screen.queryByText('Bot 处于待机状态')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '等待清理完成' })).toBeDisabled();
    expect(screen.getByText(/停止超时：清理仍在进行/)).toBeInTheDocument();
  });

  it('失败但清理已结束时允许重试，不把失败显示成运行中', async () => {
    powerStatus.mockResolvedValue({
      ok: true, available: true, state: 'failed', standby: true,
      transition: false, reason: '启动失败，已清理',
    });
    render(<StandbyBanner />);
    expect(await screen.findByText('Bot 运行时操作失败')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '启动运行' })).toBeEnabled();
  });

  it('待机时展示原因 / 操作者 / 时长，点击后调 resume 并隐藏', async () => {
    powerStatus
      .mockResolvedValueOnce({
        ok: true,
        available: true,
        state: 'standby',
        standby: true,
        reason: '升级模型',
        operator: 'admin',
        since_text: '10:00',
        standby_seconds: 125,
        connect_onebot: true,
      })
      .mockResolvedValue({ ok: true, available: true, state: 'running', standby: false });
    resume.mockResolvedValue({ ok: true, data: { message: '已启动' }, error: null, status: 200 });

    render(<StandbyBanner />);

    expect(await screen.findByText('Bot 处于待机状态')).toBeInTheDocument();
    expect(screen.getByText(/原因：升级模型/)).toBeInTheDocument();
    expect(screen.getByText(/操作者 admin/)).toBeInTheDocument();
    expect(screen.getByText(/已待机 2 分 5 秒/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '启动运行' }));

    await waitFor(() => expect(resume).toHaveBeenCalledOnce());
    await waitFor(() => expect(screen.queryByText('Bot 处于待机状态')).not.toBeInTheDocument());
  });
});
