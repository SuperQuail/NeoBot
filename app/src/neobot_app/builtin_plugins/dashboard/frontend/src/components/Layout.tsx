import { Link, NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useLayoutEffect, useRef } from 'react';
import { Home, LogOut, Package, Moon, ScrollText, Settings, BarChart3, Bot, Cpu, Rocket } from 'lucide-react';
import { ToastHost } from './Toast';
import SidebarTooltip from './SidebarTooltip';
import { clearToken } from '../api/client';
import type { IconName } from './Icon';

const LOGO = './image/licon.webp';

interface NavEntry {
  to: string;
  label: string;
  name: string;
  /** 图标名走 Icon 白名单，避免再手写内联 svg */
  icon: IconName;
}

const NAV: NavEntry[] = [
  { to: '/dashboard', label: '主页', name: '仪表盘', icon: 'home' },
  { to: '/plugins', label: '插件', name: '插件管理', icon: 'package' },
  { to: '/config', label: '配置', name: '配置管理', icon: 'settings' },
  { to: '/system', label: '系统', name: '系统状态', icon: 'cpu' },
  { to: '/usage', label: '用量', name: '用量统计', icon: 'chart' },
  { to: '/bots', label: '机器人', name: '机器人', icon: 'bot' },
  { to: '/logs', label: '日志', name: '日志', icon: 'log' },
];

/** 侧栏图标：与 Icon 组件同尺寸/同描边，避免两套 svg 观感不一致 */
const SIDEBAR_GLYPHS: Record<string, typeof Home> = {
  home: Home,
  package: Package,
  settings: Settings,
  cpu: Cpu,
  chart: BarChart3,
  bot: Bot,
  log: ScrollText,
};

function NavGlyph({ name, size = 20 }: { name: IconName; size?: number }) {
  const Glyph = SIDEBAR_GLYPHS[name] ?? Package;
  return <Glyph size={size} strokeWidth={2} aria-hidden="true" />;
}

const NAME_BY_PATH: Record<string, string> = Object.fromEntries(NAV.map((n) => [n.to, n.name]));

/** onError 里的 event.target 是 EventTarget，收窄成可改样式的元素 */
export const asElement = (target: EventTarget | null): HTMLElement => target as HTMLElement;

const THEME_KEY = 'neobot-dashboard-theme';

function toggleTheme(): void {
  const cur = document.documentElement.dataset.theme || 'light';
  const next = cur === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem(THEME_KEY, next);
}

export default function Layout() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const current = NAME_BY_PATH[pathname] || '仪表盘';
  const editorDirty = useRef(false);
  const editorBusy = useRef(false);
  const isWorkspace = pathname === '/plugins' || pathname === '/config';
  useLayoutEffect(() => {
    const handler = (event: Event) => {
      const state = (event as CustomEvent<boolean | { dirty: boolean; busy: boolean }>).detail;
      editorDirty.current = typeof state === 'boolean' ? state : state.dirty;
      editorBusy.current = typeof state === 'boolean' ? false : state.busy;
    };
    window.addEventListener('dashboard-editor-state', handler);
    return () => window.removeEventListener('dashboard-editor-state', handler);
  }, []);

  const canLeave = () => {
    if (editorBusy.current) return false;
    return !editorDirty.current || confirm('有未保存的修改，离开将丢弃这些修改，是否继续？');
  };

  const logout = () => {
    if (!canLeave()) return;
    clearToken();
    navigate('/login', { replace: true });
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand" title="NeoBot" aria-label="NeoBot">
          <img src={LOGO} alt="NeoBot" onError={(e) => (asElement(e.target).style.display = 'none')} />
        </div>

        <nav className="nav">
          {/* 舰桥入口：3D 舰载控制台是整屏场景，不套用本布局，因此用普通 Link */}
          <Link
            to="/bridge"
            className="nav-item nav-item-bridge"
            data-tooltip="舰桥"
            aria-label="舰桥"
          >
            <Rocket size={20} strokeWidth={2} aria-hidden="true" />
          </Link>

          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              onClick={(event) => {
                // 插件页已有捕获阶段的导航保护，避免重复弹出确认。
                if (pathname === '/config' && pathname !== n.to && !canLeave()) event.preventDefault();
              }}
              className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}
              data-tooltip={n.label}
              aria-label={n.label}
            >
              <NavGlyph name={n.icon} />
            </NavLink>
          ))}
        </nav>

        <nav className="nav-bottom">
          <button className="nav-item" data-tooltip="切换主题" aria-label="切换主题" onClick={toggleTheme}>
            <Moon size={20} strokeWidth={2} aria-hidden="true" />
          </button>
          <button className="nav-item" data-tooltip="退出登录" aria-label="退出登录" onClick={logout}>
            <LogOut size={20} strokeWidth={2} aria-hidden="true" />
          </button>
        </nav>

        {/* 侧栏 tooltip 使用 CSS 伪元素，由侧栏层叠上下文保证显示在主内容上方 */}
        <SidebarTooltip />
      </aside>

      <div className="main">
        {!isWorkspace && <header className="header">
          <div className="crumbs">
            <Home size={14} strokeWidth={2} aria-hidden="true" />
            <span className="current">{current}</span>
          </div>

          <span className="header-caption">NeoBot 面板</span>
        </header>}
        <main className={'content' + (pathname === '/plugins' ? ' content-workspace' : '')}>
          <Outlet />
        </main>
      </div>
      <ToastHost />
    </div>
  );
}
