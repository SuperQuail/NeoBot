import { Routes, Route, Navigate } from 'react-router-dom';
import { Suspense, lazy, type ReactElement } from 'react';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import Dashboard from './pages/Dashboard';
import Plugins from './pages/Plugins';
import ConfigManager from './pages/ConfigManager';
import System from './pages/System';
import Usage from './pages/Usage';
import Bots from './pages/Bots';
import Logs from './pages/Logs';
import Login from './pages/Login';
import { getToken } from './api/client';

// 3D 舰载控制台：three.js 体积较大，按路由懒加载，经典 2D 面板的首屏体积不受影响。
const Bridge = lazy(() => import('./bridge/bridge'));

function RequireAuth({ children }: { children: ReactElement }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return children;
}

/** 懒加载期间的舰载风格等待态（不用 spinner，避免和全息风格冲突） */
function BridgeLoading() {
  return (
    <div className="bridge-loading" role="status">
      <span className="bridge-loading-code">NEOBOT // BRIDGE OS</span>
      <p>正在装载舰内场景…</p>
    </div>
  );
}

export default function App() {
  return (
    // 路由级错误边界：任一页面渲染异常都给出可恢复界面，而不是整片白屏
    <ErrorBoundary>
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
          <Route path="plugins" element={<Plugins />} />
          <Route path="config" element={<ConfigManager />} />
          <Route path="system" element={<System />} />
          <Route path="usage" element={<Usage />} />
          <Route path="bots" element={<Bots />} />
          <Route path="logs" element={<Logs />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
        {/* 舰桥独立于 Layout：3D 场景需要整屏，不套侧栏与页头 */}
        <Route
          path="bridge"
          element={
            <RequireAuth>
              <Suspense fallback={<BridgeLoading />}>
                <Bridge />
              </Suspense>
            </RequireAuth>
          }
        />
      </Routes>
    </ErrorBoundary>
  );
}
