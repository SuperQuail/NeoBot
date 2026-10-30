import type { PluginAnchorRect } from './pluginViewBridge';

/** 跨 iframe 的 Tab 只滚动所属正文，不能把固定标题、工具栏和保存区一起推走。 */
export function revealPluginFocus(frame: HTMLIFrameElement | null, rect: PluginAnchorRect) {
  if (!frame || frame.ownerDocument.activeElement !== frame) return;
  const scroll = frame.closest<HTMLElement>('.workspace-scroll');
  if (!scroll || scroll.clientHeight === 0) return;
  const bounds = frame.getBoundingClientRect();
  if (rect.left >= bounds.width || rect.left + rect.width <= 0) return;
  const top = bounds.top + Math.max(0, rect.top);
  const bottom = bounds.top + Math.min(bounds.height, rect.top + rect.height);
  if (bottom <= top) return;
  const viewport = scroll.getBoundingClientRect();
  const margin = Math.min(32, scroll.clientHeight / 4);
  const visibleTop = viewport.top + scroll.clientTop + margin;
  const visibleBottom = viewport.top + scroll.clientTop + scroll.clientHeight - margin;
  if (top < visibleTop || bottom - top > visibleBottom - visibleTop) {
    scroll.scrollTop += top - visibleTop;
  } else if (bottom > visibleBottom) {
    scroll.scrollTop += bottom - visibleBottom;
  }
}
