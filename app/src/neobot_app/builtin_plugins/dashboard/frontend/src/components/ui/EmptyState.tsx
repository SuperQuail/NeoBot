// components/ui/EmptyState.tsx —— 空态/占位：两种既有形态收敛成一个组件
// compact: <div class="empty muted">…</div>（行内占位）
// 默认:    <div class="workspace-empty"><Icon/><h3/><…></div>（大块空态）
import type { ReactNode } from 'react';
import Icon from '../Icon';
import type { IconName } from '../Icon';
import { cn } from '../../utils/cn';

export interface EmptyStateProps {
  icon?: IconName;
  title?: ReactNode;
  /** 紧凑占位：只渲染 empty muted 容器 */
  compact?: boolean;
  className?: string;
  children?: ReactNode;
}

export default function EmptyState({ icon, title, compact = false, className, children }: EmptyStateProps) {
  if (compact) {
    return <div className={cn('empty muted', className)}>{children}</div>;
  }
  return (
    <div className={cn('workspace-empty', className)}>
      {icon ? <Icon name={icon} /> : null}
      {title != null ? <h3>{title}</h3> : null}
      {children}
    </div>
  );
}
