// turret.tsx —— 舰炮演习（近防炮位模拟器）
//
// 设计要点：
// 1) 纯逻辑与渲染彻底分离：createTurretState / stepTurret 只做数学，不碰 DOM 与 WebGL，
//    所以 jsdom（没有 WebGL）里也能直接单测命中、连击、过热、舰体损伤与结算。
// 2) 三维视窗用本组件自建的 WebGLRenderer 画在自建的 canvas 上：canvas 在 effect 内创建、
//    卸载时移除并强制归还上下文 —— React StrictMode 会挂载两次，不做这一步就会留下两个画布
//    并把浏览器的 WebGL 上下文配额耗光。
// 3) 拿不到 WebGL（软件渲染 / 远程桌面 / 测试环境）时自动降级为 HUD 平面瞄准模式：
//    规则、计分与操作完全一致，只是没有三维视窗，画布也不会被创建。

import { useCallback, useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { sfx } from '../../core/sound';
import { unlock } from '../../core/store';
import './minigames.css';

/** 三个小游戏共用的 props 契约（各文件各自导出，父级只依赖结构） */
export interface MiniGameProps {
  /** 一次演习结束时回调，父级负责存档与提示 */
  onFinish: (score: number) => void;
  /** 关闭小游戏并回到自由巡航 */
  onExit: () => void;
  /** 舰体完整度 0..100（父级由真实系统指标换算），不可用时为 null */
  hullIntegrity: number | null;
}

export const meta = {
  key: 'turret',
  name: '舰炮演习',
  code: 'WPN-SIM',
  brief: '接管近防炮位：击毁逼近舰体的陨石与敌方无人机，坚持满 60 秒。',
  scoring:
    '命中 10 分，击毁额外 15 分，两者都乘连击倍率（每 4 连击 +1 倍，上限 6 倍）；脱靶清零连击；每个突防目标扣减局部舰体完整度。',
} as const;

/** 演习时长（秒） */
export const TURRET_RUN_SECONDS = 60;
/** 击毁该数量以上点亮「近防王牌」成就（与 core/types.ts 的 ACHIEVEMENTS 对齐） */
export const TURRET_ACE_KILLS = 15;
/** 单帧最大推进步长：切后台回来时不允许一帧跳太多 */
export const TURRET_MAX_STEP = 0.25;

const AMMO_START = 120;
const FIRE_INTERVAL = 0.14;
const HEAT_PER_SHOT = 9;
/** 每秒散热上限（舰体受损会打折，见 stepTurret） */
const HEAT_COOL = 18;
const OVERHEAT_AT = 100;
const OVERHEAT_RECOVER = 40;
const HIT_SCORE = 10;
const KILL_SCORE = 15;
const MAX_TARGETS = 12;
/** 撞击伤害 */
const DAMAGE_ASTEROID = 11;
const DAMAGE_DRONE = 7;
/** 渲染用：舰体到瞄准原点的距离与最远生成距离（米） */
const SHIP_DISTANCE = 4;
const SPAWN_DISTANCE = 56;
/** 局部舰体下限：真实舰况再差也要留一点可玩空间 */
const MIN_LOCAL_HULL = 20;

const clamp = (value: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, value));

/** mulberry32 单步：返回 [0,1) 与新状态。用「状态进、状态出」保证纯函数可复现 */
function randStep(seed: number): [number, number] {
  const next = (seed + 0x6d2b79f5) >>> 0;
  let t = next;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return [((t ^ (t >>> 14)) >>> 0) / 4294967296, next];
}

export type TurretTargetKind = 'asteroid' | 'drone';

/** 一个来袭目标。x/y 是「瞄准空间」坐标（-1..1，0 为准星中心），z 是深度（1 最远，0 已抵舰） */
export interface TurretTarget {
  id: number;
  kind: TurretTargetKind;
  x: number;
  y: number;
  z: number;
  /** 剩余结构值，命中一次减 1 */
  hp: number;
  /** 每秒推进的深度比例 */
  speed: number;
  /** 瞄准空间中的基础视半径（未按深度放缩） */
  radius: number;
  /** 摆动相位，让轨迹有轻微漂移 */
  phase: number;
  /** 命中闪光计时（渲染用） */
  flash: number;
}

export type TurretEvent = 'shot' | 'hit' | 'kill' | 'miss' | 'impact' | 'overheat' | 'empty' | 'end';

