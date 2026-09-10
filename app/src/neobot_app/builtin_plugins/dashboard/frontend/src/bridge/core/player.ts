// player.ts —— 第一人称角色控制器（MC 手感）
//
// 手感参数刻意贴近 MC：走路 4.5 m/s、冲刺 5.8、蹲行 2.2、跳跃高度约 1.1 m，
// 落地点带一点相机下沉（view kick），走动时有轻微头部起伏（head bob）。
// 舰内是人工重力，所以没有 mc 的游泳/爬梯，改成「喷射跳」二段跳。

import * as THREE from 'three';
import {
  isBlocked,
  playerBox,
  resolveMovement,
  type CollisionBody,
  type CompiledBox,
} from './collision';
import type { InputHandle } from './input';
import { DECK_Y, PLAYER_EYE, PLAYER_HEIGHT, PLAYER_RADIUS, type Vec3 } from './layout';

const WALK_SPEED = 4.5;
const SPRINT_SPEED = 5.8;
const CROUCH_SPEED = 2.2;
const GRAVITY = 22;
const JUMP_SPEED = 7.2;
/** 二段喷射跳：给一个较小的向上速度，够跨过管线与货箱 */
const JET_SPEED = 5.6;
const ACCELERATION = 42;
const AIR_ACCELERATION = 8;
const FRICTION = 12;
const MOUSE_PITCH_LIMIT = Math.PI / 2 - 0.02;
/** 蹲伏时的碰撞体高度：要能钻进 1.3m 高的管线检修口 */
const CROUCH_HEIGHT = 1.25;

/**
 * 世界坐标下的「屏幕右手边」向量。
 *
 * ## 坐标约定（一句话版：+z 是舰艏，yaw 增大是向左转）
 *
 * 世界轴：+x 右舷、+y 上、+z 舰艏。相机姿态由 applyToCamera() 的 lookAt 决定
 * （看向 lookDirection(yaw, pitch)，上方向固定为 +y），因此以下三条是**定义**，
 * 不是拟合出来的经验值：
 *
 *     前向 forward(yaw) = ( sin yaw, 0,  cos yaw )      ← lookDirection 的水平分量
 *     右向 right(yaw)   = ( -cos yaw, 0, sin yaw )      ← 本函数
 *     上向              = ( 0, 1, 0 )                   ← 永远朝上，画面不会翻
 *
 * 校验方式（不需要背公式）：对正交基应有 cross(forward, right) = -up、
 * cross(forward, up) = right。代入 yaw=0 得 forward=(0,0,1)、right=(-1,0,0)，
 * cross((0,0,1),(-1,0,0)) = (0,-1,0) = -up ✓。
 *
 * 注意「yaw 增大 = 向左转」：在 +z 朝舰艏、+x 朝右舷的世界里，面向舰艏时
 * 右手边是 -x，所以向屏幕右转会让 x 分量变大（前向 = sin yaw），
 * 也就是 yaw 变小。鼠标向右拖 → yaw 减小，见 Player.update() 里的 `-=`。
 *
 * 之前踩过的三种错法，留作对照（都表现为「某个轴反了」）：
 *   · 右向取成 (cos yaw, 0, -sin yaw) → 鼠标正常但 WASD 四个方向全反；
 *   · 手写 rotation.y = yaw 而非 yaw+π → 相机上向翻成 -y，画面上下颠倒；
 *   · 手写 rotation.y = -yaw → 鼠标左右反。
 */
export function rightAxis(yaw: number, target = { x: 0, z: 0 }): { x: number; z: number } {
  target.x = -Math.cos(yaw);
  target.z = Math.sin(yaw);
  return target;
}

export interface PlayerEvents {
  onFootstep?: () => void;
  onJump?: () => void;
  onLand?: (impactSpeed: number) => void;
  onJetpack?: () => void;
}

export class Player {
  readonly position = new THREE.Vector3();
  readonly velocity = new THREE.Vector3();
  yaw = 0;
  pitch = 0;
  grounded = false;
  crouching = false;
  /** 固定后的碰撞体，供渲染循环外的射线检测复用 */
  readonly body: CollisionBody;

  private jumpBuffer = 0;
  private coyote = 0;
  private airJumps = 0;
  private bobPhase = 0;
  private bobAmount = 0;
  private viewKick = 0;
  private stepAccumulator = 0;
  private readonly horizontal = new THREE.Vector3();
  /** applyToCamera 每帧都跑，临时向量必须复用，不能每次 new */
  private readonly lookScratch = new THREE.Vector3();
  private readonly headBobUp = new THREE.Vector3(0, 1, 0);

