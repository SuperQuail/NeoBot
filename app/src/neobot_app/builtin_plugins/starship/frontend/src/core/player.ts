// core/player.ts —— MC 风格第一人称控制器：WASD + 鼠标视角 + 跳跃/潜行/疾跑 + 爬梯。

import * as THREE from 'three';
import {
  CollisionWorld,
  EYE_HEIGHT,
  EYE_HEIGHT_CROUCH,
  PLAYER_CROUCH_HEIGHT,
  PLAYER_HEIGHT,
  moveWithCollision,
} from './collision';
import type { Input } from './input';

export interface LadderVolume {
  min: THREE.Vector3;
  max: THREE.Vector3;
}

const WALK_SPEED = 4.6;
const SPRINT_SPEED = 7.4;
const CROUCH_SPEED = 2.0;
const ACCELERATION = 46;
const AIR_ACCELERATION = 9;
const FRICTION = 12;
const GRAVITY = 26;
const JUMP_VELOCITY = 8.4;
const LADDER_SPEED = 3.4;
const MAX_FALL_SPEED = 60;

export class PlayerController {
  readonly position = new THREE.Vector3(0, 0, 0);
  readonly velocity = new THREE.Vector3();
  yaw = 0;
  pitch = 0;
  grounded = false;
  crouching = false;
  sprinting = false;
  inLadder = false;
  /** 头部晃动相位（走路时的轻微摇晃） */
  bobPhase = 0;
  private stepTimer = 0;
  /** 终端聚焦时的视角插值权重：0 = 玩家视角，1 = 终端视角 */
  focusBlend = 0;

  readonly eyeOffset = new THREE.Vector3();

  constructor(private readonly ladders: LadderVolume[]) {}

  get height(): number {
    return this.crouching ? PLAYER_CROUCH_HEIGHT : PLAYER_HEIGHT;
  }

  get eyeHeight(): number {
    return this.crouching ? EYE_HEIGHT_CROUCH : EYE_HEIGHT;
  }

  spawn(position: THREE.Vector3, yaw: number): void {
    this.position.copy(position);
    this.velocity.set(0, 0, 0);
    this.yaw = yaw;
    this.pitch = 0;
    this.grounded = false;
    this.focusBlend = 0;
  }

  eyePosition(target = new THREE.Vector3()): THREE.Vector3 {
    const bob = Math.sin(this.bobPhase * 2) * 0.028 * Math.min(1, this.speedRatio * 2);
    return target.set(
      this.position.x,
      this.position.y + this.eyeHeight + bob,
      this.position.z,
    );
  }

  private get speedRatio(): number {
    const horizontal = Math.hypot(this.velocity.x, this.velocity.z);
    return Math.min(1, horizontal / WALK_SPEED);
  }

  private ladderAt(position: THREE.Vector3): boolean {
    for (const ladder of this.ladders) {
      if (
        position.x > ladder.min.x &&
        position.x < ladder.max.x &&
        position.z > ladder.min.z &&
        position.z < ladder.max.z &&
        position.y + this.height > ladder.min.y &&
        position.y < ladder.max.y
      ) {
        return true;
      }
    }
    return false;
  }

