import { useEffect, useSyncExternalStore } from 'react';
import Modal, { ModalActions } from '../Modal';
import Button from './Button';

interface ConfirmOptions {
  title: string;
  description?: string;
  confirmLabel?: string;
  danger?: boolean;
}
interface Confirmation extends ConfirmOptions {
  id: number;
  resolve: (confirmed: boolean) => void;
}
const queue: Confirmation[] = [];
let sequence = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((listener) => listener());
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
const snapshot = () => queue[0] ?? null;

export function confirmAction(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    queue.push({ ...options, id: ++sequence, resolve });
    emit();
  });
}

export function ConfirmHost() {
  const current = useSyncExternalStore(subscribe, snapshot, snapshot);
  useEffect(
    () => () => {
      const abandoned = queue.splice(0);
      emit();
      abandoned.forEach((pending) => pending.resolve(false));
    },
    [],
  );
  const settle = (confirmed: boolean) => {
    const pending = queue.shift();
    emit();
    pending?.resolve(confirmed);
  };
  return (
    <Modal
      key={current?.id ?? 'closed'}
      open={!!current}
      title={current?.title}
      onClose={() => settle(false)}
    >
      <p className="confirm-description">{current?.description}</p>
      <ModalActions>
        <Button data-autofocus onClick={() => settle(false)}>
          取消
        </Button>
        <Button variant={current?.danger ? 'danger' : 'primary'} onClick={() => settle(true)}>
          {current?.confirmLabel || '确认'}
        </Button>
      </ModalActions>
    </Modal>
  );
}
