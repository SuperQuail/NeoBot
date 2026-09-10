// 路由与侧栏回归测试 —— 8 条一级导航（含舰桥）、当前项高亮、工作区页隐藏全局头部
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { clearToken, setToken } from '../api/client';

vi.mock('../api/client.js', async () => {
  const actual = await vi.importActual('../api/client.js');
  return {
    ...actual,
    // 登录页在未登录分支渲染，避免测试里发真实请求
    authStatus: vi.fn(async () => ({ configured: true, setup_required: false, setup_allowed: false })),
    apiLogin: vi.fn(async () => ({ ok: false, error: '测试不发起真实登录' })),
    apiSetup: vi.fn(async () => ({ ok: false, error: '测试不发起真实设置' })),
  };
});

vi.mock('../pages/Dashboard.jsx', () => ({ default: () => <div data-testid="page-dashboard" /> }));
vi.mock('../pages/Plugins.jsx', () => ({ default: () => <div data-testid="page-plugins" /> }));
vi.mock('../pages/ConfigManager.jsx', () => ({ default: () => <div data-testid="page-config" /> }));
vi.mock('../pages/System.jsx', () => ({ default: () => <div data-testid="page-system" /> }));
vi.mock('../pages/Usage.jsx', () => ({ default: () => <div data-testid="page-usage" /> }));
vi.mock('../pages/Bots.jsx', () => ({ default: () => <div data-testid="page-bots" /> }));
vi.mock('../pages/Logs.jsx', () => ({ default: () => <div data-testid="page-logs" /> }));
// 3D 舰桥是懒加载路由：测试里替换成占位组件，避免在 jsdom 里初始化 WebGL
vi.mock('../bridge/bridge.jsx', () => ({ default: () => <div data-testid="page-bridge" /> }));

const NAV_LABELS = ['舰桥', '主页', '插件', '配置', '系统', '用量', '机器人', '日志'];

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  setToken('test-token', 'test-csrf');
  document.documentElement.dataset.theme = 'light';
});

describe('应用外壳', () => {
  it('侧栏固定渲染 8 条一级导航（舰桥 + 7 个经典面板）', () => {
    renderAt('/dashboard');

    for (const label of NAV_LABELS) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
    }
    expect(screen.getAllByRole('link')).toHaveLength(NAV_LABELS.length);
  });

  it('舰桥路由渲染 3D 控制台且不套经典面板的侧栏', async () => {
    renderAt('/bridge');

    expect(await screen.findByTestId('page-bridge')).toBeInTheDocument();
    // 舰桥是整屏场景，不能出现经典面板的页头
    expect(screen.queryByText('NeoBot 面板')).not.toBeInTheDocument();
  });

  it('未登录访问舰桥会被鉴权拦截', async () => {
    // 注意：setToken('') 是空操作（实现里对空值直接 return），登出必须用 clearToken
    clearToken();
    render(
      <MemoryRouter initialEntries={['/bridge']}>
        <App />
      </MemoryRouter>,
    );

    // 未登录时 RequireAuth 会重定向到登录页，舰桥内容不应挂载
    await waitFor(() => {
      expect(screen.queryByTestId('page-bridge')).not.toBeInTheDocument();
    });
    expect(await screen.findByPlaceholderText('请输入面板密码')).toBeInTheDocument();
  });

  it('非工作区页面渲染全局头部与面包屑', () => {
    renderAt('/system');

    expect(screen.getByText('NeoBot 面板')).toBeInTheDocument();
    expect(screen.getByText('系统状态')).toBeInTheDocument();
  });

  it('工作区页面（配置）不渲染全局头部', () => {
    renderAt('/config');

    expect(screen.queryByText('NeoBot 面板')).not.toBeInTheDocument();
    expect(screen.getByTestId('page-config')).toBeInTheDocument();
  });

  it('配置忙碌时阻止侧栏离开，干净状态允许离开', () => {
    renderAt('/config');
    window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: { dirty: false, busy: true } }));
    fireEvent.click(screen.getByRole('link', { name: '系统' }));
    expect(screen.getByTestId('page-config')).toBeInTheDocument();
    window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: { dirty: false, busy: false } }));
    fireEvent.click(screen.getByRole('link', { name: '系统' }));
    expect(screen.getByTestId('page-system')).toBeInTheDocument();
  });

  it('未保存修改离开侧栏需要确认', () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderAt('/config');
    window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: { dirty: true, busy: false } }));
    fireEvent.click(screen.getByRole('link', { name: '系统' }));
    expect(confirm).toHaveBeenCalledOnce();
    expect(screen.getByTestId('page-config')).toBeInTheDocument();
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getByRole('link', { name: '系统' }));
    expect(screen.getByTestId('page-system')).toBeInTheDocument();
    confirm.mockRestore();
  });

  it('未知路由回落到仪表盘', () => {
    renderAt('/not-a-page');

    expect(screen.getByTestId('page-dashboard')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '主页' })).toHaveClass('active');
  });

  it('未登录时跳转登录页', async () => {
    setToken('');
    render(
      <MemoryRouter initialEntries={['/login']}>
        <App />
      </MemoryRouter>,
    );

    expect(await screen.findByPlaceholderText('请输入面板密码')).toBeInTheDocument();
  });
});
