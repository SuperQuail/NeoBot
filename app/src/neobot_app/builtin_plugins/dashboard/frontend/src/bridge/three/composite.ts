// composite.ts —— 用场景深度给 DOM 面板做遮挡与全息合成
//
// ## 问题
//
// 用 matrix3d 投影出来的 DOM 面板永远画在 canvas **之上**：相机贴着舱壁时，
// 面板会穿墙浮在墙外面，「贴在场景里」的错觉立刻崩掉。赛博朋克那种终端观感
// 的前提是「面板被世界挡住一部分」。
//
// ## 做法
//
// 1. 深度预处理：把舰体几何用一个只写深度的材质重绘到 1x1 的离屏目标里，
//    把「归一化深度」打包进 RGBA（4 字节，精度足够）。
// 2. 合成：在 canvas 之上再叠一个 WebGL 层，在**面板投影所在的四边形**上
//    画效果（边缘辉光、扫描线、全息噪点），并按深度比较结果决定每个像素的
//    alpha——被场景挡住的像素 alpha 为 0，于是 DOM 层从那里透出来的是场景本身。
//
// 深度比较用的是相机空间 z（米），不是 NDC 深度：伪线性化和精度问题都省了。
// 四边形内部按 1/z 线性插值——平面在屏幕空间的 1/z 是线性的，
// 这样遮挡边界（比如门框切过面板）才对得准。

import * as THREE from 'three';
import type { Corner } from './projector';

const PACK_VERT = /* glsl */ `
  varying float vDepth;
  void main() {
    vec4 view = modelViewMatrix * vec4(position, 1.0);
    vDepth = -view.z;
    gl_Position = projectionMatrix * view;
  }
`;

const PACK_FRAG = /* glsl */ `
  varying float vDepth;
  void main() {
    // 把 0..1 的深度摊到 4 个字节：远离相机处精度自动变粗，正好符合需要
    float d = clamp(vDepth / 1000.0, 0.0, 1.0);
    vec4 enc = fract(d * vec4(1.0, 255.0, 65025.0, 16581375.0));
    enc -= enc.yzww * vec4(1.0 / 255.0, 1.0 / 255.0, 1.0 / 255.0, 0.0);
    gl_FragColor = enc;
  }
`;

const OVERLAY_VERT = /* glsl */ `
  // 顶点已经是屏幕像素坐标，这里换算成 NDC；同时传 1/z 供片元线性插值
  uniform vec2 uViewport;
  uniform vec4 uDepths;
  attribute float aCorner;
  varying float vInvZ;
  void main() {
    vec2 ndc = vec2(position.x / uViewport.x * 2.0 - 1.0, 1.0 - position.y / uViewport.y * 2.0);
    float depth = mix(mix(uDepths.x, uDepths.y, aCorner), mix(uDepths.w, uDepths.z, aCorner), step(1.5, aCorner));
    vInvZ = 1.0 / max(0.05, depth);
    gl_Position = vec4(ndc, 0.0, 1.0);
  }
`;

const OVERLAY_FRAG = /* glsl */ `
  precision highp float;
  uniform sampler2D uDepth;
  uniform vec2 uViewport;
  uniform float uTime;
  uniform float uReveal;   // 0..1 展开动画
  uniform float uOpacity;  // 整体不透明度（淡入淡出）
  uniform vec3 uAccent;    // 主色（青）
  uniform vec3 uAccent2;   // 辅色（品红/琥珀），用于边缘色散
  varying float vInvZ;

  float unpack(vec4 c) {
    return dot(c, vec4(1.0, 1.0 / 255.0, 1.0 / 65025.0, 1.0 / 16581375.0)) * 1000.0;
  }

  void main() {
    vec2 uv = gl_FragCoord.xy / uViewport;
    // 面板中心相对屏幕中心的归一化坐标：用于算辉光与扫描线
    vec2 rel = uv - 0.5;
    float radial = length(rel * vec2(1.0, 0.85));

    // ---- 遮挡：场景深度比面板更近 => 被挡住 ----
    float sceneDepth = unpack(texture2D(uDepth, uv));
    float panelDepth = 1.0 / max(0.05, vInvZ);
    float occluded = step(panelDepth - 0.04, sceneDepth);

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

    // 被遮挡处直接丢弃：DOM 面板从那里透出来的是场景本身，边缘因此会「切」过面板
    alpha *= (1.0 - occluded);

    gl_FragColor = vec4(color * flicker, clamp(alpha, 0.0, 0.9));
  }
`;

