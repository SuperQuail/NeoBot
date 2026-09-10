// collision.ts —— 舰内 AABB 碰撞与射线拾取
//
// 全舰的可行走空间由 layout.ts 的矩形决定，墙体/道具碰撞盒由 ship.ts 生成。
// 玩家碰撞体简化为竖直 AABB（水平方形截面），Minecraft 式操作下这种近似足够：
// 分轴推进 + 步高吸附，就能得到「贴着墙滑行」「自动迈上台阶」的手感。

import type { AABB } from './layout';

export interface CollisionBody {
  position: { x: number; y: number; z: number };
  /** 碰撞体水平半宽 */
  radius: number;
  /** 碰撞体总高 */
  height: number;
}

/**
 * 重叠容差。
 *
 * 关键点：水平移动在竖直方向**不留任何余量**（padBox 的 yPad 为 0）。
 * 甲板本身就是一块「顶面在 y=0 的实心板」，如果竖直方向也留容差，站在甲板上的
 * 角色会与甲板永远保持重叠，于是每一步水平位移都被判成撞墙——人会被钉在原地。
 * 容差只用于消除浮点误差（2cm 的视觉穿透不可见）。
 */
const EPSILON = 1e-4;

interface Box {
  minX: number;
  minY: number;
  minZ: number;
  maxX: number;
  maxY: number;
  maxZ: number;
  tag: string;
}

/** 预计算包围盒：编译一次、每帧复用，避免重复的加减运算 */
export type CompiledBox = Box;

/** 预计算包围盒边界：每帧要跑几百次重叠判定，省掉重复加法 */
export function compileColliders(colliders: readonly AABB[]): Box[] {
  return colliders.map((item) => {
    const [cx, cy, cz] = item.center;
    const [sx, sy, sz] = item.size;
    return {
      minX: cx - sx / 2,
      minY: cy - sy / 2,
      minZ: cz - sz / 2,
      maxX: cx + sx / 2,
      maxY: cy + sy / 2,
      maxZ: cz + sz / 2,
      tag: item.tag ?? 'solid',
    };
  });
}

/** 展开包围盒：±r 用于水平判定，y 方向可选扩展 */
function padBox(box: Box, radius: number, yPad = 0): Box {
  return {
    minX: box.minX - radius,
    minY: box.minY - yPad,
    minZ: box.minZ - radius,
    maxX: box.maxX + radius,
    maxY: box.maxY + yPad,
    maxZ: box.maxZ + radius,
    tag: box.tag,
  };
}

function overlaps(a: Box, b: Box): boolean {
  return (
    a.minX < b.maxX - EPSILON &&
    a.maxX > b.minX + EPSILON &&
    a.minY < b.maxY - EPSILON &&
    a.maxY > b.minY + EPSILON &&
    a.minZ < b.maxZ - EPSILON &&
    a.maxZ > b.minZ + EPSILON
  );
}

function bodyBox(body: CollisionBody, x: number, y: number, z: number): Box {
  const { radius, height } = body;
  return {
    minX: x - radius,
    minY: y,
    minZ: z - radius,
    maxX: x + radius,
    maxY: y + height,
    maxZ: z + radius,
    tag: 'player',
  };
}

function hits(boxes: readonly Box[], candidate: Box, radius: number, yPad: number): boolean {
  for (const box of boxes) {
    if (overlaps(candidate, padBox(box, radius, yPad))) return true;
  }
  return false;
}

/** 诊断出口：返回与候选位置相交的包围盒标签（供测试定位穿墙/卡死问题） */
export function debugHits(
  boxes: readonly Box[],
  x: number,
  y: number,
  z: number,
  radius: number,
  height: number,
): string[] {
  const candidate = bodyBox({ position: { x, y, z }, radius, height }, x, y, z);
  return boxes.filter((box) => overlaps(candidate, padBox(box, radius, 0))).map((box) => box.tag);
}

export interface ResolveResult {
  x: number;
  y: number;
  z: number;
  grounded: boolean;
  /** 撞到了顶棚（用于提示「舱顶」） */
  bumpedHead: boolean;
}

