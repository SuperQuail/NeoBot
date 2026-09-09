import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useEffect, useRef } from 'react';
import { ToastHost } from './Toast.jsx';
import { clearToken } from '../api/client.js';

const LOGO = './image/licon.webp';

const NAV = [
  {
    to: '/dashboard',
    label: '主页',
    name: '仪表盘',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 11.5 12 4l9 7.5" /><path d="M5 10v10h14V10" /><path d="M10 20v-6h4v6" />
      </svg>
    ),
  },
  {
    to: '/plugins',
    label: '插件',
    name: '插件管理',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 4a2 2 0 1 0-4 0v2H6a2 2 0 0 0-2 2v4h2a2 2 0 1 1 0 4H4v4a2 2 0 0 0 2 2h4v-2a2 2 0 1 1 4 0v2h4a2 2 0 0 0 2-2v-4h-2a2 2 0 1 1 0-4h2V8a2 2 0 0 0-2-2h-4z" />
      </svg>
    ),
  },
  {
    to: '/config',
    label: '配置',
    name: '配置管理',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-2.9 1.2V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 7 19.4a1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 3 15H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 9 4.6H9a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 2.9 1.2l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0 1.2 2.9H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1.4z" />
      </svg>
    ),
  },
  {
    to: '/system',
    label: '系统',
    name: '系统状态',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="7" rx="2" /><rect x="3" y="13" width="18" height="7" rx="2" /><path d="M7 7.5h.01M7 16.5h.01" />
      </svg>
    ),
  },
  {
    to: '/bots',
    label: '机器人',
    name: '机器人',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="8" width="16" height="12" rx="2" /><path d="M12 4v4" /><circle cx="12" cy="4" r="1" /><circle cx="9" cy="13" r="1" /><circle cx="15" cy="13" r="1" /><path d="M9 17h6" />
      </svg>
    ),
  },
  {
    to: '/logs',
    label: '日志',
    name: '日志',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /><path d="M8 13h8" /><path d="M8 17h5" />
      </svg>
    ),
  },
];

const NAME_BY_PATH = Object.fromEntries(NAV.map((n) => [n.to, n.name]));

const THEME_KEY = 'neobot-dashboard-theme';
function toggleTheme() {
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
  const isWorkspace = pathname === '/plugins' || pathname === '/config';
  useEffect(() => {
    const handler = (event) => { editorDirty.current = event.detail; };
    window.addEventListener('dashboard-editor-state', handler);
    return () => window.removeEventListener('dashboard-editor-state', handler);
  }, []);

  const logout = () => {
    if (editorDirty.current && !confirm('有未保存的修改或正在进行的操作，确认退出？')) return;
    clearToken();
    navigate('/login', { replace: true });
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand" title="NeoBot" aria-label="NeoBot">
          <img src={LOGO} alt="NeoBot" onError={(e) => (e.target.style.display = 'none')} />
        </div>

        <nav className="nav">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              className={({ isActive }) => 'nav-item' + (isActive ? ' active' : '')}
              data-tooltip={n.label}
              aria-label={n.label}
            >
              {n.icon}
            </NavLink>
          ))}
        </nav>

        <nav className="nav-bottom">
          <button className="nav-item" data-tooltip="切换主题" aria-label="切换主题" onClick={toggleTheme}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
            </svg>
          </button>
          <button className="nav-item" data-tooltip="退出登录" aria-label="退出登录" onClick={logout}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
            </svg>
          </button>
        </nav>
      </aside>

      <div className="main">
        {!isWorkspace && <header className="header">
          <div className="crumbs">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 11.5 12 4l9 7.5" /><path d="M5 10v10h14V10" />
            </svg>
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
