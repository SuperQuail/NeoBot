// data/queryCore 回归测试 —— 并发去重、缓存命中、失效重取、轮询生命周期
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  addPoller,
  clearQueries,
  fetchQuery,
  getEntry,
  getQuerySnapshot,
  invalidateQueries,
  setQueryData,
  subscribe,
} from '../data/queryCore';

afterEach(() => {
  clearQueries();
  vi.useRealTimers();
});

describe('queryCore', () => {
  it('同一 key 的并发请求只发一次', async () => {
    const holder: { resolve?: (value: number) => void } = {};
    const fetcher = vi.fn(
      () =>
        new Promise<number>((resolve) => {
          holder.resolve = resolve;
        }),
    );
    getEntry<number>('k1', fetcher, 0);

    const first = fetchQuery<number>('k1');
    const second = fetchQuery<number>('k1');
    holder.resolve?.(42);

    await expect(first).resolves.toBe(42);
    await expect(second).resolves.toBe(42);
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(getQuerySnapshot<number>('k1').data).toBe(42);
  });

  it('已有缓存时默认不重复请求，force 才重取', async () => {
    const fetcher = vi.fn(async () => 'v1');
    getEntry<string>('k2', fetcher, 0);

    await fetchQuery<string>('k2');
    await fetchQuery<string>('k2');
    expect(fetcher).toHaveBeenCalledTimes(1);

    await fetchQuery<string>('k2', { force: true });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('失败时记录 error 且不抛异常', async () => {
    getEntry<string>('k3', async () => {
      throw new Error('boom');
    }, 0);
    await expect(fetchQuery<string>('k3')).resolves.toBeNull();
    expect(getQuerySnapshot<string>('k3').error).toBe('boom');
  });

  it('订阅者能收到状态变化；setQueryData 直接落缓存', async () => {
    getEntry<number>('k4', async () => 1, 0);
    const listener = vi.fn();
    const unsubscribe = subscribe(getEntry<number>('k4', async () => 1, 0), listener);
    setQueryData<number>('k4', 7);
    expect(listener).toHaveBeenCalled();
    expect(getQuerySnapshot<number>('k4').data).toBe(7);
    unsubscribe();
  });

  it('invalidateQueries 按前缀匹配并强制重取', async () => {
    const fetcher = vi.fn(async () => 'x');
    getEntry<string>('stats:usage:24', fetcher, 0);
    getEntry<string>('stats:other', fetcher, 0);
    await fetchQuery<string>('stats:usage:24');
    await fetchQuery<string>('stats:other');
    expect(fetcher).toHaveBeenCalledTimes(2);

    invalidateQueries(['stats:usage']);
    await Promise.resolve();
    // 只有前缀命中的那个被重新取数
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it('轮询：有订阅者才起定时器，取消后停止', async () => {
    vi.useFakeTimers();
    const fetcher = vi.fn(async () => 'tick');
    const entry = getEntry<string>('k5', fetcher, 1000);

    const stop = addPoller('k5', entry);
    await vi.advanceTimersByTimeAsync(3000);
    const callsWhilePolling = fetcher.mock.calls.length;
    expect(callsWhilePolling).toBeGreaterThan(1);

    stop();
    await vi.advanceTimersByTimeAsync(3000);
    expect(fetcher.mock.calls.length).toBe(callsWhilePolling);
  });
});