/**
 * 分轴推进：先 y 再 xz，xz 再拆成两个独立轴，得到贴墙滑行。
 * 水平方向带步高吸附：抬升 ≤ stepHeight 就能迈上去，否则按撞墙处理。
 */
export function resolveMovement(
  boxes: readonly Box[],
  body: CollisionBody,
  delta: { x: number; y: number; z: number },
  options: { stepHeight?: number } = {},
): ResolveResult {
  const stepHeight = options.stepHeight ?? 0.45;
  const radius = body.radius;
  let { x, y, z } = body.position;
  let grounded = false;
  let bumpedHead = false;

  // ---- 竖直 ----
  if (delta.y !== 0) {
    const nextY = y + delta.y;
    if (hits(boxes, bodyBox(body, x, nextY, z), radius, 0)) {
      if (delta.y < 0) {
        // 落地：把脚底贴到最高的可站立面上
        let floor = -Infinity;
        const candidate = bodyBox(body, x, nextY, z);
        for (const box of boxes) {
          const padded = padBox(box, radius, 0);
          if (!overlaps(candidate, padded)) continue;
          if (box.maxY <= y + stepHeight + EPSILON) floor = Math.max(floor, box.maxY);
        }
        y = Number.isFinite(floor) ? floor : y;
        grounded = true;
      } else {
        bumpedHead = true;
      }
    } else {
      y = nextY;
    }
  }

  // ---- 水平：x 与 z 分别推进，撞墙时尝试步高吸附 ----
  const tryAxis = (axis: 'x' | 'z', amount: number) => {
    if (amount === 0) return;
    const nextX = axis === 'x' ? x + amount : x;
    const nextZ = axis === 'z' ? z + amount : z;
    // 注意：探测盒必须建在「候选位置」上。早先这里传的是 body 的原位置，
    // 于是任何一步位移只要原地不重叠就会被判为畅通，长距离移动能直接穿墙。
    if (!hits(boxes, bodyBox(body, nextX, y, nextZ), radius, 0)) {
      x = nextX;
      z = nextZ;
      return;
    }
    // 步高吸附：抬高一点再试。步高本身就是上限，所以最多只能迈上 stepHeight
    // （默认 45cm，MC 手感里的「一格台阶」），不需要再单独校验脚下支撑面——
    // 抬升量有界、且落点必须是空位，两者一起已经排除了「爬空气」。
    for (let lift = 0.1; lift <= stepHeight + EPSILON; lift += 0.1) {
      if (!hits(boxes, bodyBox(body, nextX, y + lift, nextZ), radius, 0)) {
        x = nextX;
        z = nextZ;
        y += lift;
        grounded = true;
        return;
      }
    }
    // 完全被挡住：该轴不动（另一轴仍然生效 → 贴墙滑行）
  };

  tryAxis('x', delta.x);
  tryAxis('z', delta.z);

  // ---- 没有竖直速度时也要维持接地判定（站在地面上） ----
  if (!grounded) {
    const probe = bodyBox(body, x, y - 0.12, z);
    grounded = boxes.some(
      (box) => overlaps(probe, padBox(box, radius, 0)) && box.maxY <= y + stepHeight + EPSILON,
    );
  }

  return { x, y, z, grounded, bumpedHead };
}

/** 头顶净空：蹲起/站起时判断能否恢复站姿 */
export function hasHeadroom(boxes: readonly Box[], body: CollisionBody, height: number): boolean {
  const candidate = bodyBox({ ...body, height }, body.position.x, body.position.y, body.position.z);
  return !hits(boxes, candidate, body.radius, 0);
}

/** 以某点为中心构造玩家包围盒（供站立判定等外部探测使用） */
export function playerBox(
  position: { x: number; y: number; z: number },
  radius: number,
  height: number,
): Box {
  return {
    minX: position.x - radius,
    minY: position.y,
    minZ: position.z - radius,
    maxX: position.x + radius,
    maxY: position.y + height,
    maxZ: position.z + radius,
    tag: 'player',
  };
}

