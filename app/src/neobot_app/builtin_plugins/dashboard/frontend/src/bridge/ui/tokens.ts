// tokens.ts —— 全息面板的配色令牌
//
// 面板有三处要「同一种青色」：合成层的边缘辉光（GLSL uniform）、CSS 里的
// 描边与文字（--accent 变量）、以及舰体自发光材质（ship.ts 里的 COLOR_CYAN）。
// 各写一遍迟早会漂移，因此统一从这里取。
//
// 优先读主题变量（theme.css 的 --accent / --accent-2），读不到再回退常量，
// 这样面板换主题时舰内全息色会跟着变。

import { Color } from 'three';

/** 面板默认主色（青）——与舰体自发光同色系 */
const FALLBACK_ACCENT = 0x3fe0ff;
/** 辅助色（品红）：只用在边缘色散与警戒态，制造赛博朋克那种轻微色差 */
const FALLBACK_ACCENT_ALT = 0xff3bd0;

function readCssColor(name: string, fallback: number): Color {
  if (typeof window === 'undefined' || typeof getComputedStyle !== 'function') {
    return new Color(fallback);
  }
  const raw = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  if (!raw) return new Color(fallback);
  try {
    return new Color(raw);
  } catch {
    return new Color(fallback);
  }
}

/** 每帧都要用，所以只解析一次（主题切换是低频操作，不为此加监听） */
export const HOLO_ACCENT = readCssColor('--accent', FALLBACK_ACCENT);
export const HOLO_ACCENT_ALT = readCssColor('--accent-2', FALLBACK_ACCENT_ALT);
