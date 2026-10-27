import { useState } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import PasswordSettings, { ChangePasswordDialog } from '../components/PasswordSettings';
import { MotionProvider } from '../components/ui/PageMotion';
import { infoBar } from '../notifications/infoBar';
import { api } from '../api/endpoints';
import { getCsrf, getToken, setToken } from '../api/client';
import { clearQueries, getQuerySnapshot, setQueryData } from '../data/queryCore';
import { mockReducedEffects } from './mediaPreference';

const auth = vi.hoisted(() => ({ canManage: true as boolean | null }));
vi.mock('../auth/AuthContext', () => ({ useAuthGate: () => auth }));
vi.mock('../api/endpoints', () => ({ api: { changePassword: vi.fn() } }));
vi.mock('../notifications/infoBar', () => ({ infoBar: vi.fn() }));

const NEXT_PASSWORD = 'Next-Password-2026';
const success = { ok: true, status: 200, error: null, data: { reauthenticate: true } };
let preference: ReturnType<typeof mockReducedEffects>;

function LoginDestination() {
  const location = useLocation();
  return <h1>请重新登录 {location.search}</h1>;
}

function Example({
  initiallyOpen = true,
  beforeOpen,
}: {
  initiallyOpen?: boolean;
  beforeOpen?: () => Promise<boolean>;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  const [sidebar, setSidebar] = useState(true);
  return (
    <>
      {sidebar && (
        <PasswordSettings
          beforeOpen={beforeOpen}
          onOpen={() => {
            setSidebar(false);
            setOpen(true);
          }}
        />
      )}
      <ChangePasswordDialog
        open={open}
        onClose={() => {
          setOpen(false);
          setSidebar(true);
        }}
      />
    </>
  );
}

function renderSettings(props: Parameters<typeof Example>[0] = {}) {
  return render(
    <MemoryRouter initialEntries={['/config']}>
      <MotionProvider>
        <Routes>
          <Route path="/config" element={<Example {...props} />} />
          <Route path="/login" element={<LoginDestination />} />
        </Routes>
      </MotionProvider>
    </MemoryRouter>,
  );
}

async function fillPasswords(next = NEXT_PASSWORD, confirm = next) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText('当前密码'), 'Original-Password-2026');
  await user.type(screen.getByLabelText('新密码', { exact: true }), next);
  await user.type(screen.getByLabelText('确认新密码'), confirm);
  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
  clearQueries();
  auth.canManage = true;
  preference = mockReducedEffects(true);
  setToken('old-session', 'old-csrf');
  vi.mocked(api.changePassword).mockResolvedValue(success);
});
afterEach(() => preference.restore());

