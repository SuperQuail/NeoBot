import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import Logs from '../pages/Logs';
import { api } from '../api/endpoints';
import type { LogPayload } from '../api/types';
import { POLL } from '../data/queryKeys';

vi.mock('../api/endpoints', () => ({ api: { logs: vi.fn(), logsSince: vi.fn() } }));
const data: LogPayload = {
  last_id: 2,
  items: [
    { id: 1, module: 'agent', level: 'INFO', time: '10:00:00', message: 'Agent 正在处理请求' },
    { id: 2, module: 'drawing', level: 'ERROR', time: '10:00:01', message: '绘图请求失败' },
  ],
};
const structuredData: LogPayload = {
  last_id: 3,
  items: [
    ...data.items!,
    {
      id: 3,
      module: 'reply',
      level: 'ERROR',
      time: '10:00:02',
      message: '上下文处理失败',
      file: 'app/src/neobot_app/reply/orchestrator.py',
      line: 42,
      function: 'generate_reply',
      fields: { conversation_id: 'fixture-group', request: { token: '***REDACTED***' } },
      exception: { type: 'ValueError', message: '字段校验失败', traceback: 'Traceback: fixture-frame' },
    },
  ],
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.logs).mockResolvedValue(data);
  vi.mocked(api.logsSince).mockResolvedValue({ items: [], last_id: 2 });
});

async function chooseModule(label: string) {
  const trigger = screen.getByRole('combobox', { name: '日志模块' });
  await act(async () => {
    fireEvent.keyDown(trigger, { key: 'ArrowDown' });
  });
  const option = screen.getByRole('option', { name: label });
  await act(async () => {
    option.focus();
    fireEvent.keyDown(option, { key: 'Enter' });
  });
}

it('统一模块下拉保留空值筛选语义，并可与等级、搜索组合使用', async () => {
  render(<Logs />);
  await screen.findByText('Agent 正在处理请求', { exact: false });
  await chooseModule('agent');
  expect(screen.queryByText('绘图请求失败', { exact: false })).not.toBeInTheDocument();
  await chooseModule('全部模块');
  expect(screen.getByText('绘图请求失败', { exact: false })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'ERROR' }));
  expect(screen.queryByText('绘图请求失败', { exact: false })).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole('textbox', { name: '搜索日志' }), { target: { value: '不存在的内容' } });
  expect(screen.getByText('没有匹配的日志，试试调整筛选条件')).toBeInTheDocument();
  expect(api.logs).toHaveBeenCalledTimes(1);
});

it('初次读取显示骨架，清屏后仍清楚显示当前模块筛选', async () => {
  let resolve!: (value: LogPayload) => void;
  vi.mocked(api.logs).mockImplementation(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  render(<Logs />);
  expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
  expect(screen.getByText('正在读取日志')).toBeInTheDocument();
  await act(async () => {
    resolve(data);
  });
  expect(screen.queryByText('正在读取日志')).not.toBeInTheDocument();
  await chooseModule('agent');
  fireEvent.click(screen.getByRole('button', { name: '清屏' }));
  expect(screen.getByRole('combobox', { name: '日志模块' })).toHaveTextContent('agent');
  await chooseModule('全部模块');
  expect(screen.getByText('暂无日志')).toBeInTheDocument();
});

it('可展开调用位置、结构化字段与异常，并通过这些上下文搜索', async () => {
  vi.mocked(api.logs).mockResolvedValue(structuredData);
  render(<Logs />);
  await screen.findByText('上下文处理失败', { exact: false });
  fireEvent.click(screen.getByText('日志详情 · 异常'));
  expect(screen.getByText('调用位置')).toBeVisible();
  expect(screen.getByText('app/src/neobot_app/reply/orchestrator.py:42 · generate_reply')).toBeVisible();
  expect(screen.getByText(/fixture-group/)).toBeVisible();
  expect(screen.getByText(/Traceback: fixture-frame/)).toBeVisible();
  for (const query of ['fixture-group', 'generate_reply', '字段校验失败', 'fixture-frame']) {
    fireEvent.change(screen.getByRole('textbox', { name: '搜索日志' }), { target: { value: query } });
    expect(screen.getByText('上下文处理失败', { exact: false })).toBeInTheDocument();
    expect(screen.queryByText('Agent 正在处理请求', { exact: false })).not.toBeInTheDocument();
  }
});

it('下载保留当前筛选日志的字段、调用位置和完整异常', async () => {
  vi.mocked(api.logs).mockResolvedValue(structuredData);
  const createObjectURL = vi.fn<(blob: Blob) => string>(() => 'blob:logs');
  const revokeObjectURL = vi.fn();
  vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  try {
    render(<Logs />);
    await screen.findByText('上下文处理失败', { exact: false });
    fireEvent.change(screen.getByRole('textbox', { name: '搜索日志' }), {
      target: { value: 'fixture-group' },
    });
    fireEvent.click(screen.getByRole('button', { name: '下载' }));
    const blob = createObjectURL.mock.calls[0][0] as Blob;
    const text = await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.readAsText(blob);
    });
    expect(text).toContain('orchestrator.py:42 · generate_reply');
    expect(text).toContain('fixture-group');
    expect(text).toContain('***REDACTED***');
    expect(text).toContain('ValueError: 字段校验失败');
    expect(text).toContain('Traceback: fixture-frame');
    expect(text).not.toContain('Agent 正在处理请求');
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:logs');
  } finally {
    click.mockRestore();
    vi.unstubAllGlobals();
  }
});

it('自动增量更新从最新游标继续，隐藏后暂停，恢复补读且卸载停止', async () => {
  vi.useFakeTimers();
  const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
  try {
    const view = render(<Logs />);
    await act(async () => {});
    vi.mocked(api.logsSince).mockResolvedValue({
      last_id: 3,
      items: [{ id: 3, module: 'agent', level: 'INFO', time: '10:00:02', message: '最新增量日志' }],
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL.liveLogs);
    });
    expect(api.logsSince).toHaveBeenCalledWith(2, 500);
    expect(screen.getByText('最新增量日志', { exact: false })).toBeInTheDocument();
    visibility.mockReturnValue('hidden');
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL.liveLogs * 2);
    });
    expect(api.logsSince).toHaveBeenCalledTimes(1);
    vi.mocked(api.logsSince).mockResolvedValue({ last_id: 3, items: [] });
    visibility.mockReturnValue('visible');
    await act(async () => {
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(api.logsSince).toHaveBeenCalledWith(3, 500);
    expect(api.logsSince).toHaveBeenCalledTimes(2);
    view.unmount();
    await vi.advanceTimersByTimeAsync(POLL.liveLogs * 2);
    expect(api.logsSince).toHaveBeenCalledTimes(2);
  } finally {
    visibility.mockRestore();
    vi.useRealTimers();
  }
});
