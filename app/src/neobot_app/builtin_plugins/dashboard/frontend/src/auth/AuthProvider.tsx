import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { authStatus, type AuthStatus } from '../api/client';
import { AuthContext } from './AuthContext';

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null);
  const [canManage, setCanManage] = useState<boolean | null>(null);
  const request = useRef(0);

  const refresh = useCallback(async () => {
    const ticket = ++request.current;
    // 探测失败时保留原来的 401 登录兜底，不能把整个面板挡在门外。
    let status: AuthStatus | null = null;
    try {
      status = await authStatus();
    } catch {
      // 网络与解析错误沿用下方的未确定权限状态。
    }
    if (ticket !== request.current) return;
    setSetupRequired(status?.configured === false);
    setCanManage(typeof status?.can_manage === 'boolean' ? status.can_manage : null);
  }, []);

  useEffect(() => {
    const pending = request;
    void refresh();
    return () => {
      pending.current++;
    };
  }, [refresh]);

  const value = useMemo(() => ({ setupRequired, canManage, refresh }), [setupRequired, canManage, refresh]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
