// data/useQuery.ts —— 把 queryCore 接到 React：useQuery（读）与 useMutation（写）
// 用法：
//   const overview = useQuery<Overview>('overview', () => api.overview(), { interval: 10000 });
//   const save = useMutation(() => api.configSave(body), { invalidate: ['config'] });
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import {
  addPoller,
  fetchQuery,
  getEntry,
  setQueryData,
  subscribe,
  invalidateQueries,
  type QueryState,
} from './queryCore';

export interface UseQueryOptions {
  /** 轮询间隔（毫秒）；0 表示只在挂载/依赖变化时取一次 */
  interval?: number;
  /** 依赖变化时重新取数（与旧 useApi 的 deps 语义一致） */
  deps?: unknown[];
  /** 默认 false：已有缓存时不再重复请求（多页共享同一 key 时生效） */
  refetchOnMount?: boolean;
}

export interface UseQueryResult<T> extends QueryState<T> {
  refetch: () => Promise<T | null>;
}

export function useQuery<T>(
  queryKey: string,
  fetcher: () => Promise<T | null>,
  { interval = 0, deps = [], refetchOnMount = false }: UseQueryOptions = {},
): UseQueryResult<T> {
  const entry = getEntry<T>(queryKey, fetcher, interval);
  const state = useSyncExternalStore(
    useCallback((listener: () => void) => subscribe(entry, listener), [entry]),
    () => entry.state as QueryState<T>,
    () => entry.state as QueryState<T>,
  );

  const depsKey = JSON.stringify(deps ?? []);
  const previousDeps = useRef(depsKey);

  useEffect(() => {
    const changed = previousDeps.current !== depsKey;
    previousDeps.current = depsKey;
    void fetchQuery(queryKey, { force: changed || refetchOnMount });
    if (interval > 0) return addPoller(queryKey, entry);
    return undefined;
    // depsKey 已覆盖 deps 的全部语义
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryKey, depsKey, interval, entry, refetchOnMount]);

  const refetch = useCallback(() => fetchQuery<T>(queryKey, { force: true }), [queryKey]);

  return { ...state, refetch };
}

export interface UseMutationOptions<T> {
  /** 成功后失效这些 key（前缀匹配），触发相关查询重取 */
  invalidate?: string[];
  /** 成功后直接写入缓存（省一次往返） */
  onSuccessData?: (data: T) => void;
  onSuccess?: (data: T) => void;
  onError?: (error: string) => void;
}

export interface UseMutationResult<T, A extends unknown[]> {
  run: (...args: A) => Promise<T | null>;
  busy: boolean;
  error: string | null;
  /** 最近一次成功的结果 */
  data: T | null;
  reset: () => void;
}

export function useMutation<T, A extends unknown[] = []>(
  action: (...args: A) => Promise<T | null>,
  { invalidate, onSuccessData, onSuccess, onError }: UseMutationOptions<T> = {},
): UseMutationResult<T, A> {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<T | null>(null);
  const actionRef = useRef(action);
  actionRef.current = action;

  const run = useCallback(
    async (...args: A) => {
      setBusy(true);
      setError(null);
      try {
        const result = await actionRef.current(...args);
        if (result == null) {
          setError('no-data');
          onError?.('no-data');
          return null;
        }
        setData(result);
        if (invalidate?.length) invalidateQueries(invalidate);
        onSuccessData?.(result);
        onSuccess?.(result);
        return result;
      } catch (e) {
        const message = (e as Error).message || String(e);
        setError(message);
        onError?.(message);
        return null;
      } finally {
        setBusy(false);
      }
    },
    // invalidate 为字面量数组时每次渲染都会新建，用 JSON 做稳定依赖
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [JSON.stringify(invalidate ?? [])],
  );

  const reset = useCallback(() => {
    setError(null);
    setData(null);
  }, []);

  return useMemo(() => ({ run, busy, error, data, reset }), [run, busy, error, data, reset]);
}

export { setQueryData, invalidateQueries };
