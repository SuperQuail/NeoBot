// components/ui/FormField.tsx —— 配置表单的一行：左标签/说明 + 右控件
// 渲染的就是线上在用的 .cfg-row / .cfg-label / .cfg-control 三元组（panel.css:34），
// 与各面板手写结构逐类名一致，替换后样式不变。
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
}

export default function FormField({
  label,
  htmlFor,
  description,
  badges,
  children,
  hint,
  className,
}: FormFieldProps) {
  return (
    <div className={cn('cfg-row', className)}>
      <div className="cfg-label">
        {label != null && <label htmlFor={htmlFor}>{label}</label>}
        {description && <p>{description}</p>}
        {badges && <span className="cfg-badges">{badges}</span>}
      </div>
      <div className="cfg-control">
        {children}
        {hint}
      </div>
    </div>
  );
}