  update(
    dt: number,
    world: CollisionWorld,
    input: Input,
    options: {
      enabled: boolean;
      onStep?: (running: boolean) => void;
      /** 疾跑增益等对速度的全局系数 */
      speedScale?: number;
      /** 跳跃增益 */
      jumpScale?: number;
    },
  ): void {
    const canMove = options.enabled;
    // 视角
    if (canMove && input.locked) {
      const sensitivity = 0.0022 * input.sensitivity;
      this.yaw -= input.pointer.deltaX * sensitivity;
      this.pitch -= input.pointer.deltaY * sensitivity * (input.invertY ? -1 : 1);
      const limit = Math.PI / 2 - 0.02;
      this.pitch = Math.max(-limit, Math.min(limit, this.pitch));
    }

    const forward = new THREE.Vector3(-Math.sin(this.yaw), 0, -Math.cos(this.yaw));
    const right = new THREE.Vector3(Math.cos(this.yaw), 0, -Math.sin(this.yaw));
    const wish = new THREE.Vector3();
    if (canMove) {
      if (input.isDown('w') || input.isDown('up')) wish.add(forward);
      if (input.isDown('s') || input.isDown('down')) wish.sub(forward);
      if (input.isDown('d') || input.isDown('right')) wish.add(right);
      if (input.isDown('a') || input.isDown('left')) wish.sub(right);
    }
    if (wish.lengthSq() > 0) wish.normalize();

    this.crouching = canMove && input.isDown('shift');
    const wantsSprint = canMove && !this.crouching && input.isDown('control');
    this.sprinting = wantsSprint && wish.lengthSq() > 0;
    const speedScale = Math.max(0.2, options.speedScale ?? 1);
    const targetSpeed =
      (this.crouching ? CROUCH_SPEED : this.sprinting ? SPRINT_SPEED : WALK_SPEED) * speedScale;

    const acceleration = this.grounded ? ACCELERATION : AIR_ACCELERATION;
    const desired = wish.multiplyScalar(targetSpeed);
    this.velocity.x = approach(this.velocity.x, desired.x, acceleration * dt);
    this.velocity.z = approach(this.velocity.z, desired.z, acceleration * dt);
    if (this.grounded && wish.lengthSq() === 0) {
      const friction = FRICTION * dt;
      this.velocity.x = approach(this.velocity.x, 0, friction * Math.abs(this.velocity.x) + friction);
      this.velocity.z = approach(this.velocity.z, 0, friction * Math.abs(this.velocity.z) + friction);
    }

    this.inLadder = this.ladderAt(this.position);
    if (this.inLadder) {
      const climb =
        (canMove && (input.isDown('w') || input.isDown('up')) ? 1 : 0) -
        (canMove && (input.isDown('s') || input.isDown('down')) ? 1 : 0);
      this.velocity.y = climb * LADDER_SPEED;
      if (canMove && input.isDown('space')) this.velocity.y = JUMP_VELOCITY * 0.6;
    } else {
      this.velocity.y -= GRAVITY * dt;
      if (this.velocity.y < -MAX_FALL_SPEED) this.velocity.y = -MAX_FALL_SPEED;
      if (canMove && this.grounded && input.isDown('space')) {
        this.velocity.y = JUMP_VELOCITY * Math.max(0.5, options.jumpScale ?? 1);
        this.grounded = false;
      }
    }

    const delta = this.velocity.clone().multiplyScalar(dt);
    const before = this.position.clone();
    const result = moveWithCollision(world, this.position, this.height, delta);
    this.position.copy(result.position);
    if (result.grounded) {
      if (this.velocity.y < 0) this.velocity.y = 0;
      this.grounded = true;
    } else {
      this.grounded = false;
    }
    if (result.hitCeiling && this.velocity.y > 0) this.velocity.y = 0;
    if (result.collidedX) this.velocity.x = 0;
    if (result.collidedZ) this.velocity.z = 0;

    // 移动产生的头部晃动与脚步声
    const horizontalSpeed = Math.hypot(
      this.position.x - before.x,
      this.position.z - before.z,
    ) / Math.max(dt, 1e-4);
    if (this.grounded && horizontalSpeed > 0.6) {
      this.bobPhase += dt * horizontalSpeed * 1.5;
      this.stepTimer -= dt * horizontalSpeed;
      if (this.stepTimer <= 0) {
        this.stepTimer = 2.2;
        options.onStep?.(this.sprinting);
      }
    } else {
      this.bobPhase += dt * 0.6;
    }
  }
}

function approach(current: number, target: number, maxDelta: number): number {
  if (current < target) return Math.min(current + maxDelta, target);
  if (current > target) return Math.max(current - maxDelta, target);
  return current;
}
