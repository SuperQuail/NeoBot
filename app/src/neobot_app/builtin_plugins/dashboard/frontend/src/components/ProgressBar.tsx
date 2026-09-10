// ProgressBar.tsx —— CPU/内存/磁盘占用条(对应旧 system.js 的 setBar)
import type { ReactNode } from 'react';
import { cn } from '../utils/cn';

export interface ProgressBarProps {
  label?: ReactNode;
  text?: ReactNode;
  /** 0-100，缺省按 0 处理 */
  pct?: number | null;
}

export default function ProgressBar({ label, text, pct }: ProgressBarProps) {
  const width = Math.min(100, Math.max(0, pct || 0));
  const tone = width >= 90 ? 'err' : width >= 70 ? 'warn' : 'ok';
  return (
    <div className="bar-row">
      <div className="bar-head">
        <span className="bar-label">{label}</span>
        <span className="bar-text">{text}</span>
      </div>
      <div className="bar-track">
        <div className={cn('bar-fill', tone)} style={{ width: width.toFixed(1) + '%' }} />
      </div>
    </div>
  );
}
