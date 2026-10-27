import { useEffect } from 'react';

/** 发布编辑状态，并为浏览器刷新/关闭保留原生离开保护。 */
export function useEditorGuard(dirty: boolean, busy: boolean): void {
  useEffect(() => {
    window.dispatchEvent(new CustomEvent('dashboard-editor-state', { detail: { dirty, busy } }));
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty && !busy) return;
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty, busy]);
  useEffect(
    () => () => {
      window.dispatchEvent(
        new CustomEvent('dashboard-editor-state', { detail: { dirty: false, busy: false } }),
      );
    },
    [],
  );
}
