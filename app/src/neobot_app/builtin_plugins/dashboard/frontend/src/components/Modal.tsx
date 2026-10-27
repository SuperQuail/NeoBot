import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import { m, useAnimationControls } from 'motion/react';
import { useLayoutEffect, useRef, type ReactNode } from 'react';
import { cn } from '../utils/cn';
import { useReducedEffects } from '../hooks/useReducedEffects';

export interface ModalProps {
  open?: boolean;
  title?: ReactNode;
  onClose: () => void;
  children?: ReactNode;
  /** 固定在滚动内容之外的操作区。 */
  footer?: ReactNode;
  closeDisabled?: boolean;
  size?: 'default' | 'wide';
  /** 额外类名（Tailwind 迁移期用于覆盖内边距等） */
  className?: string;
}

/** 弹窗页脚：收敛各处手写的 <div className="modal-actions">（渲染结果完全一致）。 */
export function ModalActions({ children, className }: { children?: ReactNode; className?: string }) {
  return <div className={cn('modal-actions', className)}>{children}</div>;
}

export default function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  closeDisabled = false,
  size = 'default',
  className,
}: ModalProps) {
  const reducedMotion = useReducedEffects();
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const frame = useAnimationControls();
  const slide = useAnimationControls();

  useLayoutEffect(() => {
    if (!open) return;
    let disposed = false;
    frame.stop();
    slide.stop();
    if (reducedMotion) {
      frame.set({ opacity: 1 });
      slide.set({ y: 0 });
    } else {
      // Radix Portal 在挂载后的布局更新才接上动画节点，避免首次打开时丢失 start。
      queueMicrotask(() => {
        if (disposed) return;
        const transition = { duration: 0.18, ease: 'easeOut' as const };
        void frame.start({ opacity: 1 }, transition);
        void slide.start({ y: 0 }, transition);
      });
    }
    return () => {
      disposed = true;
      frame.stop();
      slide.stop();
    };
  }, [open, reducedMotion, frame, slide]);
  return (
    <Dialog.Root
      open={!!open}
      onOpenChange={(next) => {
        if (!next && !closeDisabled) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay asChild>
          <m.div className="modal-backdrop" initial={{ opacity: reducedMotion ? 1 : 0 }} animate={frame} />
        </Dialog.Overlay>
        <Dialog.Content
          asChild
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => {
            const active = document.activeElement;
            // 多步设置返回此弹窗时，保留页内入口，避免记住即将卸载的上一步按钮。
            if (
              active instanceof HTMLElement &&
              active !== document.body &&
              (!returnFocusRef.current?.isConnected || !active.closest('[role="dialog"]'))
            ) {
              returnFocusRef.current = active;
            }
            const target = event.currentTarget as HTMLElement;
            const preferred = target.querySelector<HTMLElement>('[data-autofocus]');
            if (preferred) {
              event.preventDefault();
              preferred.focus();
            }
          }}
          onCloseAutoFocus={(event) => {
            const target = returnFocusRef.current;
            if (target?.isConnected && target !== document.body) {
              event.preventDefault();
              target.focus({ preventScroll: true });
            }
          }}
        >
          <m.div
            className={cn('modal', size !== 'default' && `modal-${size}`, className)}
            initial={{ opacity: reducedMotion ? 1 : 0.85 }}
            animate={frame}
          >
            <m.div className="modal-head" initial={{ y: reducedMotion ? 0 : 4 }} animate={slide}>
              <Dialog.Title asChild>
                <h3>{title}</h3>
              </Dialog.Title>
              <Dialog.Close className="icon-btn" aria-label="关闭对话框" disabled={closeDisabled}>
                <X size={17} aria-hidden="true" />
              </Dialog.Close>
            </m.div>
            <m.div className="modal-body" initial={{ y: reducedMotion ? 0 : 6 }} animate={slide}>
              {children}
            </m.div>
            {footer != null && <div className="modal-footer">{footer}</div>}
          </m.div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
