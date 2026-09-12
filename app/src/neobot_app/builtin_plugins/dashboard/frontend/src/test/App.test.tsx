// 路由与侧栏回归测试 —— 一级导航、当前项高亮、工作区页隐藏全局头部
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { setToken } from '../api/client';

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
});
