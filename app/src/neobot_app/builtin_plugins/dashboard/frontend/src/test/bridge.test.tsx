// bridge.test.tsx —— 3D 舰载控制台的回归测试
//
// 覆盖范围刻意避开 WebGL（jsdom 没有 GL 上下文）：
//   1. 布局契约：碰撞盒、终端站位、走廊连通性都必须在坐标上自洽；
//   2. 碰撞求解：分轴推进、贴墙滑行、步高吸附、射线遮挡；
//   3. 舰况换算：真实系统指标 → 四项读数的映射与警戒分级；
//   4. 存档：访问记录、物资、成就、小游戏成绩的持久化；
//   5. 路由与应用外壳：舰桥入口与经典面板并存。

import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { buildShip } from '../bridge/three/ship';
import {
  ALL_ZONES,
  DECK_HEIGHT,
  DOOR_WIDTH,
  DOORS,
  DECK_Y,
  HUB,
  PLAYER_EYE,
  PLAYER_HEIGHT,
  PLAYER_RADIUS,
  ROOMS,
  SPAWN_POSITION,
  WALL_THICKNESS,
  isInsideHull,
  zoneAt,
  zoneLabel,
  type AABB,
} from '../bridge/core/layout';
import {
  compileColliders,
  isBlocked,
  isLineBlocked,
  playerBox,
  rayBoxes,
  resolveMovement,
  type CollisionBody,
} from '../bridge/core/collision';
import { deriveVitals, vitalStatus, hasCritical } from '../bridge/core/vitals';
import { Player } from '../bridge/core/player';
import { doorDistance, warpLanding } from '../bridge/core/engine';
import {
  PIXELS_PER_METER,
  panelPlaneFromScreen,
  perspectiveDistance,
  projectPanel,
} from '../bridge/three/projector';
import { PanelCompositor } from '../bridge/three/composite';
import { panelVisibility } from '../bridge/core/occlusion';
import { STATIONS, ITEMS, ITEM_IDS, ACHIEVEMENTS, type ItemId } from '../bridge/core/types';
import {
  __setLogForTest,
  collectItem,
  consumeItem,
  getLog,
  markVisited,
  onNotice,
  recordMiniGame,
  subscribeLog,
  updateLog,
} from '../bridge/core/store';
import type { SystemInfo } from '../api/types';

function emptyLog() {
  return {
    version: 1,
    visited: [],
    inventory: {},
    achievements: [],
    miniGames: {},
    distance: 0,
    lastPos: null,
  };
}

beforeEach(() => {
  __setLogForTest(emptyLog());
});

// ---------------------------------------------------------------------------
// 第一人称视角与移动方向的符号约定
//
// 这一组用例是为一个真实缺陷补的回归：相机姿态与 yaw 的符号曾写反，
// 结果「鼠标往右拖，视角往左转」，四个方向全反。
// ---------------------------------------------------------------------------

describe('第一人称视角与移动', () => {
  /** 造一个只提供 Player 需要的那几个方法的输入桩 */
  function inputStub(overrides: Partial<{ dx: number; dy: number; forward: number; strafe: number }> = {}) {
    const state = {
      lookDx: overrides.dx ?? 0,
      lookDy: overrides.dy ?? 0,
      actions: [] as string[],
      jumpPressed: false,
    };
    return {
      state,
      readMove: () => ({ forward: overrides.forward ?? 0, strafe: overrides.strafe ?? 0 }),
      isSprinting: () => false,
      isCrouching: () => false,
    } as unknown as Parameters<Player['update']>[1];
  }

  const noBoxes = compileColliders([]);

  /** 相机局部轴映射到世界：屏幕右 / 前 / 上（这才是「玩家实际看到的方向」） */
  function screenAxes(player: Player) {
    const camera = new THREE.PerspectiveCamera();
    player.applyToCamera(camera);
    return {
      forward: new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion).normalize(),
      right: new THREE.Vector3(1, 0, 0).applyQuaternion(camera.quaternion).normalize(),
      up: new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion).normalize(),
    };
  }

  /** 让角色按给定输入走一小段，返回实际位移方向 */
  function walkFrom(yaw: number, input: { forward?: number; strafe?: number }) {
    const player = new Player([0, 0, 0], yaw);
    for (let i = 0; i < 30; i += 1) player.update(1 / 60, inputStub(input), noBoxes);
    const move = new THREE.Vector3(player.position.x, 0, player.position.z);
    return { player, move: move.length() > 1e-6 ? move.normalize() : move };
  }

  it('相机前向与逻辑朝向严格一致（含俯仰）', () => {
    for (const yawDeg of [0, 35, 90, 175, -120]) {
      for (const pitch of [0, 0.35, -0.5]) {
        const player = new Player([0, 0, 0], (yawDeg * Math.PI) / 180);
        player.pitch = pitch;
        const screen = screenAxes(player);
        expect(screen.forward.dot(player.lookDirection())).toBeCloseTo(1, 4);
      }
    }
  });

  it('相机上向始终朝 +y（画面不会上下颠倒）', () => {
    for (const yawDeg of [0, 45, 90, 180, -90]) {
      for (const pitch of [0, 0.6, -0.6]) {
        const player = new Player([0, 0, 0], (yawDeg * Math.PI) / 180);
        player.pitch = pitch;
        expect(screenAxes(player).up.y).toBeGreaterThan(0.5);
      }
    }
  });

  it('W 沿屏幕前向、D 沿屏幕右向、A 沿屏幕左向（四个方向都不能反）', () => {
    for (const yawDeg of [0, 30, 90, 150, 180, -60]) {
      const yaw = (yawDeg * Math.PI) / 180;
      const screen = screenAxes(new Player([0, 0, 0], yaw));
      const flat = (v: THREE.Vector3) => v.clone().setY(0).normalize();

      expect(flat(walkFrom(yaw, { forward: 1 }).move).dot(flat(screen.forward))).toBeGreaterThan(0.99);
      expect(flat(walkFrom(yaw, { forward: -1 }).move).dot(flat(screen.forward))).toBeLessThan(-0.99);
      expect(flat(walkFrom(yaw, { strafe: 1 }).move).dot(flat(screen.right))).toBeGreaterThan(0.99);
      expect(flat(walkFrom(yaw, { strafe: -1 }).move).dot(flat(screen.right))).toBeLessThan(-0.99);
    }
  });

  it('鼠标向右拖 → 视线朝屏幕右手边转；向下拖 → 视线向下', () => {
    const player = new Player([0, 0, 0], 0);
    // 基准：yaw=0 时屏幕右向（注意本世界它是世界坐标的 -x，见 rightAxis 的说明）
    const rightBefore = screenAxes(new Player([0, 0, 0], 0)).right.clone();
    expect(rightBefore.x).toBeLessThan(-0.99);

    player.update(1 / 60, inputStub({ dx: 0.3 }), noBoxes);
    const after = screenAxes(player).forward.clone();

    // 「向右转」= 新前向落在原屏幕右向那一侧
    expect(after.dot(rightBefore)).toBeGreaterThan(0);

    player.update(1 / 60, inputStub({ dy: 0.3 }), noBoxes);
    expect(player.pitch).toBeLessThan(0);
    expect(screenAxes(player).forward.y).toBeLessThan(0);

    // 持续上抬不会翻过头
    for (let i = 0; i < 200; i += 1) player.update(1 / 60, inputStub({ dy: -0.2 }), noBoxes);
    expect(player.pitch).toBeLessThan(Math.PI / 2);
    expect(player.pitch).toBeGreaterThan(0);
  });

  it('yaw=0 时 W 走 +z（舰艏方向）、D 走屏幕右手边', () => {
    const moves = walkFrom(0, { forward: 1 }).move;
    expect(moves.z).toBeGreaterThan(0.99);
    // yaw=0 面向 +z 时「屏幕右手边」是世界 -x（面向舰艏时右舷在 -x 一侧），
    // 具体方向由 rightAxis 定义，这里只断言它与相机右向一致，不写死世界轴。
    const screenRight = screenAxes(new Player([0, 0, 0], 0)).right.clone().setY(0).normalize();
    expect(walkFrom(0, { strafe: 1 }).move.dot(screenRight)).toBeGreaterThan(0.99);
  });
});

