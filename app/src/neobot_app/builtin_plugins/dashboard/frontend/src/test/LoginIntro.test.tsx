import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { gsap } from 'gsap';
import Login from '../pages/Login';
import { mockReducedEffects } from './mediaPreference';

vi.mock('../api/client', () => ({
  authStatus: vi.fn(async () => ({ configured: true, authenticated: false })),
  checkAuth: vi.fn(async () => false),
  getToken: vi.fn(() => null),
  setToken: vi.fn(),
  apiLogin: vi.fn(),
  apiSetup: vi.fn(),
}));
vi.mock('../auth/AuthContext', () => ({ useAuthGate: () => ({ refresh: vi.fn() }) }));

let preference: ReturnType<typeof mockReducedEffects>;
afterEach(() => preference?.restore());

function mountLogin() {
  const view = render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>,
  );
  const card = view.container.querySelector<HTMLFormElement>('.login-card');
  if (!card) throw new Error('登录表单未挂载');
  // jsdom 没有布局，offsetParent 恒为 null。GSAP CSSPlugin 的变换测量会将
  // 无布局目标临时搬到 documentElement，导致表单内焦点丢失；这里模拟可见表单。
  vi.spyOn(card, 'offsetParent', 'get').mockImplementation(() => card.parentElement);
  return view;
}

describe('登录开场与表单', () => {
  it('开场期间保留可操作表单，离开页面后停止所有叠字动画', async () => {
    const user = userEvent.setup();
    preference = mockReducedEffects(false);
    const view = mountLogin();
    await screen.findByRole('button', { name: '登录工作台' });
    const letters = Array.from(view.container.querySelectorAll('[data-login-letter]'));
    expect(gsap.getTweensOf(letters).length).toBeGreaterThan(0);
    const input = screen.getByLabelText('面板密码');
    await user.type(input, '输入中的草稿');
    // 等待受控输入提交更新，再检查完整内容与焦点。
    await waitFor(() => expect(input).toHaveValue('输入中的草稿'));
    expect(input).toHaveFocus();
    expect(screen.getByRole('button', { name: '登录工作台' })).toBeEnabled();
    view.unmount();
    expect(gsap.getTweensOf(letters)).toHaveLength(0);
  });

  it('减少动态效果时直接显示三行构图，品牌只朗读一次', async () => {
    preference = mockReducedEffects(true);
    const view = mountLogin();
    await screen.findByRole('button', { name: '登录工作台' });
    expect(screen.getAllByRole('heading', { name: 'NEOBOT' })).toHaveLength(1);
    expect(view.container.querySelectorAll('[data-login-row]')).toHaveLength(3);
    expect(view.container.querySelector('.login-wordmark')).not.toBeInTheDocument();
    expect(gsap.getTweensOf(view.container.querySelectorAll('[data-login-letter]'))).toHaveLength(0);
    expect(view.container.querySelector('.login-card')).not.toHaveStyle({ opacity: '0' });
  });

  it('途中启用减少动态效果会立即归还样式，并保留已输入内容与焦点', async () => {
    const user = userEvent.setup();
    preference = mockReducedEffects(false);
    const view = mountLogin();
    await screen.findByRole('button', { name: '登录工作台' });
    const input = screen.getByLabelText('面板密码');
    await user.type(input, '尚未提交的内容');
    await waitFor(() => expect(input).toHaveValue('尚未提交的内容'));
    expect(input).toHaveFocus();
    act(() => preference.set(true));
    expect(input).toHaveValue('尚未提交的内容');
    expect(input).toHaveFocus();
    expect(gsap.getTweensOf(view.container.querySelectorAll('[data-login-letter]'))).toHaveLength(0);
    expect(view.container.querySelector('.login-card')).not.toHaveStyle({ opacity: '0' });
    expect(view.container.querySelector('.login-brand-panel')).not.toHaveStyle({
      clipPath: 'inset(0 100% 0 0 round 18px)',
    });
  });
});