export interface TurretState {
  status: 'running' | 'over';
  endReason: 'time' | 'hull' | null;
  /** 本次演习的局部舰体完整度（从 hullIntegrity 继承） */
  hull: number;
  /** 父级传入的真实舰体完整度：用于遥测显示与散热效率 */
  sourceHull: number;
  heat: number;
  overheated: boolean;
  ammo: number;
  score: number;
  kills: number;
  hits: number;
  shots: number;
  combo: number;
  bestCombo: number;
  timeLeft: number;
  elapsed: number;
  targets: TurretTarget[];
  spawnTimer: number;
  fireCooldown: number;
  seq: number;
  /** 确定性随机数状态，保证 stepTurret 是纯函数 */
  rng: number;
}

export interface TurretInput {
  /** -1..1，0 为窗口中心 */
  aimX: number;
  aimY: number;
  firing: boolean;
}

export interface TurretStepResult {
  state: TurretState;
  events: TurretEvent[];
}

/** 连击倍率：每 4 连击 +1 倍，上限 6 倍 */
export function comboMultiplier(combo: number): number {
  if (combo <= 0) return 1;
  return Math.min(6, 1 + Math.floor(combo / 4));
}

/** 目标在瞄准空间里的视半径：越近越大，所以贴脸时更好打 */
export function apparentRadius(target: TurretTarget): number {
  return target.radius * (0.5 + 0.5 * (1 - clamp(target.z, 0, 1)));
}

/** 散热回路效率：舰体越破，冷却越慢 —— 让真实舰况影响玩法 */
export function coolingRate(sourceHull: number): number {
  return HEAT_COOL * (0.55 + 0.45 * (clamp(sourceHull, 0, 100) / 100));
}

/** 结算成就：击毁数达标点亮「近防王牌」 */
export function turretAchievements(state: TurretState): string[] {
  return state.kills >= TURRET_ACE_KILLS ? ['turret-ace'] : [];
}

/**
 * 创建一次演习。
 * @param hullIntegrity 父级传入的真实舰体完整度（null = 不可用，按满值处理）
 * @param seed 随机种子（测试传固定值即可复现同一波次）
 */
export function createTurretState(
  hullIntegrity: number | null,
  seed = Date.now() >>> 0,
  seconds = TURRET_RUN_SECONDS,
): TurretState {
  const sourceHull =
    hullIntegrity === null || !Number.isFinite(hullIntegrity) ? 100 : clamp(hullIntegrity, 0, 100);
  return {
    status: 'running',
    endReason: null,
    // 局部舰体从传入值开始，但夹在 [20,100]：真实舰况过低时也要留下可玩空间
    hull: clamp(sourceHull, MIN_LOCAL_HULL, 100),
    sourceHull,
    heat: 0,
    overheated: false,
    ammo: AMMO_START,
    score: 0,
    kills: 0,
    hits: 0,
    shots: 0,
    combo: 0,
    bestCombo: 0,
    timeLeft: seconds,
    elapsed: 0,
    targets: [],
    spawnTimer: 0.35,
    fireCooldown: 0,
    seq: 1,
    rng: seed >>> 0,
  };
}

/** 生成一个来袭目标（纯函数：随机状态进、随机状态出） */
function spawnTarget(state: TurretState): { target: TurretTarget; rng: number; interval: number } {
  let rng = state.rng;
  const [rollKind, s1] = randStep(rng);
  const [rollX, s2] = randStep(s1);
  const [rollY, s3] = randStep(s2);
  const [rollJitter, s4] = randStep(s3);
  rng = s4;

  const ramp = clamp(state.elapsed / TURRET_RUN_SECONDS, 0, 1);
  // 12 秒后开始混入无人机：更快更脆，伤害略低
  const droneChance = clamp((state.elapsed - 12) / 60, 0, 0.45);
  const kind: TurretTargetKind = rollKind < droneChance ? 'drone' : 'asteroid';
  const baseSpeed = kind === 'drone' ? 0.09 : 0.055;
  const speed = (baseSpeed + ramp * (kind === 'drone' ? 0.07 : 0.05)) * (0.85 + rollJitter * 0.3);
  return {
    target: {
      id: state.seq,
      kind,
      x: (rollX * 2 - 1) * 0.85,
      y: (rollY * 2 - 1) * 0.6,
      z: 1,
      hp: kind === 'drone' ? 1 : 2,
      speed,
      radius: kind === 'drone' ? 0.11 : 0.17,
      phase: rollKind * Math.PI * 2,
      flash: 0,
    },
    rng,
    // 难度随时间上升：来袭间隔从 1.7s 压缩到 0.65s
    interval: Math.max(0.5, 1.7 - ramp * 1.05) * (0.85 + rollKind * 0.3),
  };
}

/**
 * 推进一帧演习。纯函数：不修改入参，也不依赖时间/随机源。
 * @param dt 秒（会被夹到 TURRET_MAX_STEP，避免切后台后一帧推进过多）
 */