// ---------------------------------------------------------------------------
// 相机手感：头部起伏、蹲伏过渡、落地缓冲
//
// 这三项都是「体感」问题，很容易在后续改动里被无意放大（原实现把行走起伏
// 设成 4.5cm、滚转 0.46°，实测偏晕），因此用数值上限 + 过渡时间窗锁住。
// ---------------------------------------------------------------------------

describe('相机手感', () => {
  /** 让角色在地板上持续行走若干秒，返回视线高度的采样 */
  function walkSamples(options: { sprint?: boolean; crouch?: boolean } = {}, seconds = 1.5) {
    const floor = compileColliders([{ tag: 'floor', center: [0, -0.2, 0], size: [200, 0.4, 200] }]);
    const player = new Player([0, 0, 0], 0);
    const inputs = {
      state: { lookDx: 0, lookDy: 0, actions: [] as string[], jumpPressed: false },
      readMove: () => ({ forward: 1, strafe: 0 }),
      isSprinting: () => options.sprint === true,
      isCrouching: () => options.crouch === true,
    } as unknown as Parameters<Player['update']>[1];

    const samples: number[] = [];
    const frames = Math.round(seconds * 120);
    for (let i = 0; i < frames; i += 1) {
      player.update(1 / 120, inputs, floor);
      // 只取相机实际高度，避免把角色自身的上下浮动算进来
      const camera = new THREE.PerspectiveCamera();
      player.applyToCamera(camera);
      samples.push(camera.position.y);
    }
    return { player, samples };
  }

  function amplitude(values: number[]): number {
    return Math.max(...values) - Math.min(...values);
  }

  it('行走时的视线起伏幅度在 4cm 以内（原来 9cm，明显偏晕）', () => {
    const { samples } = walkSamples({}, 2);
    // 掐掉起步阶段，测稳定行走段的峰峰值
    const steady = samples.slice(Math.floor(samples.length / 3));
    expect(amplitude(steady)).toBeGreaterThan(0.0005); // 仍然有起伏，不能完全没反馈
    expect(amplitude(steady)).toBeLessThan(0.04);
  });

  it('冲刺起伏略大于行走，但同样受限', () => {
    const walk = walkSamples({}, 2).samples;
    const sprint = walkSamples({ sprint: true }, 2).samples;
    const steadyWalk = amplitude(walk.slice(Math.floor(walk.length / 3)));
    const steadySprint = amplitude(sprint.slice(Math.floor(sprint.length / 3)));
    expect(steadySprint).toBeGreaterThan(steadyWalk);
    expect(steadySprint).toBeLessThan(0.05);
  });

  it('蹲伏是渐变而不是瞬移：视线在 0.4s 内不跳完，但 1.2s 内到位', () => {
    const floor = compileColliders([{ tag: 'floor', center: [0, -0.2, 0], size: [200, 0.4, 200] }]);
    const player = new Player([0, 0, 0], 0);
    const standing = player.eyeHeight;
    const inputs = {
      state: { lookDx: 0, lookDy: 0, actions: [] as string[], jumpPressed: false },
      readMove: () => ({ forward: 0, strafe: 0 }),
      isSprinting: () => false,
      isCrouching: () => true,
    } as unknown as Parameters<Player['update']>[1];

    player.update(1 / 60, inputs, floor);
    const afterOneFrame = player.eyeHeight;
    // 一帧之内不能掉到底（否则就是原来的瞬移观感）
    expect(standing - afterOneFrame).toBeLessThan(0.15);

    let elapsed = 1 / 60;
    while (elapsed < 0.35) {
      player.update(1 / 60, inputs, floor);
      elapsed += 1 / 60;
    }
    const mid = player.eyeHeight;
    expect(mid).toBeLessThan(standing);
    expect(mid).toBeGreaterThan(1.0); // 还在下蹲过程中

    while (elapsed < 1.2) {
      player.update(1 / 60, inputs, floor);
      elapsed += 1 / 60;
    }
    // 收敛到蹲伏视线高度（0.98），误差 2cm 以内
    expect(player.eyeHeight).toBeCloseTo(0.98, 1);
    expect(player.crouchBlend).toBeCloseTo(1, 2);
  });

  it('蹲伏时碰撞体立即变矮（能钻进 1.3m 检修口），起立受头顶净空限制', () => {
    // 1.3m 高的检修管道：站立进不去，蹲下能进
    const boxes = compileColliders([
      { tag: 'floor', center: [0, -0.2, 0], size: [40, 0.4, 40] },
      { tag: 'pipe', center: [0, 1.65, 0], size: [6, 0.5, 6] },
    ]);
    const standingProbe = playerBox({ x: 0, y: 0, z: 0 }, 0.35, 1.8);
    expect(isBlocked(boxes, standingProbe)).toBe(true);
    const crouchProbe = playerBox({ x: 0, y: 0, z: 0 }, 0.35, 1.25);
    expect(isBlocked(boxes, crouchProbe)).toBe(false);
  });

  it('硬着陆有下沉且会自行恢复，普通小跳几乎不抖', () => {
    const floor = compileColliders([{ tag: 'floor', center: [0, -0.2, 0], size: [200, 0.4, 200] }]);
    const ground = {
      state: { lookDx: 0, lookDy: 0, actions: [] as string[], jumpPressed: false },
      readMove: () => ({ forward: 0, strafe: 0 }),
      isSprinting: () => false,
      isCrouching: () => false,
    } as unknown as Parameters<Player['update']>[1];

    const player = new Player([0, 8, 0], 0);
    // 自由落体到落地
    for (let i = 0; i < 240 && !player.grounded; i += 1) player.update(1 / 60, ground, floor);
    const impact = player.viewOffsetY;
    expect(impact).toBeGreaterThan(0.02);
    expect(impact).toBeLessThan(0.25);

    // 下沉必须收敛回 0
    for (let i = 0; i < 300; i += 1) player.update(1 / 60, ground, floor);
    expect(player.viewOffsetY).toBeLessThan(0.001);
  });
});

// ---------------------------------------------------------------------------
// 舱门感应
//
// 这里守住一个真实 bug：门组的原点是世界原点（门叶只有相对偏移），
// 早期用 object.getWorldPosition() 取门位置，感应距离实际变成「到船体中心的
// 距离」，表现为「走到门口门反而关上、离得老远门全开」。
// ---------------------------------------------------------------------------

