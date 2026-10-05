import { Routes, Route, Navigate } from 'react-router-dom';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactElement } from 'react';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import Dashboard from './pages/Dashboard';
import Deploy from './pages/Deploy';
import Plugins from './pages/Plugins';
import ConfigManager from './pages/ConfigManager';
import System from './pages/System';
import Usage from './pages/Usage';
import Analysis from './pages/Analysis';
import Prompts from './pages/Prompts';
import ChatFlows from './pages/ChatFlows';
import ScheduledTasks from './pages/ScheduledTasks';
import Archives from './pages/Archives';
import Bots from './pages/Bots';
import Logs from './pages/Logs';
import Login from './pages/Login';
import { authStatus, getToken } from './api/client';
import type { AuthStatus } from './api/client';

interface AuthGate {
  /** 面板是否需要先设置密码；null = 尚未问到（启动中或接口失败）。 */
  setupRequired: boolean | null;
  /** 重新探测。**改变了「面板是否已配置」的动作之后必须调用** —— 见 issue #78。 */
  refresh: () => Promise<void>;
}

/** 本地 token 不能替代「面板到底配没配密码」这个事实，所以问服务端；结果可刷新。 */
const SetupRequiredContext = createContext<AuthGate>({
  setupRequired: null,
  refresh: async () => {},
});

/** 供登录页等消费者读取 / 刷新探测结果。 */
export function useAuthGate(): AuthGate {
  return useContext(SetupRequiredContext);
}

function AuthStatusProvider({ children }: { children: ReactElement }) {
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null);

  const refresh = useCallback(async () => {
    try {
      const status: AuthStatus | null = await authStatus();
      // 接口失败（null）按「已配置」处理：沿用原有的 401 兜底跳登录，
      // 不能因为一次探测失败就把整个面板挡在门外。
      setSetupRequired(status?.configured === false);
    } catch {
      setSetupRequired(false);
    }
  }, []);

  // 挂载时探一次；之后的失效由调用方负责（设置密码成功、登出等）
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value = useMemo(() => ({ setupRequired, refresh }), [setupRequired, refresh]);
  return <SetupRequiredContext.Provider value={value}>{children}</SetupRequiredContext.Provider>;
}

function RequireAuth({ children }: { children: ReactElement }) {
  const { setupRequired } = useContext(SetupRequiredContext);

  if (!getToken()) return <Navigate to="/login" replace />;
  // 服务端说「还没设密码」，本地却留着上一轮会话的 token：那个 token 服务端早就不认了，
  // 放行只会得到一个「看起来登录了、数据接口全 403」的半死界面。直接送去设置密码页。
  if (setupRequired === true) return <Navigate to="/login" replace />;

  return children;
}

export default function App() {
  return (
    // 路由级错误边界：任一页面渲染异常都给出可恢复界面，而不是整片白屏
    <ErrorBoundary>
      <AuthStatusProvider>
        <Routes>
          <Route path="login" element={<Login />} />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="dashboard" element={<Dashboard />} />
        <Route path="deploy" element={<Deploy />} />
            <Route path="plugins" element={<Plugins />} />
            <Route path="config" element={<ConfigManager />} />
            <Route path="system" element={<System />} />
            <Route path="usage" element={<Usage />} />
            <Route path="analysis" element={<Analysis />} />
            <Route path="prompts" element={<Prompts />} />
            <Route path="chat-flows" element={<ChatFlows />} />
            <Route path="scheduled-tasks" element={<ScheduledTasks />} />
            <Route path="archives" element={<Archives />} />
            <Route path="bots" element={<Bots />} />
            <Route path="logs" element={<Logs />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Route>
        </Routes>
      </AuthStatusProvider>
    </ErrorBoundary>
  );
}
