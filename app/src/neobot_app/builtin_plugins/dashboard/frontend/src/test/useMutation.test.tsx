import { act, renderHook } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { useMutation } from '../data/useQuery';

it('进行中的请求使用最新回调，下一次执行使用最新操作，run 引用保持稳定', async () => {
  let finish!: (value: string) => void;
  const firstAction = vi.fn(
    () =>
      new Promise<string>((resolve) => {
        finish = resolve;
      }),
  );
  const nextAction = vi.fn(async () => '第二次结果');
  const oldCallback = vi.fn();
  const latestCallback = vi.fn();
  const { result, rerender } = renderHook(({ action, onSuccess }) => useMutation(action, { onSuccess }), {
    initialProps: { action: firstAction, onSuccess: oldCallback },
  });
  const run = result.current.run;
  let request!: Promise<string | null>;
  act(() => {
    request = run();
  });
  expect(result.current.busy).toBe(true);
  rerender({ action: nextAction, onSuccess: latestCallback });
  expect(result.current.run).toBe(run);
  await act(async () => {
    finish('第一次结果');
    await request;
  });
  expect(oldCallback).not.toHaveBeenCalled();
  expect(latestCallback).toHaveBeenCalledWith('第一次结果');
  await act(async () => {
    await result.current.run();
  });
  expect(nextAction).toHaveBeenCalledTimes(1);
  expect(latestCallback).toHaveBeenLastCalledWith('第二次结果');
  expect(result.current.busy).toBe(false);
});

it('失败后使用最新错误回调，保留错误并解除忙碌状态', async () => {
  let fail!: (error: Error) => void;
  const action = () =>
    new Promise<string>((_resolve, reject) => {
      fail = reject;
    });
  const before = vi.fn();
  const after = vi.fn();
  const { result, rerender } = renderHook(({ onError }) => useMutation(action, { onError }), {
    initialProps: { onError: before },
  });
  let request!: Promise<string | null>;
  act(() => {
    request = result.current.run();
  });
  rerender({ onError: after });
  await act(async () => {
    fail(new Error('保存失败'));
    await request;
  });
  expect(before).not.toHaveBeenCalled();
  expect(after).toHaveBeenCalledWith('保存失败');
  expect(result.current.error).toBe('保存失败');
  expect(result.current.busy).toBe(false);
});
