import type { PluginAnchorRect } from './pluginViewBridge';

/** 高亮只包围目标的可见部分，外扩和指针都必须留在舞台安全边距内。 */
export function ponderGeometry(
  rect: PluginAnchorRect | undefined,
  width: number,
  height: number,
  padding = 6,
) {
  const inset = 4;
  const cursorSize = 29;
  if (!rect || ![rect.left, rect.top, rect.width, rect.height, width, height].every(Number.isFinite))
    return null;
  if (rect.width <= 0 || rect.height <= 0 || width <= inset * 2 || height <= inset * 2) return null;
  const left = Math.max(0, rect.left);
  const top = Math.max(0, rect.top);
  const right = Math.min(width, rect.left + rect.width);
  const bottom = Math.min(height, rect.top + rect.height);
  // 先判断可见性，避免把已经滚出舞台的目标画成边缘上的一条线。
  if (right <= left || bottom <= top) return null;
  const frameLeft = Math.max(inset, left - padding);
  const frameTop = Math.max(inset, top - padding);
  const frameRight = Math.min(width - inset, right + padding);
  const frameBottom = Math.min(height - inset, bottom + padding);
  if (frameRight <= frameLeft || frameBottom <= frameTop) return null;
  return {
    frame: {
      left: frameLeft,
      top: frameTop,
      width: frameRight - frameLeft,
      height: frameBottom - frameTop,
    },
    cursor:
      width >= cursorSize + inset * 2 && height >= cursorSize + inset * 2
        ? {
            left: Math.max(inset, Math.min(width - inset - cursorSize, left + (right - left) * 0.72)),
            top: Math.max(
              inset,
              Math.min(height - inset - cursorSize, top + Math.min((bottom - top) * 0.6, 42)),
            ),
          }
        : null,
  };
}
