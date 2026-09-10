// projector.ts —— 把 DOM 面板投影到三维空间中的平面上
//
// ## 为什么是 matrix3d 而不是 CSS3DRenderer
//
// 面板内容是真正的 HTML（要滚动、要表单、要中文 IME、要能复制日志），
// 不可能退化成纹理。让 HTML「出现在世界里的某块平面上」的标准做法是
// `matrix3d` 投影：CSS 支持完整 4x4 矩阵 + perspective，能精确复刻相机投影。
//
// three 官方的 CSS3DRenderer 做的是同一件事，但它自己管 DOM 层与渲染循环，
// 我们还需要「按深度被场景遮挡」的合成步骤（见 composite.ts），自己算矩阵更好接。
//
// ## 数学
//
// 平面基点选在面板**左下角**（与 CSS transform-origin: 0 0 对齐），元素局部坐标
// (x, y) 直接就是「向右 x 米、向上 y 米」，于是：
//
//   世界坐标 = 面板中心 + facing·(-w/2) + right·x + up·y
//   相机坐标 = viewMatrix · 世界坐标
//   屏幕坐标 = projectionMatrix · 相机坐标   （CSS 的 perspective 会自己做这一步）
//
// 传给 CSS 的矩阵是 view·plane（不含投影），perspective 距离取相机焦距，
// perspective-origin 取相机主点在容器里的位置——这样 CSS 投影出的结果与
// WebGL 相机**逐像素一致**，面板看起来就是贴在场景里的一张纸。
//
// ## 面板尺寸怎么定
//
// 终端屏幕本身只有 0.8~1.6m 宽，直接按屏幕尺寸投影会让字号小到不可读。
// 所以面板按「可读视距」设计：宽度取 max(屏幕宽, 视距·tan(视场)·0.8)，
// 让它在 2.5m 处大约占屏幕宽度的 80%——像人凑到终端前看，而不是看一张贴纸。

import * as THREE from 'three';

export interface PanelPlane {
  /** 面板中心（世界坐标） */
  center: THREE.Vector3;
  /** 单位右向量（世界坐标） */
  right: THREE.Vector3;
  /** 单位上向量（世界坐标） */
  up: THREE.Vector3;
  /** 单位法向量 = right × up，指向玩家的那一侧 */
  normal: THREE.Vector3;
  /** 面板宽度（米） */
  width: number;
  /** 面板高度（米） */
  height: number;
}

export interface ProjectedPanel {
  /**
   * 可直接写进 style.transform 的值。
   *
   * 约定与 three 的 CSS3DRenderer 完全一致（见其 getCameraCSSMatrix：
   * 相机矩阵的第 2 行要取负），因为 CSS 的 Y 轴向下、three 的 Y 轴向上：
   *   transform-origin: 0 0
   *   perspective-origin: 0 0（即元素左上角）——由 principalX/Y 给出消失点，
   *   因此这里把 perspective 与视角原点一起交给调用方写入 style。
   */
  transform: string;
  /** CSS 视角原点（元素内像素坐标）：相机主光轴与面板平面的交点 */
  principalX: number;
  principalY: number;
  /** 容器内像素坐标下的四个角：顺序见 QUAD_ORDER */
  quad: [Corner, Corner, Corner, Corner];
  /** 面板中心到相机的距离（米），用于接管判定与淡出 */
  distance: number;
  /** 面板法线与视线方向的夹角余弦：<0 表示背对相机 */
  facing: number;
  /** 是否在相机背后（此时不应渲染） */
  behind: boolean;
}

export interface Corner {
  /** 容器内像素坐标 */
  x: number;
  y: number;
  /** 相机空间深度（正数，米），用于深度合成时与场景比较 */
  depth: number;
}

/**
 * 四角顺序固定为：左下 → 右下 → 右上 → 左上。
 * composite 层用这个顺序拼两个三角形 (0,1,2) 与 (0,2,3)，
 * 深度按 1/z 线性插值（平面在屏幕空间的 1/z 是线性的，这样遮挡边缘才准）。
 */
export const QUAD_ORDER = ['bottomLeft', 'bottomRight', 'topRight', 'topLeft'] as const;

/**
 * 面板元素自身的像素尺寸与米数的换算（PIXELS_PER_METER）。
 *
 * 投影矩阵按米缩放，CSS 视角原点要换算到元素像素坐标，两边必须用同一个系数；
 * 因此这里导出，PanelAnchor 用它设置元素尺寸，projector 用它算消失点。
 */
export const PIXELS_PER_METER = 150;

/**
 * 由「站位 + 朝向」推出面板应该贴在哪块平面上。
 *
 * @param anchor   终端站位（脚下坐标，面板会抬到 screenHeight 高度）
 * @param facing   终端朝向（0=+z，π=-z，±π/2=∓x），与 STATIONS.facing 同义
 * @param screenOffset 面板中心相对锚点的偏移（沿 facing / 法线方向，米）
 */
