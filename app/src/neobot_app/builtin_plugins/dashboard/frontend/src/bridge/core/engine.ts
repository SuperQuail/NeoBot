// engine.ts —— 舰内第一人称引擎（three.js 侧）
//
// 职责边界：
//   · 本文件只管「世界」：场景、渲染循环、角色、碰撞、可见交互目标、影视化反馈；
//   · React 只管「界面」：抬头显示器、全息面板、小游戏都由 React 渲染，
//     引擎通过 EngineCallbacks 单向通知，快照供 HUD 低频读取。
// 这样面板可以随时卸载重建，渲染循环不受影响，也不会因为 React 重渲染丢状态。

import * as THREE from 'three';
import { compileColliders, findFreePosition, isLineBlocked, type CompiledBox } from './collision';
import { createInput, ACTION, HOTKEY_ORDER, type InputHandle } from './input';
import {
  DOOR_WIDTH,
  PLAYER_RADIUS,
  SPAWN_POSITION,
  SPAWN_YAW,
  isInsideHull,
  zoneAt,
  zoneLabel,
  type Vec3,
} from './layout';
import { Player } from './player';
import { sfx, startAmbient } from './sound';
import { addDistance, collectItem, getLog, markVisited, notify } from './store';
import { STATIONS, type PanelId, type Station, type VitalKey } from './types';
import { vitalStatus } from './vitals';
import { buildShip, type ShipHandle, type ShipInteractable } from '../three/ship';

/** 面向 React 的每帧（节流后）快照 */
export interface HudSnapshot {
  x: number;
  y: number;
  z: number;
  yaw: number;
  zone: string;
  zoneCode: string;
  grounded: boolean;
  sprinting: boolean;
  crouching: boolean;
  fps: number;
  /** 当前可交互目标（面向玩家且在射程内） */
  target: InteractionTarget | null;
  /** 已收集物资数量 */
  collected: number;
  /** 玩家与舰内终端的最近距离，用于导航提示 */
  nearestStation: { id: PanelId; label: string; distance: number } | null;
}

export type InteractionKind = 'station' | 'pickup' | 'minigame' | 'prop';

export interface InteractionTarget {
  kind: InteractionKind;
  id: string;
  label: string;
  hint: string;
  distance: number;
  /** kind==='station' 时给出终端 id */
  station?: Station;
  item?: string;
  miniGame?: string;
}

export interface EngineCallbacks {
  /** 交互目标变化（含进入/离开射程），用于提示条的按键前缀 */
  onTargetChange?: (target: InteractionTarget | null) => void;
  /** 请求打开终端面板 */
  onOpenPanel?: (id: PanelId, station: Station) => void;
  /** 请求启动小游戏 */
  onLaunchMiniGame?: (key: string) => void;
  /** 舰内跃迁到某终端 */
  onWarp?: (station: Station) => void;
  /** 舰况告警（由 React 侧的 vitals 判定后回灌） */
  onAlarm?: (vital: VitalKey, value: number) => void;
}

export interface EngineOptions {
  canvas: HTMLCanvasElement;
  callbacks?: EngineCallbacks;
  /** 画质：low 用于小屏/低端设备，关闭阴影与环境反射 */
  quality?: 'low' | 'high';
}

const INTERACT_RANGE = 3.4;
const MINIGAME_RANGE = 3.2;
const DOOR_TRIGGER = 4.2;
const SNAPSHOT_INTERVAL = 1 / 12;
/** 视角朝向与目标方向的最小夹角余弦：正对终端才能接入 */
const FACING_DOT = 0.35;

export class BridgeEngine {
  readonly scene = new THREE.Scene();
  readonly camera: THREE.PerspectiveCamera;
  readonly player: Player;
  readonly input: InputHandle;

