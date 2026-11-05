import * as Dialog from '@radix-ui/react-dialog';
import { ArrowLeft, Lightbulb } from 'lucide-react';
import { useRef, type ReactNode } from 'react';
import Button from '../../components/ui/Button';

interface Props {
  pluginId: string;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
}

/** 思索接管整个视口；原编辑器继续挂载，焦点与无障碍隔离交给同一套基础能力。 */
export default function PluginPonderScreen({ pluginId, onClose, title, children }: Props) {
  const returnFocus = useRef<HTMLElement | null>(null);
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Content
          className="ponder-screen"
          aria-describedby={undefined}
          onOpenAutoFocus={(event) => {
            if (document.activeElement instanceof HTMLElement) returnFocus.current = document.activeElement;
            const target = (event.currentTarget as HTMLElement).querySelector<HTMLElement>(
              '[data-autofocus]',
            );
            if (target) {
              event.preventDefault();
              target.focus();
            }
          }}
          onCloseAutoFocus={(event) => {
            if (!returnFocus.current?.isConnected) return;
            event.preventDefault();
            returnFocus.current.focus({ preventScroll: true });
          }}
          onInteractOutside={(event) => event.preventDefault()}
        >
          <header className="ponder-header">
            <div className="ponder-heading">
              <Lightbulb size={18} aria-hidden="true" />
              <span>思索</span>
              <Dialog.Title className="sr-only">{pluginId} · 思索说明书</Dialog.Title>
              {title ?? <strong>{pluginId}</strong>}
            </div>
            <Button variant="ghost" size="sm" onClick={onClose} aria-label="返回配置">
              <ArrowLeft size={16} />
              <span>返回配置</span>
              <kbd>Esc</kbd>
            </Button>
          </header>
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
