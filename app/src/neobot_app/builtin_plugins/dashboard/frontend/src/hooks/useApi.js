// useApi.js —— 数据拉取 hook
// useApi:加载一次;支持可选轮询 interval(对应旧 app.js 的 setInterval 轮询)。

import { useState, useEffect, useCallback, useRef } from 'react';

export function useApi(fetcher, { interval = 0, deps = [] } = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const load = useCallback(async () => {
    try {
      const d = await fetcherRef.current();
      setData(d);
      setError(d == null ? 'no-data' : null);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    load();
    if (interval > 0) {
      const id = setInterval(() => alive && load(), interval);
      return () => {
        alive = false;
        clearInterval(id);
      };
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, loading, error, reload: load };
}
