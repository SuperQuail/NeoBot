// 路由与侧栏回归测试 —— 一级导航、当前项高亮、统一页头与工作区滚动归属
import { describe, expect, it, beforeEach, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { apiSetup, clearToken, setToken } from '../api/client';
import { authStatus } from '../api/client';
import { clearQueries } from '../data/queryCore';

const mockAuthStatus = vi.mocked(authStatus);
const mockApiSetup = vi.mocked(apiSetup);

vi.mock('../api/client', async () => {
  const actual = await vi.importActual('../api/client');
  return {
    ...actual,
    // 登录页在未登录分支渲染，避免测试里发真实请求
    authStatus: vi.fn(async () => ({ configured: true, setup_required: false, setup_allowed: false })),
    apiLogin: vi.fn(async () => ({ ok: false, error: '测试不发起真实登录' })),
    apiSetup: vi.fn(async () => ({ ok: false, error: '测试不发起真实设置' })),
  };
});

vi.mock('../api/endpoints', async () => {
  const actual = await vi.importActual<typeof import('../api/endpoints')>('../api/endpoints');
  return {
    ...actual,
    api: {
      ...actual.api,
      extensions: vi.fn(async () => ({ items: [] })),
      powerStatus: vi.fn(async () => null),
    },
  };
});

vi.mock('../pages/Dashboard', () => ({ default: () => <div data-testid="page-dashboard" /> }));
vi.mock('../pages/Plugins', () => ({ default: () => <div data-testid="page-plugins" /> }));
vi.mock('../pages/ConfigManager', () => ({ default: () => <div data-testid="page-config" /> }));
vi.mock('../pages/System', () => ({ default: () => <div data-testid="page-system" /> }));
vi.mock('../pages/Usage', () => ({ default: () => <div data-testid="page-usage" /> }));
vi.mock('../pages/Analysis', () => ({ default: () => <div data-testid="page-analysis" /> }));
vi.mock('../pages/Bots', () => ({ default: () => <div data-testid="page-bots" /> }));
vi.mock('../pages/Deploy', () => ({ default: () => <div data-testid="page-deploy" /> }));
vi.mock('../pages/Logs', () => ({ default: () => <div data-testid="page-logs" /> }));
vi.mock('../pages/Prompts', () => ({ default: () => <div data-testid="page-prompts" /> }));
vi.mock('../pages/ChatFlows', () => ({ default: () => <div data-testid="page-chat-flows" /> }));
vi.mock('../pages/ScheduledTasks', () => ({
  default: () => <div data-testid="page-scheduled-tasks" />,
}));
vi.mock('../pages/Archives', () => ({ default: () => <div data-testid="page-archives" /> }));

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
  clearQueries();
  setToken('test-token', 'test-csrf');
  document.documentElement.dataset.theme = 'light';
  // 默认「已配置密码」：绝大多数用例只关心路由与导航，不应被鉴权探测干扰。
  mockAuthStatus.mockReset();
  mockAuthStatus.mockResolvedValue({ configured: true, setup_required: false, setup_allowed: false });
});

