import { createContext, useContext } from 'react';

export interface AuthGate {
  canManage: boolean | null;
  /** null 表示尚未完成探测；本地 token 不能替代服务端密码配置状态。 */
  setupRequired: boolean | null;
  /** 设置密码、登录或退出后刷新服务端状态。 */
  refresh: () => Promise<void>;
}

export const AuthContext = createContext<AuthGate>({
  canManage: null,
  setupRequired: null,
  refresh: async () => {},
});

export function useAuthGate(): AuthGate {
  return useContext(AuthContext);
}
