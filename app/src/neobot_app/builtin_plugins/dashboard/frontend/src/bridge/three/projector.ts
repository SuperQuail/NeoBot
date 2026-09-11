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
   * 形式是**单个 matrix3d**：把元素自己的像素坐标（左上原点、y 向下）直接映射到
   * 视口像素坐标（左上原点、y 向下）。调用方只需要 `transform-origin: 0 0`，
   * 既不需要 `perspective()` 也不需要 perspective-origin —— 透视已经在矩阵的
   * 第 4 行里（w = -z），推导见 projectPanel。
   */
  transform: string;
  /**
   * 上面那条 matrix3d 的 16 个分量（列主序，与 CSS 相同）。
   *
   * 单独给出来是为了能被测试直接验算：把元素四角代进去做齐次除法，
   * 结果必须与 quad 逐个吻合 —— 这条正是用来盯住「CSS 投影与 WebGL 对不上」的。
   */
  matrix: number[];
  /** CSS 视角原点（元素内像素坐标）：相机主光轴与面板平面的交点 */
  principalX: number;
  principalY: number;
  /** 容器内像素坐标下的四个角：顺序见 QUAD_ORDER */
  quad: [Corner, Corner, Corner, Corner];
  /** 面板中心到相机的距离（米），用于接管判定与淡出 */
  distance: number;
  /** 面板法线与视线方向的夹角余弦：<0 表示背对相机 */
  facing: number;
  /**
   * 面板是否落在相机背后（此时不应渲染）。
   *
   * 判据有两条，缺一不可：
   *   · 相机在面板的正面一侧（facing > 0）——否则看到的是面板背面；
   *   · 面板整个落在相机前方（每个角的相机空间深度都 > 0）。
   *
   * 只判第一条是不够的：玩家转过身背对终端时，相机仍在面板正面一侧，
   * 但面板已经跑到相机背后了。此时写进 CSS 的矩阵会把面板投影到屏幕外
   * （实测落在 x ≈ -577px，正好差一个视口宽度），DOM 元素跟着飘出可视区，
   * 「面板就在旁边」的错觉和可点击性一起没了。
   *
   * 逐角判而不是只判中心：面板比玩家近时会有角越过相机平面，齐次矩阵在那里
   * 会翻号，画出来的内容是镜像的乱码。
   */
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
 * 这个系数同时决定两件事：
 *   · **元素内部有多少排版空间**（px）—— 面板内容是桌面级界面，正文 13px、
 *     抬头一行（编号 + 标题 + 两个按钮）至少 640px 才排得下；
 *   · **面板在场景里的物理尺寸** —— 元素像素 ÷ 这个系数 = 米。
 *
 * 取 240 时 640px 对应约 2.67m：内容排得下，同时仍是一块挂在终端上方、
 * 需要转头去看的投影。曾经取 150，小终端（CPU-05 的屏幕宽 0.86m）算出来
 * 只有 310px 宽，抬头被挤成竖排、按钮溢出机框 —— 就是「显示不完全」。
 */
export const PIXELS_PER_METER = 240;

/**
 * 面板内容的**设计像素尺寸**：低于这个尺寸排版一定会挤爆机框。
 *
 * 所有终端共用同一套机框排版，因此面板平面有一个下限（见 panelPlaneFromScreen）；
 * PanelAnchor 也用它来限制字号补偿的上限，避免把内容放大到超出机框。
 */
export const PANEL_CONTENT_SIZE = { width: 640, height: 430 } as const;

/**
 * 由「终端屏幕 + 朝向」推出面板应该贴在哪块平面上。
 *
 * ## 为什么锚点是屏幕而不是站位
 *
 * 站位锚点在终端机身中心，而玩家为了交互本来就必须站在它正前方 ——
 * 面板一旦挂在站位上，出现时正好顶在脸中央，看起来就是个屏幕 UI，
 * 完全不像场景里的东西。真实游戏（赛博朋克 2077 的终端、Elite 的面板）
 * 都把投影挂在**设备自己的屏幕上方**：它会明显偏向一侧，玩家需要转头去看，
 * 「这是舰内某个具体设备的一部分」这件事才成立。
 *
 * @param screen     终端屏幕的世界坐标（STATIONS[i].screen）
 * @param yaw        屏幕朝向（0=+z，±π/2=∓x，π=-z）
 * @param screenSize 屏幕物理尺寸；面板按倍率放大后贴在它上方
 */
