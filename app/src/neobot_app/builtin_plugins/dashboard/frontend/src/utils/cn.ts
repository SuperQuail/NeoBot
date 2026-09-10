// cn —— 类名合并：clsx 处理条件拼接，tailwind-merge 消除冲突的工具类。
// 迁移到 Tailwind 后，组件通过 className 覆盖默认样式时必须走这里，
// 否则 `p-2` 与传入的 `p-4` 会同时生效（CSS 顺序决定胜负，不可预期）。
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
