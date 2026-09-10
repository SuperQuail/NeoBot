// WorkspaceLayout.tsx —— 工作区两栏骨架（列表面板 + 编辑区）
// 统一插件管理 / 配置管理的布局、滚动与层级契约，替代各页各自拼 grid 的做法。
// 样式表在 main.tsx 统一按层级顺序引入（styles/workspace.css），组件内不再 import 全局样式。
import type { ReactNode } from 'react';
import { cn } from '../utils/cn';

export interface WorkspaceLayoutProps {
  /** 左侧列表面板 */
  panel: ReactNode;
  /** 右侧编辑区 */
  editor: ReactNode;
  /** 窄屏下是否显示详情（由页面控制移动端切换） */
  showDetail?: boolean;
  /** 左侧面板宽度覆盖，默认 264px（可传 CSS 长度） */
  panelWidth?: string;
  className?: string;
}

export default function WorkspaceLayout({
  panel,
  editor,
  showDetail = false,
  panelWidth,
  className,
}: WorkspaceLayoutProps) {
  return (
    <div
      className={cn('workspace', showDetail && 'show-detail', className)}
      style={panelWidth ? ({ '--workspace-panel-width': panelWidth } as React.CSSProperties) : undefined}
    >
      {panel}
      {editor}
    </div>
  );
}

/** 面板内的可滚动区域（列表） */
export function WorkspaceScroll({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('workspace-scroll', className)}>{children}</div>;
}