export function stepTurret(state: TurretState, dt: number, input: TurretInput): TurretStepResult {
  if (state.status === 'over') return { state, events: [] };
  const step = clamp(Number.isFinite(dt) ? dt : 0, 0, TURRET_MAX_STEP);
  const events: TurretEvent[] = [];

  const next: TurretState = {
    ...state,
    targets: [],
    elapsed: state.elapsed + step,
    timeLeft: Math.max(0, state.timeLeft - step),
  };

  // 散热：真实舰况越差，冷却回路效率越低
  next.heat = Math.max(0, next.heat - coolingRate(state.sourceHull) * step);
  if (next.overheated && next.heat <= OVERHEAT_RECOVER) next.overheated = false;

  // 目标推进 + 撞击判定
  for (const target of state.targets) {
    const moved: TurretTarget = { ...target };
    moved.z -= moved.speed * step;
    moved.phase += step * 1.6;
    // 摆动：越接近舰体摆幅越小，否则贴脸时无法命中
    const wobble = 0.4 + clamp(moved.z, 0, 1);
    moved.x = clamp(moved.x + Math.cos(moved.phase) * 0.06 * step * wobble, -1, 1);
    moved.y = clamp(moved.y + Math.sin(moved.phase * 0.7) * 0.05 * step * wobble, -1, 1);
    if (moved.flash > 0) moved.flash = Math.max(0, moved.flash - step);
    if (moved.z <= 0) {
      next.hull = Math.max(0, next.hull - (moved.kind === 'drone' ? DAMAGE_DRONE : DAMAGE_ASTEROID));
      next.combo = 0;
      events.push('impact');
    } else {
      next.targets.push(moved);
    }
  }

  // 开火：弹链 + 温度双重限制
  next.fireCooldown = Math.max(0, next.fireCooldown - step);
  if (input.firing && next.fireCooldown <= 0) {
    if (next.overheated) {
      // 过热期间扣扳机没有反馈音，避免噪音轰炸
    } else if (next.ammo <= 0) {
      next.fireCooldown = 0.35;
      events.push('empty');
    } else {
      next.fireCooldown = FIRE_INTERVAL;
      next.ammo -= 1;
      next.shots += 1;
      next.heat = Math.min(OVERHEAT_AT, next.heat + HEAT_PER_SHOT);
      events.push('shot');
      if (next.heat >= OVERHEAT_AT) {
        next.overheated = true;
        events.push('overheat');
      }

      // 命中判定：取准星容差内最靠近舰体的目标
      let bestIndex = -1;
      let bestZ = Number.POSITIVE_INFINITY;
      for (let index = 0; index < next.targets.length; index += 1) {
        const target = next.targets[index];
        if (target.z < 0.06) continue;
        const tolerance = apparentRadius(target);
        if (
          Math.abs(target.x - input.aimX) <= tolerance &&
          Math.abs(target.y - input.aimY) <= tolerance &&
          target.z < bestZ
        ) {
          bestZ = target.z;
          bestIndex = index;
        }
      }

      if (bestIndex < 0) {
        next.combo = 0;
        events.push('miss');
      } else {
        const hit = next.targets[bestIndex];
        hit.hp -= 1;
        hit.flash = 0.12;
        next.hits += 1;
        next.combo += 1;
        next.bestCombo = Math.max(next.bestCombo, next.combo);
        const multiplier = comboMultiplier(next.combo);
        next.score += HIT_SCORE * multiplier;
        if (hit.hp <= 0) {
          next.kills += 1;
          next.score += KILL_SCORE * multiplier;
          events.push('kill');
          next.targets.splice(bestIndex, 1);
        } else {
          events.push('hit');
        }
      }
    }
  }

  // 生成来袭目标
  next.spawnTimer -= step;
  if (next.spawnTimer <= 0) {
    if (next.targets.length < MAX_TARGETS) {
      const spawned = spawnTarget(next);
      next.targets.push(spawned.target);
      next.seq += 1;
      next.rng = spawned.rng;
      next.spawnTimer = spawned.interval;
    } else {
      next.spawnTimer = 0.4;
    }
  }

  // 结束判定
  if (next.hull <= 0) {
    next.status = 'over';
    next.endReason = 'hull';
    events.push('end');
  } else if (next.timeLeft <= 0) {
    next.status = 'over';
    next.endReason = 'time';
    next.combo = 0;
    events.push('end');
  }
  return { state: next, events };
}

