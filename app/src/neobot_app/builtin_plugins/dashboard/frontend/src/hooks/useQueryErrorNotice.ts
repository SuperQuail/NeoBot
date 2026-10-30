import { useEffect, useRef } from 'react';
import { infoBar } from '../notifications/infoBar';

/** 轮询会暂时清空 error；同一失败只通知一次，成功读取后才开始新的通知周期。 */
export function useQueryErrorNotice(error: string | null, updatedAt: number, title: string, enabled = true) {
  const previous = useRef({ error: '', updatedAt: 0 });
  useEffect(() => {
    if (!enabled) return;
    if (previous.current.updatedAt !== updatedAt) previous.current = { error: '', updatedAt };
    if (!error || previous.current.error === error) return;
    previous.current.error = error;
    infoBar({ title, message: error, tone: 'err' });
  }, [error, updatedAt, title, enabled]);
}
