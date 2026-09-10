// components/ui/Button.tsx —— 统一按钮：变体 + 尺寸，类名冲突交给 tailwind-merge
// 用法：<Button variant="primary" size="sm" onClick={...}>保存</Button>
// 说明：基底仍复用 theme.css 的 .btn / .btn-sm（内含 hover、disabled 等态），
// variant/className 通过 cn() 合并，调用方传入的类名总能覆盖默认值。
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '../../utils/cn';

export type ButtonVariant = 'default' | 'primary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children?: ReactNode;
}

const VARIANT_CLASS: Record<ButtonVariant, string> = {
  default: '',
  primary: 'bg-brand text-white border-brand hover:bg-brand-hover',
  danger: 'text-err border-err/40 hover:border-err',
  ghost: 'border-transparent bg-transparent hover:bg-panel-2',
};

export default function Button({
  variant = 'default',
  size = 'md',
  className,
  type = 'button',
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        'btn inline-flex items-center justify-center gap-[7px]',
        size === 'sm' && 'btn-sm',
        VARIANT_CLASS[variant],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}
