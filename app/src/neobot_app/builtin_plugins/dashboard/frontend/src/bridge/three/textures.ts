// textures.ts —— 舰内材质贴图工厂（Canvas2D 程序化生成，零外部资源）
//
// 为什么全部程序化：网页面板要随 Python 包一起分发，任何 png/jpg 都会进构建产物，
// 而舰内需要大量「同风格不同尺寸」的表面（甲板、舱壁、格栅、屏幕、铭牌……），
// 运行时用 Canvas 画最省体积，也方便统一调色。
//
// 约定（改这张表前先读三条）：
//  1. 颜色贴图一律 colorSpace = SRGBColorSpace；包裹方式默认 RepeatWrapping，
//     屏幕/铭牌等「一次性画面」用 ClampToEdgeWrapping（见各自 setup）。
//  2. Canvas 的 y 轴向下，而 three 的 CanvasTexture 默认 flipY = true，
//     于是画布里「正着」写的字在上传后依然是正的 —— 不需要手动翻转；
//     反过来说，如果哪天把 flipY 关掉，所有文字都会上下颠倒。
//  3. 画布一律 ≤ 512×512：这些贴图在主线程上生成，尺寸再大就会拖慢登舰。
//
// 另外：贴图的 repeat 保持「1 格 = 1 次」，实际平铺密度由 ship.ts 把世界尺寸
// 烘进几何体 UV（scaleUV）来保证 —— 同一张贴图要同时贴 24m 的舱壁和 0.4m 的
// 检修口，靠 texture.repeat 是做不到的（repeat 属于贴图，不属于网格）。

import * as THREE from 'three';

/** 已生成贴图的模块级缓存：重复调用返回同一实例（React StrictMode 会挂载两次） */
const cache = new Map<string, THREE.Texture>();

/** 无 canvas 环境（jsdom 等）下退化贴图的颜色：舰体深钢色 */
const FALLBACK_RGB: readonly [number, number, number] = [28, 36, 46];

let warnedNoCanvas = false;

/**
 * 环境是否支持 Canvas2D。
 *
 * jsdom（单元测试）里 createElement('canvas').getContext('2d') 会返回 null 并往
 * 虚拟控制台打一条 "Not implemented" 错误。这里在第一次失败后就把结论缓存下来，
 * 后续贴图直接走 1×1 兜底分支 —— 既少刷一屏日志，也让测试里的 buildShip 更快。
 */
let canvas2dUnavailable = false;

type Painter = (ctx: CanvasRenderingContext2D, w: number, h: number) => void;

/**
 * 生成（或取出）一张 CanvasTexture。
 * @param key 缓存键，必须能唯一描述这张图（含文字内容）
 * @param configure 覆盖默认包裹/映射方式（屏幕、星空等需要单独设置）
 */
function createCanvasTexture(
  key: string,
  width: number,
  height: number,
  paint: Painter,
  configure?: (texture: THREE.CanvasTexture) => void,
): THREE.Texture {
  const cached = cache.get(key);
  if (cached) return cached;

  const canvas =
    !canvas2dUnavailable && typeof document !== 'undefined' ? document.createElement('canvas') : null;
  const ctx = canvas ? canvas.getContext('2d') : null;
  if (canvas && !ctx) canvas2dUnavailable = true;

  let texture: THREE.Texture;
  if (canvas && ctx) {
    canvas.width = width;
    canvas.height = height;
    paint(ctx, width, height);
    const canvasTexture = new THREE.CanvasTexture(canvas);
    canvasTexture.colorSpace = THREE.SRGBColorSpace;
    canvasTexture.wrapS = THREE.RepeatWrapping;
    canvasTexture.wrapT = THREE.RepeatWrapping;
    // 4 倍各向异性：舰内大量斜视地面，不开的话远处格栅会糊成一片
    canvasTexture.anisotropy = 4;
    configure?.(canvasTexture);
    canvasTexture.needsUpdate = true;
    texture = canvasTexture;
  } else {
    // 极端环境（无 DOM / 无 2D 上下文）：退化成 1×1 单色，保证上层不崩
    if (!warnedNoCanvas) {
      warnedNoCanvas = true;
      console.warn('[bridge/three] 无法创建 2D 上下文，贴图退化为单色');
    }
    const data = new Uint8Array([FALLBACK_RGB[0], FALLBACK_RGB[1], FALLBACK_RGB[2], 255]);
    const dataTexture = new THREE.DataTexture(data, 1, 1);
    dataTexture.colorSpace = THREE.SRGBColorSpace;
    dataTexture.needsUpdate = true;
    texture = dataTexture;
  }

  cache.set(key, texture);
  return texture;
}

/** 固定种子的伪随机：保证每次构建生成的磨损/污渍位置一致，便于截图比对 */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** 中文优先的字体栈：舰内文字（舱室名、屏幕抬头）以中文为主 */
function sansFont(size: number, weight = 600): string {
  return `${weight} ${size}px "PingFang SC", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif`;
}

function monoFont(size: number, weight = 500): string {
  return `${weight} ${size}px "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace`;
}