  private readonly renderer: THREE.WebGLRenderer;
  private readonly canvas: HTMLCanvasElement;
  private readonly callbacks: EngineCallbacks;
  private readonly quality: 'low' | 'high';
  private readonly clock = new THREE.Clock();
  private ship: ShipHandle | null = null;
  private boxes: CompiledBox[] = [];
  private raf = 0;
  private disposed = false;
  private elapsed = 0;
  private snapshotTimer = 0;
  private fps = 60;
  private frames = 0;
  private fpsTimer = 0;
  private currentTarget: InteractionTarget | null = null;
  private collectedIds = new Set<string>();
  private distanceAccumulator = 0;
  private lastPosition = new THREE.Vector3(...SPAWN_POSITION);
  private stopAmbient: (() => void) | null = null;
  private highlight: THREE.Mesh | null = null;
  private dust: THREE.Points | null = null;
  private readonly resizeObserver: ResizeObserver | null = null;
  private readonly look = new THREE.Vector3();
  private paused = false;

  constructor(options: EngineOptions) {
    this.canvas = options.canvas;
    this.callbacks = options.callbacks ?? {};
    this.quality = options.quality ?? 'high';

    this.renderer = new THREE.WebGLRenderer({
      canvas: options.canvas,
      antialias: this.quality === 'high',
      powerPreference: 'high-performance',
      alpha: false,
      stencil: false,
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, this.quality === 'high' ? 2 : 1.25));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    // 轻微的电影感色调映射，让自发光蓝色不发灰
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.shadowMap.enabled = false;
    this.renderer.setClearColor(0x05070d, 1);

    this.camera = new THREE.PerspectiveCamera(74, 1, 0.05, 900);
    this.player = new Player(SPAWN_POSITION, SPAWN_YAW, {
      onFootstep: () => sfx.step(),
      onJump: () => sfx.jump(),
      onLand: (impact) => {
        sfx.land();
        if (impact > 9) sfx.alarm();
      },
      onJetpack: () => sfx.jump(),
    });

    this.input = createInput(options.canvas, { sensitivity: 0.0022 });
    this.buildWorld();

    this.resizeObserver =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => this.resize());
    if (this.resizeObserver) {
      this.resizeObserver.observe(options.canvas.parentElement ?? options.canvas);
    }
    window.addEventListener('resize', this.resize);
    document.addEventListener('visibilitychange', this.onVisibilityChange);
    this.resize();
  }

  // ------------------------------------------------------------------
  // 世界构建
  // ------------------------------------------------------------------

  private buildWorld(): void {
    this.scene.background = new THREE.Color(0x04060c);
    this.scene.fog = new THREE.FogExp2(0x060a14, 0.012);

    const ship = buildShip(this.scene, { quality: this.quality });
    this.ship = ship;
    ship.root.name = 'neobot-ship';
    this.boxes = compileColliders(ship.colliders);

    // 存档里已收集过的物资不再出现（刷新页面后站位保持一致）
    const log = getLog();
    for (const interactable of ship.interactables) {
      if (interactable.kind !== 'pickup') continue;
      const owned = interactable.item
        ? (log.inventory[interactable.item as keyof typeof log.inventory] ?? 0)
        : 0;
      if (owned > 0) {
        interactable.collected = true;
        interactable.object.visible = false;
        this.collectedIds.add(interactable.id);
      }
    }

    // 交互高亮环：跟随当前目标，给玩家「已锁定」的反馈
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.42, 0.52, 28),
      new THREE.MeshBasicMaterial({
        color: 0x4fe3ff,
        transparent: true,
        opacity: 0.75,
        side: THREE.DoubleSide,
        depthWrite: false,
      }),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.visible = false;
    ring.renderOrder = 5;
    this.scene.add(ring);
    this.highlight = ring;

    this.dust = this.createDust();
    this.scene.add(this.dust);

    // 出生点若被道具挡住（布局调整后可能发生），就近挪到枢纽中央
    if (this.isBlockedAt(this.player.position)) {
      this.player.teleport([0, 0, 0], SPAWN_YAW);
    }
  }

  private isBlockedAt(position: THREE.Vector3): boolean {
    const box = {
      minX: position.x - PLAYER_RADIUS,
      minY: position.y,
      minZ: position.z - PLAYER_RADIUS,
      maxX: position.x + PLAYER_RADIUS,
      maxY: position.y + 1.8,
      maxZ: position.z + PLAYER_RADIUS,
      tag: 'player',
    };
    return this.boxes.some(
      (item) =>
        box.minX < item.maxX &&
        box.maxX > item.minX &&
        box.minY < item.maxY &&
        box.maxY > item.minY &&
        box.minZ < item.maxZ &&
        box.maxZ > item.minZ,
    );
  }

  /** 舱内浮尘：几颗粒子就能明显提升「有体积感」的观感，成本极低 */
  private createDust(): THREE.Points {
    const count = this.quality === 'high' ? 420 : 160;
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i += 1) {
      // 沿走廊与舱室撒点，避免把粒子浪费在看不见的地方
      const along = (Math.random() - 0.5) * 76;
      const across = (Math.random() - 0.5) * 30;
      const vertical = Math.random() * 3.8 + 0.2;
      if (Math.random() > 0.5) {
        positions[i * 3] = across;
        positions[i * 3 + 1] = vertical;
        positions[i * 3 + 2] = along;
      } else {
        positions[i * 3] = along;
        positions[i * 3 + 1] = vertical;
        positions[i * 3 + 2] = across;
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const material = new THREE.PointsMaterial({
      color: 0x9fd8ff,
      size: 0.045,
      transparent: true,
      opacity: 0.5,
      depthWrite: false,
      sizeAttenuation: true,
    });
    const points = new THREE.Points(geometry, material);
    points.name = 'dust';
    return points;
  }

  // ------------------------------------------------------------------
  // 生命周期
  // ------------------------------------------------------------------

  start(): void {
    if (this.raf !== 0) return;
    this.stopAmbient = startAmbient();
    this.clock.start();
    const loop = () => {
      this.raf = requestAnimationFrame(loop);
      this.frame();
    };
    this.raf = requestAnimationFrame(loop);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    if (this.raf !== 0) cancelAnimationFrame(this.raf);
    this.raf = 0;
    this.resizeObserver?.disconnect();
    window.removeEventListener('resize', this.resize);
    document.removeEventListener('visibilitychange', this.onVisibilityChange);
    this.stopAmbient?.();
    this.input.dispose();

    if (this.dust) {
      this.scene.remove(this.dust);
      this.dust.geometry.dispose();
      (this.dust.material as THREE.Material).dispose();
      this.dust = null;
    }
    if (this.highlight) {
      this.scene.remove(this.highlight);
      this.highlight.geometry.dispose();
      (this.highlight.material as THREE.Material).dispose();
      this.highlight = null;
    }
    this.ship?.dispose();
    if (this.ship) this.scene.remove(this.ship.root);
    this.ship = null;
    this.renderer.dispose();
  }

  private onVisibilityChange = () => {
    // 后台标签页不渲染，回来后重置时钟避免一次巨大的 dt
    this.paused = document.hidden;
    if (!this.paused) this.clock.getDelta();
  };

  private resize = () => {
    const parent = this.canvas.parentElement;
    const width = parent?.clientWidth || window.innerWidth;
    const height = parent?.clientHeight || window.innerHeight;
    if (width === 0 || height === 0) return;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  };

  // ------------------------------------------------------------------
  // 每帧
  // ------------------------------------------------------------------

  private frame(): void {
    if (this.disposed) return;
    // dt 上限 1/20 秒：卡顿或切标签页回来时不会瞬移穿墙
    const dt = Math.min(this.clock.getDelta(), 0.05);
    if (this.paused) {
      this.renderer.render(this.scene, this.camera);
      return;
    }
    this.elapsed += dt;

    this.player.update(dt, this.input, this.boxes);
    this.player.applyToCamera(this.camera);
    this.applyShake(dt);
    this.ship?.update(dt, this.elapsed);

    if (this.dust) {
      this.dust.rotation.y = this.elapsed * 0.01;
      this.dust.position.y = Math.sin(this.elapsed * 0.2) * 0.06;
    }

    this.updateDoors(dt);
    this.updateTargeting();
    this.updateTracking(dt);
    this.ensureNotStuck();
    this.handleActions();

    this.renderer.render(this.scene, this.camera);

    // 帧率统计 + 快照节流（HUD 不需要每帧重渲染）
    this.frames += 1;
    this.fpsTimer += dt;
    if (this.fpsTimer >= 0.5) {
      this.fps = Math.round(this.frames / this.fpsTimer);
      this.frames = 0;
      this.fpsTimer = 0;
    }
    this.snapshotTimer += dt;
    if (this.snapshotTimer >= SNAPSHOT_INTERVAL) {
      this.snapshotTimer = 0;
      this.callbacks.onTargetChange?.(this.currentTarget);
    }
    this.input.endFrame();
  }

  private shake = 0;

  /** 舰况告警时轻微晃动镜头 */
  private applyShake(dt: number): void {
    if (this.shake <= 0) return;
    this.shake = Math.max(0, this.shake - dt * 1.6);
    const amount = this.shake * 0.045;
    this.camera.position.x += (Math.random() - 0.5) * amount;
    this.camera.position.y += (Math.random() - 0.5) * amount;
  }

  /**
   * 卡死自救：传送落点或布局变更可能让角色正好落在碰撞体内，
   * 此时分轴推进会把所有方向都判成撞墙。检测到就就近挪到空位，
   * 避免出现「视角能转、人一动不动」的假死状态。
   */
  private ensureNotStuck(): void {
    const stuck = this.isBlockedAt(this.player.position);
    if (!stuck) {
      this.stuckFrames = 0;
      return;
    }
    this.stuckFrames += 1;
    // 只在先出现异常时判定一次，避免贴墙瞬移
    if (this.stuckFrames !== 3) return;
    const free = findFreePosition(this.boxes, this.player.body, { maxRadius: 6 });
    if (free) {
      this.player.teleport([free.x, free.y, free.z]);
      notify('姿态修正：已脱离舱壁干涉区', 'warn');
    }
    this.stuckFrames = 0;
  }

  private stuckFrames = 0;

  /** 触发镜头震动（受损、爆炸、跃迁） */
  triggerShake(strength = 1): void {
    this.shake = Math.min(2, this.shake + strength);
  }

  private updateDoors(dt: number): void {
    const ship = this.ship;
    if (!ship) return;
    // 复用同一个临时向量：这个循环每帧都跑，逐帧 new Vector3 会持续制造垃圾
    const world = this.doorProbe;
    for (const door of ship.doors) {
      door.object.getWorldPosition(world);
      const distance = this.player.position.distanceTo(world);
      const next = distance < DOOR_TRIGGER;
      if (next !== door.open) {
        door.open = next;
        sfx.door();
      }
      // 用真实 dt：高刷屏（120Hz）下固定 1/60 会让门动画快一倍
      door.update(dt);
    }
  }

  private readonly doorProbe = new THREE.Vector3();

  // ------------------------------------------------------------------
  // 交互目标
  // ------------------------------------------------------------------

  /** 在终端与场景道具中挑选「正对且最近」的一个作为交互目标 */
  private updateTargeting(): void {
    const eye = new THREE.Vector3(
      this.player.position.x,
      this.player.position.y + this.player.eyeHeight,
      this.player.position.z,
    );
    this.player.lookDirection(this.look);

    // 用可变容器承载候选目标：只在属性上赋值，避免 TS 把变量收窄成 never
    const pick: { target: InteractionTarget | null; position: THREE.Vector3 } = {
      target: null,
      position: new THREE.Vector3(),
    };
    let bestScore = -Infinity;

    const consider = (target: InteractionTarget, point: THREE.Vector3, range: number) => {
      const toTarget = point.clone().sub(eye);
      const distance = toTarget.length();
      if (distance > range) return;
      const direction = toTarget.normalize();
      const facing = direction.dot(this.look);
      if (facing < FACING_DOT) return;
      // 越近、越正对得分越高；两个条件都影响排序，避免「贴脸但侧对」也能接入
      const score = facing * 2 - distance / range;
      if (score > bestScore) {
        bestScore = score;
        pick.target = target;
        pick.position = point.clone();
      }
    };

    for (const station of STATIONS) {
      consider(
        {
          kind: 'station',
          id: `station:${station.id}`,
          label: station.label,
          hint: `接入 ${station.terminal}`,
          distance: 0,
          station,
        },
        new THREE.Vector3(station.anchor[0], station.anchor[1] + 1.0, station.anchor[2]),
        INTERACT_RANGE,
      );
    }

    for (const interactable of this.ship?.interactables ?? []) {
      if (interactable.kind === 'prop' || interactable.collected) continue;
      consider(
        {
          kind: interactable.kind === 'minigame' ? 'minigame' : 'pickup',
          id: interactable.id,
          label: interactable.hint,
          hint: interactable.hint,
          distance: 0,
          item: interactable.item,
          miniGame: interactable.miniGame,
        },
        interactable.position.clone(),
        interactable.kind === 'minigame' ? MINIGAME_RANGE : INTERACT_RANGE,
      );
    }

    // 隔墙不能操作：终端与道具都要求视线可达
    if (pick.target !== null) {
      if (isLineBlocked(this.boxes, eye, pick.position)) {
        pick.target = null;
      } else {
        pick.target.distance = pick.position.distanceTo(eye);
      }
    }

    const resolved: InteractionTarget | null = pick.target;

    if (resolved !== this.currentTarget) {
      this.currentTarget = resolved;
      if (this.highlight) {
        const position = resolved ? this.targetPosition(resolved) : null;
        this.highlight.visible = position !== null;
        if (position) this.highlight.position.set(position.x, 0.06, position.z);
      }
      this.callbacks.onTargetChange?.(resolved);
    } else if (this.highlight && this.currentTarget) {
      // 高亮环呼吸，提示可交互
      const material = this.highlight.material as THREE.MeshBasicMaterial;
      material.opacity = 0.5 + Math.sin(this.elapsed * 3.2) * 0.25;
    }
  }

  private findInteractablePosition(id: string): THREE.Vector3 | null {
    const found = this.ship?.interactables.find((item) => item.id === id);
    return found ? found.position.clone() : null;
  }

  private targetPosition(target: InteractionTarget): THREE.Vector3 | null {
    if (target.station) {
      return new THREE.Vector3(target.station.anchor[0], target.station.anchor[1] + 1.0, target.station.anchor[2]);
    }
    return this.findInteractablePosition(target.id);
  }

  private updateTracking(dt: number): void {
    const moved = this.player.position.distanceTo(this.lastPosition);
    this.lastPosition.copy(this.player.position);
    if (moved < 3) {
      this.distanceAccumulator += moved;
      if (this.distanceAccumulator >= 25) {
        addDistance(this.distanceAccumulator);
        this.distanceAccumulator = 0;
      }
    }
    void dt;
  }

  // ------------------------------------------------------------------
  // 动作分发
  // ------------------------------------------------------------------

  private handleActions(): void {
    const actions = this.input.state.actions;
    if (actions.length === 0) return;
    for (const action of actions) {
      if (action === ACTION.interact) {
        this.performInteract();
      } else if (action.startsWith('terminal:')) {
        const digit = action.slice('terminal:'.length);
        const index = (HOTKEY_ORDER as readonly string[]).indexOf(digit);
        if (index >= 0 && index < STATIONS.length) {
          const station = STATIONS[index];
          const distance = this.player.position.distanceTo(
            new THREE.Vector3(station.anchor[0], station.anchor[1], station.anchor[2]),
          );
          markVisited(station.id);
          sfx.open();
          this.callbacks.onOpenPanel?.(station.id, station);
          if (distance > 6) this.callbacks.onWarp?.(station);
        }
      }
    }
  }

  /** 由 HUD 的交互按钮调用（触屏与键鼠共用同一条路径） */
  performInteract(): void {
    const target = this.currentTarget;
    if (!target) {
      sfx.deny();
      notify('附近没有可接入的舰载设备', 'warn');
      return;
    }
    if (target.kind === 'station' && target.station) {
      markVisited(target.station.id);
      sfx.open();
      this.callbacks.onOpenPanel?.(target.station.id, target.station);
      return;
    }
    if (target.kind === 'minigame') {
      if (target.miniGame) {
        sfx.open();
        this.callbacks.onLaunchMiniGame?.(target.miniGame);
      } else {
        sfx.deny();
      }
      return;
    }
    if (target.kind === 'pickup') {
      const interactable = this.ship?.interactables.find((item) => item.id === target.id);
      if (interactable && !interactable.collected) {
        interactable.collected = true;
        interactable.object.visible = false;
        this.collectedIds.add(interactable.id);
        sfx.pickup();
        if (interactable.item) {
          collectItem(interactable.item as Parameters<typeof collectItem>[0]);
          notify(`已回收 ${target.label}`, 'good');
        }
      }
      this.currentTarget = null;
    }
  }

  /** HUD 高频读取的轻量快照 */
  snapshot(): HudSnapshot {
    const zone = zoneAt(this.player.position.x, this.player.position.z);
    let nearest: HudSnapshot['nearestStation'] = null;
    for (const station of STATIONS) {
      const distance = this.player.position.distanceTo(
        new THREE.Vector3(station.anchor[0], station.anchor[1], station.anchor[2]),
      );
      if (!nearest || distance < nearest.distance) {
        nearest = { id: station.id, label: station.label, distance };
      }
    }
    return {
      x: this.player.position.x,
      y: this.player.position.y,
      z: this.player.position.z,
      yaw: this.player.yaw,
      zone: zoneLabel(zone),
      zoneCode: 'code' in (zone ?? {}) ? (zone as { code: string }).code : (zone?.id ?? 'OUTSIDE'),
      grounded: this.player.grounded,
      sprinting: this.input.isSprinting(),
      crouching: this.player.crouching,
      fps: this.fps,
      target: this.currentTarget,
      collected: this.collectedIds.size,
      nearestStation: nearest,
    };
  }

  /** 当前面向的交互目标（HUD 与触屏按钮读取） */
  getTarget(): InteractionTarget | null {
    return this.currentTarget;
  }

  /** 舰内跃迁：瞬移到终端门前并朝内站立 */
  warpTo(station: Station): void {
    const [x, y, z] = station.anchor;
    // 从终端法线方向后退 2.4m：终端面朝 facing，玩家应站在 facing 的反方向
    const offset = 2.4;
    const target: Vec3 = [x - Math.sin(station.facing) * offset, y, z - Math.cos(station.facing) * offset];
    if (!isInsideHull(target[0], target[2])) {
      target[0] = x;
      target[2] = z;
    }
    const yaw = Math.atan2(x - target[0], z - target[2]);
    this.player.teleport(target, yaw);
    this.triggerShake(0.6);
    sfx.warp();
    notify(`已跃迁至 ${station.label}`, 'info');
  }

  /** 舰况告警联动：严重时镜头抖动，给玩家「舰体在响」的体感 */
  reportVitals(vitals: { key: VitalKey; value: number }[]): void {
    for (const vital of vitals) {
      if (vitalStatus(vital.key, vital.value) === 'critical') {
        this.shake = Math.max(this.shake, 0.35);
      }
    }
  }

  /** 门宽常量导出给 HUD 做提示文案时保持一致 */
  static readonly doorWidth = DOOR_WIDTH;
}

/** 场景里所有交互道具的数量（HUD 显示探索进度用） */
export function countPickups(ship: ShipHandle | null): number {
  if (!ship) return 0;
  return ship.interactables.filter((item: ShipInteractable) => item.kind === 'pickup').length;
}
