import { useEffect, useId, useRef } from 'react';
import type { ReactNode } from 'react';
import { cn } from '../utils/cn';

export interface ModalProps {
  open?: boolean;
  title?: ReactNode;
  onClose: () => void;
  children?: ReactNode;
  size?: 'default' | 'wide';
  /** 额外类名（Tailwind 迁移期用于覆盖内边距等） */
  className?: string;
}

export default function Modal({ open, title, onClose, children, size = 'default', className }: ModalProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const closeRef = useRef(onClose);
  const titleId = useId();
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    if (!dialog) return;
    const focusable = (): HTMLElement[] => [
      ...dialog.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), [href], [tabindex="0"]',
      ),
    ];
    // 优先聚焦显式声明的 [data-autofocus]，否则聚焦第一个可用控件。
    // （不用原生 autoFocus：它由 React 在挂载时直接聚焦，这里的时序更可控）
    (dialog.querySelector<HTMLElement>('[data-autofocus]') || focusable()[0] || dialog).focus();

    function keyboard(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeRef.current();
      }
      if (event.key !== 'Tab') return;
      const targets = focusable();
      if (!targets.length) {
        event.preventDefault();
        dialog?.focus();
        return;
      }
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog)) {
        event.preventDefault();
        first.focus();
      }
    }

    dialog.addEventListener('keydown', keyboard);
    return () => {
      dialog.removeEventListener('keydown', keyboard);
      previous?.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div
      className="modal-backdrop"
      role="presentation"
      // 点击遮罩自身关闭；点击对话框内部不冒泡到关闭逻辑（原先靠内部 stopPropagation）
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      onKeyDown={(event) => {
        // 背景可点击关闭，因此也需要键盘等价操作（Esc 在对话框内部另行处理）
        if (event.key === 'Escape') onClose();
      }}
    >
      <div
        className={cn('modal', size !== 'default' && `modal-${size}`, className)}
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="modal-head">
          <h3 id={titleId}>{title}</h3>
          <button className="icon-btn" aria-label="关闭对话框" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}
