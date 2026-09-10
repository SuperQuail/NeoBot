// components/ui/InlineAlert.tsx —— 行内提示条：错误 / 警告 / 成功 / 信息
// 取代散落各页的 <div className="workspace-error|config-notice"> 手写结构。
import type { ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, Info, XCircle } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '../../utils/cn';

export type AlertTone = 'error' | 'warning' | 'success' | 'info';

export interface InlineAlertProps {
  tone?: AlertTone;
  /** 标题（可选，用于「校验失败：」这类前缀） */
  title?: ReactNode;
  children?: ReactNode;
  /** 右侧操作区（如「重试」「重新读取」） */
  actions?: ReactNode;
  /** 列表型内容（错误明细），会渲染成 <ul class="cfg-errors"> */
  items?: ReactNode[];
  className?: string;
}

const TONE: Record<AlertTone, { wrap: string; icon: LucideIcon }> = {
  error: {
    wrap: 'bg-err/8 text-err border border-err/20',
    icon: XCircle,
  },
  warning: {
    wrap: 'bg-warn/10 text-warn border border-warn/25',
    icon: AlertTriangle,
  },
  success: {
    wrap: 'bg-ok/8 text-ok border border-ok/20',
    icon: CheckCircle2,
  },
  info: {
    wrap: 'bg-brand-soft text-brand-hover border border-brand/25',
    icon: Info,
  },
};

export default function InlineAlert({
  tone = 'error',
  title,
  children,
  actions,
  items,
  className,
}: InlineAlertProps) {
  const { wrap, icon: Glyph } = TONE[tone];
  return (
    <div
      className={cn('flex flex-wrap items-center gap-2.5 rounded-[7px] px-3 py-3 text-xs', wrap, className)}
      role={tone === 'error' ? 'alert' : 'status'}
    >
      <Glyph size={16} strokeWidth={2} aria-hidden="true" />
      <span className="min-w-0 break-words">
        {title}
        {children}
      </span>
      {items && items.length > 0 && (
        <ul className="cfg-errors m-0 w-full pl-[18px] text-xs leading-relaxed">
          {items.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      )}
      {actions && <span className="ml-auto flex items-center gap-2">{actions}</span>}
    </div>
  );
}
