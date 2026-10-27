import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import AuthProvider from '../auth/AuthProvider';
import { useAuthGate } from '../auth/AuthContext';
import { authStatus, type AuthStatus } from '../api/client';

vi.mock('../api/client', () => ({ authStatus: vi.fn() }));
const probe = vi.mocked(authStatus);

beforeEach(() => probe.mockReset());

it('显式刷新完成后，较慢的启动探测不能覆盖新的配置与权限状态', async () => {
  let finish!: (status: AuthStatus) => void;
  probe.mockReturnValueOnce(
    new Promise<AuthStatus>((resolve) => {
      finish = resolve;
    }),
  );
  probe.mockResolvedValueOnce({ configured: true, can_manage: false });
  const { result } = renderHook(useAuthGate, { wrapper: AuthProvider });
  await waitFor(() => expect(probe).toHaveBeenCalledTimes(1));
  await act(async () => {
    await result.current.refresh();
  });
  expect(result.current).toMatchObject({ setupRequired: false, canManage: false });
  await act(async () => {
    finish({ configured: false, can_manage: true });
  });
  expect(result.current).toMatchObject({ setupRequired: false, canManage: false });
});

it('探测失败保留登录兜底与未知权限，后续刷新可恢复', async () => {
  probe.mockRejectedValueOnce(new Error('连接失败'));
  const { result } = renderHook(useAuthGate, { wrapper: AuthProvider });
  await waitFor(() => expect(result.current.setupRequired).toBe(false));
  expect(result.current.canManage).toBeNull();
  probe.mockResolvedValueOnce({ configured: true, can_manage: true });
  await act(async () => {
    await result.current.refresh();
  });
  expect(result.current.canManage).toBe(true);
});