/** 在 [x0,x1]×[y0,y1] 上画一层「阴影渐晕」，让平面贴图有轻微的立体感 */
function vignette(
  ctx: CanvasRenderingContext2D,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  alpha: number,
): void {
  const g = ctx.createLinearGradient(0, y0, 0, y1);
  g.addColorStop(0, `rgba(0,0,0,${alpha})`);
  g.addColorStop(0.35, 'rgba(0,0,0,0)');
  g.addColorStop(0.75, 'rgba(0,0,0,0)');
  g.addColorStop(1, `rgba(0,0,0,${alpha})`);
  ctx.fillStyle = g;
  ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
}

// ---------------------------------------------------------------------------
// 甲板 / 舱壁 / 结构件
// ---------------------------------------------------------------------------

/** 甲板钢板：128px 一块的拼板 + 铆钉 + 防滑纹 + 油污 */
export function floorPlateTexture(): THREE.Texture {
  return createCanvasTexture('floor-plate', 512, 512, (ctx, w, h) => {
    const rnd = mulberry32(0x51a7);
    ctx.fillStyle = '#131920';
    ctx.fillRect(0, 0, w, h);

    const cell = 128;
    for (let gy = 0; gy < 4; gy += 1) {
      for (let gx = 0; gx < 4; gx += 1) {
        const x = gx * cell;
        const y = gy * cell;
        const tone = 26 + Math.floor(rnd() * 12);
        ctx.fillStyle = `rgb(${tone},${tone + 8},${tone + 16})`;
        ctx.fillRect(x + 2, y + 2, cell - 4, cell - 4);

        // 防滑纹：横向细密压痕
        ctx.strokeStyle = 'rgba(165,195,220,0.05)';
        ctx.lineWidth = 1;
        for (let i = 1; i < 6; i += 1) {
          const ly = y + 2 + (i * (cell - 4)) / 6;
          ctx.beginPath();
          ctx.moveTo(x + 3, ly);
          ctx.lineTo(x + cell - 3, ly);
          ctx.stroke();
        }

        // 四角铆钉（高光点 + 暗影，两笔画出一颗铆钉）
        for (const [dx, dy] of [[11, 11], [cell - 12, 11], [11, cell - 12], [cell - 12, cell - 12]]) {
          ctx.fillStyle = 'rgba(6,9,13,0.55)';
          ctx.beginPath();
          ctx.arc(x + dx + 1, y + dy + 1, 3, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = 'rgba(196,220,240,0.20)';
          ctx.beginPath();
          ctx.arc(x + dx, y + dy, 2.6, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }

    // 板缝：深色为主，上缘补一道高光
    ctx.lineWidth = 4;
    ctx.strokeStyle = 'rgba(0,0,0,0.66)';
    for (let i = 0; i <= 4; i += 1) {
      ctx.beginPath();
      ctx.moveTo(i * cell, 0);
      ctx.lineTo(i * cell, h);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, i * cell);
      ctx.lineTo(w, i * cell);
      ctx.stroke();
    }
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(190,215,235,0.07)';
    for (let i = 0; i <= 4; i += 1) {
      ctx.beginPath();
      ctx.moveTo(i * cell + 3, 0);
      ctx.lineTo(i * cell + 3, h);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(0, i * cell + 3);
      ctx.lineTo(w, i * cell + 3);
      ctx.stroke();
    }

    // 使用痕迹：斜向划痕
    for (let i = 0; i < 90; i += 1) {
      const x = rnd() * w;
      const y = rnd() * h;
      const light = rnd() > 0.5;
      ctx.strokeStyle = light
        ? `rgba(210,232,248,${0.03 + rnd() * 0.05})`
        : `rgba(8,11,15,${0.05 + rnd() * 0.08})`;
      ctx.lineWidth = 1 + rnd() * 1.4;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + (rnd() - 0.5) * 96, y + (rnd() - 0.5) * 24);
      ctx.stroke();
    }

    // 油污/积水：径向渐变（不用 ctx.filter，兼容性更好）
    for (let i = 0; i < 6; i += 1) {
      const x = rnd() * w;
      const y = rnd() * h;
      const r = 40 + rnd() * 90;
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      g.addColorStop(0, 'rgba(5,8,12,0.40)');
      g.addColorStop(1, 'rgba(5,8,12,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    }
  });
}

/** 舱壁装甲板：竖向分块 + 内凹面板 + 百叶通风口 + 螺栓 */
export function wallPanelTexture(): THREE.Texture {
  return createCanvasTexture('wall-panel', 512, 512, (ctx, w, h) => {
    const rnd = mulberry32(0x2f13);
    ctx.fillStyle = '#1d2530';
    ctx.fillRect(0, 0, w, h);

    // 上下横梁：把舱壁分成「踢脚 / 面板 / 檐口」三段
    ctx.fillStyle = '#161d26';
    ctx.fillRect(0, 0, w, 34);
    ctx.fillRect(0, h - 52, w, 52);
    ctx.fillStyle = 'rgba(190,215,235,0.06)';
    ctx.fillRect(0, 34, w, 2);
    ctx.fillRect(0, h - 54, w, 2);

    const col = 128;
    for (let i = 0; i < 4; i += 1) {
      const x = i * col;
      // 面板本体
      ctx.fillStyle = i % 2 === 0 ? '#222b37' : '#1f2833';
      ctx.fillRect(x + 6, 44, col - 12, h - 108);
      // 内凹边缘：左上暗、右下亮（假想光源来自上方）
      ctx.fillStyle = 'rgba(0,0,0,0.42)';
      ctx.fillRect(x + 6, 44, 4, h - 108);
      ctx.fillRect(x + 6, 44, col - 12, 4);
      ctx.fillStyle = 'rgba(190,215,235,0.10)';
      ctx.fillRect(x + col - 10, 44, 4, h - 108);
      ctx.fillRect(x + 6, h - 68, col - 12, 4);

      // 百叶通风口
      ctx.fillStyle = 'rgba(4,7,10,0.62)';
      for (let v = 0; v < 5; v += 1) {
        ctx.fillRect(x + 22, 78 + v * 13, col - 44, 6);
      }
      ctx.fillStyle = 'rgba(190,215,235,0.05)';
      for (let v = 0; v < 5; v += 1) {
        ctx.fillRect(x + 22, 84 + v * 13, col - 44, 1);
      }

      // 检修小盖板
      ctx.fillStyle = '#2b3644';
      ctx.fillRect(x + 30, h - 190, col - 60, 62);
      ctx.strokeStyle = 'rgba(9,13,18,0.8)';
      ctx.lineWidth = 3;
      ctx.strokeRect(x + 30, h - 190, col - 60, 62);
      ctx.fillStyle = 'rgba(56,225,255,0.16)';
      ctx.fillRect(x + 40, h - 176, col - 80, 8);

      // 螺栓阵列
      for (let b = 0; b < 6; b += 1) {
        const bx = x + 14 + (b % 2) * (col - 30);
        const by = 60 + Math.floor(b / 2) * ((h - 150) / 3);
        ctx.fillStyle = 'rgba(6,9,13,0.5)';
        ctx.beginPath();
        ctx.arc(bx + 1, by + 1, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = 'rgba(200,224,244,0.18)';
        ctx.beginPath();
        ctx.arc(bx, by, 3.4, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // 竖向接缝
    ctx.strokeStyle = 'rgba(0,0,0,0.55)';
    ctx.lineWidth = 3;
    for (let i = 1; i < 4; i += 1) {
      ctx.beginPath();
      ctx.moveTo(i * col, 0);
      ctx.lineTo(i * col, h);
      ctx.stroke();
    }

    // 细微噪点，避免大面积纯色在低光下出现色带
    for (let i = 0; i < 2200; i += 1) {
      const x = rnd() * w;
      const y = rnd() * h;
      ctx.fillStyle = rnd() > 0.5 ? 'rgba(255,255,255,0.018)' : 'rgba(0,0,0,0.05)';
      ctx.fillRect(x, y, 2, 2);
    }

    vignette(ctx, 0, 34, w, h - 52, 0.10);
  });
}

/** 金属格栅：走廊/猫道的镂空踏板 */
export function grateTexture(): THREE.Texture {
  return createCanvasTexture('grate', 256, 256, (ctx, w, h) => {
    // 底色即「镂空」处（深不见底）
    ctx.fillStyle = '#080c11';
    ctx.fillRect(0, 0, w, h);

    // 纵向承重条
    for (let i = 0; i < 8; i += 1) {
      const x = i * 32 + 5;
      ctx.fillStyle = '#39434f';
      ctx.fillRect(x, 0, 21, h);
      ctx.fillStyle = 'rgba(200,224,244,0.16)';
      ctx.fillRect(x, 0, 3, h);
      ctx.fillStyle = 'rgba(0,0,0,0.5)';
      ctx.fillRect(x + 18, 0, 3, h);
    }

    // 横向连接条
    for (let i = 0; i < 4; i += 1) {
      const y = i * 64 + 8;
      ctx.fillStyle = '#46515f';
      ctx.fillRect(0, y, w, 9);
      ctx.fillStyle = 'rgba(210,232,248,0.12)';
      ctx.fillRect(0, y, w, 2);
    }

    // 边缘压条上的铆钉
    for (let i = 0; i < 4; i += 1) {
      for (let j = 0; j < 4; j += 1) {
        ctx.fillStyle = 'rgba(214,236,252,0.22)';
        ctx.beginPath();
        ctx.arc(16 + i * 64, 12 + j * 64, 2.2, 0, Math.PI * 2);
        ctx.fill();
      }
    }
  });
}

/** 危险警示斜纹（橙 / 深灰交替）：舱门框、反应堆护栏、甲板边缘 */
export function hazardStripeTexture(): THREE.Texture {
  return createCanvasTexture('hazard-stripe', 128, 128, (ctx, w, h) => {
    ctx.fillStyle = '#161b22';
    ctx.fillRect(0, 0, w, h);

    // 45° 斜纹：为了能无缝平铺，旋转坐标系后条纹周期取 w/(√2·n)，
    // 这样画布平移 w（或 h）后的相位差正好是整数个周期。
    const period = w / (Math.SQRT2 * 2);
    ctx.save();
    ctx.translate(w / 2, h / 2);
    ctx.rotate(-Math.PI / 4);
    ctx.fillStyle = '#ff9b3d';
    for (let i = -8; i <= 8; i += 1) {
      ctx.fillRect(i * period * 2, -w * 2, period, w * 4);
    }
    ctx.restore();

    // 磨损：让警示漆看起来被踩过
    const rnd = mulberry32(0x7c31);
    for (let i = 0; i < 60; i += 1) {
      const x = rnd() * w;
      const y = rnd() * h;
      ctx.fillStyle = `rgba(22,27,34,${0.15 + rnd() * 0.4})`;
      ctx.fillRect(x, y, 3 + rnd() * 10, 2 + rnd() * 5);
    }
    vignette(ctx, 0, 0, w, h, 0.18);
  });
}

/** 六边形蜂窝板：反应堆外壳、主机机柜等「高科技」表面 */
export function hexPanelTexture(): THREE.Texture {
  return createCanvasTexture(
    'hex-panel',
    384,
    384,
    (ctx, w, h) => {
      const rnd = mulberry32(0x1f77);
      ctx.fillStyle = '#141b24';
      ctx.fillRect(0, 0, w, h);

      const r = 32; // 外接圆半径（尖顶六边形）
      const hStep = r * 1.5; // 列间距
      const vStep = Math.sqrt(3) * r; // 行间距

      const hexPath = (cx: number, cy: number): void => {
        ctx.beginPath();
        for (let k = 0; k < 6; k += 1) {
          const a = (Math.PI / 3) * k;
          const px = cx + Math.cos(a) * r * 0.94;
          const py = cy + Math.sin(a) * r * 0.94;
          if (k === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        }
        ctx.closePath();
      };

      // 多画一圈，保证四周被完全覆盖（镜像平铺时接缝不明显）
      for (let col = -1; col <= w / hStep + 1; col += 1) {
        for (let row = -1; row <= h / vStep + 1; row += 1) {
          const cx = col * hStep;
          const cy = row * vStep + (col % 2 === 0 ? 0 : vStep / 2);
          const tone = 22 + Math.floor(rnd() * 10);
          hexPath(cx, cy);
          ctx.fillStyle = `rgb(${tone},${tone + 9},${tone + 18})`;
          ctx.fill();
          ctx.strokeStyle = 'rgba(6,9,13,0.85)';
          ctx.lineWidth = 3;
          ctx.stroke();
          ctx.strokeStyle = 'rgba(120,190,220,0.10)';
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }
    },
    (texture) => {
      // 六边形图案的非整数周期无法完美平铺，用镜像包裹遮掩接缝
      texture.wrapS = THREE.MirroredRepeatWrapping;
      texture.wrapT = THREE.MirroredRepeatWrapping;
    },
  );
}

/** 舰体外壳：大块装甲板 + 面板线 + 铆钉 + 流痕 + 检修口 */
export function hullTexture(): THREE.Texture {
  return createCanvasTexture('hull', 512, 512, (ctx, w, h) => {
    const rnd = mulberry32(0x9d21);
    const base = ctx.createLinearGradient(0, 0, 0, h);
    base.addColorStop(0, '#33404f');
    base.addColorStop(0.5, '#2a3542');
    base.addColorStop(1, '#222c38');
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, w, h);

    // 面板线：不规则分块，避免看起来像瓷砖
    ctx.strokeStyle = 'rgba(4,7,11,0.75)';
    ctx.lineWidth = 4;
    for (let i = 1; i < 4; i += 1) {
      const x = i * 128 + (i === 2 ? 18 : -12);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
    for (let i = 1; i < 3; i += 1) {
      const y = i * 170 + (i === 1 ? 14 : -20);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(190,215,235,0.09)';
    for (let i = 1; i < 4; i += 1) {
      const x = i * 128 + (i === 2 ? 20 : -10);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }

    // 铆钉带
    for (let i = 0; i < 40; i += 1) {
      const x = 22 + (i % 8) * 62;
      const y = 24 + Math.floor(i / 8) * 120;
      ctx.fillStyle = 'rgba(6,9,13,0.5)';
      ctx.beginPath();
      ctx.arc(x + 1, y + 1, 3.4, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = 'rgba(206,228,248,0.16)';
      ctx.beginPath();
      ctx.arc(x, y, 2.8, 0, Math.PI * 2);
      ctx.fill();
    }

    // greeble：小型检修口 / 传感器底座
    for (let i = 0; i < 14; i += 1) {
      const x = 28 + rnd() * (w - 120);
      const y = 28 + rnd() * (h - 120);
      const bw = 36 + rnd() * 62;
      const bh = 18 + rnd() * 34;
      ctx.fillStyle = '#39444f';
      ctx.fillRect(x, y, bw, bh);
      ctx.strokeStyle = 'rgba(5,8,12,0.7)';
      ctx.lineWidth = 3;
      ctx.strokeRect(x, y, bw, bh);
      ctx.fillStyle = 'rgba(255,155,61,0.20)';
      ctx.fillRect(x + 5, y + 5, bw - 10, 4);
    }

    // 垂直流痕（太空里的积尘与烧蚀痕迹）
    for (let i = 0; i < 26; i += 1) {
      const x = rnd() * w;
      const len = 60 + rnd() * 240;
      const g = ctx.createLinearGradient(0, 0, 0, len);
      g.addColorStop(0, 'rgba(10,14,19,0.30)');
      g.addColorStop(1, 'rgba(10,14,19,0)');
      ctx.save();
      ctx.translate(x, rnd() * h * 0.6);
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, 3 + rnd() * 12, len);
      ctx.restore();
    }

    vignette(ctx, 0, 0, w, h, 0.14);
  });
}

// ---------------------------------------------------------------------------
// 界面 / 标识
// ---------------------------------------------------------------------------

/** 终端屏幕：假读数（抬头 + 若干行 + 状态条 + 扫描线） */
export function screenTexture(title: string, lines: readonly string[]): THREE.Texture {
  // 行内容进缓存键：不同终端必须拿到不同贴图
  const body = lines.slice(0, 7).map((line) => line.slice(0, 42));
  return createCanvasTexture(
    `screen:${title}:${body.join('|')}`,
    512,
    288,
    (ctx, w, h) => {
      const rnd = mulberry32(0x33b1);

      // 底：偏青的深色玻璃
      const bg = ctx.createLinearGradient(0, 0, 0, h);
      bg.addColorStop(0, '#04121a');
      bg.addColorStop(1, '#020a10');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);

      // 背景栅格
      ctx.strokeStyle = 'rgba(56,225,255,0.06)';
      ctx.lineWidth = 1;
      for (let x = 0; x <= w; x += 32) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0; y <= h; y += 32) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      // 抬头
      ctx.fillStyle = 'rgba(56,225,255,0.16)';
      ctx.fillRect(0, 0, w, 48);
      ctx.fillStyle = '#8ff2ff';
      ctx.font = monoFont(24, 700);
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText(title.slice(0, 26), 18, 25);
      ctx.fillStyle = '#38e1ff';
      ctx.fillRect(0, 46, w, 2);

      // 正文行
      ctx.font = monoFont(17, 500);
      for (let i = 0; i < body.length; i += 1) {
        const y = 74 + i * 26;
        ctx.fillStyle = '#38e1ff';
        ctx.fillText('>', 18, y);
        ctx.fillStyle = i === 0 ? '#e6fbff' : 'rgba(198,238,252,0.78)';
        ctx.fillText(body[i] ?? '', 40, y);
      }

      // 右侧假数据条（不接真实数据，纯装饰，故不写数值）
      for (let i = 0; i < 3; i += 1) {
        const y = 70 + i * 30;
        const len = 60 + rnd() * 90;
        ctx.fillStyle = 'rgba(56,225,255,0.14)';
        ctx.fillRect(w - 150, y, 130, 12);
        ctx.fillStyle = 'rgba(56,225,255,0.55)';
        ctx.fillRect(w - 150, y, len, 12);
      }

      // 底部状态行
      ctx.fillStyle = '#7ef0b0';
      ctx.font = monoFont(15, 600);
      ctx.fillText('SYS ONLINE', 18, h - 22);
      ctx.fillStyle = 'rgba(198,238,252,0.5)';
      ctx.textAlign = 'right';
      ctx.fillText('NEOBOT // LINK OK', w - 18, h - 22);
      ctx.textAlign = 'left';

      // 扫描线 + 边角暗角
      ctx.fillStyle = 'rgba(0,0,0,0.20)';
      for (let y = 0; y < h; y += 4) ctx.fillRect(0, y, w, 1);
      const vg = ctx.createRadialGradient(w / 2, h / 2, h * 0.2, w / 2, h / 2, w * 0.7);
      vg.addColorStop(0, 'rgba(0,0,0,0)');
      vg.addColorStop(1, 'rgba(0,0,0,0.5)');
      ctx.fillStyle = vg;
      ctx.fillRect(0, 0, w, h);
    },
    (texture) => {
      texture.wrapS = THREE.ClampToEdgeWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;
    },
  );
}

/** 舱室铭牌：白字透明底，三维里用自发光材质染成青色 */
export function labelTexture(text: string, sub?: string): THREE.Texture {
  return createCanvasTexture(
    `label:${text}:${sub ?? ''}`,
    512,
    128,
    (ctx, w, h) => {
      ctx.clearRect(0, 0, w, h);

      // 四角装饰括号，让铭牌看起来是「舰载标识」而不是普通文字
      ctx.strokeStyle = 'rgba(255,255,255,0.55)';
      ctx.lineWidth = 3;
      const m = 12;
      const len = 26;
      const corners: Array<[number, number, number, number]> = [
        [m, m, 1, 1],
        [w - m, m, -1, 1],
        [m, h - m, 1, -1],
        [w - m, h - m, -1, -1],
      ];
      for (const [x, y, sx, sy] of corners) {
        ctx.beginPath();
        ctx.moveTo(x + sx * len, y);
        ctx.lineTo(x, y);
        ctx.lineTo(x, y + sy * len);
        ctx.stroke();
      }

      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      // 外发光用两次描边模拟（shadowBlur 在部分环境里更慢）
      const cx = w / 2;
      if (sub) {
        ctx.font = sansFont(52, 700);
        ctx.fillStyle = 'rgba(255,255,255,0.35)';
        ctx.fillText(text, cx, 46);
        ctx.fillStyle = '#ffffff';
        ctx.fillText(text, cx, 44);
        ctx.font = monoFont(22, 500);
        ctx.fillStyle = 'rgba(255,255,255,0.7)';
        ctx.fillText(sub.toUpperCase().slice(0, 30), cx, 92);
      } else {
        ctx.font = sansFont(60, 700);
        ctx.fillStyle = 'rgba(255,255,255,0.35)';
        ctx.fillText(text, cx, 66);
        ctx.fillStyle = '#ffffff';
        ctx.fillText(text, cx, 64);
      }
    },
    (texture) => {
      texture.wrapS = THREE.ClampToEdgeWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;
    },
  );
}

/** 发光灯带：横向「透明→亮→透明」渐变，纵向叠一排 LED 点 */
export function emissiveStripTexture(): THREE.Texture {
  return createCanvasTexture(
    'emissive-strip',
    128,
    32,
    (ctx, w, h) => {
      const g = ctx.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, 'rgba(255,255,255,0)');
      g.addColorStop(0.42, 'rgba(255,255,255,0.75)');
      g.addColorStop(0.5, 'rgba(255,255,255,1)');
      g.addColorStop(0.58, 'rgba(255,255,255,0.75)');
      g.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);

      // LED 点阵：叠在渐变上形成「灯珠」节奏
      ctx.fillStyle = 'rgba(255,255,255,0.85)';
      for (let x = 4; x < w; x += 14) {
        ctx.beginPath();
        ctx.arc(x, h / 2, 3.4, 0, Math.PI * 2);
        ctx.fill();
      }
    },
    (texture) => {
      // 沿灯带长度方向平铺，截面方向拉伸
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;
    },
  );
}

/** 等离子核心：中心炽白 → 青 → 深蓝 → 透明的湍流 */
export function plasmaCoreTexture(): THREE.Texture {
  return createCanvasTexture(
    'plasma-core',
    256,
    256,
    (ctx, w, h) => {
      const rnd = mulberry32(0x4c0d);
      ctx.clearRect(0, 0, w, h);
      const cx = w / 2;
      const cy = h / 2;

      const core = ctx.createRadialGradient(cx, cy, 0, cx, cy, w / 2);
      core.addColorStop(0, 'rgba(255,255,255,1)');
      core.addColorStop(0.16, 'rgba(196,248,255,0.95)');
      core.addColorStop(0.42, 'rgba(56,225,255,0.55)');
      core.addColorStop(0.72, 'rgba(24,96,196,0.22)');
      core.addColorStop(1, 'rgba(6,16,48,0)');
      ctx.fillStyle = core;
      ctx.fillRect(0, 0, w, h);

      // 涡流弧线
      ctx.lineCap = 'round';
      for (let i = 0; i < 22; i += 1) {
        const a0 = rnd() * Math.PI * 2;
        const a1 = a0 + 0.5 + rnd() * 1.5;
        const r0 = 18 + rnd() * 70;
        const r1 = r0 + 12 + rnd() * 46;
        ctx.strokeStyle = `rgba(${rnd() > 0.7 ? '255,255,255' : '150,240,255'},${0.1 + rnd() * 0.28})`;
        ctx.lineWidth = 1 + rnd() * 3;
        ctx.beginPath();
        ctx.arc(cx, cy, (r0 + r1) / 2, a0, a1);
        ctx.stroke();
      }

      // 高能噪点
      for (let i = 0; i < 320; i += 1) {
        const a = rnd() * Math.PI * 2;
        const r = Math.pow(rnd(), 0.6) * (w / 2);
        ctx.fillStyle = `rgba(255,255,255,${0.05 + rnd() * 0.4})`;
        ctx.fillRect(cx + Math.cos(a) * r, cy + Math.sin(a) * r, 1.6, 1.6);
      }
    },
    (texture) => {
      // 反应堆里这张图要缓慢平移（offset）制造流动感，因此必须允许循环包裹
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.RepeatWrapping;
    },
  );
}

// ---------------------------------------------------------------------------
// 舷外 / 光效
// ---------------------------------------------------------------------------

/** 远处的气态行星：横向云带 + 风暴涡旋，给舷窗外一个「目的地」 */
export function planetTexture(): THREE.Texture {
  return createCanvasTexture(
    'planet',
    512,
    256,
    (ctx, w, h) => {
      const rnd = mulberry32(0x9a11);
      // 底色：从赤道暖色到两极冷色
      const base = ctx.createLinearGradient(0, 0, 0, h);
      base.addColorStop(0, '#20304a');
      base.addColorStop(0.28, '#6b5a55');
      base.addColorStop(0.5, '#c9a173');
      base.addColorStop(0.72, '#6d5b62');
      base.addColorStop(1, '#1d2a41');
      ctx.fillStyle = base;
      ctx.fillRect(0, 0, w, h);

      // 云带
      for (let i = 0; i < 26; i += 1) {
        const y = rnd() * h;
        const thickness = 3 + rnd() * 16;
        ctx.fillStyle =
          rnd() > 0.5
            ? `rgba(255,236,208,${0.05 + rnd() * 0.12})`
            : `rgba(60,48,52,${0.06 + rnd() * 0.14})`;
        ctx.beginPath();
        ctx.moveTo(0, y);
        for (let x = 0; x <= w; x += 32) {
          ctx.lineTo(x, y + Math.sin((x / w) * Math.PI * 2 + i) * 3);
        }
        ctx.lineTo(w, y + thickness);
        for (let x = w; x >= 0; x -= 32) {
          ctx.lineTo(x, y + thickness + Math.sin((x / w) * Math.PI * 2 + i) * 3);
        }
        ctx.closePath();
        ctx.fill();
      }

      // 风暴涡旋
      for (let i = 0; i < 3; i += 1) {
        const x = rnd() * w;
        const y = h * (0.3 + rnd() * 0.4);
        const r = 14 + rnd() * 26;
        const g = ctx.createRadialGradient(x, y, 0, x, y, r);
        g.addColorStop(0, 'rgba(255,222,186,0.55)');
        g.addColorStop(0.5, 'rgba(190,120,90,0.35)');
        g.addColorStop(1, 'rgba(120,80,80,0)');
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.ellipse(x, y, r * 1.6, r * 0.7, 0, 0, Math.PI * 2);
        ctx.fill();
      }

      // 昼夜明暗：一侧被恒星照亮，另一侧沉入阴影
      const terminator = ctx.createLinearGradient(0, 0, w, 0);
      terminator.addColorStop(0, 'rgba(0,0,0,0.78)');
      terminator.addColorStop(0.32, 'rgba(0,0,0,0.12)');
      terminator.addColorStop(0.62, 'rgba(255,240,220,0.16)');
      terminator.addColorStop(1, 'rgba(0,0,0,0.82)');
      ctx.fillStyle = terminator;
      ctx.fillRect(0, 0, w, h);
    },
    (texture) => {
      // 经度方向可平铺，纬度方向夹紧
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;
    },
  );
}

/** 舷外星野（等距柱状投影，用作 scene.background） */
export function starfieldTexture(): THREE.Texture {
  return createCanvasTexture(
    'starfield',
    512,
    256,
    (ctx, w, h) => {
      const rnd = mulberry32(0x5eed);
      const bg = ctx.createLinearGradient(0, 0, 0, h);
      bg.addColorStop(0, '#01030a');
      bg.addColorStop(0.5, '#03060f');
      bg.addColorStop(1, '#01030a');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, w, h);

      // 星云：几团大半径低透明色斑，给深空一点颜色层次
      const nebulaColors = ['56,120,220', '150,70,210', '40,180,200', '220,120,90'];
      for (let i = 0; i < 7; i += 1) {
        const x = rnd() * w;
        const y = 40 + rnd() * (h - 80);
        const r = 50 + rnd() * 120;
        const g = ctx.createRadialGradient(x, y, 0, x, y, r);
        g.addColorStop(0, `rgba(${nebulaColors[i % nebulaColors.length]},${0.05 + rnd() * 0.08})`);
        g.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = g;
        ctx.fillRect(x - r, y - r, r * 2, r * 2);
      }

      // 银河带
      const band = ctx.createLinearGradient(0, h * 0.42, 0, h * 0.62);
      band.addColorStop(0, 'rgba(180,205,255,0)');
      band.addColorStop(0.5, 'rgba(190,215,255,0.09)');
      band.addColorStop(1, 'rgba(180,205,255,0)');
      ctx.fillStyle = band;
      ctx.fillRect(0, h * 0.4, w, h * 0.24);
      for (let i = 0; i < 900; i += 1) {
        const x = rnd() * w;
        const y = h * 0.42 + Math.pow(rnd(), 1.7) * h * 0.18;
        ctx.fillStyle = `rgba(226,238,255,${0.15 + rnd() * 0.5})`;
        ctx.fillRect(x, y, 1, 1);
      }

      // 星点：少量亮星带十字光芒
      for (let i = 0; i < 460; i += 1) {
        const x = rnd() * w;
        const y = rnd() * h;
        const bright = rnd();
        const r = bright > 0.94 ? 1.8 : bright > 0.7 ? 1.1 : 0.7;
        const tint = rnd() > 0.86 ? '255,226,190' : rnd() > 0.6 ? '200,224,255' : '255,255,255';
        ctx.fillStyle = `rgba(${tint},${0.35 + bright * 0.65})`;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
        if (bright > 0.96) {
          ctx.strokeStyle = 'rgba(255,255,255,0.28)';
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(x - 6, y);
          ctx.lineTo(x + 6, y);
          ctx.moveTo(x, y - 6);
          ctx.lineTo(x, y + 6);
          ctx.stroke();
        }
      }
    },
    (texture) => {
      texture.mapping = THREE.EquirectangularReflectionMapping;
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;
    },
  );
}

/**
 * 舰内环境反射（等距柱状）：上半是舱顶灯带、下半是甲板反射。
 *
 * 这里没有用 RoomEnvironment + PMREMGenerator —— buildShip 只拿到 scene，
 * 拿不到 WebGLRenderer，而 PMREMGenerator 必须由 renderer 构造（再建一个
 * 离屏 renderer 会多占一个 WebGL 上下文，得不偿失）。改成手绘等距柱状贴图后，
 * three 的 WebGLCubeUVMaps 会在首次渲染时自动对它做 PMREM 卷积，
 * 金属材质照样能拿到带方向性的环境光。
 */
export function environmentTexture(): THREE.Texture {
  return createCanvasTexture(
    'environment',
    256,
    128,
    (ctx, w, h) => {
      const sky = ctx.createLinearGradient(0, 0, 0, h);
      sky.addColorStop(0, '#2b3d52');
      sky.addColorStop(0.42, '#1b2836');
      sky.addColorStop(0.52, '#0d131b');
      sky.addColorStop(1, '#070a0f');
      ctx.fillStyle = sky;
      ctx.fillRect(0, 0, w, h);

      // 舱顶灯（上部亮斑）：给金属一条明显的顶光
      const lamps: Array<[number, number, number, string]> = [
        [0.18, 0.14, 34, 'rgba(198,236,255,0.85)'],
        [0.5, 0.1, 40, 'rgba(255,228,190,0.75)'],
        [0.82, 0.16, 30, 'rgba(198,236,255,0.7)'],
        [0.32, 0.3, 22, 'rgba(56,225,255,0.35)'],
        [0.68, 0.28, 22, 'rgba(56,225,255,0.3)'],
      ];
      for (const [fx, fy, r, color] of lamps) {
        const x = fx * w;
        const y = fy * h;
        const g = ctx.createRadialGradient(x, y, 0, x, y, r);
        g.addColorStop(0, color);
        g.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = g;
        ctx.fillRect(x - r, y - r, r * 2, r * 2);
      }

      // 甲板侧：冷色反射 + 一点橙色警示灯
      const floor = ctx.createRadialGradient(w * 0.5, h, 0, w * 0.5, h, h * 0.8);
      floor.addColorStop(0, 'rgba(60,90,120,0.35)');
      floor.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = floor;
      ctx.fillRect(0, h / 2, w, h / 2);
      const warn = ctx.createRadialGradient(w * 0.9, h * 0.62, 0, w * 0.9, h * 0.62, 20);
      warn.addColorStop(0, 'rgba(255,155,61,0.4)');
      warn.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = warn;
      ctx.fillRect(w * 0.9 - 20, h * 0.62 - 20, 40, 40);
    },
    (texture) => {
      texture.mapping = THREE.EquirectangularReflectionMapping;
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;
    },
  );
}

/** 接触阴影贴片：黑色径向渐变，贴在甲板上代替实时阴影 */
export function blobShadowTexture(): THREE.Texture {
  return createCanvasTexture(
    'blob-shadow',
    128,
    128,
    (ctx, w, h) => {
      ctx.clearRect(0, 0, w, h);
      const cx = w / 2;
      const cy = h / 2;
      const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, w / 2);
      g.addColorStop(0, 'rgba(0,0,0,0.85)');
      g.addColorStop(0.45, 'rgba(0,0,0,0.55)');
      g.addColorStop(0.78, 'rgba(0,0,0,0.18)');
      g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);
    },
    (texture) => {
      texture.wrapS = THREE.ClampToEdgeWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;
    },
  );
}

/** 柔和光点：星野 Points 与拾取物光晕共用 */
export function softDotTexture(): THREE.Texture {
  return createCanvasTexture(
    'soft-dot',
    64,
    64,
    (ctx, w, h) => {
      ctx.clearRect(0, 0, w, h);
      const g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
      g.addColorStop(0, 'rgba(255,255,255,1)');
      g.addColorStop(0.25, 'rgba(220,246,255,0.75)');
      g.addColorStop(0.6, 'rgba(140,220,255,0.22)');
      g.addColorStop(1, 'rgba(120,200,255,0)');
      ctx.fillStyle = g;
      ctx.fillRect(0, 0, w, h);
    },
    (texture) => {
      texture.wrapS = THREE.ClampToEdgeWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;
    },
  );
}

/** 甲板标识：虚线圆 + 文字 + 四角刻度，用于机库停机位、货舱装载区等 */
export function deckStencilTexture(text: string, sub?: string): THREE.Texture {
  return createCanvasTexture(
    `deck-stencil:${text}:${sub ?? ''}`,
    512,
    512,
    (ctx, w, h) => {
      ctx.clearRect(0, 0, w, h);
      const cx = w / 2;
      const cy = h / 2;

      ctx.strokeStyle = 'rgba(255,255,255,0.55)';
      ctx.lineWidth = 5;
      ctx.setLineDash([26, 18]);
      ctx.beginPath();
      ctx.arc(cx, cy, 210, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.lineWidth = 3;
      ctx.strokeStyle = 'rgba(255,255,255,0.35)';
      ctx.beginPath();
      ctx.arc(cx, cy, 176, 0, Math.PI * 2);
      ctx.stroke();

      // 四角刻度：甲板定位用的十字标
      for (let i = 0; i < 4; i += 1) {
        const a = (Math.PI / 2) * i + Math.PI / 4;
        const x = cx + Math.cos(a) * 240;
        const y = cy + Math.sin(a) * 240;
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(a);
        ctx.fillStyle = 'rgba(255,255,255,0.5)';
        ctx.fillRect(-22, -4, 44, 8);
        ctx.restore();
      }

      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = 'rgba(255,255,255,0.72)';
      ctx.font = sansFont(64, 700);
      ctx.fillText(text.slice(0, 10), cx, sub ? cy - 16 : cy);
      if (sub) {
        ctx.font = monoFont(30, 500);
        ctx.fillStyle = 'rgba(255,255,255,0.5)';
        ctx.fillText(sub.toUpperCase().slice(0, 22), cx, cy + 44);
      }
    },
    (texture) => {
      texture.wrapS = THREE.ClampToEdgeWrapping;
      texture.wrapT = THREE.ClampToEdgeWrapping;
    },
  );
}

/**
 * 释放并清空贴图缓存。
 *
 * React StrictMode 下组件会「挂载 → 卸载 → 再挂载」，卸载时必须把 GPU 上的
 * 贴图还回去；下次 buildShip 会按需重新生成（这些画布都很小，重建代价可忽略）。
 */
export function disposeTextureCache(): void {
  for (const texture of cache.values()) texture.dispose();
  cache.clear();
}