/** 给定玩家包围盒是否与场景碰撞体相交 */
export function isBlocked(boxes: readonly Box[], player: Box): boolean {
  for (const box of boxes) {
    if (overlaps(player, box)) return true;
  }
  return false;
}

/** 相机中心射线与包围盒求交，返回命中距离（未命中为 null） */
export function rayBoxes(
  boxes: readonly Box[],
  origin: { x: number; y: number; z: number },
  direction: { x: number; y: number; z: number },
  maxDistance: number,
): { distance: number; tag: string } | null {
  let best: { distance: number; tag: string } | null = null;
  for (const box of boxes) {
    const t = rayBox(origin, direction, box, maxDistance);
    if (t === null) continue;
    if (!best || t < best.distance) best = { distance: t, tag: box.tag };
  }
  return best;
}

function rayBox(
  origin: { x: number; y: number; z: number },
  direction: { x: number; y: number; z: number },
  box: Box,
  maxDistance: number,
): number | null {
  let tMin = 0;
  let tMax = maxDistance;
  const axes: Array<[number, number, number, number]> = [
    [origin.x, direction.x, box.minX, box.maxX],
    [origin.y, direction.y, box.minY, box.maxY],
    [origin.z, direction.z, box.minZ, box.maxZ],
  ];
  for (const [originValue, dirValue, min, max] of axes) {
    if (Math.abs(dirValue) < 1e-8) {
      if (originValue < min || originValue > max) return null;
      continue;
    }
    const inv = 1 / dirValue;
    let t1 = (min - originValue) * inv;
    let t2 = (max - originValue) * inv;
    if (t1 > t2) [t1, t2] = [t2, t1];
    tMin = Math.max(tMin, t1);
    tMax = Math.min(tMax, t2);
    if (tMin > tMax) return null;
  }
  return tMin;
}

/** 两点之间的直线是否被遮挡（用于「隔墙不能操作终端」） */
export function isLineBlocked(
  boxes: readonly Box[],
  from: { x: number; y: number; z: number },
  to: { x: number; y: number; z: number },
): boolean {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const dz = to.z - from.z;
  const length = Math.hypot(dx, dy, dz);
  if (length < 1e-6) return false;
  const hit = rayBoxes(boxes, from, { x: dx / length, y: dy / length, z: dz / length }, length - 0.05);
  return hit !== null;
}

/**
 * 脱困：当角色已经位于某个碰撞体内部时（传送落点被道具占用、布局热更新、
 * 出生点压在货箱上等），分轴推进会把每一个方向都判成撞墙，角色就永远动不了。
 * 这里在周围按递增半径螺旋搜索一个空位，把角色挪出去。
 *
 * 返回 null 表示附近确实找不到空位（例如整个舱室都被填满），调用方应保持原位。
 */
export function findFreePosition(
  boxes: readonly Box[],
  body: CollisionBody,
  options: { maxRadius?: number; step?: number } = {},
): { x: number; y: number; z: number } | null {
  const maxRadius = options.maxRadius ?? 4;
  const step = options.step ?? 0.25;
  const origin = body.position;
  const free = (x: number, y: number, z: number) =>
    !hits(boxes, bodyBox(body, x, y, z), body.radius, 0);

  if (free(origin.x, origin.y, origin.z)) return { ...origin };
  const directions: Array<[number, number]> = [
    [1, 0],
    [-1, 0],
    [0, 1],
    [0, -1],
    [0.7071, 0.7071],
    [-0.7071, 0.7071],
    [0.7071, -0.7071],
    [-0.7071, -0.7071],
  ];
  for (let radius = step; radius <= maxRadius; radius += step) {
    for (const [dx, dz] of directions) {
      // 先试同高度，再试略微抬高（压在矮货箱上时抬高就能站住）
      for (const dy of [0, 0.25, 0.5, 1]) {
        const x = origin.x + dx * radius;
        const z = origin.z + dz * radius;
        const y = origin.y + dy;
        if (free(x, y, z)) return { x, y, z };
      }
    }
  }
  return null;
}