  constructor(spawn: Vec3, yaw: number, private events: PlayerEvents = {}) {
    this.position.set(spawn[0], spawn[1] + 0.001, spawn[2]);
    this.yaw = yaw;
    this.body = {
      position: this.position,
      radius: PLAYER_RADIUS,
      height: PLAYER_HEIGHT,
    };
  }
  /** 传送（舰内跃迁）：同时清零速度，避免落点被惯性带走 */
  teleport(target: Vec3, yaw?: number): void {
    this.position.set(target[0], target[1] + 0.02, target[2]);
    this.velocity.set(0, 0, 0);
    if (yaw !== undefined) this.yaw = yaw;
    this.pitch = 0;
  }

  get eyeHeight(): number {
    return this.crouching ? PLAYER_EYE - 0.55 : PLAYER_EYE;
  }

  /** 相机世界坐标（含头部起伏） */
  applyToCamera(camera: THREE.PerspectiveCamera): void {
    const bobY = this.bobAmount * Math.sin(this.bobPhase * 2) * 0.045;
    const bobX = this.bobAmount * Math.cos(this.bobPhase) * 0.03;
    const right = rightAxis(this.yaw);
    const eyeX = this.position.x + right.x * bobX;
    const eyeY = this.position.y + this.eyeHeight + bobY - this.viewKick;
    const eyeZ = this.position.z + right.z * bobX;

    // 用 lookAt 而不是手写欧拉角：相机姿态直接由「看向哪」和「哪边是上」决定，
    // 不可能出现滚转或上下颠倒，也不用再猜 three 的 -Z 前向与 yaw 的换算关系。
    // 之前正是因为手写 rotation.y = ±yaw(+π) 反复出现「左右反 / 上下反」。
    const look = this.lookDirection(this.lookScratch);
    this.headBobUp.set(0, 1, 0);
    camera.up.copy(this.headBobUp);
    camera.position.set(eyeX, eyeY, eyeZ);
    camera.lookAt(eyeX + look.x, eyeY + look.y, eyeZ + look.z);
    // 行走时的轻微侧倾：绕视线方向的 roll，幅度很小，不会影响方向判定
    if (this.bobAmount > 0.001) {
      camera.rotateZ(this.bobAmount * Math.sin(this.bobPhase) * 0.008);
    }
  }

  /** 视线方向（单位向量）。与相机前向严格一致，由 applyToCamera 的 lookAt 保证 */
  lookDirection(target = new THREE.Vector3()): THREE.Vector3 {
    const cosPitch = Math.cos(this.pitch);
    return target.set(
      Math.sin(this.yaw) * cosPitch,
      Math.sin(this.pitch),
      Math.cos(this.yaw) * cosPitch,
    );
  }