export function panelPlaneFromScreen(
  screen: readonly [number, number, number],
  yaw: number,
  screenSize: { width: number; height: number },
  options: {
    /** 面板相对屏幕的放大倍率 */
    scale?: number;
    /** 面板中心相对屏幕中心的竖直偏移（米），正值向上 */
    rise?: number;
    /** 面板向玩家一侧浮出的距离（米） */
    forward?: number;
    /** 宽高比下限，避免窄终端投影出细长条面板 */
    aspect?: number;
  } = {},
): PanelPlane {
  const scale = options.scale ?? 2.4;
  const rise = options.rise ?? 0.62;
  const forward = options.forward ?? 0.42;
  const aspect = options.aspect ?? 1.55;

  // yaw=0 时终端面向 +z：法线 = (sin, 0, cos)
  const normal = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw)).normalize();
  // 面板「+x」对应的世界方向。
  //
  // 取的是**朝向玩家时的左手边**，看似别扭，但这是唯一能让面板文字正着显示的选择：
  // 本世界的 (玩家右, 上, 法线) 构成左手基（det = -1），直接用 makeBasis 建出来的
  // 面板矩阵会把内容**水平镜像**——文字会左右翻过来。取负号后 det = +1。
  const right = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw)).normalize();
  const up = new THREE.Vector3(0, 1, 0);
  const center = new THREE.Vector3(screen[0], screen[1] + rise, screen[2]).addScaledVector(
    normal,
    forward,
  );

  // 宽度 = 屏幕宽 × 倍率，但**不得小于内容的排版宽度**：小终端的屏幕只有
  // 0.8~0.9m，按倍率算出来放不下抬头那一行（编号 / 标题 / 按钮会被挤成竖排）。
  const width = Math.max(screenSize.width * scale, PANEL_CONTENT_SIZE.width / PIXELS_PER_METER);
  // 高度按屏幕比例走，同样兜住内容的高度下限，避免出现细长条
  const height = Math.max(
    width / aspect,
    (screenSize.height * scale * 1.25),
    PANEL_CONTENT_SIZE.height / PIXELS_PER_METER,
  );

  return { center, right, up, normal, width, height };
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

  // ---- CSS 投影矩阵（单应） ----
  //
  // 面板是一块平面，透视投影就是「平面 → 屏幕」的一个 3×3 齐次变换（单应），
  // CSS 的 matrix3d 正好能表达它：第 1、2 列放 x/y 的线性部分，第 4 列放平移，
  // 第 4 行放 w，浏览器做完齐次除法就得到视口像素。
  //
  // ## 为什么不是 `transform: perspective(P) matrix3d(...)`
  //
  // 那是 three 的 CSS3DRenderer 的写法，前提是「世界单位 = CSS 像素」。本场景以
  // **米**为单位，元素尺寸却是 `plane.width × PIXELS_PER_METER` 像素，照搬会把
  // 1 米当成 1 像素：矩阵退化成单位阵（平移只剩零点几像素），面板于是被原样画在
  // 元素尺寸的框里并整体翻到左上角外侧 —— 实测 getBoundingClientRect() 恒为
  // [-577,-372,577,372]，与视口零面积相交，表现就是「接入终端后屏幕只是暗了一下，
  // 什么都没出现」。
  //
  // 正确做法是把两条换算显式写进矩阵：
  //   元素像素 (u,v) --E--> 面板局部米(x,y) --view·plane--> 相机空间米(X,Y,Z)
  //                --内参--> 视口像素(x_s,y_s)，其中 w = -Z
  // 内参由垂直视场角推出焦距 f（像素），主点取视口中心，与 PerspectiveCamera 的
  // 投影矩阵严格一致，CSS 层与 WebGL 层因此逐像素对得上。
  const planeMatrix = new THREE.Matrix4().makeBasis(plane.right, plane.up, plane.normal);
  planeMatrix.setPosition(center);
  const view = new THREE.Matrix4().copy(camera.matrixWorld).invert();
  // E：元素像素（左上原点、y 向下）→ 面板局部米（左下原点、y 向上）
  const elementToPlane = new THREE.Matrix4().set(
    1 / PIXELS_PER_METER, 0, 0, -plane.width / 2,
    0, -1 / PIXELS_PER_METER, 0, plane.height / 2,
    0, 0, 1, 0,
    0, 0, 0, 1,
  );
  const elementToCamera = view.clone().multiply(planeMatrix).multiply(elementToPlane);
  const e = elementToCamera.elements;

  const focal = perspectiveDistance(camera, height);
  const centerX = width / 2;
  const centerY = height / 2;
  // (u,v,1) → 齐次屏幕坐标：x_s = f·X − cx·Z，y_s = −f·Y − cy·Z，w = −Z
  const h00 = focal * e[0] - centerX * e[2];
  const h01 = focal * e[4] - centerX * e[6];
  const h02 = focal * e[12] - centerX * e[14];
  const h10 = -focal * e[1] - centerY * e[2];
  const h11 = -focal * e[5] - centerY * e[6];
  const h12 = -focal * e[13] - centerY * e[14];
  const h20 = -e[2];
  const h21 = -e[6];
  const h22 = -e[14];
  // 列主序：第 1/2 列是 x、y 基向量的像，第 4 列是平移，第 4 行是同次分量
  const cssElements = [
    h00, h10, 0, h20,
    h01, h11, 0, h21,
    0, 0, 1, 0,
    h02, h12, 0, h22,
  ];
  const matrix = cssElements.slice();
  const transform = `matrix3d(${cssElements
    .map((value) => (Math.abs(value) < 1e-6 ? 0 : Number(value.toFixed(6))))
    .join(',')})`;

  // ---- 消失点：相机主光轴与面板平面的交点（元素内像素坐标） ----
  // 不再用于 CSS（透视已经在 matrix3d 里），保留作为排障时的读数。
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

  return {
    transform,
    matrix,
    principalX,
    principalY,
    quad,
    distance,
    facing,
    behind: facing <= 0.02 || quad.some((corner) => corner.depth <= 0.05),
  };
}

/** 面板的透视距离：取相机焦距（垂直视场角），CSS 用它才能与 WebGL 完全一致 */
export function perspectiveDistance(camera: THREE.PerspectiveCamera, viewportHeight: number): number {
  const fovRadians = (camera.fov * Math.PI) / 180;
  return viewportHeight / 2 / Math.tan(fovRadians / 2);
}
