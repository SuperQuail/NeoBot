import { lazy, type ComponentType, type LazyExoticComponent } from 'react';
import { matchRoutes } from 'react-router-dom';
import type { IconName } from '../components/Icon';
import type { SkeletonKind } from '../components/ui/PageSkeleton';

export const NAV_GROUPS = ['概览', '配置', '运行与数据', '维护'] as const;

interface PageRoute {
  path: string;
  label: string;
  title: string;
  group: (typeof NAV_GROUPS)[number];
  icon: IconName;
  viewport: boolean;
  skeleton: SkeletonKind;
  component: LazyExoticComponent<ComponentType>;
}

/** 路由、导航、面包屑、滚动外壳和骨架的唯一页面目录。 */
export const PAGE_ROUTES: readonly PageRoute[] = [
  {
    path: '/dashboard',
    label: '主页',
    title: '仪表盘',
    group: '概览',
    icon: 'home',
    viewport: true,
    skeleton: 'overview',
    component: lazy(() => import('../pages/Dashboard')),
  },
  {
    path: '/deploy',
    label: '部署',
    title: '快捷部署',
    group: '概览',
    icon: 'play',
    viewport: true,
    skeleton: 'workspace',
    component: lazy(() => import('../pages/Deploy')),
  },
  {
    path: '/bots',
    label: '机器人',
    title: '机器人',
    group: '概览',
    icon: 'bot',
    viewport: true,
    skeleton: 'overview',
    component: lazy(() => import('../pages/Bots')),
  },
  {
    path: '/config',
    label: '配置',
    title: '配置管理',
    group: '配置',
    icon: 'settings',
    viewport: true,
    skeleton: 'workspace',
    component: lazy(() => import('../pages/ConfigManager')),
  },
  {
    path: '/plugins',
    label: '插件',
    title: '插件管理',
    group: '配置',
    icon: 'package',
    viewport: true,
    skeleton: 'workspace',
    component: lazy(() => import('../pages/Plugins')),
  },
  {
    path: '/prompts',
    label: '提示词',
    title: '提示词模板',
    group: '配置',
    icon: 'edit',
    viewport: true,
    skeleton: 'workspace',
    component: lazy(() => import('../pages/Prompts')),
  },
  {
    path: '/chat-flows',
    label: '聊天流',
    title: '聊天流',
    group: '运行与数据',
    icon: 'message',
    viewport: true,
    skeleton: 'workspace',
    component: lazy(() => import('../pages/ChatFlows')),
  },
  {
    path: '/scheduled-tasks',
    label: '定时',
    title: '定时任务',
    group: '运行与数据',
    icon: 'clock',
    viewport: false,
    skeleton: 'table',
    component: lazy(() => import('../pages/ScheduledTasks')),
  },
  {
    path: '/archives',
    label: '档案',
    title: '档案管理',
    group: '运行与数据',
    icon: 'archive',
    viewport: true,
    skeleton: 'workspace',
    component: lazy(() => import('../pages/Archives')),
  },
  {
    path: '/usage',
    label: '用量',
    title: '用量统计',
    group: '运行与数据',
    icon: 'chart',
    viewport: true,
    skeleton: 'overview',
    component: lazy(() => import('../pages/Usage')),
  },
  {
    path: '/analysis',
    label: '分析',
    title: '提示词分析',
    group: '运行与数据',
    icon: 'code',
    viewport: true,
    skeleton: 'overview',
    component: lazy(() => import('../pages/Analysis')),
  },
  {
    path: '/system',
    label: '系统',
    title: '系统状态',
    group: '维护',
    icon: 'cpu',
    viewport: true,
    skeleton: 'overview',
    component: lazy(() => import('../pages/System')),
  },
  {
    path: '/logs',
    label: '日志',
    title: '日志',
    group: '维护',
    icon: 'log',
    viewport: true,
    skeleton: 'workspace',
    component: lazy(() => import('../pages/Logs')),
  },
];

const MATCHABLE_ROUTES = PAGE_ROUTES.map((route) => ({ path: route.path, handle: route }));

export function pageRoute(pathname: string): PageRoute {
  return matchRoutes(MATCHABLE_ROUTES, pathname)?.[0].route.handle ?? PAGE_ROUTES[0];
}
