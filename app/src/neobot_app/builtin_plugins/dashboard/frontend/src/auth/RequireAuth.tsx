import type { ReactElement } from 'react';
import { Navigate } from 'react-router-dom';
import { getToken } from '../api/client';
import { useAuthGate } from './AuthContext';

export default function RequireAuth({ children }: { children: ReactElement }) {
  const { setupRequired } = useAuthGate();
  // 首次设置前的旧 token 已失效，不放行到一个所有数据接口都被拒绝的空壳。
  if (!getToken() || setupRequired === true) return <Navigate to="/login" replace />;
  return children;
}
