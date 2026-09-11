// core/collision.ts —— 轴对齐包围盒（AABB）世界与玩家碰撞解算。
// 飞船内部全部由轴对齐的房间/墙体构成，因此用 AABB 足够精确且极快。

import * as THREE from 'three';

export interface Box {
  min: THREE.Vector3;
  max: THREE.Vector3;
  /** 标签，便于调试与特殊规则（ladder / glass / door） */
  tag?: string;
}

export const PLAYER_RADIUS = 0.42;
export const PLAYER_HEIGHT = 1.78;
export const PLAYER_CROUCH_HEIGHT = 1.15;
export const EYE_HEIGHT = 1.62;
export const EYE_HEIGHT_CROUCH = 1.0;

export class CollisionWorld {
  readonly boxes: Box[] = [];

  add(min: THREE.Vector3, max: THREE.Vector3, tag?: string): void {
    this.boxes.push({ min, max, tag });
  }

  addBox(box: Box): void {
    this.boxes.push(box);
  }

  addFromCenter(center: THREE.Vector3, size: THREE.Vector3, tag?: string): void {
    const half = size.clone().multiplyScalar(0.5);
    this.boxes.push({
      min: center.clone().sub(half),
      max: center.clone().add(half),
      tag,
    });
  }

  /** 查询与给定 AABB 相交的所有盒子 */
  query(box: Box, out: Box[] = []): Box[] {
    out.length = 0;
    for (const candidate of this.boxes) {
      if (
        candidate.max.x <= box.min.x ||
        candidate.min.x >= box.max.x ||
        candidate.max.y <= box.min.y ||
        candidate.min.y >= box.max.y ||
        candidate.max.z <= box.min.z ||
        candidate.min.z >= box.max.z
      ) {
        continue;
      }
      out.push(candidate);
    }
    return out;
  }
}

export interface MoveResult {
  position: THREE.Vector3;
  grounded: boolean;
  hitCeiling: boolean;
  collidedX: boolean;
  collidedZ: boolean;
}

const scratch: Box[] = [];

/** 单轴移动并解算碰撞（先 X，再 Z，最后 Y —— 与 MC 的碰撞顺序一致） */
function moveAxis(
  world: CollisionWorld,
  position: THREE.Vector3,
  height: number,
  axis: 'x' | 'y' | 'z',
  amount: number,
): { value: number; blocked: boolean } {
  if (amount === 0) return { value: position[axis], blocked: false };
  const before = position[axis];
  position[axis] = before + amount;
  const half = PLAYER_RADIUS;
  const feet = position.y;
  const head = position.y + height;
  const box: Box = {
    min: new THREE.Vector3(position.x - half, feet, position.z - half),
    max: new THREE.Vector3(position.x + half, head, position.z + half),
  };
  const hits = world.query(box, scratch);
  if (hits.length === 0) return { value: position[axis], blocked: false };
  let value = position[axis];
  for (const hit of hits) {
    if (axis === 'y') {
      if (amount > 0) {
        value = Math.min(value, hit.min.y - height - 1e-4);
      } else {
        value = Math.max(value, hit.max.y + 1e-4);
      }
    } else if (axis === 'x') {
      if (amount > 0) value = Math.min(value, hit.min.x - half - 1e-4);
      else value = Math.max(value, hit.max.x + half + 1e-4);
    } else {
      if (amount > 0) value = Math.min(value, hit.min.z - half - 1e-4);
      else value = Math.max(value, hit.max.z + half + 1e-4);
    }
  }
  position[axis] = value;
  return { value, blocked: true };
}

export function moveWithCollision(
  world: CollisionWorld,
  position: THREE.Vector3,
  height: number,
  delta: THREE.Vector3,
): MoveResult {
  const result: MoveResult = {
    position: position.clone(),
    grounded: false,
    hitCeiling: false,
    collidedX: false,
    collidedZ: false,
  };
  const working = position.clone();
  const stepHeight = 0.55;

  let target = working.y;
  const xMove = moveAxis(world, working, height, 'x', delta.x);
  result.collidedX = xMove.blocked;
  const zMove = moveAxis(world, working, height, 'z', delta.z);
  result.collidedZ = zMove.blocked;

  // 台阶：小台阶直接抬上去（舷梯、门槛）
  if (result.collidedX || result.collidedZ) {
    const raised = working.clone();
    raised.y = position.y + stepHeight;
    const probeX = moveAxis(world, raised, height, 'x', delta.x);
    const probeZ = moveAxis(world, raised, height, 'z', delta.z);
    if (!probeX.blocked && !probeZ.blocked) {
      working.x = raised.x;
      working.z = raised.z;
      working.y = position.y;
      result.collidedX = false;
      result.collidedZ = false;
    }
  }

  // 重力：先看脚下有没有地面，再决定是否下落
  const feetProbe: Box = {
    min: new THREE.Vector3(
      working.x - PLAYER_RADIUS,
      working.y - 0.12,
      working.z - PLAYER_RADIUS,
    ),
    max: new THREE.Vector3(
      working.x + PLAYER_RADIUS,
      working.y - 1e-3,
      working.z + PLAYER_RADIUS,
    ),
  };
  const groundHits = world.query(feetProbe, []);
  const supported = groundHits.length > 0;
  if (delta.y <= 0 && supported && working.y + delta.y < position.y) {
    // 站在地面上且在下落：贴地
    const highest = groundHits.reduce((acc, box) => Math.max(acc, box.max.y), -Infinity);
    working.y = highest + 1e-4;
    result.grounded = true;
  } else {
    const yMove = moveAxis(world, working, height, 'y', delta.y);
    if (yMove.blocked) {
      if (delta.y < 0) result.grounded = true;
      else result.hitCeiling = true;
    }
  }
  target = working.y;
  result.position.copy(working);
  result.position.y = target;
  return result;
}
