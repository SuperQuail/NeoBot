// occlusion.ts —— 面板的遮挡可见度（纯 CPU，撞包围盒）
//
// ## 为什么不在 GPU 上做
//
// 最初的做法是「把舰体用一个只写深度的材质重绘进离屏目标，再按像素比较深度」。
// 但那个离屏目标由合成器（第二个 WebGL 上下文）创建，真正的绘制却发生在引擎的
// 主上下文里 —— **同一个 WebGLRenderTarget 不能跨上下文使用**，合成器采样到的
// 永远是一张没写过的空纹理。于是：
//   · 逐像素遮挡（门框切过全息辉光）从来没有生效过；
//   · 统计「可见比例」用的遮罩小图也没画出任何像素，可见度恒为 0，
//     面板被永久压到 25% 不透明度；
//   · 而为了拿到那个恒为 0 的数值，每 6 帧还要做一次 GPU 同步回读，
//     实测占掉主线程 38% 的时间（单次阻塞约 240ms）—— 这就是「一开面板就卡死」。
//
// 舰内的可行走空间本来就是一组 AABB（collision.ts 的 compileColliders），
// 判断「面板是不是被墙挡住」用它们做几条线段求交就够了：纯数学、零 GPU、
// 可以在 jsdom 里直接测，也没有任何跨上下文问题。

import { isLineBlocked, type CompiledBox } from './collision';
import type { PanelPlane } from '../three/projector';

/** 采样网格：列 × 行。5×4 已经足够区分「整块被挡住」与「露出一角」 */
const GRID_COLS = 5;
const GRID_ROWS = 4;
/**
 * 采样点相对面板边缘的收缩比例。
 *
 * 面板边缘紧贴终端机身的轮廓，采到那里容易把「机身压住面板一个角」误判成
 * 大面积遮挡；收缩 6% 之后统计的是面板主体，读数稳得多。
 */
const EDGE_INSET = 0.06;

export interface PanelVisibilityOptions {
  cols?: number;
  rows?: number;
  inset?: number;
}

/**
 * 面板有多少比例没被舰体挡住（0~1）。
 *
 * @param boxes 编译后的碰撞盒（engine.boxes）
 * @param eye   观察点（通常是相机位置）
 * @param plane 面板所在平面（projector.panelPlaneFromScreen）
 */
export function panelVisibility(
  boxes: readonly CompiledBox[],
  eye: { x: number; y: number; z: number },
  plane: PanelPlane,
  options: PanelVisibilityOptions = {},
): number {
  const cols = Math.max(1, options.cols ?? GRID_COLS);
  const rows = Math.max(1, options.rows ?? GRID_ROWS);
  const inset = options.inset ?? EDGE_INSET;
  const spanX = plane.width * (1 - inset * 2);
  const spanY = plane.height * (1 - inset * 2);

  let visible = 0;
  const sample = { x: 0, y: 0, z: 0 };
  for (let row = 0; row < rows; row += 1) {
    // 行/列都取格心：2 列时是 ±0.25，而不是压在两端的边缘上
    const v = ((row + 0.5) / rows - 0.5) * spanY;
    for (let col = 0; col < cols; col += 1) {
      const u = ((col + 0.5) / cols - 0.5) * spanX;
      sample.x = plane.center.x + plane.right.x * u + plane.up.x * v;
      sample.y = plane.center.y + plane.right.y * u + plane.up.y * v;
      sample.z = plane.center.z + plane.right.z * u + plane.up.z * v;
      if (!isLineBlocked(boxes, eye, sample)) visible += 1;
    }
  }
  return visible / (cols * rows);
}