describe('PasswordSettings', () => {
  it.each([false, null])('没有确认管理权限 (%s) 时按钮不可用', (permission) => {
    auth.canManage = permission;
    renderSettings({ initiallyOpen: false });
    expect(screen.getByRole('button', { name: '修改密码' })).toBeDisabled();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(api.changePassword).not.toHaveBeenCalled();
  });

  it('先确认页面草稿；拒绝不打开，允许后关闭侧栏仍保留弹窗', async () => {
    const user = userEvent.setup();
    const beforeOpen = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    renderSettings({ initiallyOpen: false, beforeOpen });
    await user.click(screen.getByRole('button', { name: '修改密码' }));
    expect(beforeOpen).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '修改密码' }));
    expect(screen.getByRole('dialog', { name: '修改面板密码' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '修改密码' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('当前密码')).toHaveFocus();
  });

  it.each([
    ['short', 'short', '新密码须为 8–128 个字符'],
    [NEXT_PASSWORD, 'Different-Password-2026', '两次输入的新密码不一致'],
    ['!'.repeat(8), '!'.repeat(8), '密码至少包含一个字母或数字'],
    [' Next-Password-2026', ' Next-Password-2026', '密码首尾不能包含空白字符'],
  ])('在对应字段校验新密码 (%s)，不发起请求', async (next, confirm, message) => {
    renderSettings();
    const user = await fillPasswords(next, confirm);
    await user.click(screen.getByRole('button', { name: '修改并重新登录' }));
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(api.changePassword).not.toHaveBeenCalled();
    expect(infoBar).not.toHaveBeenCalled();
    expect(getToken()).toBe('old-session');
  });

  it('当前密码错误通过 InfoBar 反馈，输入内容和会话不丢失', async () => {
    vi.mocked(api.changePassword).mockResolvedValue({
      ok: false,
      status: 403,
      error: '当前密码不正确',
      data: null,
    });
    renderSettings();
    const user = await fillPasswords();
    await user.click(screen.getByRole('button', { name: '修改并重新登录' }));
    await waitFor(() =>
      expect(infoBar).toHaveBeenCalledWith({ title: '密码未修改', tone: 'err', message: '当前密码不正确' }),
    );
    expect(screen.getByLabelText('当前密码')).toHaveValue('Original-Password-2026');
    expect(screen.getByLabelText('新密码', { exact: true })).toHaveValue(NEXT_PASSWORD);
    expect(screen.getByLabelText('确认新密码')).toHaveValue(NEXT_PASSWORD);
    expect(getToken()).toBe('old-session');
    expect(getCsrf()).toBe('old-csrf');
    expect(screen.getByRole('button', { name: '修改并重新登录' })).toBeEnabled();
  });

  it('没有收到 HTTP 响应时不假定密码未变，保留输入和会话', async () => {
    vi.mocked(api.changePassword).mockResolvedValue({
      ok: false,
      status: 0,
      error: 'Network error',
      data: null,
    });
    renderSettings();
    const user = await fillPasswords();
    await user.click(screen.getByRole('button', { name: '修改并重新登录' }));
    await waitFor(() =>
      expect(infoBar).toHaveBeenCalledWith({
        title: '未能确认改密结果',
        tone: 'err',
        message: '连接失败，请稍后重试。',
      }),
    );
    expect(screen.getByLabelText('新密码', { exact: true })).toHaveValue(NEXT_PASSWORD);
    expect(getToken()).toBe('old-session');
  });

  it('请求期间锁定字段、取消和关闭，重复提交只发送一次；成功清会话和缓存', async () => {
    let resolve!: (value: typeof success) => void;
    vi.mocked(api.changePassword).mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    setQueryData('private-config', { secret: 'cached-only-test-value' });
    renderSettings();
    const user = await fillPasswords();
    await user.click(screen.getByRole('button', { name: '修改并重新登录' }));
    expect(screen.getByRole('button', { name: '修改中…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '取消' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '关闭对话框' })).toBeDisabled();
    expect(screen.getByLabelText('当前密码')).toBeDisabled();
    fireEvent.submit(screen.getByLabelText('当前密码').closest('form')!);
    await user.keyboard('{Escape}');
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(api.changePassword).toHaveBeenCalledTimes(1);
    expect(api.changePassword).toHaveBeenCalledWith({
      current_password: 'Original-Password-2026',
      new_password: NEXT_PASSWORD,
      confirm: NEXT_PASSWORD,
    });
    await act(async () => resolve(success));
    expect(
      await screen.findByRole('heading', { name: '请重新登录 ?reason=password-changed' }),
    ).toBeInTheDocument();
    expect(getToken()).toBe('');
    expect(getCsrf()).toBe('');
    expect(getQuerySnapshot('private-config').data).toBeNull();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('网络失败保留草稿，取消并再次打开后不保留密码', async () => {
    vi.mocked(api.changePassword).mockRejectedValue(new Error('offline'));
    renderSettings();
    const user = await fillPasswords();
    await user.click(screen.getByRole('button', { name: '修改并重新登录' }));
    await waitFor(() =>
      expect(infoBar).toHaveBeenCalledWith(
        expect.objectContaining({ title: '未能确认改密结果', tone: 'err' }),
      ),
    );
    expect(screen.getByLabelText('新密码', { exact: true })).toHaveValue(NEXT_PASSWORD);
    expect(getToken()).toBe('old-session');
    await user.click(screen.getByRole('button', { name: '取消' }));
    await user.click(screen.getByRole('button', { name: '修改密码' }));
    expect(screen.getByLabelText('当前密码')).toHaveValue('');
    expect(screen.getByLabelText('新密码', { exact: true })).toHaveValue('');
    expect(screen.getByLabelText('确认新密码')).toHaveValue('');
  });

  it('弹窗内管理权限失效时无法提交', () => {
    auth.canManage = false;
    renderSettings();
    expect(screen.getByRole('button', { name: '修改并重新登录' })).toBeDisabled();
    fireEvent.submit(screen.getByLabelText('当前密码').closest('form')!);
    expect(api.changePassword).not.toHaveBeenCalled();
  });
});
