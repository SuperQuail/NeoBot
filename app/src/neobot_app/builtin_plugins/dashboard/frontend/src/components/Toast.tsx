// Toast.tsx —— 全局轻量提示(移植自旧 ui/toast.js)
// 用法:任意位置 import { toast } from './Toast'; toast('已保存', 'ok')
import { useState, useEffect } from 'react';
import { cn } from '../utils/cn';

export type ToastKind = 'info' | 'ok' | 'warn' | 'err';

interface ToastItem {
  id: number;
  text: string;
  kind: ToastKind;
}

type PushFn = (text: string, kind: ToastKind, duration: number) => void;

let pushFn: PushFn | null = null;

export function toast(text: string, kind: ToastKind = 'info', duration = 4000): void {
  if (pushFn) pushFn(text, kind, duration);
}

export function ToastHost() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    pushFn = (text, kind, duration) => {
      const id = Date.now() + Math.random();
      setItems((s) => [...s, { id, text, kind }]);
      if (duration > 0) {
        setTimeout(() => setItems((s) => s.filter((i) => i.id !== id)), duration);
      }
    };
    return () => {
      pushFn = null;
    };
  }, []);

  const dismiss = (id: number) => setItems((s) => s.filter((i) => i.id !== id));

  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((i) => (
        <div
          key={i.id}
          className={cn('toast', i.kind)}
          role="button"
          tabIndex={0}
          onClick={() => dismiss(i.id)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              dismiss(i.id);
            }
          }}
        >
          <span className="dismiss">×</span>
          {i.text}
        </div>
      ))}
    </div>
  );
}