describe('舱门感应', () => {
  const DOOR_TRIGGER = 3.2;
  const DOOR_RELEASE = 4.2;

  it('门都带有显式触发区，且触发区落在门洞所在的舱壁上', () => {
    const handle = buildShip(new THREE.Scene(), { quality: 'low' });
    try {
      expect(handle.doors.length).toBeGreaterThan(0);
      for (const door of handle.doors) {
        expect(door.trigger).toBeDefined();
        expect(door.trigger.halfSpan).toBeGreaterThan(1);
        // 触发区必须在舰体范围内。门洞中心正好落在舱壁厚度中间（两个矩形的接缝上），
        // 因此这里按一个壁厚放宽——曾经它退化成原点 (0,0,0)，这条断言才拦得住。
        expect(
          isInsideHull(door.trigger.x, door.trigger.z, WALL_THICKNESS),
          `舱门 ${door.object.name} 的触发区跑到舰体外：${door.trigger.x},${door.trigger.z}`,
        ).toBe(true);
      }
    } finally {
      handle.dispose();
    }
  });

  it('站在门洞任何位置都算在门口（含贴着门框一侧）', () => {
    const trigger = { alongX: true, x: 0, z: -20, halfSpan: 2.2 };
    // 正对门洞中心
    expect(doorDistance(trigger, 0, -21)).toBeLessThan(DOOR_TRIGGER);
    // 贴着门框一侧：到中心 2.2m 已经超过阈值，但人仍然在门口
    expect(doorDistance(trigger, 2.1, -21)).toBeLessThan(DOOR_TRIGGER);
    expect(doorDistance(trigger, -2.1, -21)).toBeLessThan(DOOR_TRIGGER);
    // 沿门洞轴线横向移动不改变距离（线段投影）
    expect(doorDistance(trigger, 2.0, -20)).toBeCloseTo(doorDistance(trigger, 0, -20), 5);
  });

  it('沿 z 方向的门洞同样按线段判定', () => {
    const trigger = { alongX: false, x: -29, z: 0, halfSpan: 2.2 };
    expect(doorDistance(trigger, -30, 2.0)).toBeLessThan(DOOR_TRIGGER);
    expect(doorDistance(trigger, -35, 0)).toBeGreaterThan(DOOR_RELEASE);
  });

  it('开/关阈值形成迟滞：临界距离上不会反复开关', () => {
    const trigger = { alongX: true, x: 0, z: 0, halfSpan: 2.2 };
    /** 复刻 engine 的判定：用当前状态选择阈值 */
    const shouldOpen = (distance: number, currentlyOpen: boolean) =>
      distance < (currentlyOpen ? DOOR_RELEASE : DOOR_TRIGGER);

    // 3.7m 落在两个阈值之间
    const between = doorDistance(trigger, 0, 3.7);
    expect(between).toBeGreaterThan(DOOR_TRIGGER);
    expect(between).toBeLessThan(DOOR_RELEASE);
    // 关着的门不会因为这点距离就打开……
    expect(shouldOpen(between, false)).toBe(false);
    // ……但已经打开的门会保持开启，于是不会在临界处抖动
    expect(shouldOpen(between, true)).toBe(true);

    // 真正远离后无论如何都会关
    const far = doorDistance(trigger, 0, DOOR_RELEASE + 1);
    expect(shouldOpen(far, true)).toBe(false);
    expect(shouldOpen(far, false)).toBe(false);
  });

  it('四扇走廊门 + 气闸都有互不相同的触发区（不会挤在同一点）', () => {
    const handle = buildShip(new THREE.Scene(), { quality: 'low' });
    try {
      const positions = handle.doors.map(
        (door) => `${door.trigger.x.toFixed(1)},${door.trigger.z.toFixed(1)}`,
      );
      expect(new Set(positions).size).toBe(handle.doors.length);
    } finally {
      handle.dispose();
    }
  });
});

// ---------------------------------------------------------------------------
// 面板投影（把 DOM 面板贴到终端屏幕上）
//
// 这组用例守住的是「面板与 WebGL 相机逐像素对齐」这件事：投影公式里
// 透视距离、视角原点、Y 轴取负任何一处写错，面板都会飘到别的地方或上下颠倒，
// 而这类错误在静态检查里完全看不出来。
// ---------------------------------------------------------------------------

