// data/queryCore.ts —— 轻量查询缓存：同 key 并发去重、结果缓存、失效重取
// 目标：替换散落各页的 useApi + 手写 setInterval，做到
//   1) 同一接口在任何时刻最多一个在途请求（Dashboard 与 System 不再各拉一份 /api/system）；
//   2) 卸载后不再 setState（内置订阅式 store，无竞态）；
//   3) 写操作后可精确失效（invalidate）指定 key。
// 刻意不引入 TanStack Query：面板规模小，几十行足够，且避免新增运行时依赖。

export interface QueryState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  /** 最近一次成功取数的时刻（轮询/新鲜度判断用） */
  updatedAt: number;
}

interface Entry<T = unknown> {
  state: QueryState<T>;
  promise: Promise<T | null> | null;
  listeners: Set<() => void>;
  fetcher: () => Promise<T | null>;
  /** 轮询订阅者数量：归零后可停止轮询 */
  pollers: number;
  timer: ReturnType<typeof setInterval> | null;
  intervalMs: number;
}

const entries = new Map<string, Entry<any>>();

const EMPTY: QueryState<never> = { data: null, error: null, loading: true, updatedAt: 0 };

function emit(entry: Entry<any>): void {
  for (const listener of entry.listeners) listener();
}

function setState<T>(entry: Entry<T>, patch: Partial<QueryState<T>>): void {
  entry.state = { ...entry.state, ...patch };
  emit(entry);
}

function startPolling(queryKey: string, entry: Entry<any>): void {
  if (entry.timer || entry.intervalMs <= 0 || entry.pollers <= 0) return;
  entry.timer = setInterval(() => {
    void fetchQuery(queryKey, { force: true });
  }, entry.intervalMs);
}

function stopPolling(entry: Entry<any>): void {
  if (entry.timer) {
    clearInterval(entry.timer);
    entry.timer = null;
  }
}

/** 读取（不存在则注册）一个查询条目 */
export function getEntry<T>(queryKey: string, fetcher: () => Promise<T | null>, intervalMs = 0): Entry<T> {
  let entry = entries.get(queryKey) as Entry<T> | undefined;
  if (!entry) {
    entry = {
      state: { ...EMPTY },
      promise: null,
      listeners: new Set(),
      fetcher,
      pollers: 0,
      timer: null,
      intervalMs,
    };
    entries.set(queryKey, entry);
  } else {
    // 每次渲染都拿最新闭包，避免依赖陈旧 fetch 函数
    entry.fetcher = fetcher;
    entry.intervalMs = intervalMs;
  }
  return entry;
}

/** 取数：并发去重；force=false 且已有数据时不重复请求 */
export async function fetchQuery<T>(queryKey: string, options: { force?: boolean } = {}): Promise<T | null> {
  const entry = entries.get(queryKey) as Entry<T> | undefined;
  if (!entry) return null;
  if (entry.promise) return entry.promise;
  const fresh = entry.state.updatedAt > 0 && !options.force;
  if (fresh && entry.state.data !== null) return entry.state.data;

  setState(entry, { loading: entry.state.data === null, error: null });
  entry.promise = (async () => {
    try {
      const data = await entry.fetcher();
      setState(entry, {
        data,
        error: data == null ? 'no-data' : null,
        loading: false,
        updatedAt: Date.now(),
      });
      return data;
    } catch (e) {
      setState(entry, { error: (e as Error).message || String(e), loading: false });
      return null;
    } finally {
      entry.promise = null;
    }
  })();
  return entry.promise;
}

export function subscribe(entry: Entry<any>, listener: () => void): () => void {
  entry.listeners.add(listener);
  return () => entry.listeners.delete(listener);
}

export function addPoller(queryKey: string, entry: Entry<any>): () => void {
  entry.pollers += 1;
  startPolling(queryKey, entry);
  return () => {
    entry.pollers = Math.max(0, entry.pollers - 1);
    if (entry.pollers === 0) stopPolling(entry);
  };
}

/** 写入缓存（写操作成功后可直接落最新数据，省一次往返） */
export function setQueryData<T>(queryKey: string, data: T): void {
  const entry = entries.get(queryKey) as Entry<T> | undefined;
  if (!entry) return;
  setState(entry, { data, error: null, loading: false, updatedAt: Date.now() });
}

/** 让若干 key 立即重新取数（写操作后调用） */
export function invalidateQueries(prefixes: string[]): void {
  for (const queryKey of entries.keys()) {
    if (prefixes.some((prefix) => queryKey.startsWith(prefix))) {
      void fetchQuery(queryKey, { force: true });
    }
  }
}

/** 供测试/登出使用：清空所有缓存 */
export function clearQueries(): void {
  for (const entry of entries.values()) {
    stopPolling(entry);
    entry.listeners.clear();
  }
  entries.clear();
}

export function getQuerySnapshot<T>(queryKey: string): QueryState<T> {
  return (entries.get(queryKey)?.state as QueryState<T>) || (EMPTY as QueryState<T>);
}