/** 深度目标尺寸：深度只需要在遮挡边界处准，半分辨率足够且更省 */
const DEPTH_SCALE = 0.5;

export interface PanelCompositeInput {
  quad: [Corner, Corner, Corner, Corner];
  reveal: number;
  opacity: number;
  accent: THREE.Color;
  accent2: THREE.Color;
}

/**
 * 面板合成器。
 *
 * ## 为什么要两个渲染器
 *
 * 主渲染器每帧已经把画面画进默认帧缓冲，要在其上再叠一层就得改整条渲染流程
 * （后处理链 / RT 转存 / 手动 blit），改动面大且容易碰坏既有效果。
 * 这里改成「叠一个透明 canvas」：顺序上是 主 canvas → 合成 canvas → DOM 面板，
 * 面板的 HTML 从最上层透出来，全息辉光与噪点由合成层贡献，被遮挡的像素则由
 * 深度比较结果把 DOM 面板**裁掉**（见 draw 里对 CSS mask 的用法）。
 *
 * 多一个 GL 上下文是这里唯一的代价：浏览器上限通常 16 个，本方案只用 2 个。
 *
 * ## 深度预处理为什么要回调
 *
 * WebGLRenderTarget 属于创建它的 GL 上下文，不能跨上下文用。而舰体几何与相机
 * 都在**主渲染器**的场景里，因此深度这一步必须由主渲染器来画：
 * captureDepth 只负责「借出」自己的 render target，真正的 render 由调用方执行。
 */
export class PanelCompositor {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly overlayScene = new THREE.Scene();
  private readonly overlayCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  private readonly material: THREE.ShaderMaterial;
  private readonly geometry: THREE.BufferGeometry;
  private readonly depthTarget: THREE.WebGLRenderTarget;
  private readonly packMaterial: THREE.ShaderMaterial;
  private supported = true;

  constructor(canvas: HTMLCanvasElement) {
    try {
      this.renderer = new THREE.WebGLRenderer({
        canvas,
        alpha: true,
        antialias: false,
        premultipliedAlpha: false,
        powerPreference: 'low-power',
      });
    } catch {
      // 拿不到第二个上下文也不能让整个舰桥挂掉：退化成「无遮挡的全息层」由 CSS 承担
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
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.autoClear = true;

    this.depthTarget = new THREE.WebGLRenderTarget(2, 2, {
      minFilter: THREE.NearestFilter,
      magFilter: THREE.NearestFilter,
      depthBuffer: true,
      stencilBuffer: false,
    });

    this.packMaterial = new THREE.ShaderMaterial({
      vertexShader: PACK_VERT,
      fragmentShader: PACK_FRAG,
      side: THREE.DoubleSide,
    });

    this.material = new THREE.ShaderMaterial({
      vertexShader: OVERLAY_VERT,
      fragmentShader: OVERLAY_FRAG,
      transparent: true,
      depthTest: false,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uDepth: { value: this.depthTarget.texture },
        uViewport: { value: new THREE.Vector2(1, 1) },
        uTime: { value: 0 },
        uReveal: { value: 0 },
        uOpacity: { value: 1 },
        uAccent: { value: accentColor() },
        uAccent2: { value: new THREE.Color(0xff3bd0) },
        uDepths: { value: new THREE.Vector4(1, 1, 1, 1) },
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

  get isSupported(): boolean {
    return this.supported;
  }

  /** 深度目标尺寸，供调用方在 resize 时提供 */
  get depthSize(): { width: number; height: number } {
    return { width: this.depthTarget.width, height: this.depthTarget.height };
  }

  /**
   * 预处理场景深度。
   *
   * 调用方（engine）用自己的渲染器把舰体几何画进这里借出的 render target：
   * 期间要把材质临时换成只写深度的 packMaterial，画完立刻还原。
   */
  captureDepth(render: (target: THREE.WebGLRenderTarget, material: THREE.Material) => void): void {
    if (!this.supported) return;
    render(this.depthTarget, this.packMaterial);
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
    (uniforms.uDepths.value as THREE.Vector4).set(
      quad[0].depth,
      quad[1].depth,
      quad[2].depth,
      quad[3].depth,
    );

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
    this.depthTarget.setSize(
      Math.max(2, Math.floor(width * DEPTH_SCALE)),
      Math.max(2, Math.floor(height * DEPTH_SCALE)),
    );
  }

  dispose(): void {
    this.geometry.dispose();
    this.material.dispose();
    this.packMaterial.dispose();
    this.depthTarget.dispose();
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