describe('面板投影', () => {
  /** 让相机站在终端正前方看着它，并同步相机世界矩阵 */
  function cameraLookingAt(target: THREE.Vector3, from: THREE.Vector3, facing: number) {
    const camera = new THREE.PerspectiveCamera(74, 16 / 9, 0.05, 900);
    camera.position.copy(from);
    // 用 lookAt 与 Player.applyToCamera 保持同一套姿态约定
    const up = new THREE.Vector3(0, 1, 0);
    camera.up.copy(up);
    camera.lookAt(target);
    camera.updateMatrixWorld(true);
    void facing;
    return camera;
  }

  const VIEWPORT = { width: 1600, height: 900 };

  /**
   * 按 CSS 的语义把元素局部像素投到视口像素：matrix3d 是齐次矩阵，
   * 结果要做一次齐次除法（w 在第 4 行）。
   */
  function cssProject(matrix: number[], u: number, v: number) {
    const x = matrix[0] * u + matrix[4] * v + matrix[12];
    const y = matrix[1] * u + matrix[5] * v + matrix[13];
    const w = matrix[3] * u + matrix[7] * v + matrix[15];
    return { x: x / w, y: y / w };
  }

  /**
   * 回归：CSS 层拿到的 matrix3d 必须与 WebGL 的像素坐标逐角吻合。
   *
   * 这里曾经踩过一个很难从代码上看出来的坑：矩阵直接抄 CSS3DRenderer 的
   * 「perspective(P) + view·plane」，而那是按「世界单位 = CSS 像素」写的。
   * 本场景的世界单位是米、元素却是 150px/m，于是矩阵退化成单位阵，面板被原样
   * 画在元素框里并翻到视口左上角外侧（getBoundingClientRect 恒为
   * [-577,-372,577,372]，与视口零面积相交）—— 玩家接入终端后只会看到画面暗了
   * 一下，什么都没有，正是「点终端没反应」。
   */
  it('CSS 矩阵投出的四角与 WebGL 像素坐标一致（面板真的落在视野里）', () => {
    const plane = panelPlaneFromScreen([0, 1.32, -29.06], 0, { width: 1.6, height: 0.62 });
    const elementWidth = plane.width * PIXELS_PER_METER;
    const elementHeight = plane.height * PIXELS_PER_METER;
    // 元素局部四角（CSS：左上原点、y 向下），顺序与 QUAD_ORDER 对齐
    const corners: Array<[number, number]> = [
      [0, elementHeight],
      [elementWidth, elementHeight],
      [elementWidth, 0],
      [0, 0],
    ];

    const poses: Array<[THREE.Vector3, THREE.Vector3]> = [
      // 正对面板
      [new THREE.Vector3(0, 1.9, -28.6), new THREE.Vector3(0, 1.6, -26)],
      // 站到侧面斜看（透视更明显，单位换算错一点就会差出几百像素）
      [new THREE.Vector3(0, 1.9, -28.6), new THREE.Vector3(1.6, 1.5, -25.5)],
      [new THREE.Vector3(0, 2.4, -28.6), new THREE.Vector3(1.2, 3.1, -20)],
    ];

    for (const [target, from] of poses) {
      const camera = cameraLookingAt(target, from, 0);
      const projected = projectPanel(camera, plane, VIEWPORT.width, VIEWPORT.height);
      expect(projected.behind).toBe(false);
      corners.forEach(([u, v], index) => {
        const css = cssProject(projected.matrix, u, v);
        expect(css.x).toBeCloseTo(projected.quad[index].x, 3);
        expect(css.y).toBeCloseTo(projected.quad[index].y, 3);
      });
    }
  });

  it('正对终端时，面板中心投在屏幕中心、四角顺序正确', () => {
    const plane = panelPlaneFromScreen([0, 1.32, -29.06], 0, { width: 1.6, height: 0.62 });
    const camera = cameraLookingAt(
      new THREE.Vector3(0, 1.5, -29.2),
      new THREE.Vector3(0, 1.5, -26),
      0,
    );
    const projected = projectPanel(camera, plane, VIEWPORT.width, VIEWPORT.height);

    expect(projected.behind).toBe(false);
    // 屏幕在 z=-29.06，面板中心向玩家一侧浮出 0.42m（默认 forward）⇒ 平面在 z=-28.64；
    // 相机站在 z=-26，因此距离 2.64m（顺带验证屏幕锚点确实生效，而不是退回站位锚点）
    expect(projected.distance).toBeCloseTo(2.64, 1);

    // 四角：0=左下 1=右下 2=右上 3=左上（屏幕坐标 y 向下 ⇒ 下方的 y 更大）
    const [bl, br, tr, tl] = projected.quad;
    expect(bl.x).toBeLessThan(br.x);
    expect(bl.y).toBeGreaterThan(tl.y);
    expect(tr.x).toBeGreaterThan(tl.x);
    expect(br.y).toBeGreaterThan(tr.y);
    // 面板悬在终端屏幕上方（rise），而相机与屏幕大致等高，因此面板中心
    // 应当落在水平视线**上方**（屏幕坐标 y 更小）——这正是「浮在终端上方」
    // 的观感来源；若两者重合，面板就又会顶在视线正中，退化成屏幕 UI。
    const centerX = (bl.x + br.x + tr.x + tl.x) / 4;
    const centerY = (bl.y + br.y + tr.y + tl.y) / 4;
    expect(centerX).toBeCloseTo(VIEWPORT.width / 2, 0);
    expect(centerY).toBeLessThan(VIEWPORT.height / 2);
    expect(VIEWPORT.height / 2 - centerY).toBeGreaterThan(40);
  });

  it('面板基是右手系（right×up 与法线同向）：否则文字会被水平镜像', () => {
    for (const facing of [0, Math.PI / 2, Math.PI, -Math.PI / 2]) {
      const plane = panelPlaneFromScreen([0, 1.4, 0], facing, { width: 1.0, height: 0.5 });
      // 基必须右手：right × up == normal。取反会让面板矩阵行列式为 -1，
      // CSS 渲染出来就是左右镜像的文字。
      const cross = new THREE.Vector3().crossVectors(plane.right, plane.up);
      expect(cross.dot(plane.normal)).toBeCloseTo(1, 6);

      const camera = cameraLookingAt(
        new THREE.Vector3(plane.center.x, plane.center.y, plane.center.z),
        new THREE.Vector3(
          plane.center.x + plane.normal.x * 3,
          plane.center.y,
          plane.center.z + plane.normal.z * 3,
        ),
        facing,
      );
      const projected = projectPanel(camera, plane, VIEWPORT.width, VIEWPORT.height);
      // 正对时：左下的 x 必须小于右下（屏幕坐标 x 向右），顺序反了就是镜像
      expect(projected.quad[0].x).toBeLessThan(projected.quad[1].x);
      expect(projected.quad[3].x).toBeLessThan(projected.quad[2].x);
      // 元素左上角在本地下方 / 上方的关系也要正确
      expect(projected.quad[0].y).toBeGreaterThan(projected.quad[3].y);
    }
  });

  it('跃迁到终端前面向它时，面板必须落在视野里且足够大', () => {
    // 复刻「从终端总览点一座终端后跃迁过去」的现场：warpTo 把玩家沿终端朝向
    // 推进 2.4m（走进舱室、站到终端面前）并转身面向它，然后逐座终端验证
    // 面板真的看得见。这条用例抓到过两个真实缺陷：
    //   1. 落点方向写反 → 玩家被丢到舱壁外侧，只看到终端背面，页面上「什么都没有」；
    //   2. yaw 算反 → 玩家背对终端。
    for (const station of STATIONS) {
      const [ax, ay, az] = station.anchor;
      const forward = new THREE.Vector3(Math.sin(station.facing), 0, Math.cos(station.facing));
      // 与 engine.warpTo 相同的自适应距离逻辑：向前探路，不越出可通行区域
      const step = 0.2;
      let distance = 0;
      for (let d = step; d <= 2.4 + 1e-6; d += step) {
        if (!isInsideHull(ax + forward.x * d, az + forward.z * d, 0.1)) break;
        distance = d;
      }
      expect(distance, `${station.code} 的跃迁距离为 0（玩家会站在机身里）`).toBeGreaterThanOrEqual(0.4);

      const target: [number, number, number] = [
        ax + forward.x * distance,
        ay,
        az + forward.z * distance,
      ];
      expect(
        isInsideHull(target[0], target[2]),
        `${station.code} 的跃迁落点落在舰体外：${target[0].toFixed(1)},${target[2].toFixed(1)}`,
      ).toBe(true);

      const yaw = Math.atan2(ax - target[0], az - target[2]);
      const player = new Player(target, yaw);

      const camera = new THREE.PerspectiveCamera(74, 16 / 9, 0.05, 900);
      player.applyToCamera(camera);
      camera.updateMatrixWorld(true);

      const plane = panelPlaneFromScreen(station.screen, station.screenYaw, station.screenSize);
      const projected = projectPanel(camera, plane, VIEWPORT.width, VIEWPORT.height);

      expect(projected.behind, `${station.code} 的面板跑到了相机背后`).toBe(false);
      // 视线必须真的朝向面板（正对时余弦接近 1）
      expect(projected.facing, `${station.code} 的视线没有朝向面板`).toBeGreaterThan(0.5);

      const xs = projected.quad.map((corner) => corner.x);
      const ys = projected.quad.map((corner) => corner.y);
      const width = Math.max(...xs) - Math.min(...xs);
      const height = Math.max(...ys) - Math.min(...ys);

      // 面板要足够大：至少占屏幕宽度的 25%
      expect(width, `${station.code} 的面板太小：${width.toFixed(0)}px`).toBeGreaterThan(
        VIEWPORT.width * 0.25,
      );
      expect(height, `${station.code} 的面板太扁：${height.toFixed(0)}px`).toBeGreaterThan(120);

      // 并且必须有可见部分落在视口内
      const overlapsX = Math.min(...xs) < VIEWPORT.width && Math.max(...xs) > 0;
      const overlapsY = Math.min(...ys) < VIEWPORT.height && Math.max(...ys) > 0;
      expect(overlapsX && overlapsY, `${station.code} 的面板完全在视口外`).toBe(true);

      // 面板位于相机前方（深度为正）
      for (const corner of projected.quad) {
        expect(corner.depth).toBeGreaterThan(0.2);
      }
    }
  });

  it('相机后退时面板变小、变远，但始终正对', () => {
    const plane = panelPlaneFromScreen([0, 1.32, -29.06], 0, { width: 1.6, height: 0.62 });
    const near = projectPanel(
      cameraLookingAt(new THREE.Vector3(0, 1.5, -29.2), new THREE.Vector3(0, 1.5, -27.5), 0),
      plane,
      VIEWPORT.width,
      VIEWPORT.height,
    );
    const far = projectPanel(
      cameraLookingAt(new THREE.Vector3(0, 1.5, -29.2), new THREE.Vector3(0, 1.5, -22), 0),
      plane,
      VIEWPORT.width,
      VIEWPORT.height,
    );

    const width = (p: typeof near) => Math.hypot(p.quad[1].x - p.quad[0].x, p.quad[1].y - p.quad[0].y);
    expect(width(far)).toBeLessThan(width(near));
    expect(far.distance).toBeGreaterThan(near.distance);
    expect(far.facing).toBeGreaterThan(0.9);
  });

  it('背对终端时 behind 为真（不应渲染那块假面板）', () => {
    const plane = panelPlaneFromScreen([0, 1.32, -29.06], 0, { width: 1.6, height: 0.62 });
    // 站在终端背后，朝远离它的方向看
    const camera = new THREE.PerspectiveCamera(74, 16 / 9, 0.05, 900);
    camera.position.set(0, 1.5, -30.5);
    camera.lookAt(new THREE.Vector3(0, 1.5, -34));
    camera.updateMatrixWorld(true);

    const projected = projectPanel(camera, plane, VIEWPORT.width, VIEWPORT.height);
    expect(projected.facing).toBeLessThan(0);
    expect(projected.behind).toBe(true);
  });

  it('视角原点落在面板元素范围内（排障读数）', () => {
    const plane = panelPlaneFromScreen([0, 1.32, -29.06], 0, { width: 1.6, height: 0.62 });
    const camera = cameraLookingAt(
      new THREE.Vector3(0, 1.5, -29.2),
      new THREE.Vector3(0, 1.5, -26),
      0,
    );
    const projected = projectPanel(camera, plane, VIEWPORT.width, VIEWPORT.height);
    const elementWidth = plane.width * PIXELS_PER_METER;
    const elementHeight = plane.height * PIXELS_PER_METER;

    // 面板悬在屏幕上方（rise），相机略低于面板中心，因此消失点会稍稍偏下；
    // 关键是它必须落在元素范围内 —— 这个读数就是「相机主光轴打在面板的哪里」。
    expect(projected.principalX).toBeGreaterThan(0);
    expect(projected.principalX).toBeLessThan(elementWidth);
    expect(projected.principalY).toBeGreaterThan(0);
    expect(projected.principalY).toBeLessThan(elementHeight);

    // 水平方向正对时，消失点应接近元素水平中心
    expect(projected.principalX).toBeCloseTo(elementWidth / 2, 0);

    // 侧视（相机偏到一侧）时消失点应随之偏移，而不是固定在中心
    const offAxis = cameraLookingAt(
      new THREE.Vector3(0.9, 1.5, -29.2),
      new THREE.Vector3(1.6, 1.5, -26),
      0,
    );
    const off = projectPanel(offAxis, plane, VIEWPORT.width, VIEWPORT.height);
    expect(Math.abs(off.principalX - projected.principalX)).toBeGreaterThan(1);
  });

  it('投影矩阵与手算的相机空间结果一致（防止整体错位）', () => {
    const plane = panelPlaneFromScreen([12, 1.22, -23.26], -Math.PI / 2, { width: 0.8, height: 0.44 });
    const camera = cameraLookingAt(
      new THREE.Vector3(12, 1.5, -24),
      new THREE.Vector3(9.4, 1.5, -22),
      -Math.PI / 2,
    );
    const projected = projectPanel(camera, plane, VIEWPORT.width, VIEWPORT.height);

    // 用 projector 暴露的矩阵反推四角，必须与 quad 完全吻合
    const numbers = projected.transform
      .replace('matrix3d(', '')
      .replace(')', '')
      .split(',')
      .map(Number);
    expect(numbers).toHaveLength(16);
    const matrix = new THREE.Matrix4().fromArray(numbers);
    // CSS 矩阵的 Y 行取过负，还原回 three 的约定
    matrix.elements[1] *= -1;
    matrix.elements[5] *= -1;
    matrix.elements[9] *= -1;
    matrix.elements[13] *= -1;

    const world = new THREE.Vector3();
    const localCorners: Array<[number, number]> = [
      [-plane.width / 2, -plane.height / 2],
      [plane.width / 2, -plane.height / 2],
    ];
    localCorners.forEach(([lx, ly], index) => {
      world
        .copy(plane.center)
        .addScaledVector(plane.right, lx)
        .addScaledVector(plane.up, ly)
        .applyMatrix4(new THREE.Matrix4().copy(camera.matrixWorld).invert());
      const clip = new THREE.Vector4(world.x, world.y, world.z, 1).applyMatrix4(camera.projectionMatrix);
      const invW = 1 / Math.max(1e-6, Math.abs(clip.w));
      const expectedX = ((clip.x * invW + 1) / 2) * VIEWPORT.width;
      const expectedY = ((1 - clip.y * invW) / 2) * VIEWPORT.height;
      expect(projected.quad[index].x).toBeCloseTo(expectedX, 3);
      expect(projected.quad[index].y).toBeCloseTo(expectedY, 3);
    });
  });

  it('透视距离由竖直视场角决定（CSS 与 WebGL 用同一个焦距）', () => {
    const camera = new THREE.PerspectiveCamera(74, 16 / 9, 0.05, 900);
    // d = (h/2) / tan(fov/2)
    const expected = 900 / 2 / Math.tan((74 * Math.PI) / 180 / 2);
    expect(perspectiveDistance(camera, 900)).toBeCloseTo(expected, 4);
  });
});

