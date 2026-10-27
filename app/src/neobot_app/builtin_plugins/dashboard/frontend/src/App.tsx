import { Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import { ConfirmHost } from './components/ui/ConfirmDialog';
import { MotionProvider } from './components/ui/PageMotion';
import PageSkeleton from './components/ui/PageSkeleton';
import AuthProvider from './auth/AuthProvider';
import RequireAuth from './auth/RequireAuth';
import { PAGE_ROUTES } from './app/routes';

const Login = lazy(() => import('./pages/Login'));

export default function App() {
  return (
    // 路由级错误边界：任一页面渲染异常都给出可恢复界面，而不是整片白屏
    <MotionProvider>
      <ErrorBoundary>
        <AuthProvider>
          <Routes>
            <Route
              path="login"
              element={
                <Suspense fallback={<PageSkeleton kind="workspace" label="正在读取登录页" />}>
                  <Login />
                </Suspense>
              }
            />
            <Route
              element={
                <RequireAuth>
                  <Layout />
                </RequireAuth>
              }
            >
              <Route index element={<Navigate to="/dashboard" replace />} />
              {PAGE_ROUTES.map(({ path, component: Page }) => (
                <Route key={path} path={path.slice(1)} element={<Page />} />
              ))}
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Route>
          </Routes>
        </AuthProvider>
        <ConfirmHost />
      </ErrorBoundary>
    </MotionProvider>
  );
}
