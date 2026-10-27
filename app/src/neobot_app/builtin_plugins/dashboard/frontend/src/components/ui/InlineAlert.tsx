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

const TONE: Record<AlertTone, LucideIcon> = {
  error: XCircle,
  warning: AlertTriangle,
  success: CheckCircle2,
  info: Info,
};

export default function InlineAlert({
  tone = 'error',
  title,
  children,
  actions,
  items,
  className,
}: InlineAlertProps) {
  const Glyph = TONE[tone];
  return (
    <div
      className={cn('inline-alert', `inline-alert--${tone}`, className)}
      role={tone === 'error' ? 'alert' : 'status'}
    >
      <Glyph className="inline-alert-icon" size={17} strokeWidth={1.8} aria-hidden="true" />
      <div className="inline-alert-content">
        {title && <div className="inline-alert-title">{title}</div>}
        {children && <div className="inline-alert-description">{children}</div>}
        {items && items.length > 0 && (
          <ul className="cfg-errors">
            {items.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        )}
      </div>
      {actions && <div className="inline-alert-actions">{actions}</div>}
    </div>
  );
}
