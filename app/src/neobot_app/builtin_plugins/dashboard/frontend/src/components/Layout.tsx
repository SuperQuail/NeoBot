import { Link, Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Suspense, useEffect, useLayoutEffect, useRef, useState } from 'react';
import {
  Archive,
  Home,
  LogOut,
  Package,
  ScrollText,
  Settings,
  BarChart3,
  Bot,
  Cpu,
  Code,
  Rocket,
  Pencil,
  MessagesSquare,
  Clock,
  PanelLeftClose,
  PanelLeftOpen,
  Menu,
  X,
  ChevronRight,
} from 'lucide-react';
import * as Dialog from '@radix-ui/react-dialog';
import * as Tooltip from '@radix-ui/react-tooltip';
import { useQuery } from '../data/useQuery';
import { QK, POLL } from '../data/queryKeys';
import { api } from '../api/endpoints';
import { InfoBarHost } from './InfoBar';
import ThemePicker from './ui/ThemePicker';
import { confirmAction } from './ui/ConfirmDialog';
import StandbyBanner from './StandbyBanner';
import { clearToken } from '../api/client';
import type { IconName } from './Icon';
import { useAuthGate } from '../auth/AuthContext';
import { NAV_GROUPS, PAGE_ROUTES, pageRoute } from '../app/routes';
import PageMotion from './ui/PageMotion';
import { m, useAnimationControls } from 'motion/react';
import { useReducedEffects } from '../hooks/useReducedEffects';
import PageSkeleton from './ui/PageSkeleton';

const LOGO = './image/icon.webp';

/** 侧栏图标：与 Icon 组件同尺寸/同描边，避免两套 svg 观感不一致 */
const SIDEBAR_GLYPHS: Record<string, typeof Home> = {
  home: Home,
  play: Rocket,
  package: Package,
  settings: Settings,
  cpu: Cpu,
  chart: BarChart3,
  code: Code,
  bot: Bot,
  log: ScrollText,
  game: Rocket,
  edit: Pencil,
  message: MessagesSquare,
  clock: Clock,
  archive: Archive,
};

/** 面板 HTTP 扩展（例如官方星舰游戏插件）的侧栏入口；扩展不存在时不渲染任何东西 */
function ExtensionNav() {
  const query = useQuery(QK.extensions, () => api.extensions(), { interval: POLL.power });
  const entries = (query.data?.items || []).filter((item) => item?.panel?.path && item?.panel?.title);
  if (entries.length === 0) return null;
  return (
    <>
      {entries.map((item) => {
        const panel = item.panel!;
        const title = panel.title || item.name || '扩展页面';
        return (
          <a
            key={item.name || title}
            className="nav-item"
            href={panel.path}
            data-tooltip={title}
            aria-label={title}
            title={panel.description || title}
          >
            <NavGlyph name={(panel.icon as IconName) || 'game'} />
            <span className="nav-label">{title}</span>
          </a>
        );
      })}
    </>
  );
}

function NavGlyph({ name, size = 20 }: { name: IconName; size?: number }) {
  const Glyph = SIDEBAR_GLYPHS[name] ?? Package;
  return <Glyph size={size} strokeWidth={2} aria-hidden="true" />;
}

