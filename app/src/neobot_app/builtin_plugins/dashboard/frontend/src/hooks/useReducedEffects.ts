import { useCallback, useMemo, useSyncExternalStore } from 'react';

/** 同时覆盖首次加载和运行中修改系统动态效果偏好。 */
export function useReducedEffects(): boolean {
  const media = useMemo(() => window.matchMedia?.('(prefers-reduced-motion: reduce)'), []);
  const subscribe = useCallback(
    (notify: () => void) => {
      if (!media) return () => {};
      if (media.addEventListener) {
        media.addEventListener('change', notify);
        return () => media.removeEventListener('change', notify);
      }
      media.addListener(notify);
      return () => media.removeListener(notify);
    },
    [media],
  );
  const snapshot = useCallback(() => media?.matches ?? false, [media]);
  return useSyncExternalStore(subscribe, snapshot, () => false);
}
