// StatCard.tsx —— 统计卡(带图标,对齐原版 stat-card)
import type { ReactNode } from 'react';
import { cn } from '../utils/cn';

export interface StatCardProps {
  label?: ReactNode;
  value?: ReactNode;
  sub?: ReactNode;
  /** 数值强调色（CSS 颜色值），传了就覆盖默认文本色 */
  accent?: string;
  icon?: ReactNode;
  iconAccent?: boolean;
  children?: ReactNode;
  className?: string;
}

export default function StatCard({ label, value, sub, accent, icon, iconAccent, children, className }: StatCardProps) {
  return (
    <div className={cn('card stat-card', className)}>
      {icon && <div className={cn('stat-icon', iconAccent && 'accent')}>{icon}</div>}
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={accent ? { color: accent } : undefined}>
        {value ?? '—'}
      </div>
      {sub != null && <div className="stat-sub">{sub}</div>}
      {children}
    </div>
  );
}