/** WebGL 可用性探针：测试环境 / 无显卡环境返回 false，组件据此走 HUD 平面模式 */
export function detectWebGL(): boolean {
  try {
    const probe = document.createElement('canvas');
    const context = probe.getContext('webgl2') ?? probe.getContext('webgl');
    return Boolean(context);
  } catch {
    return false;
  }
}

/** 音效守卫：AudioContext 从未创建时 sfx 内部会直接 return，这里再兜一层，保证任何环境都不抛 */
function play(effect: () => void): void {
  try {
    effect();
  } catch {
    // 音频不可用：静默降级
  }
}

/** 递归释放场景里的几何与材质（不释放会在 StrictMode 二次挂载时持续占显存） */
function disposeTree(root: THREE.Object3D): void {
  root.traverse((node) => {
    const holder = node as unknown as {
      geometry?: THREE.BufferGeometry;
      material?: THREE.Material | THREE.Material[];
    };
    holder.geometry?.dispose();
    const material = holder.material;
    if (Array.isArray(material)) material.forEach((item) => item.dispose());
    else material?.dispose();
  });
}

type TurretPhase = 'brief' | 'running' | 'over';

interface GlScene {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  meshes: Map<number, THREE.Mesh>;
  rockGeometry: THREE.BufferGeometry;
  droneGeometry: THREE.BufferGeometry;
  rockMaterial: THREE.Material;
  droneMaterial: THREE.Material;
}

const AIM_KEYS = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'w', 'a', 's', 'd']);

