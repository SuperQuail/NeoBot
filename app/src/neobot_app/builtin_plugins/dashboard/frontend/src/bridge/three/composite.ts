// composite.ts —— 面板的全息合成层（叠在场景之上、DOM 面板之下）
//
// ## 这一层负责什么
//
// 用 matrix3d 投影出来的 DOM 面板永远画在 canvas **之上**，所以「面板是投影在
// 空气里的一块光」这件事得靠额外一层来补：在 canvas 之上、DOM 面板之下再叠一个
// 透明 WebGL 层，在**面板投影所在的四边形**上画边缘辉光、扫描线、网格与展开时
// 扫过的那道亮线。DOM 面板半透明，底层的光就透出来，观感才成立。
//
// 顺序：主 canvas → 本层的 overlay canvas → 面板 DOM。
//
// ## 遮挡不在这里做
//
// 这里曾经还有一条「按场景深度裁剪全息辉光」的链路：把舰体重绘到离屏目标、
// 比较相机空间深度、再读回一张 8×8 的遮罩图算可见比例。那条链路有两个致命的
// 结构性问题，且都已经实证：
//
//   1. **跨上下文**：离屏目标由本层（第二个 WebGL 上下文）创建，真正画进去的却是
//      引擎的主上下文。同一个 WebGLRenderTarget 不能跨上下文使用，本层采样到的
//      永远是没写过的空纹理 —— 逐像素遮挡从未生效。
//   2. **同步回读**：为了拿那个可见比例，每 6 帧要做一次 GPU 同步回读，实测占掉
//      主线程 38% 的时间（单次阻塞约 240ms），表现就是「一开面板就卡死」。
//
// 现在遮挡改由 core/occlusion.ts 在 CPU 上用碰撞盒做线段求交，算出一个 0~1 的
// 可见比例，再乘进面板的整体不透明度（见 ui/PanelAnchor.tsx）。这里只保留合成。

import * as THREE from 'three';
import type { Corner } from './projector';

const OVERLAY_VERT = /* glsl */ `
  // 顶点已经是屏幕像素坐标，这里换算成 NDC
  uniform vec2 uViewport;
  attribute float aCorner;
  void main() {
    vec2 ndc = vec2(position.x / uViewport.x * 2.0 - 1.0, 1.0 - position.y / uViewport.y * 2.0);
    gl_Position = vec4(ndc, 0.0, 1.0);
  }
`;

const OVERLAY_FRAG = /* glsl */ `
  precision highp float;
  uniform vec2 uViewport;
  uniform float uTime;
  uniform float uReveal;   // 0..1 展开动画
  uniform float uOpacity;  // 整体不透明度（含距离衰减与遮挡可见度）
  uniform vec3 uAccent;    // 主色（青）
  uniform vec3 uAccent2;   // 辅色（品红/琥珀），用于边缘色散

  void main() {
    vec2 uv = gl_FragCoord.xy / uViewport;
    // 面板中心相对屏幕中心的归一化坐标：用于算辉光与扫描线
    vec2 rel = uv - 0.5;
    float radial = length(rel * vec2(1.0, 0.85));

    // ---- 全息质感 ----
    float scan = 0.5 + 0.5 * sin((gl_FragCoord.y + uTime * 240.0) * 1.6);
    float scanMask = 0.06 * scan;
    float grid = step(0.985, fract(gl_FragCoord.x / 7.0)) + step(0.985, fract(gl_FragCoord.y / 7.0));
    float gridMask = 0.035 * grid;
    float flicker = 0.965 + 0.035 * sin(uTime * 37.0) * sin(uTime * 13.3);
    // 边缘辉光：越靠外越亮，模拟全息投影在空气中的散射
    float rim = smoothstep(0.30, 0.62, radial);
    // 展开动画：一道由下往上扫过的亮线
    float sweep = smoothstep(0.0, 0.08, uReveal - uv.y) * (1.0 - smoothstep(0.08, 0.22, uReveal - uv.y));

    vec3 color = uAccent * (0.10 + rim * 0.55 + gridMask + scanMask + sweep * 0.9);
    color += uAccent2 * rim * rim * 0.35;
    float alpha = (0.10 + rim * 0.42 + gridMask + scanMask + sweep * 0.75) * uOpacity;

    gl_FragColor = vec4(color * flicker, clamp(alpha, 0.0, 0.9));
  }
`;

export interface PanelCompositeInput {
  quad: [Corner, Corner, Corner, Corner];
  reveal: number;
  opacity: number;
  accent: THREE.Color;
  accent2: THREE.Color;
}

export interface PanelCompositorOptions {
  /**
   * 注入渲染器，**仅供测试**：jsdom 里造不出 WebGL 上下文，
   * 有了这个口子才能直接断言「本层不再做任何 GPU 回读」。
   */
  renderer?: THREE.WebGLRenderer;
}

