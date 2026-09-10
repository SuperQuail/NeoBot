// components/ui/FormField.tsx —— 配置表单的一行：左标签/说明 + 右控件
// 对齐 .cfg-row 的两列网格，但把布局收到组件里，避免各面板重复拼 DOM。
import type { ReactNode } from 'react';
import { cn } from '../../utils/cn';

export interface FormFieldProps {
  /** 字段名（<label for> 用） */
  label?: ReactNode;
  htmlFor?: string;
  /** 字段说明（配置路径 / 一句话解释） */
  description?: ReactNode;
  /** 标签下方的额外徽标（热重载标记等） */
  badges?: ReactNode;
  /** 右侧控件 */
  children: ReactNode;
  /** 控件下方的补充说明（错误、恢复默认等） */
  hint?: ReactNode;
  className?: string;
  /** 单列布局（弹窗内、窄屏） */
  stacked?: boolean;
}

export default function FormField({
  label,
  htmlFor,
  description,
  badges,
  children,
  hint,
  className,
  stacked = false,
}: FormFieldProps) {
  return (
    <div
      className={cn(
        'cfg-row grid items-center gap-8 border-t border-border-soft py-5',
        stacked ? 'grid-cols-1 gap-1.5' : 'grid-cols-[minmax(140px,1fr)_minmax(180px,1.1fr)]',
        className,
      )}
    >
      <div className="cfg-label min-w-0">
        {label != null && (
          <label className="block text-xs font-semibold break-words" htmlFor={htmlFor}>
            {label}
          </label>
        )}
        {description && <p className="mt-[5px] text-[11px] leading-relaxed text-muted">{description}</p>}
        {badges && <span className="cfg-badges">{badges}</span>}
      </div>
      <div className="cfg-control min-w-0">
        {children}
        {hint}
      </div>
    </div>
  );
}
