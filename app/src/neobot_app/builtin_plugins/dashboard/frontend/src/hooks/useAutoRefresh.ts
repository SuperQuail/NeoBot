import { useEffect, useRef } from 'react';
import { startAutoRefresh } from '../data/autoRefresh';
import { POLL } from '../data/queryKeys';

/** 表单焦点、非法 JSON 草稿或弹窗尚在交互时，不替换编辑区。 */
export function isEditingSurfaceActive() {
  const active = document.activeElement;
  return (
    !!active?.closest('input, textarea, select, [contenteditable="true"], [role="textbox"]') ||
    !!document.querySelector(
      'input[aria-invalid="true"], textarea[aria-invalid="true"], [contenteditable="true"][aria-invalid="true"], [role="dialog"]',
    )
  );
}

interface AutoRefreshOptions {
  enabled?: boolean;
  interval?: number;
  /** 状态或只读列表可持续更新；编辑文档默认保护正在操作的控件。 */
  pauseWhileEditing?: boolean;
}

/** 首次读取仍由页面负责；自动更新只读回服务端状态，不执行写操作。 */
export function useAutoRefresh(
  refresh: () => unknown | Promise<unknown>,
  { enabled = true, interval = POLL.editor, pauseWhileEditing = true }: AutoRefreshOptions = {},
) {
  const latest = useRef({ refresh, enabled, pauseWhileEditing });
  latest.current = { refresh, enabled, pauseWhileEditing };
  useEffect(
    () =>
      startAutoRefresh(
        () => latest.current.refresh(),
        interval,
        () => latest.current.enabled && (!latest.current.pauseWhileEditing || !isEditingSurfaceActive()),
      ),
    [interval],
  );
}