/**
 * 面板全息合成器。
 *
 * ## 为什么要第二个渲染器
 *
 * 主渲染器每帧已经把画面画进默认帧缓冲，要在其上再叠一层就得改整条渲染流程
 * （后处理链 / RT 转存 / 手动 blit），改动面大且容易碰坏既有效果。这里改成
 * 「叠一个透明 canvas」：顺序上是 主 canvas → 合成 canvas → DOM 面板，
 * 面板的 HTML 从最上层透出来，全息辉光与噪点由合成层贡献。
 *
 * 多一个 GL 上下文是这里唯一的代价：浏览器上限通常 16 个，本方案只用 2 个。
 * 注意它只负责**画**，不负责读 —— 任何 readPixels 都会把主线程钉住（见文件头）。
 */
export class PanelCompositor {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly overlayScene = new THREE.Scene();
  private readonly overlayCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private readonly material: THREE.ShaderMaterial;
  private readonly geometry: THREE.BufferGeometry;
  private supported = true;

  constructor(canvas: HTMLCanvasElement, options: PanelCompositorOptions = {}) {
    if (options.renderer) {
      this.renderer = options.renderer;
    } else {
      try {
        this.renderer = new THREE.WebGLRenderer({
          canvas,
          alpha: true,
          antialias: false,
          premultipliedAlpha: false,
          powerPreference: 'low-power',
        });
      } catch {
        // 拿不到第二个上下文也不能让整个舰桥挂掉：退化成「没有辉光」，
        // 面板本身（DOM 层）照常显示
        this.supported = false;
        this.renderer = {
          setSize() {},
          setPixelRatio() {},
          setClearColor() {},
          setRenderTarget() {},
          clear() {},
          render() {},
          dispose() {},
        } as unknown as THREE.WebGLRenderer;
      }
    }
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.autoClear = true;

    this.material = new THREE.ShaderMaterial({
      vertexShader: OVERLAY_VERT,
      fragmentShader: OVERLAY_FRAG,
      transparent: true,
      depthTest: false,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uViewport: { value: new THREE.Vector2(1, 1) },
        uTime: { value: 0 },
        uReveal: { value: 0 },
        uOpacity: { value: 1 },
        uAccent: { value: accentColor() },
        uAccent2: { value: new THREE.Color(0xff3bd0) },
      },
    });

    // 两个三角形拼出面板四边形，位置每帧由 CPU 写入
    this.geometry = new THREE.BufferGeometry();
    this.geometry.setAttribute(
      'position',
      new THREE.BufferAttribute(new Float32Array(6 * 3), 3).setUsage(THREE.DynamicDrawUsage),
    );
    this.geometry.setAttribute(
      'aCorner',
      new THREE.BufferAttribute(new Float32Array([0, 1, 2, 0, 2, 3]), 1).setUsage(THREE.StaticDrawUsage),
    );
    this.overlayScene.add(new THREE.Mesh(this.geometry, this.material));
  }

  /** 第二个 GL 上下文是否可用（不可用时退化成「没有辉光」，面板本身照常显示） */
  get isSupported(): boolean {
    return this.supported;
  }

  /** 合成：在面板四边形上画全息层 */
  draw(input: PanelCompositeInput, viewportWidth: number, viewportHeight: number): void {
    if (!this.supported) return;
    const { quad } = input;
    const position = this.geometry.getAttribute('position') as THREE.BufferAttribute;
    const order = [0, 1, 2, 0, 2, 3];
    for (let i = 0; i < order.length; i += 1) {
      const corner = quad[order[i]];
      position.setXYZ(i, corner.x, corner.y, 0);
    }
    position.needsUpdate = true;
    this.geometry.computeBoundingSphere();

    const uniforms = this.material.uniforms;
    uniforms.uViewport.value.set(viewportWidth, viewportHeight);
    uniforms.uTime.value = performance.now() / 1000;
    uniforms.uReveal.value = input.reveal;
    uniforms.uOpacity.value = input.opacity;
    (uniforms.uAccent.value as THREE.Color).copy(input.accent);
    (uniforms.uAccent2.value as THREE.Color).copy(input.accent2);

    this.renderer.setRenderTarget(null);
    this.renderer.clear();
    this.renderer.render(this.overlayScene, this.overlayCamera);
  }

  /** 清空合成层（面板关闭时调用，否则上一帧的辉光会留在画面上） */
  clear(): void {
    if (!this.supported) return;
    this.renderer.setRenderTarget(null);
    this.renderer.clear();
  }

  resize(width: number, height: number, pixelRatio: number): void {
    if (!this.supported) return;
    this.renderer.setPixelRatio(Math.min(pixelRatio, 1.5));
    this.renderer.setSize(width, height, false);
  }

  dispose(): void {
    this.geometry.dispose();
    this.material.dispose();
    this.renderer.dispose();
  }
}

/** 主色取自主题变量，读不到时回退到舰体的青色 */
function accentColor(): THREE.Color {
  const fallback = new THREE.Color(0x3fe0ff);
  if (typeof window === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
  return value ? new THREE.Color(value) : fallback;
}
