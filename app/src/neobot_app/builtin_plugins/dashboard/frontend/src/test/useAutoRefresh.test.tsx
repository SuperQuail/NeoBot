import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useAutoRefresh } from '../hooks/useAutoRefresh';

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

it('只在周期到达读取，使用最新回调，并在卸载后释放时钟', async () => {
  const first = vi.fn();
  const next = vi.fn();
  const view = renderHook(({ read, enabled }) => useAutoRefresh(read, { interval: 1000, enabled }), {
    initialProps: { read: first, enabled: false },
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(first).not.toHaveBeenCalled();
  view.rerender({ read: next, enabled: true });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(first).not.toHaveBeenCalled();
  expect(next).toHaveBeenCalledTimes(1);
  view.unmount();
  await vi.advanceTimersByTimeAsync(2000);
  expect(next).toHaveBeenCalledTimes(1);
});

it('隐藏与离线暂停，恢复后补读且可见/聚焦事件不会重复并发', async () => {
  const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
  const online = vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
  const read = vi.fn();
  const view = renderHook(() => useAutoRefresh(read, { interval: 1000 }));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
  expect(read).not.toHaveBeenCalled();
  visibility.mockReturnValue('visible');
  await act(async () => {
    document.dispatchEvent(new Event('visibilitychange'));
    window.dispatchEvent(new Event('focus'));
  });
  expect(read).toHaveBeenCalledTimes(1);
  online.mockReturnValue(false);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
  expect(read).toHaveBeenCalledTimes(1);
  online.mockReturnValue(true);
  await act(async () => {
    window.dispatchEvent(new Event('online'));
  });
  expect(read).toHaveBeenCalledTimes(2);
  view.unmount();
});

it('请求未完成时不重叠，失败后下一周期继续读取', async () => {
  let finish!: () => void;
  const read = vi
    .fn()
    .mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    )
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValue(undefined);
  const view = renderHook(() => useAutoRefresh(read, { interval: 1000 }));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });
  expect(read).toHaveBeenCalledTimes(1);
  await act(async () => {
    finish();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
  expect(read).toHaveBeenCalledTimes(3);
  view.unmount();
});

it('输入聚焦、非法 JSON 或弹窗交互时暂停，但已保存的无效下拉值不阻止恢复', async () => {
  const read = vi.fn();
  const view = renderHook(() => useAutoRefresh(read, { interval: 1000 }));
  const input = document.createElement('textarea');
  document.body.append(input);
  input.focus();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(read).not.toHaveBeenCalled();
  input.setAttribute('aria-invalid', 'true');
  input.blur();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(read).not.toHaveBeenCalled();
  input.remove();
  const dialog = document.createElement('div');
  dialog.setAttribute('role', 'dialog');
  document.body.append(dialog);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(read).not.toHaveBeenCalled();
  dialog.setAttribute('role', 'combobox');
  dialog.setAttribute('aria-invalid', 'true');
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
  expect(read).toHaveBeenCalledTimes(1);
  dialog.remove();
  view.unmount();
});