export default function TurretGame({ onFinish, onExit, hullIntegrity }: MiniGameProps) {
  const [glReady] = useState<boolean>(() => detectWebGL());
  const [phase, setPhase] = useState<TurretPhase>('brief');
  const [view, setView] = useState<TurretState>(() => createTurretState(hullIntegrity, 1));
  const [aimView, setAimView] = useState({ x: 0, y: 0 });
  const [locked, setLocked] = useState(false);

  const stageRef = useRef<HTMLDivElement | null>(null);
  const glRef = useRef<GlScene | null>(null);
  const stateRef = useRef<TurretState | null>(null);
  const inputRef = useRef<TurretInput>({ aimX: 0, aimY: 0, firing: false });
  const keysRef = useRef<Set<string>>(new Set());
  const runningRef = useRef(false);
  const finishedRef = useRef(false);
  const runSeqRef = useRef(0);
  const hullRef = useRef(hullIntegrity);
  const onFinishRef = useRef(onFinish);

  // 父级传入的值可能随时变化（真实舰况是实时数据），用 ref 同步，避免重建三维场景
  useEffect(() => {
    hullRef.current = hullIntegrity;
  }, [hullIntegrity]);

  useEffect(() => {
    onFinishRef.current = onFinish;
  }, [onFinish]);

  /** 建立三维视窗。canvas 由 effect 自己创建/移除，StrictMode 双挂载不会残留第二个画布 */
  useEffect(() => {
    if (!glReady) return undefined;
    const host = stageRef.current;
    if (!host) return undefined;

    const canvas = document.createElement('canvas');
    canvas.className = 'mg-turret-canvas';
    canvas.setAttribute('aria-label', '舰炮演习三维瞄准视窗');
    host.appendChild(canvas);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: 'high-performance' });
    } catch {
      canvas.remove();
      return undefined;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x04101d);
    scene.fog = new THREE.Fog(0x04101d, 26, 96);
    const camera = new THREE.PerspectiveCamera(64, 1.6, 0.1, 320);
    camera.rotation.order = 'YXZ';

    const rockGeometry = new THREE.IcosahedronGeometry(1, 0);
    const droneGeometry = new THREE.OctahedronGeometry(1, 0);
    const rockMaterial = new THREE.MeshStandardMaterial({
      color: 0x9fb0c0,
      roughness: 0.92,
      metalness: 0.08,
      flatShading: true,
    });
    const droneMaterial = new THREE.MeshStandardMaterial({
      color: 0x7dd3fc,
      emissive: 0x0ea5e9,
      emissiveIntensity: 0.8,
      roughness: 0.35,
    });

    // 舰艏前方的护盾网格：给三维视窗一个深度参照
    const grid = new THREE.GridHelper(140, 20, 0x1d6fa5, 0x0d3b57);
    grid.rotation.x = Math.PI / 2;
    grid.position.z = -3;
    scene.add(grid);

    scene.add(new THREE.HemisphereLight(0x8fd6ff, 0x0a1a2a, 1.15));
    const keyLight = new THREE.DirectionalLight(0xffffff, 1.3);
    keyLight.position.set(3, 4, 6);
    scene.add(keyLight);

    // 星野：确定性随机，保证每次进入观感一致
    const starCount = 420;
    const starPositions = new Float32Array(starCount * 3);
    let starSeed = 20240921;
    for (let index = 0; index < starCount; index += 1) {
      const [a, s1] = randStep(starSeed);
      const [b, s2] = randStep(s1);
      const [c, s3] = randStep(s2);
      starSeed = s3;
      starPositions[index * 3] = (a - 0.5) * 280;
      starPositions[index * 3 + 1] = (b - 0.5) * 170;
      starPositions[index * 3 + 2] = -70 - c * 200;
    }
    const starGeometry = new THREE.BufferGeometry();
    starGeometry.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
    const starMaterial = new THREE.PointsMaterial({
      color: 0xbfe9ff,
      size: 1.1,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.85,
    });
    scene.add(new THREE.Points(starGeometry, starMaterial));

    glRef.current = {
      renderer,
      scene,
      camera,
      meshes: new Map(),
      rockGeometry,
      droneGeometry,
      rockMaterial,
      droneMaterial,
    };

    const resize = (): void => {
      const width = host.clientWidth || 640;
      const height = host.clientHeight || 360;
      camera.aspect = width / Math.max(1, height);
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
    };
    resize();

    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver === 'function') {
      observer = new ResizeObserver(resize);
      observer.observe(host);
    } else {
      window.addEventListener('resize', resize);
    }

    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', resize);
      const gl = glRef.current;
      if (gl) {
        for (const mesh of gl.meshes.values()) gl.scene.remove(mesh);
        gl.meshes.clear();
        disposeTree(gl.scene);
        gl.rockGeometry.dispose();
        gl.droneGeometry.dispose();
        gl.rockMaterial.dispose();
        gl.droneMaterial.dispose();
        gl.renderer.dispose();
        // 主动归还 WebGL 上下文：否则 StrictMode 的两次挂载会各占一个上下文
        gl.renderer.forceContextLoss();
      }
      canvas.remove();
      glRef.current = null;
    };
  }, [glReady]);

  /** 把目标与准星同步到三维场景。命中判定用的是纯数学瞄准空间，这里只是同一参数的投影 */
  const renderScene = useCallback(() => {
    const gl = glRef.current;
    if (!gl) return;
    const input = inputRef.current;
    const halfY = THREE.MathUtils.degToRad(gl.camera.fov * 0.5);
    const halfX = Math.atan(Math.tan(halfY) * Math.max(0.2, gl.camera.aspect));
    const tanY = Math.tan(halfY);
    const tanX = Math.tan(halfX);
    gl.camera.rotation.set(input.aimY * halfY, -input.aimX * halfX, 0);

    const live = new Set<number>();
    const targets = stateRef.current?.targets ?? [];
    for (const target of targets) {
      live.add(target.id);
      let mesh = gl.meshes.get(target.id);
      if (!mesh) {
        mesh = new THREE.Mesh(
          target.kind === 'drone' ? gl.droneGeometry : gl.rockGeometry,
          target.kind === 'drone' ? gl.droneMaterial : gl.rockMaterial,
        );
        mesh.rotation.set(target.phase, target.phase * 1.7, target.phase * 0.6);
        gl.scene.add(mesh);
        gl.meshes.set(target.id, mesh);
      }
      const depth = SHIP_DISTANCE + clamp(target.z, 0, 1) * SPAWN_DISTANCE;
      mesh.position.set(target.x * depth * tanX, target.y * depth * tanY, -depth);
      mesh.scale.setScalar(
        Math.max(0.05, apparentRadius(target) * depth * tanY) * (target.flash > 0 ? 1.4 : 1),
      );
      mesh.rotation.y += 0.012;
    }
    for (const [id, mesh] of gl.meshes) {
      if (live.has(id)) continue;
      gl.scene.remove(mesh);
      gl.meshes.delete(id);
    }
    gl.renderer.render(gl.scene, gl.camera);
  }, []);

  const applyEvents = useCallback((events: readonly TurretEvent[], state: TurretState) => {
    for (const event of events) {
      switch (event) {
        case 'shot':
          play(sfx.shot);
          break;
        case 'hit':
          play(sfx.hit);
          break;
        case 'kill':
          play(sfx.hit);
          play(sfx.pickup);
          break;
        case 'impact':
          // 舰体进入危险区才拉警报，否则只放金属撞击声
          if (state.hull > 0 && state.hull <= 40) play(sfx.alarm);
          else play(sfx.land);
          break;
        case 'overheat':
        case 'empty':
          play(sfx.deny);
          break;
        default:
          break;
      }
    }
  }, []);

  const finishRun = useCallback((state: TurretState) => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    runningRef.current = false;
    inputRef.current.firing = false;
    keysRef.current.clear();
    if (document.pointerLockElement) document.exitPointerLock();
    const badges = turretAchievements(state);
    if (badges.length > 0) play(sfx.achievement);
    if (state.endReason === 'hull') play(sfx.alarm);
    else play(sfx.close);
    for (const badge of badges) unlock(badge);
    setPhase('over');
    setView(state);
    onFinishRef.current(state.score);
  }, []);

  // ---- 主循环：无论有没有 WebGL 都跑同一套纯逻辑，保证两种模式规则一致 ----
  useEffect(() => {
    let raf = 0;
    let last = performance.now();
    let hudClock = 0;
    const tick = (now: number): void => {
      raf = requestAnimationFrame(tick);
      const dt = clamp((now - last) / 1000, 0, 0.1);
      last = now;
      const current = stateRef.current;
      if (current && runningRef.current) {
        const keys = keysRef.current;
        if (keys.size > 0) {
          const input = inputRef.current;
          const speed = 1.15 * dt;
          if (keys.has('ArrowLeft') || keys.has('a')) input.aimX = clamp(input.aimX - speed, -1, 1);
          if (keys.has('ArrowRight') || keys.has('d')) input.aimX = clamp(input.aimX + speed, -1, 1);
          if (keys.has('ArrowUp') || keys.has('w')) input.aimY = clamp(input.aimY + speed, -1, 1);
          if (keys.has('ArrowDown') || keys.has('s')) input.aimY = clamp(input.aimY - speed, -1, 1);
        }
        const result = stepTurret(current, dt, inputRef.current);
        stateRef.current = result.state;
        if (result.events.length > 0) applyEvents(result.events, result.state);
        hudClock += dt;
        // HUD 20Hz 刷新即可，没必要每帧重渲染 DOM
        if (hudClock >= 0.05 || result.state.status === 'over') {
          hudClock = 0;
          setView(result.state);
          setAimView({ x: inputRef.current.aimX, y: inputRef.current.aimY });
        }
        if (result.state.status === 'over') finishRun(result.state);
      }
      renderScene();
    };
    if (typeof requestAnimationFrame === 'function') raf = requestAnimationFrame(tick);
    return () => {
      if (typeof cancelAnimationFrame === 'function') cancelAnimationFrame(raf);
    };
  }, [applyEvents, finishRun, renderScene]);

  // ---- 输入：鼠标绝对位置瞄准 + 拖动 + 指针锁定 + 键盘 ----
  useEffect(() => {
    const host = stageRef.current;
    if (!host) return undefined;

    const aimAt = (clientX: number, clientY: number): void => {
      const rect = host.getBoundingClientRect();
      const width = rect.width || 1;
      const height = rect.height || 1;
      inputRef.current.aimX = clamp(((clientX - rect.left) / width) * 2 - 1, -1, 1);
      inputRef.current.aimY = clamp(1 - ((clientY - rect.top) / height) * 2, -1, 1);
    };

    const onPointerMove = (event: PointerEvent): void => {
      if (document.pointerLockElement) return;
      aimAt(event.clientX, event.clientY);
    };
    const onPointerDown = (event: PointerEvent): void => {
      if (event.button !== 0) return;
      aimAt(event.clientX, event.clientY);
      inputRef.current.firing = true;
      // 这里刻意不调用 preventDefault：取消 pointerdown 会连带压掉兼容鼠标事件，
      // 拖影/选中交给 CSS（user-select:none）处理，双击锁定才不会被误伤。
    };
    const onPointerUp = (): void => {
      inputRef.current.firing = false;
    };
    // 双击锁定指针：锁定后改用相对位移瞄准，长距离转向不再受窗口边界限制
    const onDoubleClick = (): void => {
      const canvas = host.querySelector('canvas');
      if (canvas && typeof canvas.requestPointerLock === 'function' && !document.pointerLockElement) {
        canvas.requestPointerLock();
      }
    };
    const onMouseMove = (event: MouseEvent): void => {
      if (!document.pointerLockElement) return;
      const input = inputRef.current;
      input.aimX = clamp(input.aimX + event.movementX * 0.0022, -1, 1);
      input.aimY = clamp(input.aimY - event.movementY * 0.0022, -1, 1);
    };
    const onLockChange = (): void => setLocked(Boolean(document.pointerLockElement));
    const onKeyDown = (event: KeyboardEvent): void => {
      if (!runningRef.current) return;
      const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
      if (key === ' ') {
        event.preventDefault();
        keysRef.current.add(key);
        inputRef.current.firing = true;
        return;
      }
      if (AIM_KEYS.has(key)) {
        event.preventDefault();
        keysRef.current.add(key);
      }
    };
    const onKeyUp = (event: KeyboardEvent): void => {
      const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
      keysRef.current.delete(key);
      if (key === ' ') inputRef.current.firing = false;
    };

    host.addEventListener('pointermove', onPointerMove);
    host.addEventListener('pointerdown', onPointerDown);
    host.addEventListener('dblclick', onDoubleClick);
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerUp);
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    document.addEventListener('pointerlockchange', onLockChange);
    return () => {
      host.removeEventListener('pointermove', onPointerMove);
      host.removeEventListener('pointerdown', onPointerDown);
      host.removeEventListener('dblclick', onDoubleClick);
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerUp);
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      document.removeEventListener('pointerlockchange', onLockChange);
    };
  }, []);

  const startRun = useCallback(() => {
    runSeqRef.current += 1;
    const seed = (Date.now() ^ (runSeqRef.current * 0x9e3779b9)) >>> 0;
    const fresh = createTurretState(hullRef.current, seed);
    stateRef.current = fresh;
    inputRef.current = { aimX: 0, aimY: 0, firing: false };
    keysRef.current.clear();
    finishedRef.current = false;
    runningRef.current = true;
    setAimView({ x: 0, y: 0 });
    setView(fresh);
    setPhase('running');
    play(sfx.pulse);
  }, []);

  const handleExit = useCallback(() => {
    runningRef.current = false;
    inputRef.current.firing = false;
    if (document.pointerLockElement) document.exitPointerLock();
    play(sfx.close);
    onExit();
  }, [onExit]);

  const handleCellAim = useCallback((dx: number, dy: number) => {
    const input = inputRef.current;
    input.aimX = clamp(input.aimX + dx, -1, 1);
    input.aimY = clamp(input.aimY + dy, -1, 1);
    setAimView({ x: input.aimX, y: input.aimY });
  }, []);

  const heatPercent = Math.round(view.heat);
  const coolingPercent = Math.round((coolingRate(view.sourceHull) / HEAT_COOL) * 100);
  // 舰况是实时数据：遥测显示父级当前传入的值，而散热效率沿用开局快照（演习中途不改规则）
  const liveHull =
    hullIntegrity === null || !Number.isFinite(hullIntegrity)
      ? null
      : Math.round(clamp(hullIntegrity, 0, 100));
  const running = phase === 'running';

  return (
    <section className="mg-root mg-turret" aria-label={`${meta.name} · ${meta.code}`}>
      <header className="mg-head">
        <div className="mg-head-main">
          <span className="mg-code">{meta.code}</span>
          <h2 className="mg-title">{meta.name}</h2>
        </div>
        <div className="mg-head-side">
          <span className={`mg-chip ${glReady ? 'is-ok' : 'is-warn'}`}>
            {glReady ? '三维视窗在线' : 'HUD 平面模式'}
          </span>
          {locked ? <span className="mg-chip is-ok">指针已锁定</span> : null}
          <button type="button" className="mg-btn is-ghost" onClick={handleExit}>
            返回
          </button>
        </div>
      </header>

      <div className="mg-stage" ref={stageRef}>
        {glReady ? null : (
          <div className="mg-flat">
            {view.targets.map((target) => {
              const size = Math.max(2, apparentRadius(target) * 100);
              return (
                <span
                  key={target.id}
                  className={`mg-flat-blip is-${target.kind}`}
                  style={{
                    left: `${50 + (target.x - aimView.x) * 50}%`,
                    top: `${50 - (target.y - aimView.y) * 50}%`,
                    width: `${size}%`,
                    height: `${size}%`,
                  }}
                />
              );
            })}
          </div>
        )}
        <div className="mg-crosshair" />

        {phase !== 'brief' ? (
          <div className="mg-hud">
            <div className="mg-hud-top">
              <span className="mg-hud-clock">{view.timeLeft.toFixed(1)}s</span>
              <span className="mg-hud-score">{view.score}</span>
            </div>

            <div className="mg-hud-bars">
              <div className="mg-bar-row">
                <span className="mg-bar-label">局部舰体</span>
                <div
                  className="mg-bar"
                  role="progressbar"
                  aria-label="局部舰体完整度"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(view.hull)}
                >
                  <div
                    className={`mg-bar-fill ${view.hull <= 35 ? 'is-err' : 'is-ok'}`}
                    style={{ width: `${view.hull}%` }}
                  />
                </div>
                <span className="mg-bar-value">{Math.round(view.hull)}%</span>
              </div>
              <div className="mg-bar-row">
                <span className="mg-bar-label">炮塔温度</span>
                <div
                  className="mg-bar"
                  role="progressbar"
                  aria-label="炮塔温度"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={heatPercent}
                >
                  <div
                    className={`mg-bar-fill ${view.overheated ? 'is-err' : 'is-warn'}`}
                    style={{ width: `${heatPercent}%` }}
                  />
                </div>
                <span className="mg-bar-value">{view.overheated ? '过热' : `${heatPercent}%`}</span>
              </div>
            </div>

            <dl className="mg-telemetry">
              <div>
                <dt>舰体实况</dt>
                <dd>{liveHull === null ? '—' : `${liveHull}%`}</dd>
              </div>
              <div>
                <dt>散热回路</dt>
                <dd>{coolingPercent}%</dd>
              </div>
              <div>
                <dt>弹链</dt>
                <dd>{view.ammo} 发</dd>
              </div>
              <div>
                <dt>击毁</dt>
                <dd>{view.kills}</dd>
              </div>
              <div>
                <dt>连击</dt>
                <dd>
                  {view.combo} ×{comboMultiplier(view.combo)}
                </dd>
              </div>
              <div>
                <dt>来袭</dt>
                <dd>{view.targets.length}</dd>
              </div>
            </dl>

            {/* 触屏/无鼠标场景的备用瞄准与开火控件 */}
            <div className="mg-touch-pad">
              <button
                type="button"
                className="mg-btn is-ghost"
                onClick={() => handleCellAim(-0.12, 0)}
                aria-label="炮塔左转"
              >
                ◀
              </button>
              <button
                type="button"
                className="mg-btn is-ghost"
                onClick={() => handleCellAim(0, 0.12)}
                aria-label="炮塔上仰"
              >
                ▲
              </button>
              <button
                type="button"
                className="mg-btn is-ghost"
                onClick={() => handleCellAim(0, -0.12)}
                aria-label="炮塔下俯"
              >
                ▼
              </button>
              <button
                type="button"
                className="mg-btn is-ghost"
                onClick={() => handleCellAim(0.12, 0)}
                aria-label="炮塔右转"
              >
                ▶
              </button>
            </div>
          </div>
        ) : null}

        {phase === 'brief' ? (
          <div className="mg-overlay">
            <h3 className="mg-overlay-title">演习简报</h3>
            <p className="mg-brief">{meta.brief}</p>
            <p className="mg-scoring">{meta.scoring}</p>
            {!glReady ? (
              <p className="mg-note">本终端未启用 3D 加速，已切换为 HUD 平面瞄准模式（规则与计分一致）。</p>
            ) : null}
            <button type="button" className="mg-btn is-primary" onClick={startRun}>
              开始演习
            </button>
          </div>
        ) : null}

        {phase === 'over' ? (
          <div className="mg-overlay">
            <h3 className="mg-overlay-title">
              {view.endReason === 'hull' ? '舰体受损 · 演习终止' : '演习结束'}
            </h3>
            <p className="mg-brief">
              得分 {view.score} · 击毁 {view.kills} · 命中率{' '}
              {view.shots > 0 ? Math.round((view.hits / view.shots) * 100) : 0}% · 最高连击 {view.bestCombo}
            </p>
            {view.kills >= TURRET_ACE_KILLS ? (
              <p className="mg-note">已达成「近防王牌」：击毁 {view.kills} 个目标。</p>
            ) : null}
            <div className="mg-overlay-actions">
              <button type="button" className="mg-btn is-primary" onClick={startRun}>
                重新演习
              </button>
              <button type="button" className="mg-btn" onClick={handleExit}>
                返回
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {running ? (
        <p className="mg-help-strip">鼠标瞄准 · 左键/空格开火 · 方向键微调 · 双击视窗锁定指针</p>
      ) : (
        <section className="mg-help" aria-label="操作说明">
          <h3 className="mg-help-title">操作说明</h3>
          <ul className="mg-help-list">
            <li>移动鼠标即转动炮塔（光标位置就是弹着点），按住左键拖动同样可以瞄准。</li>
            <li>双击视窗进入指针锁定，长距离转向不受窗口边界限制，Esc 解除。</li>
            <li>左键或空格开火；方向键 / WASD 微调准星，触屏可用右下角方向按钮。</li>
            <li>连续命中累积连击倍率，脱靶清零；炮塔温度到 100% 会强制停火降温。</li>
            <li>弹链 120 发，打空后只能靠精准射击撑到时间结束。</li>
            <li>任何突防目标都会扣减局部舰体完整度，归零演习立即终止；舰体真实损伤还会拖慢散热回路。</li>
          </ul>
        </section>
      )}
    </section>
  );
}
