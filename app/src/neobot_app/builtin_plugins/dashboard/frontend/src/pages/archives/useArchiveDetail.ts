import { useCallback, useEffect, useMemo, useRef } from 'react';
import { api } from '../../api/endpoints';
import type { ArchiveItemDetail, Result } from '../../api/types';
import { getQuerySnapshot } from '../../data/queryCore';
import { QK } from '../../data/queryKeys';
import { useQuery } from '../../data/useQuery';
import { isEditingSurfaceActive } from '../../hooks/useAutoRefresh';

/** 只读详情与编辑世代隔离；开始编辑前发出的请求也不能推进草稿的版本。 */
export function useArchiveDetail(table: string, key: string, protectedState: boolean) {
  const queryKey = QK.archiveItem(table, key);
  const generation = useMemo(() => ({ queryKey, protectedState }), [queryKey, protectedState]);
  const latest = useRef({ generation, protectedState, queryKey });
  latest.current = { generation, protectedState, queryKey };
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const query = useQuery(
    queryKey,
    async () => {
      if (!table || !key) return null;
      const previous = () => getQuerySnapshot<Result<ArchiveItemDetail>>(queryKey).data;
      const canApply = () =>
        mounted.current &&
        latest.current.queryKey === queryKey &&
        latest.current.generation === generation &&
        !latest.current.protectedState &&
        (!previous() || !isEditingSurfaceActive());
      try {
        const result = await api.archiveItem(table, key);
        // 检查回包时的状态，不能只依赖轮询发起时的 enabled。
        if (!canApply()) return previous();
        return result;
      } catch (error) {
        if (!canApply()) return previous();
        throw error;
      }
    },
    { deps: [table, key] },
  );
  const { refetch } = query;
  const automaticRead = useRef<ReturnType<typeof refetch> | null>(null);
  const refetchAutomatically = useCallback(async () => {
    const pending = refetch();
    automaticRead.current = pending;
    try {
      return await pending;
    } finally {
      if (automaticRead.current === pending) automaticRead.current = null;
    }
  }, [refetch]);
  const refetchAfterWrite = useCallback(async () => {
    // 等待被守护丢弃的旧轮询结束，再发写后读取，避免查询去重吞掉本次失效。
    await automaticRead.current;
    return refetch();
  }, [refetch]);
  return { ...query, refetchAutomatically, refetchAfterWrite };
}