export default function Layout() {
  const { canManage } = useAuthGate();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const reducedMotion = useReducedEffects();
  const currentPage = pageRoute(pathname);
  const current = currentPage.title;
  const editorDirty = useRef(false);
  const editorBusy = useRef(false);
  const contentRef = useRef<HTMLElement>(null);
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem('neobot-dashboard-sidebar') === 'collapsed',
  );
  const [mobile, setMobile] = useState(() => window.matchMedia?.('(max-width: 800px)').matches ?? false);
  const [menuOpen, setMenuOpen] = useState(false);
  const drawerFrame = useAnimationControls();
  const drawerPanel = useAnimationControls();
  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 800px)');
    const update = () => {
      setMobile(media?.matches ?? false);
      setMenuOpen(false);
    };
    media?.addEventListener?.('change', update);
    return () => media?.removeEventListener?.('change', update);
  }, []);
  useLayoutEffect(() => {
    if (!mobile || !menuOpen) return;
    let disposed = false;
    if (reducedMotion) {
      drawerFrame.stop();
      drawerPanel.stop();
      drawerFrame.set({ opacity: 1 });
      drawerPanel.set({ opacity: 1, x: 0 });
    } else {
      queueMicrotask(() => {
        if (disposed) return;
        void drawerFrame.start({ opacity: 1, transition: { duration: 0.14 } });
        void drawerPanel.start({ opacity: 1, x: 0, transition: { duration: 0.2 } });
      });
    }
    return () => {
      disposed = true;
      drawerFrame.stop();
      drawerPanel.stop();
    };
  }, [drawerFrame, drawerPanel, menuOpen, mobile, reducedMotion]);
  useLayoutEffect(() => {
    contentRef.current?.scrollTo?.({ top: 0 });
  }, [pathname]);
  useLayoutEffect(() => {
    const handler = (event: Event) => {
      const state = (event as CustomEvent<boolean | { dirty: boolean; busy: boolean }>).detail;
      editorDirty.current = typeof state === 'boolean' ? state : state.dirty;
      editorBusy.current = typeof state === 'boolean' ? false : state.busy;
    };
    window.addEventListener('dashboard-editor-state', handler);
    return () => window.removeEventListener('dashboard-editor-state', handler);
  }, []);

  const canLeave = async () => {
    if (editorBusy.current) return false;
    return (
      !editorDirty.current ||
      (await confirmAction({
        title: '放弃未保存的修改？',
        description: '离开当前页面后，这些修改不会保存。',
        confirmLabel: '放弃并离开',
        danger: true,
      }))
    );
  };

  const logout = async () => {
    if (!(await canLeave())) return;
    clearToken();
    navigate('/login', { replace: true });
  };
  const sidebar = (
    <>
      <div className="brand" title="NeoBot" aria-label="NeoBot">
        <img src={LOGO} alt="NeoBot" onError={(e) => (e.currentTarget.style.display = 'none')} />
        <div className="brand-copy">
          <strong>NeoBot</strong>
          <span>机器人工作台</span>
        </div>
        {mobile && (
          <button className="icon-btn drawer-close" aria-label="关闭导航" onClick={() => setMenuOpen(false)}>
            <X size={18} />
          </button>
        )}
      </div>

      <nav className="nav" aria-label="主导航">
        {NAV_GROUPS.map((group) => (
          <div className="nav-group" key={group}>
            <span className="nav-group-label">{group}</span>
            {PAGE_ROUTES.filter((route) => route.group === group).map((n) => (
              <Tooltip.Root key={n.path} delayDuration={250}>
                <Tooltip.Trigger asChild>
                  <Link
                    to={n.path}
                    onClick={(event) => {
                      if (pathname !== n.path && (editorDirty.current || editorBusy.current)) {
                        event.preventDefault();
                        void canLeave().then((allowed) => {
                          if (allowed) {
                            setMenuOpen(false);
                            navigate(n.path);
                          }
                        });
                      } else setMenuOpen(false);
                    }}
                    className={'nav-item' + (currentPage.path === n.path ? ' active' : '')}
                    aria-current={currentPage.path === n.path ? 'page' : undefined}
                    data-tooltip={n.label}
                    aria-label={n.label}
                  >
                    <NavGlyph name={n.icon} />
                    <span className="nav-label">{n.title}</span>
                  </Link>
                </Tooltip.Trigger>
                {collapsed && !mobile && (
                  <Tooltip.Portal>
                    <Tooltip.Content className="nav-tooltip" side="right" sideOffset={12}>
                      {n.title}
                    </Tooltip.Content>
                  </Tooltip.Portal>
                )}
              </Tooltip.Root>
            ))}
          </div>
        ))}
        {/* 子插件挂到面板端口上的页面（星舰游戏等） */}
        <ExtensionNav />
      </nav>

      <nav className="nav-bottom">
        <ThemePicker />
        <button className="nav-item" data-tooltip="退出登录" aria-label="退出登录" onClick={logout}>
          <LogOut size={20} strokeWidth={2} aria-hidden="true" />
          <span className="nav-label">退出登录</span>
        </button>
        {!mobile && (
          <button
            className="nav-item collapse-toggle"
            aria-label={collapsed ? '展开侧栏' : '收起侧栏'}
            onClick={() => {
              const next = !collapsed;
              setCollapsed(next);
              localStorage.setItem('neobot-dashboard-sidebar', next ? 'collapsed' : 'expanded');
            }}
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
            <span className="nav-label">收起侧栏</span>
          </button>
        )}
      </nav>
    </>
  );
  return (
    <Tooltip.Provider>
      <div className={'app' + (collapsed && !mobile ? ' is-collapsed' : '')}>
        {mobile ? (
          <Dialog.Root open={menuOpen} onOpenChange={setMenuOpen}>
            <Dialog.Portal>
              <Dialog.Overlay asChild>
                <m.div
                  className="sidebar-backdrop"
                  initial={reducedMotion ? false : { opacity: 0 }}
                  animate={drawerFrame}
                />
              </Dialog.Overlay>
              <Dialog.Content asChild aria-describedby={undefined}>
                <m.aside
                  className="sidebar sidebar-drawer"
                  initial={reducedMotion ? false : { opacity: 0.6, x: -14 }}
                  animate={drawerPanel}
                >
                  <Dialog.Title className="sr-only">NeoBot 导航</Dialog.Title>
                  {sidebar}
                </m.aside>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>
        ) : (
          <aside className="sidebar">{sidebar}</aside>
        )}

        <div className="main">
          <a
            href="#main-content"
            className="skip-link"
            onClick={(event) => {
              event.preventDefault();
              contentRef.current?.focus();
            }}
          >
            跳到主内容
          </a>
          <div className="shell-topbar">
            <div className="shell-topbar-inner">
              {mobile && (
                <button className="icon-btn" aria-label="打开导航" onClick={() => setMenuOpen(true)}>
                  <Menu size={19} />
                </button>
              )}
              <div className="crumbs" aria-label="当前位置">
                <span>NeoBot</span>
                <ChevronRight size={12} />
                <span className="current">{current}</span>
              </div>
              <span className="header-caption">{canManage === false ? '只读模式' : 'NeoBot 面板'}</span>
            </div>
          </div>
          {/* 待机是全局状态：任意页面都要能看到并一键启动运行 */}
          <StandbyBanner />
          <main
            ref={contentRef}
            id="main-content"
            tabIndex={-1}
            className={'content' + (currentPage.viewport ? ' content--viewport' : '')}
          >
            <Suspense
              key={pathname}
              fallback={<PageSkeleton kind={currentPage.skeleton} label={`正在加载${current}`} />}
            >
              <PageMotion>
                <Outlet />
              </PageMotion>
            </Suspense>
          </main>
        </div>
        <InfoBarHost />
      </div>
    </Tooltip.Provider>
  );
}
