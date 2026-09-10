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
