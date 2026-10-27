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

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}

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
    getEntry<string>(
      'k3',
      async () => {
        throw new Error('boom');
      },
      0,
    );
    await expect(fetchQuery<string>('k3')).resolves.toBeNull();
    expect(getQuerySnapshot<string>('k3').error).toBe('boom');
  });

  it('订阅者能收到状态变化；setQueryData 直接落缓存', async () => {
    getEntry<number>('k4', async () => 1, 0);
    const listener = vi.fn();
    const unsubscribe = subscribe(
      getEntry<number>('k4', async () => 1, 0),
      listener,
    );
    setQueryData<number>('k4', 7);
    expect(listener).toHaveBeenCalled();
    expect(getQuerySnapshot<number>('k4').data).toBe(7);
    unsubscribe();
  });

  it('自动读取返回空响应时保留上次数据和时间，之后可恢复', async () => {
    const fetcher = vi
      .fn<() => Promise<string | null>>()
      .mockResolvedValueOnce('recent')
      .mockResolvedValueOnce(null)
      .mockResolvedValueOnce('recovered');
    getEntry('retain', fetcher);
    await fetchQuery('retain');
    const updatedAt = getQuerySnapshot('retain').updatedAt;
    await fetchQuery('retain', { force: true });
    expect(getQuerySnapshot('retain')).toMatchObject({
      data: 'recent',
      updatedAt,
      error: 'no-data',
      loading: false,
    });
    await fetchQuery('retain', { force: true });
    expect(getQuerySnapshot('retain')).toMatchObject({ data: 'recovered', error: null });
  });

  it.each(['success', 'error'] as const)(
    '权威写回后忽略旧请求的 %s 结果，失效会在其结束后自动重新读取',
    async (outcome) => {
      const stale = deferred<string>();
      const fresh = deferred<string>();
      const fetcher = vi
        .fn<() => Promise<string>>()
        .mockReturnValueOnce(stale.promise)
        .mockReturnValueOnce(fresh.promise);
      const entry = getEntry<string>('authoritative', fetcher, 0);
      const earlier = fetchQuery<string>('authoritative');

      setQueryData('authoritative', 'confirmed');
      invalidateQueries(['authoritative']);
      expect(fetcher).toHaveBeenCalledTimes(1);
      if (outcome === 'success') stale.resolve('stale');
      else stale.reject(new Error('stale error'));

      await expect(earlier).resolves.toBe('confirmed');
      expect(getQuerySnapshot<string>('authoritative')).toMatchObject({
        data: 'confirmed',
        error: null,
        loading: false,
      });
      expect(fetcher).toHaveBeenCalledTimes(2);
      expect(entry.promise).not.toBeNull();

      const followup = entry.promise;
      fresh.resolve('next');
      await expect(followup).resolves.toBe('next');
      expect(fetcher).toHaveBeenCalledTimes(2);
      expect(getQuerySnapshot<string>('authoritative')).toMatchObject({
        data: 'next',
        error: null,
        loading: false,
      });
      expect(entry.promise).toBeNull();
    },
  );

  it.each(['success', 'error'] as const)(
    '没有权威写回时，重复失效合并成一次尾读并丢弃旧 %s 结果',
    async (outcome) => {
      const stale = deferred<string>();
      const fresh = deferred<string>();
      const fetcher = vi
        .fn<() => Promise<string>>()
        .mockResolvedValueOnce('before')
        .mockReturnValueOnce(stale.promise)
        .mockReturnValueOnce(fresh.promise);
      const entry = getEntry('write:pending', fetcher);
      await fetchQuery('write:pending');
      const snapshots: Array<{ data: unknown; error: string | null }> = [];
      subscribe(entry, () => {
        snapshots.push({ data: entry.state.data, error: entry.state.error });
      });
      const earlier = fetchQuery('write:pending', { force: true });

      invalidateQueries(['write:']);
      invalidateQueries(['write:pending']);
      invalidateQueries(['write:', 'write:pending']);
      expect(fetcher).toHaveBeenCalledTimes(2);
      expect(entry.pendingInvalidate).toBe(true);
      if (outcome === 'success') stale.resolve('stale');
      else stale.reject(new Error('stale error'));

      await expect(earlier).resolves.toBe('before');
      expect(fetcher).toHaveBeenCalledTimes(3);
      expect(entry.pendingInvalidate).toBe(false);
      expect(getQuerySnapshot('write:pending')).toMatchObject({ data: 'before', error: null });
      const followup = entry.promise;
      fresh.resolve('after-write');
      await expect(followup).resolves.toBe('after-write');
      expect(getQuerySnapshot('write:pending')).toMatchObject({
        data: 'after-write',
        error: null,
        loading: false,
      });
      expect(snapshots.every((snapshot) => snapshot.data !== 'stale' && snapshot.error === null)).toBe(true);
      expect(entry.promise).toBeNull();
      expect(fetcher).toHaveBeenCalledTimes(3);
    },
  );

  it('清空缓存取消待补读取，旧请求结束不能读写同 key 的新会话', async () => {
    const stale = deferred<string>();
    const oldFetcher = vi.fn(() => stale.promise);
    const oldEntry = getEntry('session', oldFetcher);
    const listener = vi.fn();
    subscribe(oldEntry, listener);
    const earlier = fetchQuery('session');
    invalidateQueries(['session']);
    expect(oldEntry.pendingInvalidate).toBe(true);

    clearQueries();
    listener.mockClear();
    const newFetcher = vi.fn(async () => 'new-session');
    getEntry('session', newFetcher);
    await fetchQuery('session');
    stale.resolve('old-session');
    await expect(earlier).resolves.toBeNull();

    expect(oldEntry.pendingInvalidate).toBe(false);
    expect(oldFetcher).toHaveBeenCalledTimes(1);
    expect(newFetcher).toHaveBeenCalledTimes(1);
    expect(listener).not.toHaveBeenCalled();
    expect(getQuerySnapshot('session')).toMatchObject({ data: 'new-session', error: null, loading: false });
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
