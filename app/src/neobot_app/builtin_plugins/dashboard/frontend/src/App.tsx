import { Routes, Route, Navigate } from 'react-router-dom';
import type { ReactElement } from 'react';
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

function RequireAuth({ children }: { children: ReactElement }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return children;
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
      </Routes>
    </ErrorBoundary>
  );
}
