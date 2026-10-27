// components/ui/Button.tsx —— 统一按钮：变体 + 尺寸
// 输出的类名与手写按钮完全一致（btn / btn-sm + primary|danger），
// 因此替换调用点不改变任何现有样式与测试。
// 用法：<Button variant="primary" size="sm" onClick={...}>保存</Button>
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '../../utils/cn';
import { cva } from 'class-variance-authority';

export type ButtonVariant = 'default' | 'primary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children?: ReactNode;
}

// 与 theme.css / panel.css 里已有的 .btn/.btn-sm/.primary/.danger 一一对应
const VARIANT_CLASS: Record<ButtonVariant, string> = {
  default: '',
  primary: 'primary',
  danger: 'danger',
  ghost: 'ghost',
};

const buttonClasses = cva('', {
  variants: { size: { sm: 'btn-sm', md: 'btn' } },
  defaultVariants: { size: 'md' },
});

export default function Button({
  variant = 'default',
  size = 'md',
  className,
  type = 'button',
  children,
  ...props
}: ButtonProps) {
  return (
    <button type={type} className={cn(buttonClasses({ size }), VARIANT_CLASS[variant], className)} {...props}>
      {children}
    </button>
  );
}
