// Toast.jsx —— 全局轻量提示(移植自旧 ui/toast.js)
// 用法:任意位置 import { toast } from './Toast.jsx'; toast('已保存', 'ok')
import { useState, useEffect } from 'react';

let pushFn = null;

export function toast(text, kind = 'info', duration = 4000) {
  if (pushFn) pushFn(text, kind, duration);
}

export function ToastHost() {
  const [items, setItems] = useState([]);

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

  const dismiss = (id) => setItems((s) => s.filter((i) => i.id !== id));

  return (
    <div className="toasts">
      {items.map((i) => (
        <div key={i.id} className={'toast ' + i.kind} onClick={() => dismiss(i.id)}>
          <span className="dismiss">×</span>
          {i.text}
        </div>
      ))}
    </div>
  );
}