  update(dt: number, input: InputHandle, boxes: Parameters<typeof resolveMovement>[0]): void {
    // ---- 视角 ----
    //
    // 符号约定（配合 rightAxis 的说明一起看）：
    //   · 本世界 yaw=0 朝 +z（舰艏），+x 是右舷；面向舰艏时「屏幕右手边」是 -x，
    //     所以「视线向右转」= 前向 x 分量变大 = yaw 变小，鼠标向右拖用 -=；
    //   · 鼠标向下拖（movementY > 0）视线应向下，pitch 以向上为正，同样用 -=。
    const { state } = input;
    if (state.lookDx !== 0 || state.lookDy !== 0) {
      this.yaw -= state.lookDx;
      this.pitch -= state.lookDy;
      this.pitch = Math.max(-MOUSE_PITCH_LIMIT, Math.min(MOUSE_PITCH_LIMIT, this.pitch));
    }

    // ---- 蹲伏 ----
    const wantCrouch = input.isCrouching();
    if (wantCrouch) {
      this.crouching = true;
    } else if (this.crouching) {
      // 站起前先确认头顶净空，避免卡进管线
      this.body.height = PLAYER_HEIGHT;
      const probe = playerBox(this.position, PLAYER_RADIUS, PLAYER_HEIGHT);
      this.crouching = isBlocked(boxes, probe);
    }
    this.body.height = this.crouching ? CROUCH_HEIGHT : PLAYER_HEIGHT;

    // ---- 期望移动方向：以「前向 + 右向量」为基（两者都必须与相机一致） ----
    const { forward, strafe } = input.readMove();
    const sin = Math.sin(this.yaw);
    const cos = Math.cos(this.yaw);
    const right = rightAxis(this.yaw);
    // forward=(sin,0,cos)、right=(cos,0,-sin)，strafe>0（按 D）就是向右手边走
    const wishX = sin * forward + right.x * strafe;
    const wishZ = cos * forward + right.z * strafe;
    const wishLength = Math.hypot(wishX, wishZ);

    let speed = input.isSprinting() && forward > 0 ? SPRINT_SPEED : WALK_SPEED;
    if (this.crouching) speed = CROUCH_SPEED;

    const accel = this.grounded ? ACCELERATION : AIR_ACCELERATION;
    if (wishLength > 0.001) {
      const dirX = wishX / (wishLength || 1);
      const dirZ = wishZ / (wishLength || 1);
      const scale = Math.min(wishLength, 1);
      this.velocity.x += dirX * accel * scale * dt;
      this.velocity.z += dirZ * accel * scale * dt;
      // 限速：只在水平分量上做，避免影响空中机动
      const current = Math.hypot(this.velocity.x, this.velocity.z);
      const limit = speed * scale;
      if (current > limit) {
        this.horizontal.set(this.velocity.x, 0, this.velocity.z).normalize();
        this.velocity.x = this.horizontal.x * limit;
        this.velocity.z = this.horizontal.z * limit;
      }
    } else if (this.grounded) {
      const decay = Math.max(0, 1 - FRICTION * dt);
      this.velocity.x *= decay;
      this.velocity.z *= decay;
    }

    // ---- 跳跃 / 喷射 ----
    if (state.jumpPressed) this.jumpBuffer = 0.15;
    else this.jumpBuffer = Math.max(0, this.jumpBuffer - dt);

    if (this.grounded) {
      this.coyote = 0.12;
      this.airJumps = 1;
    } else {
      this.coyote = Math.max(0, this.coyote - dt);
    }

    if (this.jumpBuffer > 0) {
      if (this.grounded || this.coyote > 0) {
        this.velocity.y = JUMP_SPEED;
        this.grounded = false;
        this.coyote = 0;
        this.jumpBuffer = 0;
        this.events.onJump?.();
      } else if (this.airJumps > 0) {
        this.velocity.y = JET_SPEED;
        this.airJumps -= 1;
        this.jumpBuffer = 0;
        // 喷射跳顺带补一点前向推力，跨越管沟更顺手
        const dir = this.lookDirection();
        this.velocity.x += dir.x * 1.6;
        this.velocity.z += dir.z * 1.6;
        this.events.onJetpack?.();
      }
    }

    // ---- 重力 ----
    this.velocity.y -= GRAVITY * dt;
    // 终端速度，防止穿透地板
    if (this.velocity.y < -60) this.velocity.y = -60;

    // ---- 位移求解 ----
    const wasGrounded = this.grounded;
    const fallSpeed = this.velocity.y;
    const result = resolveMovement(
      boxes,
      this.body,
      { x: this.velocity.x * dt, y: this.velocity.y * dt, z: this.velocity.z * dt },
      { stepHeight: this.grounded ? 0.45 : 0.2 },
    );
    const movedX = result.x - this.position.x;
    const movedZ = result.z - this.position.z;
    this.position.set(result.x, result.y, result.z);
    this.grounded = result.grounded;

    // 撞墙后把该轴速度清零，否则会一直贴着墙「推」
    if (Math.abs(movedX) < Math.abs(this.velocity.x * dt) * 0.5) this.velocity.x = 0;
    if (Math.abs(movedZ) < Math.abs(this.velocity.z * dt) * 0.5) this.velocity.z = 0;
    if (this.grounded && this.velocity.y < 0) {
      if (!wasGrounded && fallSpeed < -6) {
        // 落地缓冲：速度越高下沉越明显，但不超过 0.18
        this.viewKick = Math.min(0.18, -fallSpeed * 0.014);
        this.events.onLand?.(-fallSpeed);
      }
      this.velocity.y = 0;
    }

    // 掉出舰体（理论上不该发生）→ 送回避难坐标
    if (this.position.y < -12) {
      this.teleport([0, DECK_Y, 0]);
    }

    // ---- 相机反馈 ----
    this.viewKick = Math.max(0, this.viewKick - dt * 0.55);
    const planarSpeed = Math.hypot(this.velocity.x, this.velocity.z);
    if (this.grounded && planarSpeed > 0.6) {
      const target = Math.min(1, planarSpeed / WALK_SPEED);
      this.bobAmount += (target - this.bobAmount) * Math.min(1, dt * 6);
      this.bobPhase += dt * (input.isSprinting() ? 12 : 9);
      // 脚步节奏：按累计位移触发，与视觉起伏大致同步
      this.stepAccumulator += dt * planarSpeed;
      if (this.stepAccumulator > (input.isSprinting() ? 1.9 : 2.4)) {
        this.stepAccumulator = 0;
        this.events.onFootstep?.();
      }
    } else {
      this.bobAmount += (0 - this.bobAmount) * Math.min(1, dt * 5);
    }
  }
}