export function panelPlaneFromStation(
  anchor: readonly [number, number, number],
  facing: number,
  options: {
    /** 面板中心高度（米，甲板面之上） */
    height?: number;
    /** 面板中心向玩家一侧推出的距离（米） */
    forward?: number;
    /** 面板宽度（米） */
    width?: number;
    /** 面板高度（米） */
    heightMeters?: number;
  } = {},
): PanelPlane {
  const height = options.height ?? 1.5;
  const forward = options.forward ?? 0.55;
  const width = options.width ?? 2.1;
  const heightMeters = options.heightMeters ?? 1.35;

  // facing=0 时终端面向 +z：法线 = (sin, 0, cos)
  const normal = new THREE.Vector3(Math.sin(facing), 0, Math.cos(facing)).normalize();
  // 面板「+x」对应的世界方向。
  //
  // 这里取的是**朝向玩家时的左手边**，看似别扭，但它是唯一能让面板文字正着显示的选择：
  // CSS 元素局部 +x 必须映射到「玩家看到的右边」，而本世界的坐标约定下
  // (玩家右, 上, 法线) 构成的是左手基（det = -1），直接用 makeBasis 建出来的
  // 面板矩阵会把内容**水平镜像**——文字会左右翻过来，这是必须避免的。
  // 取负号后 det = +1，投影出来才是正常的正字。
  const right = new THREE.Vector3(Math.cos(facing), 0, -Math.sin(facing)).normalize();
  const up = new THREE.Vector3(0, 1, 0);
  const center = new THREE.Vector3(anchor[0], anchor[1] + height, anchor[2]).addScaledVector(
    normal,
    forward,
  );

  return { center, right, up, normal, width, height: heightMeters };
}

/**
 * 把平面投影到屏幕。
 *
 * @param camera   引擎相机（每帧已由 Player.applyToCamera 更新）
 * @param width    画布 CSS 像素宽
 * @param height   画布 CSS 像素高
 * @param lift     面板整体沿法线的额外抬升（米），用于「从屏幕里浮出来」的动画
 */
export function projectPanel(
  camera: THREE.PerspectiveCamera,
  plane: PanelPlane,
  width: number,
  height: number,
  lift = 0,
): ProjectedPanel {
  const center = plane.center.clone().addScaledVector(plane.normal, lift);

  // ---- CSS 用的 view·plane 矩阵 ----
  //
  // 与 three 的 CSS3DRenderer 保持同一约定：相机矩阵的第 2 行（Y 行）取负。
  // 原因是 CSS 的 Y 轴朝下、three 的朝上，不取负面板会上下颠倒。
  const planeMatrix = new THREE.Matrix4().makeBasis(plane.right, plane.up, plane.normal);
  planeMatrix.setPosition(center);
  const view = new THREE.Matrix4().copy(camera.matrixWorld).invert();
  const local = view.clone().multiply(planeMatrix);
  const e = local.elements;
  const cssElements = [
    e[0], -e[1], e[2], e[3],
    e[4], -e[5], e[6], e[7],
    e[8], -e[9], e[10], e[11],
    e[12], -e[13], e[14], e[15],
  ];
  const transform = `matrix3d(${cssElements
    .map((value) => (Math.abs(value) < 1e-6 ? 0 : Number(value.toFixed(6))))
    .join(',')})`;

  // ---- 消失点：相机主光轴与面板平面的交点（元素内像素坐标） ----
  // CSS 的 perspective-origin 默认是元素中心，而面板很大且不透明，
  // 不修正就会出现「透视往元素中心收」的错位；这里显式给出正确的视角原点。
  const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion).normalize();
  const denominator = forward.dot(plane.normal);
  const principal = new THREE.Vector3();
  if (Math.abs(denominator) > 1e-4) {
    const t = camera.position.clone().sub(center).dot(plane.normal) / denominator;
    principal.copy(camera.position).addScaledVector(forward, t);
  } else {
    principal.copy(center);
  }
  const offset = principal.clone().sub(center);
  const principalX = (offset.dot(plane.right) + plane.width / 2) * PIXELS_PER_METER;
  // 同样取负：CSS 的 Y 向下
  const principalY = (-offset.dot(plane.up) + plane.height / 2) * PIXELS_PER_METER;

  // ---- 四角在屏幕上的位置 + 相机空间深度 ----
  const halfW = plane.width / 2;
  const halfH = plane.height / 2;
  const localCorners: Array<[number, number]> = [
    [-halfW, -halfH],
    [halfW, -halfH],
    [halfW, halfH],
    [-halfW, halfH],
  ];

  const world = new THREE.Vector3();
  const clip = new THREE.Vector4();
  const quad = localCorners.map(([lx, ly]) => {
    world
      .copy(center)
      .addScaledVector(plane.right, lx)
      .addScaledVector(plane.up, ly)
      // 相机空间深度：相机朝自身 -z 看，取正值表示「在相机前方多少米」
      .applyMatrix4(view);
    const depth = -world.z;
    clip.set(world.x, world.y, world.z, 1).applyMatrix4(camera.projectionMatrix);
    const invW = 1 / Math.max(1e-6, Math.abs(clip.w));
    const ndcX = clip.x * invW;
    const ndcY = clip.y * invW;
    return {
      x: ((ndcX + 1) / 2) * width,
      y: ((1 - ndcY) / 2) * height,
      depth,
    };
  }) as [Corner, Corner, Corner, Corner];

  const toCamera = camera.position.clone().sub(center);
  const distance = toCamera.length();
  const facing = distance < 1e-4 ? 1 : toCamera.normalize().dot(plane.normal);

  return { transform, principalX, principalY, quad, distance, facing, behind: facing <= 0.02 };
}

/** 面板的透视距离：取相机焦距（垂直视场角），CSS 用它才能与 WebGL 完全一致 */
export function perspectiveDistance(camera: THREE.PerspectiveCamera, viewportHeight: number): number {
  const fovRadians = (camera.fov * Math.PI) / 180;
  return viewportHeight / 2 / Math.tan(fovRadians / 2);
}
