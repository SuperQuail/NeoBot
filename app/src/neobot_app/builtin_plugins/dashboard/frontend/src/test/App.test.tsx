// 路由与侧栏回归测试 —— 一级导航、当前项高亮、工作区页隐藏全局头部
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { clearToken, setToken } from '../api/client';
import { authStatus } from '../api/client';

const mockAuthStatus = vi.mocked(authStatus);

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
vi.mock('../pages/Analysis.jsx', () => ({ default: () => <div data-testid="page-analysis" /> }));
vi.mock('../pages/Bots.jsx', () => ({ default: () => <div data-testid="page-bots" /> }));
vi.mock('../pages/Logs.jsx', () => ({ default: () => <div data-testid="page-logs" /> }));
vi.mock('../pages/Prompts.jsx', () => ({ default: () => <div data-testid="page-prompts" /> }));
vi.mock('../pages/ChatFlows.jsx', () => ({ default: () => <div data-testid="page-chat-flows" /> }));
vi.mock('../pages/ScheduledTasks.jsx', () => ({
  default: () => <div data-testid="page-scheduled-tasks" />,
}));
vi.mock('../pages/Archives.jsx', () => ({ default: () => <div data-testid="page-archives" /> }));

const NAV_LABELS = [
  '主页',
  '部署',
  '插件',
  '配置',
  '系统',
  '用量',
  '分析',
  '提示词',
  '聊天流',
  '定时',
  '档案',
  '机器人',
  '日志',
];

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
  // 默认「已配置密码」：绝大多数用例只关心路由与导航，不应被鉴权探测干扰。
  mockAuthStatus.mockReset();
  mockAuthStatus.mockResolvedValue({ configured: true, setup_required: false, setup_allowed: false });
});

describe('应用外壳', () => {
  it('侧栏渲染全部一级导航', () => {
    renderAt('/dashboard');

    for (const label of NAV_LABELS) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
    }
    expect(screen.getAllByRole('link')).toHaveLength(NAV_LABELS.length);
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

  it('分析路由渲染分析页并高亮侧栏', () => {
    renderAt('/analysis');

    expect(screen.getByTestId('page-analysis')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '分析' })).toHaveClass('active');
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

  it('未设置密码时带旧 token 打开控制台，自动落到设置密码页', async () => {
    // 回归：旧实现只看 localStorage 里有没有 token，于是一个服务端早就不认的
    // token 就能换到主界面；数据接口随后全 403，用户只能手动退出登录才走得出去。
    mockAuthStatus.mockResolvedValue({
      configured: false,
      setup_required: true,
      setup_allowed: true,
      loopback: true,
    });
    setToken('stale-token', 'stale-csrf');

    renderAt('/dashboard');

    expect(await screen.findByPlaceholderText('至少 8 个字符')).toBeInTheDocument();
    expect(screen.getByText('设置面板密码')).toBeInTheDocument();
    expect(screen.queryByTestId('page-dashboard')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '主页' })).not.toBeInTheDocument();
  });

  it('已设置密码时带 token 直接进主界面（不被鉴权探测拦住）', async () => {
    renderAt('/dashboard');

    expect(await screen.findByTestId('page-dashboard')).toBeInTheDocument();
    expect(mockAuthStatus).toHaveBeenCalled();
  });

  it('已设置密码但无 token 时仍跳登录页', async () => {
    // 注意：setToken('') 是空操作（内部有 if (token) 守卫），清会话要用 clearToken，
    // 与「退出登录」按钮走的是同一条路径。
    clearToken();

    renderAt('/dashboard');

    expect(await screen.findByPlaceholderText('请输入面板密码')).toBeInTheDocument();
    expect(screen.queryByTestId('page-dashboard')).not.toBeInTheDocument();
  });

  it('外网未设置密码时落到「仅本机可设置」提示页', async () => {
    mockAuthStatus.mockResolvedValue({
      configured: false,
      setup_required: true,
      setup_allowed: false,
      loopback: false,
    });
    setToken('stale-token', 'stale-csrf');

    renderAt('/dashboard');

    expect(await screen.findByText('尚未设置面板密码')).toBeInTheDocument();
    expect(screen.queryByTestId('page-dashboard')).not.toBeInTheDocument();
  });
});