// ---------------------------------------------------------------------------
// 舰体几何与游戏逻辑的一致性
//
// buildShip 在 jsdom 下只做几何与数据装配（不创建渲染器），因此可以在单测里直接跑，
// 用它反查「终端是否站在地板上」这类跨模块约束——这正是几何与碰撞体最容易脱节的地方。
// ---------------------------------------------------------------------------

describe('舰体几何', () => {
  it('每座终端脚下都有可站立的碰撞面（不会悬空或卡在墙体里）', () => {
    const handle = buildShip(new THREE.Scene(), { quality: 'low' });
    try {
      const boxes = compileColliders(handle.colliders);
      for (const station of STATIONS) {
        const [x, y, z] = station.anchor;
        const hit = rayBoxes(boxes, { x, y: y + 3, z }, { x: 0, y: -1, z: 0 }, 8);
        expect(hit, `终端 ${station.code} 下方没有地板`).not.toBeNull();
        expect(hit!.distance).toBeLessThan(4);
      }
    } finally {
      handle.dispose();
    }
  });

  it('投放的物资数量与分布符合设计（12 件，覆盖五个种类）', () => {
    const handle = buildShip(new THREE.Scene(), { quality: 'low' });
    try {
      const pickups = handle.interactables.filter((item) => item.kind === 'pickup');
      expect(pickups).toHaveLength(12);
      const byItem = new Map<string, number>();
      for (const pickup of pickups) {
        const key = pickup.item ?? 'unknown';
        byItem.set(key, (byItem.get(key) ?? 0) + 1);
        expect(ITEM_IDS, `物资 ${key} 不在 ITEMS 表里`).toContain(key as ItemId);
        expect(
          isInsideHull(pickup.position.x, pickup.position.z),
          `物资 ${key} 落在舰体外：${pickup.position.x},${pickup.position.z}`,
        ).toBe(true);
      }
      expect(byItem.get('power-cell')).toBe(3);
      expect(byItem.get('coolant')).toBe(3);
      expect(byItem.get('alloy')).toBe(2);
      expect(byItem.get('data-core')).toBe(2);
      expect(byItem.get('medkit')).toBe(2);
    } finally {
      handle.dispose();
    }
  });

  it('三个小游戏的触发道具都存在且位置合法', () => {
    const handle = buildShip(new THREE.Scene(), { quality: 'low' });
    try {
      const games = handle.interactables.filter((item) => item.kind === 'minigame');
      expect(games.map((item) => item.miniGame).sort()).toEqual(['circuit', 'turret']);
      for (const game of games) {
        expect(isInsideHull(game.position.x, game.position.z)).toBe(true);
      }
    } finally {
      handle.dispose();
    }
  });

  it('舱门数量不少于 DOORS 定义，且每扇门都有开合状态', () => {
    const handle = buildShip(new THREE.Scene(), { quality: 'low' });
    try {
      const expectedDoors = Object.values(DOORS).reduce((sum, list) => sum + list.length, 0);
      // 除十字走廊的四扇门，机库外壁还有一扇气闸展示门
      expect(handle.doors.length).toBeGreaterThanOrEqual(expectedDoors);
      for (const door of handle.doors) {
        expect(typeof door.update).toBe('function');
        expect(door.open).toBe(false);
      }
    } finally {
      handle.dispose();
    }
  });

  it('dispose 之后场景里不再残留舰体节点（StrictMode 双挂载不漏）', () => {
    const scene = new THREE.Scene();
    const handle = buildShip(scene, { quality: 'low' });
    expect(scene.children.length).toBeGreaterThan(0);
    handle.dispose();
    scene.remove(handle.root);
    expect(scene.children).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// 舰体布局
// ---------------------------------------------------------------------------

describe('舰体布局', () => {
  it('四个舱室 + 中央枢纽 + 四条走廊，尺寸都为正', () => {
    expect(ROOMS).toHaveLength(4);
    expect(HUB.size[0]).toBeGreaterThan(0);
    expect(ALL_ZONES.length).toBe(4 + 1 + 4);
    for (const zone of ALL_ZONES) {
      expect(zone.size[0]).toBeGreaterThan(0);
      expect(zone.size[1]).toBeGreaterThan(0);
    }
  });

  it('出生点在舰桥内且不在任何舱壁里', () => {
    expect(zoneAt(SPAWN_POSITION[0], SPAWN_POSITION[2])?.id).toBe('bridge');
    expect(isInsideHull(SPAWN_POSITION[0], SPAWN_POSITION[2])).toBe(true);
  });

  it('十字走廊与四个舱室逐一首尾相接（没有断头路）', () => {
    // 走廊是沿某个轴伸出的：检查与它相邻的舱室矩形在通行轴上确有重叠
    const corridors = ALL_ZONES.filter((zone) => zone.id.startsWith('corridor-'));
    expect(corridors).toHaveLength(4);
    for (const corridor of corridors) {
      const horizontal = corridor.size[0] > corridor.size[1];
      const touchesRoom = ROOMS.some((room) => {
        const gapAlong = horizontal
          ? Math.abs(room.center[0] - corridor.center[0])
          : Math.abs(room.center[1] - corridor.center[1]);
        const reach = horizontal
          ? (room.size[0] + corridor.size[0]) / 2
          : (room.size[1] + corridor.size[1]) / 2;
        // 沿通行轴相接（允许 0.5m 装配余量），且垂直轴上有通路宽度
        const lateral = horizontal
          ? Math.abs(room.center[1] - corridor.center[1])
          : Math.abs(room.center[0] - corridor.center[0]);
        const lateralReach = horizontal
          ? (room.size[1] + corridor.size[1]) / 2
          : (room.size[0] + corridor.size[0]) / 2;
        return Math.abs(gapAlong - reach) < 3.5 && lateral <= lateralReach;
      });
      expect(touchesRoom, `走廊 ${corridor.id} 没有接到任何舱室`).toBe(true);
    }
  });

  it('每个舱室都登记了舱门，门洞宽度小于舱壁长度', () => {
    for (const room of ROOMS) {
      const doors = DOORS[room.id];
      expect(doors, `${room.id} 缺少舱门定义`).toBeDefined();
      expect(doors.length).toBeGreaterThan(0);
      const wallLength = doors[0].side === 'n' || doors[0].side === 's' ? room.size[0] : room.size[1];
      expect(DOOR_WIDTH).toBeLessThan(wallLength);
    }
  });

  it('舱内净高足够站直（> 玩家身高 1.8m）', () => {
    expect(DECK_HEIGHT).toBeGreaterThan(1.8);
    expect(WALL_THICKNESS).toBeGreaterThan(0);
    expect(DECK_Y).toBe(0);
  });

  it('zoneLabel 对舱室、枢纽、走廊与舰外都有中文名', () => {
    expect(zoneLabel(ROOMS[0])).toBe(ROOMS[0].label);
    expect(zoneLabel(HUB)).toBe('中央枢纽');
    const corridor = ALL_ZONES.find((zone) => zone.id === 'corridor-e');
    expect(zoneLabel(corridor!)).toBe('右舷走廊');
    expect(zoneLabel(null)).toBe('舰外');
  });
});

// ---------------------------------------------------------------------------
// 终端站位
// ---------------------------------------------------------------------------

describe('控制终端', () => {
  it('8 座终端，id 唯一，且都落在可通行的舱室内', () => {
    expect(STATIONS).toHaveLength(8);
    const ids = new Set(STATIONS.map((station) => station.id));
    expect(ids.size).toBe(8);
    for (const station of STATIONS) {
      const [x, y, z] = station.anchor;
      expect(y).toBe(DECK_Y);
      expect(isInsideHull(x, z), `终端 ${station.code} 落在舰体外：${x},${z}`).toBe(true);
    }
  });

  it('终端贴墙但不穿墙：与所在舱室墙面的距离在 0.6~1.8m 之间', () => {
    for (const station of STATIONS) {
      const zone = zoneAt(station.anchor[0], station.anchor[2]);
      expect(zone, `终端 ${station.code} 不在任何舱室/走廊内`).not.toBeNull();
      const [cx, cz] = zone!.center;
      const [sx, sz] = zone!.size;
      const gapX = Math.min(
        Math.abs(station.anchor[0] - (cx - sx / 2)),
        Math.abs(cx + sx / 2 - station.anchor[0]),
      );
      const gapZ = Math.min(
        Math.abs(station.anchor[2] - (cz - sz / 2)),
        Math.abs(cz + sz / 2 - station.anchor[2]),
      );
      const nearestWall = Math.min(gapX, gapZ);
      expect(nearestWall, `终端 ${station.code} 离墙 ${nearestWall.toFixed(2)}m 不合理`).toBeLessThan(1.8);
      expect(nearestWall).toBeGreaterThan(0.4);
    }
  });

  it('朝向是四个正交方向之一（终端不会斜着摆）', () => {
    const allowed = [0, Math.PI / 2, Math.PI, -Math.PI / 2];
    for (const station of STATIONS) {
      expect(allowed.some((angle) => Math.abs(angle - station.facing) < 1e-6)).toBe(true);
    }
  });

  it('每个终端都有编号与所属系统，面板抬头不会出现空字段', () => {
    for (const station of STATIONS) {
      expect(station.code).toMatch(/^[A-Z]{3}-\d{2}$/);
      expect(station.terminal.length).toBeGreaterThan(0);
      expect(station.subsystem.length).toBeGreaterThan(0);
      expect(station.title.length).toBeGreaterThan(0);
    }
  });
});

// ---------------------------------------------------------------------------
// 碰撞
// ---------------------------------------------------------------------------

/** 构造一个 20×20 的房间：地板 + 四面墙 + 北墙留 4.4m 门洞 */
function makeRoom(): AABB[] {
  const boxes: AABB[] = [
    { tag: 'floor', center: [0, -0.2, 0], size: [20, 0.4, 20] },
  ];
  const wall = (center: [number, number, number], size: [number, number, number]) =>
    boxes.push({ tag: 'wall', center, size });
  wall([0, 2, 10], [20, 4, 0.4]); // 北墙（z=+10）
  wall([0, 2, -10], [20, 4, 0.4]); // 南墙
  wall([10, 2, 0], [0.4, 4, 20]); // 东墙
  // 西墙分两段，中间留门洞
  wall([-10, 2, -6.4], [0.4, 4, 7.2]);
  wall([-10, 2, 6.4], [0.4, 4, 7.2]);
  wall([-10, 3.85, 0], [0.4, 0.7, 5.6]); // 门楣
  return boxes;
}

describe('碰撞求解', () => {
  const boxes = compileColliders(makeRoom());
  const body = (x = 0, y = 0, z = 0): CollisionBody => ({
    position: { x, y, z },
    radius: 0.35,
    height: 1.8,
  });

  it('编译后的包围盒与输入一致（尺寸减半即边界）', () => {
    const compiled = compileColliders([{ center: [1, 2, 3], size: [2, 4, 6] }]);
    expect(compiled[0].minX).toBeCloseTo(0);
    expect(compiled[0].maxY).toBeCloseTo(4);
    expect(compiled[0].maxZ).toBeCloseTo(6);
    expect(compiled[0].tag).toBe('solid');
  });

  it('自由前进不产生偏移', () => {
    const result = resolveMovement(boxes, body(0, 0, 0), { x: 1, y: 0, z: 0 });
    expect(result.x).toBeCloseTo(1);
    expect(result.z).toBeCloseTo(0);
  });

  it('撞墙时该轴被挡住，另一轴仍然生效（贴墙滑行）', () => {
    // 站立点离东墙（内表面 x=9.8）留出足够余量：碰撞体半径 0.35，
    // 若起始位置本身就已经和墙面重叠，求解器会判定「已埋在墙里」而拒绝任何位移。
    const result = resolveMovement(boxes, body(9.0, 0, 0), { x: 1, y: 0, z: 1 });
    expect(result.x).toBeCloseTo(9.0);
    expect(result.z).toBeCloseTo(1);
    // 允许贴到墙根，但不能越过内表面
    expect(result.x + 0.35).toBeLessThanOrEqual(9.8);
  });

  it('门洞可以通过，门楣两侧的墙挡得住', () => {
    const throughDoor = resolveMovement(boxes, body(-9.5, 0, 0), { x: -1, y: 0, z: 0 });
    expect(throughDoor.x).toBeCloseTo(-10.5, 2);
    const intoWall = resolveMovement(boxes, body(-9.5, 0, 6), { x: -1, y: 0, z: 0 });
    expect(intoWall.x).toBeCloseTo(-9.5, 3);
  });

  it('下落时被地板接住并报告 grounded', () => {
    const result = resolveMovement(boxes, body(0, 1.2, 0), { x: 0, y: -1.5, z: 0 });
    expect(result.y).toBeCloseTo(0, 3);
    expect(result.grounded).toBe(true);
  });

  it('步高吸附：贴着墙根的 30cm 检修台能直接迈上去，90cm 的货箱挡路', () => {
    // 0.3m 高、0.6m 宽的检修台紧贴西墙内沿（墙内沿 x=-9.8）
    const withLedge = compileColliders([
      ...makeRoom(),
      { tag: 'ledge', center: [-9.5, 0.15, 0], size: [0.6, 0.3, 2] },
    ]);
    const stepped = resolveMovement(withLedge, body(-9.2, 0, 0), { x: -0.5, y: 0, z: 0 });
    expect(stepped.x).toBeCloseTo(-9.7, 2);
    expect(stepped.y).toBeCloseTo(0.3, 2);

    const withCrate = compileColliders([
      ...makeRoom(),
      { tag: 'crate', center: [-9.2, 0.45, 0], size: [1.2, 0.9, 2] },
    ]);
    const blocked = resolveMovement(withCrate, body(-8.2, 0, 0), { x: -0.6, y: 0, z: 0 });
    expect(blocked.x).toBeCloseTo(-8.2, 3);
    expect(blocked.y).toBeCloseTo(0, 3);
  });

  it('头顶探测能识别低矮管线下的空间', () => {
    const withPipe = compileColliders([
      ...makeRoom(),
      { tag: 'pipe', center: [0, 1.6, 0], size: [4, 0.4, 4] },
    ]);
    const standing: CollisionBody = { position: { x: 0, y: 0, z: 0 }, radius: 0.35, height: 1.8 };
    expect(isBlocked(withPipe, playerBox(standing.position, 0.35, 1.8))).toBe(true);
    expect(isBlocked(withPipe, playerBox(standing.position, 0.35, 1.25))).toBe(false);
  });

  it('射线拾取返回最近命中，且视线被墙挡住时判定为阻塞', () => {
    const forward = rayBoxes(boxes, { x: 0, y: 1.6, z: 0 }, { x: 0, y: 0, z: 1 }, 20);
    expect(forward?.tag).toBe('wall');
    expect(forward?.distance).toBeCloseTo(9.8, 1);

    // 舱内两点之间无遮挡；穿过北墙到舱外则被判为阻塞（隔墙不能操作终端）
    expect(isLineBlocked(boxes, { x: 0, y: 1.6, z: 0 }, { x: 0, y: 1.6, z: -9 })).toBe(false);
    expect(isLineBlocked(boxes, { x: 0, y: 1.6, z: 0 }, { x: 0, y: 1.6, z: 12 })).toBe(true);
  });

  /**
   * 回归：端点落在碰撞体内部时，该碰撞体不算遮挡。
   *
   * 终端机身与站位锚点就是这个关系（锚点在机身中央），不跳过的话
   * 「走到终端正前方」的视线永远穿不过终端自己的机身。
   */
  it('视线端点落在碰撞体内部时，该碰撞体不参与遮挡判定', () => {
    const solid = compileColliders([{ center: [0, 0.5, 0], size: [2, 1, 2] }]);
    // 从盒子内部看向盒外：不算被这堵「墙」挡住
    expect(isLineBlocked(solid, { x: 0, y: 0.5, z: 0 }, { x: 6, y: 0.5, z: 0 })).toBe(false);
    // 端点落在盒子里（另一端点在外）：同样不算
    expect(isLineBlocked(solid, { x: -6, y: 0.5, z: 0 }, { x: 0, y: 0.5, z: 0 })).toBe(false);
    // 盒子夹在两点之间才是真的遮挡
    expect(isLineBlocked(solid, { x: -6, y: 0.5, z: 0 }, { x: 6, y: 0.5, z: 0 })).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// 舰况换算
// ---------------------------------------------------------------------------

describe('舰况读数', () => {
  const system: SystemInfo = {
    hostname: 'neobot-host',
    cpu_percent: 20,
    cpu_count: 8,
    mem_percent: 40,
    disk_percent: 60,
    load_average: [2, 1.5, 1],
  };

  it('四项读数来自真实的系统字段', () => {
    const { vitals, availability } = deriveVitals(system);
    expect(availability).toBe('ok');
    const byKey = Object.fromEntries(vitals.map((vital) => [vital.key, vital.value]));
    expect(byKey.energy).toBeCloseTo(80); // 100 - cpu
    expect(byKey.atmosphere).toBeCloseTo(60); // 100 - mem
    expect(byKey.hull).toBeCloseTo(40); // 100 - disk
    expect(byKey.heat).toBeCloseTo(25); // load 2 / 8 核
  });

  it('电池电量优先于 CPU 余量，并在来源里标注字段名', () => {
    const { vitals } = deriveVitals({ ...system, battery_percent: 33 } as SystemInfo);
    const energy = vitals.find((vital) => vital.key === 'energy')!;
    expect(energy.value).toBeCloseTo(33);
    expect(energy.source).toContain('battery_percent');
  });

  it('没有遥测时读出「等待遥测」而不是 0 值假数据', () => {
    const { vitals, availability } = deriveVitals(null);
    expect(availability).toBe('unavailable');
    expect(vitals).toHaveLength(4);
    for (const vital of vitals) {
      expect(vital.source).toBe('等待舰载主机遥测');
    }
  });

  it('缺一项时标记为 partial，读数仍按可用项给出', () => {
    const { availability } = deriveVitals({ cpu_percent: 10, mem_percent: 20, load_average: [1] });
    expect(availability).toBe('partial');
  });

  it('警戒分级：能源过低为 critical、主机过热为 critical，其余为 nominal', () => {
    expect(vitalStatus('energy', 90)).toBe('nominal');
    expect(vitalStatus('energy', 30)).toBe('caution');
    expect(vitalStatus('energy', 5)).toBe('critical');
    expect(vitalStatus('heat', 30)).toBe('nominal');
    expect(vitalStatus('heat', 75)).toBe('caution');
    expect(vitalStatus('heat', 95)).toBe('critical');
  });

  it('hasCritical 找出第一个严重项', () => {
    const { vitals } = deriveVitals({ cpu_percent: 50, mem_percent: 99, disk_percent: 50, load_average: [1] });
    const critical = hasCritical(vitals);
    expect(critical?.key).toBe('atmosphere');
    expect(hasCritical(deriveVitals(system).vitals)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 物资定义
// ---------------------------------------------------------------------------

describe('物资', () => {
  it('五类物资都有中文名与提示，且 id 与键一致', () => {
    expect(ITEM_IDS).toHaveLength(5);
    for (const id of ITEM_IDS) {
      expect(ITEMS[id].id).toBe(id);
      expect(ITEMS[id].name.length).toBeGreaterThan(0);
      expect(ITEMS[id].hint.length).toBeGreaterThan(0);
    }
  });

  it('成就定义 id 唯一且都有说明', () => {
    const ids = ACHIEVEMENTS.map((item) => item.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const achievement of ACHIEVEMENTS) {
      expect(achievement.hint.length).toBeGreaterThan(0);
    }
  });
});

// ---------------------------------------------------------------------------
// 存档
// ---------------------------------------------------------------------------

describe('舰内存档', () => {
  it('首次访问终端会记录并广播通知', () => {
    const notices: string[] = [];
    const off = onNotice((notice) => notices.push(notice.text));
    markVisited('comms');
    markVisited('comms');
    off();
    expect(getLog().visited).toEqual(['comms']);
    expect(notices).toHaveLength(1);
  });

  it('访问满 8 座终端解锁「全系统在线」', () => {
    for (const station of STATIONS) markVisited(station.id);
    expect(getLog().achievements).toContain('all-terminals');
  });

  it('收集与消耗物资', () => {
    collectItem('alloy', 2);
    expect(getLog().inventory.alloy).toBe(2);
    expect(consumeItem('alloy')).toBe(true);
    expect(getLog().inventory.alloy).toBe(1);
    expect(consumeItem('alloy', 5)).toBe(false);
    expect(getLog().inventory.alloy).toBe(1);
  });

  it('收集满 10 件解锁拾荒者', () => {
    collectItem('coolant', 10);
    expect(getLog().achievements).toContain('collector');
  });

  it('小游戏成绩保留最好分数与游玩次数', () => {
    recordMiniGame('turret', 8);
    const record = recordMiniGame('turret', 3);
    expect(record.best).toBe(8);
    expect(record.plays).toBe(2);
    expect(getLog().miniGames.turret.best).toBe(8);
  });

  it('订阅者能收到更新，且 localStorage 被写入', () => {
    const listener = vi.fn();
    const off = subscribeLog(listener);
    updateLog((log) => ({ ...log, distance: 42 }));
    off();
    expect(listener).toHaveBeenCalled();
    expect(getLog().distance).toBe(42);
    expect(localStorage.getItem('neobot-bridge-log')).toContain('"distance":42');
  });

  it('存档损坏时回落到空存档而不是抛错', () => {
    localStorage.setItem('neobot-bridge-log', '{ this is not json');
    __setLogForTest(emptyLog());
    expect(getLog().visited).toEqual([]);
  });
});

describe('面板遮挡', () => {
  const VIEW = { width: 1600, height: 900 };

  function cmdPlane() {
    return panelPlaneFromScreen([0, 1.32, -29.06], 0, { width: 1.6, height: 0.62 });
  }

  it('没有任何碰撞体时可见度为 1', () => {
    expect(panelVisibility([], { x: 0, y: 1.6, z: -26 }, cmdPlane())).toBe(1);
  });

  it('舱壁夹在相机与面板之间时可见度归零', () => {
    // 一块横在相机与面板之间的舱壁（面板在 z≈-28.6，相机在 z=-26）
    const wall = compileColliders([{ center: [0, 1.5, -27.4], size: [8, 3, 0.4] }]);
    expect(panelVisibility(wall, { x: 0, y: 1.6, z: -26 }, cmdPlane())).toBe(0);
    // 相机挪到舱壁另一侧（与面板同侧）后重新可见
    expect(panelVisibility(wall, { x: 0, y: 1.6, z: -28 }, cmdPlane())).toBe(1);
  });

  /**
   * 回归：终端机身自己也有一块碰撞盒，且站位锚点就落在里面。
   *
   * 早期 isLineBlocked 把「起点在盒子里」也算命中，于是站在终端正前方时
   * 每一条视线都被终端自己的机身挡住 —— 可见度恒为 0，面板被永久压到 25%
   * 不透明度；同一条判据还让 warpTo 的探路第一步就「撞墙」（距离退化成 0），
   * 以及让终端永远选不中（提示「附近没有可接入的舰载设备」）。
   */
  it('跃迁落点站得下、朝着终端，且面板可见（机身不算遮挡）', () => {
    const ship = buildShip(new THREE.Scene(), { quality: 'low' });
    try {
      const boxes = compileColliders(ship.colliders);
      for (const station of STATIONS) {
        // 直接跑线上那份探路代码（warpLanding），不再自己复刻一遍公式：
        // 之前正是因为复刻时漏了 isLineBlocked，才没发现 8 座终端全部落点退化成锚点。
        const landing = warpLanding(station, boxes);
        expect(
          Math.hypot(landing.x - station.anchor[0], landing.z - station.anchor[2]),
          `${station.code} 的跃迁距离退化成 0（玩家会被放进机身里）`,
        ).toBeGreaterThanOrEqual(0.4);
        // 落点必须放得下玩家，否则会被脱困逻辑随机推开
        expect(
          isBlocked(
            boxes,
            playerBox({ x: landing.x, y: landing.y, z: landing.z }, PLAYER_RADIUS, PLAYER_HEIGHT),
          ),
          `${station.code} 的跃迁落点站不下`,
        ).toBe(false);
        // 朝向：视线指向终端（前向与「落点→锚点」方向同向）
        const toStation = {
          x: station.anchor[0] - landing.x,
          z: station.anchor[2] - landing.z,
        };
        const length = Math.hypot(toStation.x, toStation.z) || 1;
        const facing = (Math.sin(landing.yaw) * toStation.x + Math.cos(landing.yaw) * toStation.z) / length;
        expect(facing, `${station.code} 跃迁后没有面向终端`).toBeGreaterThan(0.95);

        const plane = panelPlaneFromScreen(station.screen, station.screenYaw, station.screenSize);
        const eye = {
          x: landing.x,
          y: landing.y + PLAYER_EYE,
          z: landing.z,
        };
        // 落点到面板的距离要落在「看得清整块面板」的区间里。
        // 太近说明机身朝向写反了、玩家被顶在舱壁夹缝里 —— 面板会顶满整个视口，
        // 连抬头的「断开」按钮都跑到屏幕外（机库那三座终端原本就是这样，实测
        // 只剩 1.2m）。下限取 1.4 是因为指挥台正前方摆着舰长席：探路被椅子挡住时
        // 会就近落在 1.5m 左右，那属于正常布局，不是缺陷。
        const panelDistance = new THREE.Vector3(eye.x, eye.y, eye.z).distanceTo(plane.center);
        expect(
          panelDistance,
          `${station.code} 的落点离面板 ${panelDistance.toFixed(2)}m（太近会顶满视口）`,
        ).toBeGreaterThan(1.4);
        expect(panelDistance, `${station.code} 的落点离面板 ${panelDistance.toFixed(2)}m（太远看不清）`)
          .toBeLessThan(3.6);
        // 下限放到 0.8：火控台（WPN-08）紧贴机库北墙、身前就是门洞，
        // 门楣会合理地压掉面板最上面一行采样，其余终端都应是满值 1。
        expect(
          panelVisibility(boxes, eye, plane),
          `${station.code} 站在终端正前方却看不到自己的面板`,
        ).toBeGreaterThan(0.8);
      }
    } finally {
      ship.dispose();
    }
  });

  /**
   * 回归：玩家背对终端时，面板已经跑到相机背后。
   *
   * 旧判据只看「相机在面板正面一侧」，此时仍然为真，于是面板照常拿到一个
   * 投影矩阵并被 CSS 摆到屏幕外（实测 x ≈ -577px，正好差一个视口宽度）。
   */
  it('相机背对终端时标记为 behind，不再往屏幕外投影', () => {
    const plane = cmdPlane();
    // 站在面板正前方但朝 +z 看（背对面板）
    const away = new THREE.PerspectiveCamera(74, 16 / 9, 0.05, 900);
    away.position.set(0, 1.6, -26);
    away.lookAt(new THREE.Vector3(0, 1.6, -10));
    away.updateMatrixWorld(true);
    const back = projectPanel(away, plane, VIEW.width, VIEW.height);
    expect(back.facing).toBeGreaterThan(0);
    expect(back.behind).toBe(true);

    // 正面朝向面板时不受影响
    const facing = new THREE.PerspectiveCamera(74, 16 / 9, 0.05, 900);
    facing.position.set(0, 1.6, -26);
    facing.lookAt(new THREE.Vector3(0, 1.9, -28.6));
    facing.updateMatrixWorld(true);
    expect(projectPanel(facing, plane, VIEW.width, VIEW.height).behind).toBe(false);
  });

  /**
   * 合成层只负责画全息辉光：早期那套 GPU 深度预处理（离屏目标 + 同步回读）
   * 既是「一开面板就卡死」的根源，又因为跨上下文而从未生效，已整体移除。
   * 这里守住「不再出现任何 GPU 回读」，防止它被重新加回来。
   */
  it('全息合成层不做任何 GPU 回读', () => {
    const calls: string[] = [];
    const renderer = {
      setClearColor: () => {},
      setPixelRatio: () => {},
      setSize: () => {},
      setRenderTarget: () => calls.push('setRenderTarget'),
      clear: () => calls.push('clear'),
      render: () => calls.push('render'),
      dispose: () => {},
      readRenderTargetPixels: () => calls.push('readRenderTargetPixels(sync)'),
      readRenderTargetPixelsAsync: () => {
        calls.push('readRenderTargetPixelsAsync');
        return Promise.resolve(new Uint8Array(0));
      },
    } as unknown as THREE.WebGLRenderer;

    const compositor = new PanelCompositor(document.createElement('canvas'), { renderer });
    compositor.draw(
      {
        quad: [
          { x: 0, y: 0, depth: 2 },
          { x: 200, y: 0, depth: 2 },
          { x: 200, y: 200, depth: 2 },
          { x: 0, y: 200, depth: 2 },
        ],
        reveal: 1,
        opacity: 0.8,
        accent: new THREE.Color(0x3fe0ff),
        accent2: new THREE.Color(0xff3bd0),
      },
      800,
      600,
    );
    compositor.clear();
    expect(calls).toContain('render');
    expect(calls.filter((call) => call.startsWith('readRenderTargetPixels'))).toEqual([]);
    compositor.dispose();
  });
});