describe('应用外壳', () => {
  it('侧栏渲染全部一级导航', async () => {
    renderAt('/dashboard');
    await screen.findByTestId('page-dashboard');

    for (const label of NAV_LABELS) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
      expect(screen.getByRole('link', { name: label })).toHaveClass('nav-item');
    }
    expect(within(screen.getByRole('navigation', { name: '主导航' })).getAllByRole('link')).toHaveLength(
      NAV_LABELS.length,
    );
  });

  it('非工作区页面渲染全局头部与面包屑', async () => {
    renderAt('/scheduled-tasks');
    await screen.findByTestId('page-scheduled-tasks');

    expect(screen.getByText('NeoBot 面板')).toBeInTheDocument();
    expect(within(screen.getByLabelText('当前位置')).getByText('定时任务')).toBeInTheDocument();
    expect(screen.getByRole('main')).not.toHaveClass('content--viewport');
  });

  it.each(['/scheduled-tasks/', '/SCHEDULED-TASKS', '/scheduled%2Dtasks'])(
    '路径 %s 的布局元信息与 Router 的匹配规则一致',
    async (path) => {
      renderAt(path);
      await screen.findByTestId('page-scheduled-tasks');
      expect(within(screen.getByLabelText('当前位置')).getByText('定时任务')).toBeInTheDocument();
      expect(screen.getByRole('main')).not.toHaveClass('content--viewport');
      expect(screen.getByRole('link', { name: '定时' })).toHaveClass('active');
    },
  );

  it.each([
    ['/dashboard', 'dashboard', '仪表盘'],
    ['/bots', 'bots', '机器人'],
    ['/deploy', 'deploy', '快捷部署'],
    ['/config', 'config', '配置管理'],
    ['/plugins', 'plugins', '插件管理'],
    ['/prompts', 'prompts', '提示词模板'],
    ['/chat-flows', 'chat-flows', '聊天流'],
    ['/archives', 'archives', '档案管理'],
    ['/logs', 'logs', '日志'],
    ['/usage', 'usage', '用量统计'],
    ['/analysis', 'analysis', '提示词分析'],
    ['/system', 'system', '系统状态'],
  ])('工作区 %s 保留统一页头并由内部区域滚动', async (route, page, title) => {
    renderAt(route);
    expect(await screen.findByTestId(`page-${page}`)).toBeInTheDocument();
    expect(screen.getByText('NeoBot 面板')).toBeInTheDocument();
    expect(within(screen.getByLabelText('当前位置')).getByText(title)).toBeInTheDocument();
    expect(screen.getByRole('main')).toHaveClass('content--viewport');
  });

  it('配置忙碌时阻止侧栏离开，干净状态允许离开', async () => {
    renderAt('/config');
    await screen.findByTestId('page-config');
    window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: { dirty: false, busy: true } }));
    fireEvent.click(screen.getByRole('link', { name: '系统' }));
    expect(screen.getByTestId('page-config')).toBeInTheDocument();
    window.dispatchEvent(
      new CustomEvent('dashboard-editor-state', { detail: { dirty: false, busy: false } }),
    );
    fireEvent.click(screen.getByRole('link', { name: '系统' }));
    expect(await screen.findByTestId('page-system')).toBeInTheDocument();
  });

  it('未保存修改离开侧栏需要确认', async () => {
    renderAt('/config');
    await screen.findByTestId('page-config');
    window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: { dirty: true, busy: false } }));
    fireEvent.click(screen.getByRole('link', { name: '系统' }));
    const dialog = await screen.findByRole('dialog', { name: '放弃未保存的修改？' });
    fireEvent.click(within(dialog).getByRole('button', { name: '取消' }));
    expect(screen.getByTestId('page-config')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('link', { name: '系统' }));
    fireEvent.click(await screen.findByRole('button', { name: '放弃并离开' }));
    expect(await screen.findByTestId('page-system')).toBeInTheDocument();
  });

  it('跳到主内容只移动焦点，保留配置路由', async () => {
    renderAt('/config');
    await screen.findByTestId('page-config');
    expect(fireEvent.click(screen.getByRole('link', { name: '跳到主内容' }))).toBe(false);
    expect(screen.getByRole('main')).toHaveFocus();
    expect(screen.getByTestId('page-config')).toBeInTheDocument();
  });

  it('折叠侧栏保留所有导航并持久化偏好', async () => {
    renderAt('/dashboard');
    await screen.findByTestId('page-dashboard');
    fireEvent.click(screen.getByRole('button', { name: '收起侧栏' }));
    expect(localStorage.getItem('neobot-dashboard-sidebar')).toBe('collapsed');
    expect(screen.getByRole('button', { name: '展开侧栏' })).toBeInTheDocument();
    for (const label of NAV_LABELS) expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
  });

  it('分析路由渲染分析页并高亮侧栏', async () => {
    renderAt('/analysis');

    expect(await screen.findByTestId('page-analysis')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '分析' })).toHaveClass('active');
  });

  it('未知路由回落到仪表盘', async () => {
    renderAt('/not-a-page');

    expect(await screen.findByTestId('page-dashboard')).toBeInTheDocument();
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
    expect(screen.getByRole('heading', { name: '设置面板密码' })).toBeInTheDocument();
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

describe('首次设置密码后的跳转（issue #78）', () => {
  it('设置成功后直接进入仪表盘，不再被弹回登录页', async () => {
    clearToken();
    // 服务端状态：设置密码之前 configured=false，设置成功之后才变 true。
    // 用可变状态而不是「第 N 次调用」来模拟，避免依赖探测次数。
    let configured = false;
    const status = () => ({
      configured,
      authenticated: configured,
      setup_required: !configured,
      setup_allowed: true,
      loopback: true,
    });
    mockAuthStatus.mockImplementation(async () => status() as never);
    mockApiSetup.mockImplementation(async () => {
      configured = true;
      return { ok: true, token: 'new-token', csrf: 'new-csrf' } as never;
    });

    renderAt('/login');

    const password = await screen.findByPlaceholderText('至少 8 个字符');
    fireEvent.change(password, { target: { value: 'password123' } });
    fireEvent.change(screen.getByPlaceholderText('再次输入新密码'), { target: { value: 'password123' } });
    fireEvent.click(screen.getByRole('button', { name: '设置面板密码' }));

    // 修复前：RequireAuth 仍按挂载时的旧探测（setupRequired=true）弹回 /login，
    // 两个 replace 跳转来回 → 这里永远等不到仪表盘。
    expect(await screen.findByTestId('page-dashboard')).toBeInTheDocument();
    expect(screen.queryByPlaceholderText('至少 8 个字符')).not.toBeInTheDocument();
  });
});
