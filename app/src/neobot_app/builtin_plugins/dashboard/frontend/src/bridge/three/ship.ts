// ship.ts —— 「NeoBot 号」舰内三维场景：舱体、陈设、终端、灯光与动画
//
// 坐标契约来自 core/layout.ts（甲板 y=0、舱内净高 4.2、舱壁厚 0.4、门洞宽 4.4）。
// 本文件只负责「看起来像一艘战舰」，可行走范围、碰撞体与视觉全部由同一份布局
// 数据生成 —— 要改布局请改 layout.ts，不要在这里手摆盒子。
//
// 关键设计（先读这几条再看代码）：
//  1. 舱壁由通用函数 buildWallRect() 按「矩形 + 洞口表」切分：它同时产出视觉盒体
//     与碰撞 AABB，两者出自同一份数据，永远不会互相打架（门楣/窗台也在其中）。
//  2. 舱壁厚度一律向矩形【外侧】生长，因此 layout.ts 的地板矩形就是玩家能站的
//     净空，贴着舱壁站不会被挤进墙里。
//  3. 静态构件按材质合批（Batcher）：几十个盒子合并成一个 Mesh，全舰静态几何的
//     draw call 压在 ~15 个以内。
//  4. 不开实时阴影（完全不碰 renderer.shadowMap）：舱内光源多、投影物体杂，阴影
//     会把 draw call 翻倍。改用甲板上的接触阴影贴片（单个 InstancedMesh）+ 自发光。
//  5. 只留 5 盏 PointLight（反应堆 / 舰桥 / 机库 / 枢纽 / 货舱），其余氛围全靠
//     自发光材质与终端屏幕 —— 既省性能，也更像「舱内灯带」而不是打光棚。

import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import {
  CORRIDORS,
  DECK_HEIGHT,
  DECK_Y,
  DOORS,
  DOOR_LINTEL,
  DOOR_WIDTH,
  HUB,
  ROOMS,
  WALL_THICKNESS,
  type AABB,
  type WallSide,
} from '../core/layout';
import { ITEMS, STATIONS, type ItemId } from '../core/types';
import {
  blobShadowTexture,
  deckStencilTexture,
  disposeTextureCache,
  emissiveStripTexture,
  environmentTexture,
  floorPlateTexture,
  grateTexture,
  hazardStripeTexture,
  hexPanelTexture,
  hullTexture,
  labelTexture,
  planetTexture,
  plasmaCoreTexture,
  screenTexture,
  softDotTexture,
  starfieldTexture,
  wallPanelTexture,
} from './textures';

// ---------------------------------------------------------------------------
// 对外接口（被 game 层与 UI 层引用，签名已冻结）
// ---------------------------------------------------------------------------

export interface ShipHandle {
  root: THREE.Group; // add to scene
  colliders: AABB[]; // static world collision boxes (floor, walls, props)
  interactables: ShipInteractable[]; // pickups + minigame props + extra props the game can focus
  doors: ShipDoor[]; // animated doors
  update(dt: number, elapsed: number): void; // animate doors, plasma core, screens, dust, stars
  dispose(): void; // dispose geometries/materials/textures
}

export interface ShipInteractable {
  id: string; // 'pickup:power-cell:3', 'minigame:turret', 'prop:core'
  kind: 'pickup' | 'minigame' | 'prop';
  /** Optional item id for pickups (see ITEMS in core/types.ts) */
  item?: string;
  /** world position the player must approach */
  position: THREE.Vector3;
  /** hint shown by the HUD, e.g. '拾取能量电池' */
  hint: string;
  /** small floating mesh group to hide when collected */
  object: THREE.Object3D;
  /** minigame key for kind==='minigame': 'turret' | 'circuit' | 'cargo' */
  miniGame?: string;
  collected?: boolean;
}

export interface ShipDoor {
  /** pivot group that rotates/slides when opened */
  object: THREE.Object3D;
  /** closed -> open target, animated in update() */
  open: boolean;
  /** true while the player is within trigger distance (set by the game each frame) */
  update(dt: number): void;
}

// ---------------------------------------------------------------------------
// 常量与调色板（与 styles/theme.css 的 --brand-mid / --brand-light 同色系）
// ---------------------------------------------------------------------------

/** 舱内净高：舱壁从甲板直抵舱顶 */
const WALL_H = DECK_HEIGHT;
const FLOOR_T = 0.25;
const CEIL_T = 0.3;
/** 门洞净高（门楣以下） */
const DOOR_H = DECK_HEIGHT - DOOR_LINTEL; // 3.5

const COLOR_CYAN = 0x38e1ff;
const COLOR_CYAN_DEEP = 0x0d5f7a;
const COLOR_ORANGE = 0xff9b3d;
const COLOR_WARM = 0xffd9a8;

/** 贴图平铺密度（次/米）：甲板 1 格 = 2m，舱壁 1 格 ≈ 2.4m */
const FLOOR_UV = 0.5;
const WALL_UV = 0.42;
const GRATE_UV = 1.0;

/**
 * 中央枢纽的半径。
 *
 * layout.ts 里 HUB.size = [9, 9]，而四条走廊的尺寸是 [9, 11]：
 * 走廊-n 的 z 跨度是 [-20, -9]、走廊-e 的 x 跨度是 [9, 20] —— 11 = 20 - 9，
 * 也就是说走廊正好从舱壁（±20）接到枢纽边界（±9）上。因此 HUB.size 只能按
 * 【半径】理解（枢纽是 18×18 的中央大厅，四条走廊在 ±9 处接入）。
 *
 * 若按「全宽 9」理解，走廊与枢纽之间会留下 4.5m 既无地板也无归属的空档：
 * 玩家走不过去，isInsideHull()/zoneAt() 还会把那一带判成「舰外」。
 * layout.ts 是共享契约、不能改，所以把结论写在这里。
 */
const HUB_HALF = HUB.size[0];

// ---------------------------------------------------------------------------
// 几何工具
// ---------------------------------------------------------------------------

interface Rect {
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
}

function rectOf(center: readonly [number, number], size: readonly [number, number]): Rect {
  return {
    minX: center[0] - size[0] / 2,
    maxX: center[0] + size[0] / 2,
    minZ: center[1] - size[1] / 2,
    maxZ: center[1] + size[1] / 2,
  };
}

function rectWidth(rect: Rect): number {
  return rect.maxX - rect.minX;
}

function rectDepth(rect: Rect): number {
  return rect.maxZ - rect.minZ;
}

/**
 * 把世界尺寸烘进 UV。
 *
 * texture.repeat 属于贴图而不是网格，同一张甲板贴图要同时铺 24m 的舰桥和 1.8m
 * 的检修口，只能靠几何体自己的 UV 缩放来保证「每米几格」一致。
 */
function scaleUV(geometry: THREE.BufferGeometry, su: number, sv: number): void {
  const uv = geometry.getAttribute('uv');
  if (!uv) return;
  for (let i = 0; i < uv.count; i += 1) {
    uv.setXY(i, uv.getX(i) * su, uv.getY(i) * sv);
  }
  uv.needsUpdate = true;
}

/** 固定种子伪随机：陈设摆放每次构建都一致，便于复现问题 */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function makeAABB(tag: string, cx: number, cy: number, cz: number, sx: number, sy: number, sz: number): AABB {
  return { tag, center: [cx, cy, cz], size: [sx, sy, sz] };
}

/** 水平面片（甲板标识 / 灯板）：faceUp=true 朝上，否则朝下 */
function planeGeometry(width: number, height: number, faceUp: boolean): THREE.PlaneGeometry {
  const geometry = new THREE.PlaneGeometry(width, height);
  geometry.rotateX(faceUp ? -Math.PI / 2 : Math.PI / 2);
  return geometry;
}

/**
 * 静态几何合批器：同一材质的盒子/圆柱先收集，最后 mergeGeometries 成单 Mesh。
 * 合并后源几何立即释放，避免几十份临时 BufferGeometry 常驻显存。
 */
class Batcher {
  private readonly buckets = new Map<THREE.Material, THREE.BufferGeometry[]>();

  add(material: THREE.Material, geometry: THREE.BufferGeometry): void {
    let list = this.buckets.get(material);
    if (!list) {
      list = [];
      this.buckets.set(material, list);
    }
    list.push(geometry);
  }

  /** 把世界坐标盒体塞进合批（UV 按「每米几格」烘进去） */
  box(
    material: THREE.Material,
    cx: number,
    cy: number,
    cz: number,
    sx: number,
    sy: number,
    sz: number,
    density: number,
    rot?: readonly [number, number, number],
  ): void {
    const geometry = new THREE.BoxGeometry(sx, sy, sz);
    // 盒体的可见面是长边侧面：u 沿最长的水平边，v 沿高度
    scaleUV(geometry, Math.max(sx, sz) * density, sy * density);
    if (rot) {
      if (rot[0] !== 0) geometry.rotateX(rot[0]);
      if (rot[1] !== 0) geometry.rotateY(rot[1]);
      if (rot[2] !== 0) geometry.rotateZ(rot[2]);
    }
    geometry.translate(cx, cy, cz);
    this.add(material, geometry);
  }

  /** 合并并挂到 parent（每个材质一个 Mesh） */
  flush(parent: THREE.Object3D): void {
    for (const [material, geometries] of this.buckets) {
      if (geometries.length === 0) continue;
      let merged: THREE.BufferGeometry | null;
      if (geometries.length === 1) {
        merged = geometries[0];
      } else {
        merged = mergeGeometries(geometries, false) as THREE.BufferGeometry | null;
        for (const geometry of geometries) geometry.dispose();
      }
      if (!merged) continue;
      merged.computeBoundingSphere();
      const mesh = new THREE.Mesh(merged, material);
      mesh.name = 'batch';
      // 合批后的包围球覆盖全舰，视锥剔除没有意义
      mesh.frustumCulled = false;
      parent.add(mesh);
    }
    this.buckets.clear();
  }
}

/**
 * 局部坐标系下的构件投放器。
 *
 * 终端/道具都在「本地坐标」里描述（+z 为屏幕朝向、原点在站位中心），由 frame
 * 矩阵统一旋转到 facing 并平移到 anchor —— 这样每座终端都能用同一套直观的局部
 * 坐标写，同时仍然合批进全局静态几何。
 */
class Parts {
  constructor(
    private readonly batch: Batcher,
    private readonly frame: THREE.Matrix4,
  ) {}

  box(
    material: THREE.Material,
    x: number,
    y: number,
    z: number,
    sx: number,
    sy: number,
    sz: number,
    uv?: readonly [number, number],
    rot?: readonly [number, number, number],
  ): void {
    this.place(material, new THREE.BoxGeometry(sx, sy, sz), x, y, z, uv, rot);
  }

  cyl(
    material: THREE.Material,
    x: number,
    y: number,
    z: number,
    radiusTop: number,
    radiusBottom: number,
    height: number,
    segments = 14,
    uv?: readonly [number, number],
    rot?: readonly [number, number, number],
  ): void {
    this.place(
      material,
      new THREE.CylinderGeometry(radiusTop, radiusBottom, height, segments, 1, false),
      x,
      y,
      z,
      uv,
      rot,
    );
  }

  /** 圆环：反应堆约束环、全息台环、扶手等 */
  torus(
    material: THREE.Material,
    x: number,
    y: number,
    z: number,
    radius: number,
    tube: number,
    rot?: readonly [number, number, number],
  ): void {
    this.place(material, new THREE.TorusGeometry(radius, tube, 8, 28), x, y, z, undefined, rot);
  }

  sphere(
    material: THREE.Material,
    x: number,
    y: number,
    z: number,
    radius: number,
    uv?: readonly [number, number],
  ): void {
    this.place(material, new THREE.SphereGeometry(radius, 18, 12), x, y, z, uv);
  }

  capsule(
    material: THREE.Material,
    x: number,
    y: number,
    z: number,
    radius: number,
    length: number,
    rot?: readonly [number, number, number],
  ): void {
    this.place(material, new THREE.CapsuleGeometry(radius, length, 6, 12), x, y, z, undefined, rot);
  }

  private place(
    material: THREE.Material,
    geometry: THREE.BufferGeometry,
    x: number,
    y: number,
    z: number,
    uv?: readonly [number, number],
    rot?: readonly [number, number, number],
  ): void {
    if (uv) scaleUV(geometry, uv[0], uv[1]);
    if (rot) {
      if (rot[0] !== 0) geometry.rotateX(rot[0]);
      if (rot[1] !== 0) geometry.rotateY(rot[1]);
      if (rot[2] !== 0) geometry.rotateZ(rot[2]);
    }
    geometry.translate(x, y, z);
    geometry.applyMatrix4(this.frame);
    this.batch.add(material, geometry);
  }
}

// ---------------------------------------------------------------------------
// 墙体生成（视觉与碰撞同源）
// ---------------------------------------------------------------------------

/** 墙上的洞口：门洞（bottom=0）或舷窗（bottom>0） */
interface WallOpening {
  /** 洞口中心（沿墙方向的世界坐标） */
  at: number;
  width: number;
  /** 洞口下沿高度，默认 0 */
  bottom?: number;
  /** 洞口上沿高度，默认 height - DOOR_LINTEL（标准门洞） */
  top?: number;
}

type OpeningsBySide = Partial<Record<WallSide, WallOpening[]>>;

interface WallRectOptions {
  rect: Rect;
  height: number;
  thickness: number;
  openings?: OpeningsBySide;
  /** 整侧不建墙：与走廊/枢纽连通的一侧 */
  open?: WallSide[];
  /** 每侧沿墙方向的收进 [起点, 终点]：把墙头塞进相邻墙体，避免共面闪烁 */
  trim?: Partial<Record<WallSide, [number, number]>>;
}

/** 墙体盒体：世界中心 + 尺寸（视觉几何与碰撞 AABB 共用这一份数据） */
interface WallBox {
  cx: number;
  cy: number;
  cz: number;
  sx: number;
  sy: number;
  sz: number;
}

const WALL_SIDES: readonly WallSide[] = ['n', 's', 'e', 'w'];

/**
 * 按「矩形 + 洞口表」生成墙体盒体。
 *
 * 约定：
 *  · n = -z 侧、s = +z 侧、w = -x 侧、e = +x 侧（与 DOORS 的 side 语义一致：
 *    舰桥的门在 s 侧，也就是朝走廊那一侧的墙）；
 *  · 墙体厚度向矩形外侧生长，矩形内部始终是净空；
 *  · n/s 两侧会把墙延伸到 [minX - t, maxX + t]，正好包住四角，外墙不漏缝；
 *  · 洞口上下不足墙高的部分（门楣 / 窗台）自动补实体，碰撞盒同样来自这里。
 */
function buildWallRect(options: WallRectOptions): WallBox[] {
  const { rect, height } = options;
  const t = options.thickness;
  const boxes: WallBox[] = [];
  const open = options.open ?? [];

  for (const side of WALL_SIDES) {
    if (open.includes(side)) continue;

    let start: number;
    let end: number;
    let fixed: number; // 墙体所在平面的中心坐标
    let alongX: boolean;
    let dir: 1 | -1; // 墙体相对矩形的生长方向

    if (side === 'n' || side === 's') {
      alongX = true;
      start = rect.minX - t;
      end = rect.maxX + t;
      dir = side === 'n' ? -1 : 1;
      fixed = (side === 'n' ? rect.minZ : rect.maxZ) + (dir * t) / 2;
    } else {
      alongX = false;
      start = rect.minZ;
      end = rect.maxZ;
      dir = side === 'w' ? -1 : 1;
      fixed = (side === 'w' ? rect.minX : rect.maxX) + (dir * t) / 2;
    }

    const trim = options.trim?.[side];
    if (trim) {
      start += trim[0];
      end -= trim[1];
    }

    const emit = (from: number, to: number, y0: number, y1: number): void => {
      if (to - from <= 1e-4 || y1 - y0 <= 1e-4) return;
      const mid = (from + to) / 2;
      const len = to - from;
      if (alongX) {
        boxes.push({ cx: mid, cy: (y0 + y1) / 2, cz: fixed, sx: len, sy: y1 - y0, sz: t });
      } else {
        boxes.push({ cx: fixed, cy: (y0 + y1) / 2, cz: mid, sx: t, sy: y1 - y0, sz: len });
      }
    };

    const list = (options.openings?.[side] ?? []).slice().sort((a, b) => a.at - b.at);
    let cursor = start;
    for (const opening of list) {
      const bottom = opening.bottom ?? 0;
      const top = opening.top ?? height - DOOR_LINTEL;
      const from = Math.max(start, opening.at - opening.width / 2);
      const to = Math.min(end, opening.at + opening.width / 2);
      if (to <= cursor) continue;
      if (from > cursor) emit(cursor, from, 0, height);
      // 窗台与门楣：洞口上下的实体，碰撞也在这里产生
      if (bottom > 0) emit(from, to, 0, bottom);
      if (top < height) emit(from, to, top, height);
      cursor = to;
    }
    if (cursor < end) emit(cursor, end, 0, height);
  }

  return boxes;
}

// ---------------------------------------------------------------------------
// 滑动舰门
// ---------------------------------------------------------------------------

interface DoorLeaf {
  readonly mesh: THREE.Mesh;
  readonly closed: THREE.Vector3;
  readonly axis: THREE.Vector3;
  readonly travel: number;
}

/**
 * 双扇滑动舰门：两片门叶沿墙面反向滑出，开启后完全缩进舱壁厚度内，
 * 门洞 4.4m 全宽净空（满足「开启状态必须让开 DOOR_WIDTH」）。
 *
 * 门叶不产生碰撞体 —— 门洞能不能过由游戏逻辑决定；这样即使游戏还没接上开门
 * 逻辑，玩家也不会被一扇虚掩的门卡死。
 */
class SlidingDoor implements ShipDoor {
  readonly object: THREE.Group;

  open = false;

  /** 0 = 全关，1 = 全开（供指示灯与虹膜扇叶读取） */
  private progress = 0;

  private readonly leaves: DoorLeaf[] = [];

  /** 行程速度：约 0.75s 开合，配合 sfx.door() 的手感 */
  private static readonly SPEED = 1.35;

  constructor(name: string) {
    this.object = new THREE.Group();
    this.object.name = name;
  }

  addLeaf(mesh: THREE.Mesh, closedCenter: THREE.Vector3, axis: THREE.Vector3, travel: number): void {
    mesh.position.copy(closedCenter);
    this.object.add(mesh);
    this.leaves.push({ mesh, closed: closedCenter.clone(), axis: axis.clone().normalize(), travel });
  }

  get openness(): number {
    return this.progress;
  }

  update(dt: number): void {
    const target = this.open ? 1 : 0;
    if (this.progress === target) return;
    const step = dt * SlidingDoor.SPEED;
    this.progress =
      Math.abs(target - this.progress) <= step ? target : this.progress + Math.sign(target - this.progress) * step;
    // smoothstep：起步与到位都有一点缓冲，像液压门
    const eased = this.progress * this.progress * (3 - 2 * this.progress);
    for (const leaf of this.leaves) {
      leaf.mesh.position.copy(leaf.closed).addScaledVector(leaf.axis, eased * leaf.travel);
    }
  }
}

// ---------------------------------------------------------------------------
// buildShip
// ---------------------------------------------------------------------------

export function buildShip(scene: THREE.Scene, options?: { quality?: 'low' | 'high' }): ShipHandle {
  const quality = options?.quality ?? 'high';
  const low = quality === 'low';

  const root = new THREE.Group();
  root.name = 'NeoBotShip';
  scene.add(root);

  const batch = new Batcher();
  const colliders: AABB[] = [];
  const interactables: ShipInteractable[] = [];
  const doors: ShipDoor[] = [];
  const anims: Array<(dt: number, elapsed: number) => void> = [];

  /** 接触阴影登记表：所有「踩在地上」的道具都往这里登记，最后合成一个 InstancedMesh */
  interface ShadowSpot {
    readonly x: number;
    readonly z: number;
    readonly rx: number;
    readonly rz: number;
    readonly strength: number;
  }
  const shadowSpots: ShadowSpot[] = [];

  // ---- 贴图与材质 ---------------------------------------------------------

  const texFloor = floorPlateTexture();
  const texWall = wallPanelTexture();
  const texGrate = grateTexture();
  const texHazard = hazardStripeTexture();
  const texHex = hexPanelTexture();
  const texHull = hullTexture();
  const texStrip = emissiveStripTexture();
  const texPlasma = plasmaCoreTexture();
  const texDot = softDotTexture();
  const texShadow = blobShadowTexture();
  const texPlanet = planetTexture();

  const wallMaterial = new THREE.MeshStandardMaterial({
    map: texWall,
    color: 0xbfd0e0,
    roughness: 0.68,
    metalness: 0.55,
    envMapIntensity: 0.45,
  });
  const ceilingMaterial = new THREE.MeshStandardMaterial({
    map: texHex,
    color: 0x8c9dad,
    roughness: 0.8,
    metalness: 0.4,
    envMapIntensity: 0.3,
  });
  const floorMaterial = new THREE.MeshStandardMaterial({
    map: texFloor,
    color: 0xc3d2df,
    roughness: 0.85,
    metalness: 0.35,
    envMapIntensity: 0.35,
  });
  const grateMaterial = new THREE.MeshStandardMaterial({
    map: texGrate,
    color: 0xa9b8c6,
    roughness: 0.7,
    metalness: 0.65,
    envMapIntensity: 0.5,
  });
  const hazardMaterial = new THREE.MeshStandardMaterial({
    map: texHazard,
    color: 0xffffff,
    roughness: 0.6,
    metalness: 0.25,
    envMapIntensity: 0.4,
  });
  const hullMaterial = new THREE.MeshStandardMaterial({
    map: texHull,
    color: 0xb3c1cf,
    roughness: 0.55,
    metalness: 0.7,
    envMapIntensity: 0.6,
  });
  const hexMaterial = new THREE.MeshStandardMaterial({
    map: texHex,
    color: 0x9fb0c0,
    roughness: 0.5,
    metalness: 0.8,
    envMapIntensity: 0.7,
  });
  const steelMaterial = new THREE.MeshStandardMaterial({ color: 0x5d6a78, roughness: 0.45, metalness: 0.85 });
  const darkMaterial = new THREE.MeshStandardMaterial({ color: 0x2b333d, roughness: 0.7, metalness: 0.6 });
  const pipeMaterial = new THREE.MeshStandardMaterial({ color: 0x77828f, roughness: 0.38, metalness: 0.9 });
  const pipeWarmMaterial = new THREE.MeshStandardMaterial({ color: 0xb5652f, roughness: 0.45, metalness: 0.75 });
  const conduitMaterial = new THREE.MeshStandardMaterial({ color: 0x1d232b, roughness: 0.9, metalness: 0.15 });
  const lightMaterial = new THREE.MeshStandardMaterial({ color: 0xdfe8ef, roughness: 0.6, metalness: 0.2 });
  const glowMaterial = new THREE.MeshBasicMaterial({ color: COLOR_CYAN, toneMapped: false, side: THREE.DoubleSide });
  const glowWarmMaterial = new THREE.MeshBasicMaterial({
    color: COLOR_ORANGE,
    toneMapped: false,
    side: THREE.DoubleSide,
  });
  // 灯带：叠加混合 + 关闭深度写入，避免挡住后面的星野与粒子
  const stripMaterial = new THREE.MeshBasicMaterial({
    map: texStrip,
    color: COLOR_CYAN,
    transparent: true,
    opacity: 0.85,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
    side: THREE.DoubleSide,
  });
  const stripWarmMaterial = new THREE.MeshBasicMaterial({
    map: texStrip,
    color: COLOR_WARM,
    transparent: true,
    opacity: 0.7,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
    side: THREE.DoubleSide,
  });
  const holoMaterial = new THREE.MeshBasicMaterial({
    color: COLOR_CYAN,
    transparent: true,
    opacity: 0.3,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
    side: THREE.DoubleSide,
  });
  const glassMaterial = new THREE.MeshStandardMaterial({
    color: 0x0b2230,
    metalness: 1,
    roughness: 0.06,
    transparent: true,
    opacity: 0.28,
    envMapIntensity: 1.6,
    side: THREE.DoubleSide,
  });
  const plasmaMaterial = new THREE.MeshBasicMaterial({
    map: texPlasma,
    transparent: true,
    opacity: 0.9,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
    side: THREE.DoubleSide,
  });
  const ringMaterial = new THREE.MeshStandardMaterial({
    color: 0x54657a,
    metalness: 0.95,
    roughness: 0.28,
    emissive: new THREE.Color(COLOR_CYAN_DEEP),
    emissiveIntensity: 0.5,
  });
  const crateMaterial = new THREE.MeshStandardMaterial({
    map: texHull,
    color: 0xa8b4c0,
    roughness: 0.6,
    metalness: 0.6,
  });
  const forceFieldMaterial = new THREE.MeshBasicMaterial({
    color: COLOR_CYAN,
    transparent: true,
    opacity: 0.16,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
    side: THREE.DoubleSide,
  });
  const shadowMaterial = new THREE.MeshBasicMaterial({
    map: texShadow,
    transparent: true,
    opacity: 0.6,
    depthWrite: false,
    polygonOffset: true,
    polygonOffsetFactor: -2,
  });
  const ledMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff, toneMapped: false });
  const starMaterial = new THREE.PointsMaterial({
    map: texDot,
    size: 2.4,
    sizeAttenuation: true,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    vertexColors: true,
    toneMapped: false,
  });
  const dustMaterial = new THREE.PointsMaterial({
    map: texDot,
    color: COLOR_WARM,
    size: 0.022,
    sizeAttenuation: true,
    transparent: true,
    opacity: 0.5,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    toneMapped: false,
  });
  const haloMaterial = new THREE.MeshBasicMaterial({
    color: COLOR_CYAN,
    transparent: true,
    opacity: 0.32,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    toneMapped: false,
  });
  const planetMaterial = new THREE.MeshBasicMaterial({ map: texPlanet });
  const pickupGlowMaterial = new THREE.MeshBasicMaterial({ color: COLOR_CYAN, toneMapped: false });
  const doorLeafMaterial = new THREE.MeshStandardMaterial({
    map: texHull,
    color: 0xc6d3e0,
    roughness: 0.5,
    metalness: 0.75,
    envMapIntensity: 0.6,
  });
  const bladeMaterial = new THREE.MeshStandardMaterial({
    map: texHex,
    color: 0xb9c8d6,
    roughness: 0.4,
    metalness: 0.9,
  });

  /** 所有自建材质：dispose 时统一释放（traverse 之外的兜底） */
  const ownedMaterials: THREE.Material[] = [
    wallMaterial,
    ceilingMaterial,
    floorMaterial,
    grateMaterial,
    hazardMaterial,
    hullMaterial,
    hexMaterial,
    steelMaterial,
    darkMaterial,
    pipeMaterial,
    pipeWarmMaterial,
    conduitMaterial,
    lightMaterial,
    glowMaterial,
    glowWarmMaterial,
    stripMaterial,
    stripWarmMaterial,
    holoMaterial,
    glassMaterial,
    plasmaMaterial,
    ringMaterial,
    crateMaterial,
    forceFieldMaterial,
    shadowMaterial,
    ledMaterial,
    starMaterial,
    dustMaterial,
    haloMaterial,
    planetMaterial,
    pickupGlowMaterial,
    doorLeafMaterial,
    bladeMaterial,
  ];

  // ---- 舱室 / 走廊矩形 ----------------------------------------------------

  const roomRects = new Map<string, Rect>();
  for (const room of ROOMS) roomRects.set(room.id, rectOf(room.center, room.size));

  const corridorRects = new Map<string, Rect>();
  for (const corridor of CORRIDORS) {
    const rect = rectOf(corridor.center, corridor.size);
    // 走廊-s 的矩形（z 到 20）与机库（z 从 17 起）重叠 3m：甲板只能铺一次，
    // 否则共面闪烁；裁到舱壁处，重叠段交给机库甲板。
    if (corridor.id === 'corridor-s') rect.maxZ = roomRects.get('hangar')?.minZ ?? rect.maxZ;
    corridorRects.set(corridor.id, rect);
  }

  const hubRect: Rect = { minX: -HUB_HALF, maxX: HUB_HALF, minZ: -HUB_HALF, maxZ: HUB_HALF };

  /** 所有可行走矩形（甲板 / 舱顶 / 灯位 / 尘埃活动范围都用它） */
  const floorRects: Rect[] = [...roomRects.values(), hubRect, ...corridorRects.values()];

  // 陈设的固定站位：提前声明成常量，货箱随机撒点时要拿它做排除，
  // 免得「箱子长在控制台里」。同一份坐标只写一次。
  const RACK_POSITIONS: ReadonlyArray<readonly [number, number]> = [
    [24, -9.35],
    [27.4, -9.35],
  ];
  const CHAIR_POSITIONS: ReadonlyArray<readonly [number, number]> = [
    [0, -26.4],
    [-9.6, -27.2],
    [9.6, -27.2],
  ];
  const DRONE_POSITIONS: ReadonlyArray<{ x: number; z: number; ry: number }> = [
    { x: -8.4, z: 24.0, ry: -0.35 },
    { x: 7.6, z: 27.6, ry: 2.5 },
  ];
  const TURRET_POS = { x: -5.4, z: 21.0 };
  const BREAKER_POS = { x: 33, z: -9.35 };
  /** 危险品货箱：贴舱壁的橙色标识箱（手工摆放，不参与随机撒箱） */
  const HAZARD_CRATE_SPOTS: ReadonlyArray<readonly [number, number]> = [
    [-35.5, 8.2],
    [-22.6, -8.4],
    [12.6, 30.4],
  ];

  /**
   * 12 件物资的落点（3 能量电池 / 3 冷却剂 / 2 合金板 / 2 数据核心 / 2 医疗包）。
   * 全部位于对应舱室/走廊的可行走矩形内、离舱壁 ≥0.8m，并避开控制台、反应堆与
   * 工具架 —— 玩家从任意方向走过去都能直接拾取。
   */
  const pickupSpots: Array<{ item: ItemId; x: number; z: number }> = [
    { item: 'power-cell', x: 34.2, z: 5.4 }, // 工程舱（反应堆外侧）
    { item: 'coolant', x: 22.6, z: -6.4 }, // 工程舱（工具架前）
    { item: 'power-cell', x: -34.2, z: 6.4 }, // 货舱（左舷角）
    { item: 'alloy', x: -23.4, z: -7.4 }, // 货舱（舱门内侧）
    { item: 'data-core', x: -35.6, z: -8.2 }, // 货舱（主机机柜旁）
    { item: 'coolant', x: -11.6, z: 28.6 }, // 机库（舰载机后方）
    { item: 'alloy', x: 11.4, z: 20.6 }, // 机库（猫道下方）
    { item: 'data-core', x: 8.6, z: -27.4 }, // 舰桥（星图台前）
    { item: 'medkit', x: -8.4, z: -21.6 }, // 舰桥（通讯席前）
    { item: 'power-cell', x: 3.6, z: 3.6 }, // 中央枢纽
    { item: 'coolant', x: 14.6, z: -2.8 }, // 右舷走廊
    { item: 'medkit', x: -2.8, z: 13.6 }, // 后部走廊
  ];

  // ---- 甲板 ---------------------------------------------------------------

  for (const rect of floorRects) {
    const w = rectWidth(rect);
    const d = rectDepth(rect);
    const cx = (rect.minX + rect.maxX) / 2;
    const cz = (rect.minZ + rect.maxZ) / 2;
    const geometry = new THREE.BoxGeometry(w, FLOOR_T, d);
    scaleUV(geometry, w * FLOOR_UV, d * FLOOR_UV);
    geometry.translate(cx, DECK_Y - FLOOR_T / 2, cz);
    batch.add(floorMaterial, geometry);
    colliders.push(makeAABB('floor', cx, DECK_Y - FLOOR_T / 2, cz, w, FLOOR_T, d));
  }

  // ---- 舱顶（每块甲板正上方都要有，否则玩家会看到虚空） -------------------

  for (const rect of floorRects) {
    const w = rectWidth(rect);
    const d = rectDepth(rect);
    const geometry = new THREE.BoxGeometry(w, CEIL_T, d);
    scaleUV(geometry, w * 0.25, d * 0.25);
    geometry.translate((rect.minX + rect.maxX) / 2, DECK_HEIGHT + CEIL_T / 2, (rect.minZ + rect.maxZ) / 2);
    batch.add(ceilingMaterial, geometry);
  }

  // ---- 墙体 ---------------------------------------------------------------

  /** 门洞表：直接来自 layout.ts 的 DOORS */
  const doorOpeningsFor = (roomId: string): OpeningsBySide => {
    const result: OpeningsBySide = {};
    for (const door of DOORS[roomId] ?? []) {
      const list = result[door.side] ?? [];
      list.push({ at: door.at, width: DOOR_WIDTH, bottom: 0, top: DOOR_H });
      result[door.side] = list;
    }
    return result;
  };

  /** 舷窗：舰桥舰艏大窗 + 侧窗；机库舰艉舷窗（中央留给气闸）与侧窗 */
  const windowOpenings: Record<string, OpeningsBySide> = {
    bridge: {
      n: [{ at: 0, width: 11.2, bottom: 1.15, top: 3.35 }],
      e: [{ at: -25, width: 3.6, bottom: 1.3, top: 3.1 }],
      w: [{ at: -25, width: 3.6, bottom: 1.3, top: 3.1 }],
    },
    hangar: {
      e: [{ at: 25, width: 5, bottom: 1.3, top: 3.1 }],
      w: [{ at: 25, width: 5, bottom: 1.3, top: 3.1 }],
      s: [
        { at: 0, width: 3.6, bottom: 0, top: 3.4 }, // 气闸舱口（不装玻璃）
        { at: -8, width: 3.2, bottom: 1.3, top: 3.0 },
        { at: 8, width: 3.2, bottom: 1.3, top: 3.0 },
      ],
    },
  };

  const roomOpenings = new Map<string, OpeningsBySide>();
  const wallBoxes: WallBox[] = [];

  for (const room of ROOMS) {
    const rect = roomRects.get(room.id);
    if (!rect) continue;
    const openings: OpeningsBySide = { ...doorOpeningsFor(room.id) };
    const windows = windowOpenings[room.id] ?? {};
    for (const side of WALL_SIDES) {
      const extra = windows[side];
      if (extra) openings[side] = [...(openings[side] ?? []), ...extra];
    }
    roomOpenings.set(room.id, openings);
    wallBoxes.push(...buildWallRect({ rect, height: WALL_H, thickness: WALL_THICKNESS, openings }));
  }

  // 走廊：只建两条长边；两端要么是舱室墙、要么是枢纽，所以整侧留空。
  // trim 0.4 让墙头正好顶在相邻墙体上（面贴合、法线相反，不会共面闪烁）。
  for (const corridor of CORRIDORS) {
    const rect = corridorRects.get(corridor.id);
    if (!rect) continue;
    const alongZ = corridor.size[1] > corridor.size[0];
    wallBoxes.push(
      ...buildWallRect({
        rect,
        height: WALL_H,
        thickness: WALL_THICKNESS,
        open: alongZ ? ['n', 's'] : ['e', 'w'],
        trim: alongZ ? { e: [0.4, 0.4], w: [0.4, 0.4] } : { n: [0.4, 0.4], s: [0.4, 0.4] },
      }),
    );
  }

  // 枢纽：四面各开一个 9m 宽的全高洞口（走廊接口），剩下的四段即中央大厅的墙
  const hubOpenings: OpeningsBySide = {
    n: [{ at: 0, width: 9, bottom: 0, top: WALL_H }],
    s: [{ at: 0, width: 9, bottom: 0, top: WALL_H }],
    w: [{ at: 0, width: 9, bottom: 0, top: WALL_H }],
    e: [{ at: 0, width: 9, bottom: 0, top: WALL_H }],
  };
  wallBoxes.push(
    ...buildWallRect({
      rect: hubRect,
      height: WALL_H,
      thickness: WALL_THICKNESS,
      openings: hubOpenings,
    }),
  );

  for (const box of wallBoxes) {
    batch.box(wallMaterial, box.cx, box.cy, box.cz, box.sx, box.sy, box.sz, WALL_UV);
    colliders.push(makeAABB('wall', box.cx, box.cy, box.cz, box.sx, box.sy, box.sz));
  }

  // ---- 舷窗玻璃 + 窗棂 ----------------------------------------------------

  /** 洞口在世界坐标里的玻璃面片 */
  const glassGeometryFor = (rect: Rect, side: WallSide, opening: WallOpening): THREE.BufferGeometry => {
    const width = opening.width;
    const bottom = opening.bottom ?? 0;
    const top = opening.top ?? WALL_H;
    const geometry = new THREE.PlaneGeometry(width, top - bottom);
    const y = (bottom + top) / 2;
    if (side === 'n') {
      geometry.translate(opening.at, y, rect.minZ - WALL_THICKNESS / 2);
    } else if (side === 's') {
      geometry.translate(opening.at, y, rect.maxZ + WALL_THICKNESS / 2);
    } else if (side === 'w') {
      geometry.rotateY(Math.PI / 2);
      geometry.translate(rect.minX - WALL_THICKNESS / 2, y, opening.at);
    } else {
      geometry.rotateY(-Math.PI / 2);
      geometry.translate(rect.maxX + WALL_THICKNESS / 2, y, opening.at);
    }
    return geometry;
  };

  for (const room of ROOMS) {
    const rect = roomRects.get(room.id);
    const windows = windowOpenings[room.id];
    if (!rect || !windows) continue;
    for (const side of WALL_SIDES) {
      const list = windows[side];
      if (!list) continue;
      for (const opening of list) {
        // 机库艉部中央是气闸舱口：不装玻璃，它后面是力场与星野
        if (room.id === 'hangar' && side === 's' && opening.at === 0 && (opening.bottom ?? 0) === 0) continue;
        batch.add(glassMaterial, glassGeometryFor(rect, side, opening));
      }
    }
  }

  // 舰桥艏窗窗棂：4 根立柱把 11.2m 大窗分成 5 格，正中留空不挡视线
  for (const offset of [-4.48, -2.24, 2.24, 4.48]) {
    batch.box(steelMaterial, offset, 2.25, -30.2, 0.16, 2.2, 0.34, 0.6);
  }

  // ---- 结构细节：肋条 / 管线 / 线槽 / 危险边条 / 格栅 ---------------------

  const ribStep = low ? 5.6 : 3.2;
  const ribGeometry = new THREE.BoxGeometry(0.34, WALL_H - 0.2, 0.16);
  scaleUV(ribGeometry, 1.4, 1.6);
  const ribTransforms: THREE.Matrix4[] = [];
  const ribScratch = new THREE.Object3D();

  /** 沿某侧舱壁均匀布肋；洞口前后 0.5m 内跳过，避免横在舷窗/门洞中间 */
  const addRibs = (rect: Rect, side: WallSide, openings?: WallOpening[]): void => {
    const alongX = side === 'n' || side === 's';
    const length = alongX ? rectWidth(rect) : rectDepth(rect);
    const count = Math.max(1, Math.floor(length / ribStep));
    for (let i = 0; i <= count; i += 1) {
      const at = (alongX ? rect.minX : rect.minZ) + (i / count) * length;
      if (openings?.some((opening) => Math.abs(at - opening.at) < opening.width / 2 + 0.5)) continue;
      let x: number;
      let z: number;
      let ry = 0;
      if (side === 'n') {
        x = at;
        z = rect.minZ + 0.08;
      } else if (side === 's') {
        x = at;
        z = rect.maxZ - 0.08;
      } else if (side === 'w') {
        x = rect.minX + 0.08;
        z = at;
        ry = Math.PI / 2;
      } else {
        x = rect.maxX - 0.08;
        z = at;
        ry = Math.PI / 2;
      }
      ribScratch.position.set(x, WALL_H / 2, z);
      ribScratch.rotation.set(0, ry, 0);
      ribScratch.updateMatrix();
      ribTransforms.push(ribScratch.matrix.clone());
    }
  };

  for (const room of ROOMS) {
    const rect = roomRects.get(room.id);
    if (!rect) continue;
    const openings = roomOpenings.get(room.id) ?? {};
    for (const side of WALL_SIDES) addRibs(rect, side, openings[side]);
  }
  for (const side of WALL_SIDES) addRibs(hubRect, side, hubOpenings[side]);

  const ribMesh = new THREE.InstancedMesh(ribGeometry, steelMaterial, Math.max(1, ribTransforms.length));
  ribTransforms.forEach((matrix, index) => ribMesh.setMatrixAt(index, matrix));
  ribMesh.count = ribTransforms.length;
  ribMesh.instanceMatrix.needsUpdate = true;
  ribMesh.frustumCulled = false;
  ribMesh.name = 'ribs';
  root.add(ribMesh);

  // 管线：沿走廊贴顶布置，附带吊架
  interface PipeRun {
    readonly from: THREE.Vector3;
    readonly to: THREE.Vector3;
    readonly radius: number;
    readonly warm: boolean;
  }
  const pipeRuns: PipeRun[] = [
    { from: new THREE.Vector3(-1.6, 3.86, -19.6), to: new THREE.Vector3(-1.6, 3.86, 9.4), radius: 0.09, warm: false },
    { from: new THREE.Vector3(-1.2, 3.62, -19.6), to: new THREE.Vector3(-1.2, 3.62, 9.4), radius: 0.06, warm: true },
    { from: new THREE.Vector3(1.5, 3.86, -19.6), to: new THREE.Vector3(1.5, 3.86, 16.6), radius: 0.11, warm: false },
    { from: new THREE.Vector3(9.4, 3.86, 1.6), to: new THREE.Vector3(19.6, 3.86, 1.6), radius: 0.09, warm: false },
    { from: new THREE.Vector3(-19.6, 3.86, -1.5), to: new THREE.Vector3(-9.4, 3.86, -1.5), radius: 0.1, warm: false },
    { from: new THREE.Vector3(-19.6, 3.6, 1.2), to: new THREE.Vector3(-9.4, 3.6, 1.2), radius: 0.06, warm: true },
    { from: new THREE.Vector3(31, 4.15, 4.8), to: new THREE.Vector3(31, 2.6, 4.8), radius: 0.18, warm: false },
    { from: new THREE.Vector3(33.5, 4.15, 6.5), to: new THREE.Vector3(33.5, 1.2, 6.5), radius: 0.12, warm: true },
  ];
  if (!low) {
    pipeRuns.push({
      from: new THREE.Vector3(24, 4.15, -6),
      to: new THREE.Vector3(24, 2.4, -6),
      radius: 0.14,
      warm: false,
    });
  }
  for (const run of pipeRuns) {
    const length = run.from.distanceTo(run.to);
    const mid = run.from.clone().add(run.to).multiplyScalar(0.5);
    const geometry = new THREE.CylinderGeometry(run.radius, run.radius, length, 10, 1);
    // 圆柱默认沿 +y：沿 x 走用 rotateZ，沿 z 走用 rotateX
    if (Math.abs(run.to.x - run.from.x) > Math.abs(run.to.z - run.from.z)) geometry.rotateZ(Math.PI / 2);
    else geometry.rotateX(Math.PI / 2);
    geometry.translate(mid.x, mid.y, mid.z);
    batch.add(run.warm ? pipeWarmMaterial : pipeMaterial, geometry);

    const steps = Math.max(1, Math.floor(length / 3.4));
    for (let i = 0; i <= steps; i += 1) {
      const p = run.from.clone().lerp(run.to, i / steps);
      batch.box(darkMaterial, p.x, Math.min(4.14, p.y + 0.2), p.z, 0.34, 0.18, 0.34, 0.8);
    }
  }

  // 墙面线槽（检修走线）与踢脚危险边条：沿每个可行走矩形贴一圈
  for (const rect of floorRects) {
    const w = rectWidth(rect);
    const d = rectDepth(rect);
    const cx = (rect.minX + rect.maxX) / 2;
    const cz = (rect.minZ + rect.maxZ) / 2;
    batch.box(conduitMaterial, cx, 2.62, rect.minZ + 0.12, w - 0.3, 0.14, 0.14, 1.2);
    batch.box(conduitMaterial, cx, 2.62, rect.maxZ - 0.12, w - 0.3, 0.14, 0.14, 1.2);
    batch.box(conduitMaterial, rect.minX + 0.12, 2.62, cz, 0.14, 0.14, d - 0.3, 1.2);
    batch.box(conduitMaterial, rect.maxX - 0.12, 2.62, cz, 0.14, 0.14, d - 0.3, 1.2);

    batch.box(hazardMaterial, cx, 0.09, rect.minZ + 0.09, w - 0.2, 0.18, 0.06, 1.4);
    batch.box(hazardMaterial, cx, 0.09, rect.maxZ - 0.09, w - 0.2, 0.18, 0.06, 1.4);
    batch.box(hazardMaterial, rect.minX + 0.09, 0.09, cz, 0.06, 0.18, d - 0.2, 1.4);
    batch.box(hazardMaterial, rect.maxX - 0.09, 0.09, cz, 0.06, 0.18, d - 0.2, 1.4);
  }

  // 格栅带：走廊中央通风格栅 + 机库中轴车道 + 枢纽十字
  const grateStrips: Array<readonly [number, number, number, number]> = [
    [-1.8, -19.6, 1.8, -9.2],
    [-1.8, 9.2, 1.8, 16.8],
    [9.2, -1.8, 19.6, 1.8],
    [-19.6, -1.8, -9.2, 1.8],
    [-2.6, 18.2, 2.6, 32.6],
    [-3.2, -8.6, 3.2, 8.6],
  ];
  for (const [x0, z0, x1, z1] of grateStrips) {
    const geometry = new THREE.BoxGeometry(x1 - x0, 0.022, z1 - z0);
    scaleUV(geometry, (x1 - x0) * GRATE_UV, (z1 - z0) * GRATE_UV);
    geometry.translate((x0 + x1) / 2, DECK_Y + 0.011, (z0 + z1) / 2);
    batch.add(grateMaterial, geometry);
  }

  // ---- 舱顶灯具 + 踢脚灯带 ------------------------------------------------

  const housingStep = low ? 7 : 5;
  for (const rect of floorRects) {
    const w = rectWidth(rect);
    const d = rectDepth(rect);
    const nx = Math.max(1, Math.round(w / housingStep));
    const nz = Math.max(1, Math.round(d / housingStep));
    for (let ix = 0; ix < nx; ix += 1) {
      for (let iz = 0; iz < nz; iz += 1) {
        const x = rect.minX + (w * (ix + 0.5)) / nx;
        const z = rect.minZ + (d * (iz + 0.5)) / nz;
        batch.box(darkMaterial, x, DECK_HEIGHT - 0.08, z, Math.min(1.7, w * 0.5), 0.16, 0.44, 0.6);
        const panel = planeGeometry(Math.min(1.5, w * 0.45), 0.3, false);
        scaleUV(panel, 3, 1);
        panel.translate(x, DECK_HEIGHT - 0.17, z);
        batch.add(stripMaterial, panel);
      }
    }
  }

  /** 舱壁低位的冷光灯带：竖向贴墙，离甲板 0.34m */
  const skirting = (rect: Rect, material: THREE.Material): void => {
    const w = rectWidth(rect);
    const d = rectDepth(rect);
    const cx = (rect.minX + rect.maxX) / 2;
    const cz = (rect.minZ + rect.maxZ) / 2;
    const north = new THREE.PlaneGeometry(w - 0.7, 0.11);
    scaleUV(north, 4, 1);
    north.translate(cx, 0.34, rect.minZ + 0.06);
    batch.add(material, north);

    const south = new THREE.PlaneGeometry(w - 0.7, 0.11);
    scaleUV(south, 4, 1);
    south.rotateY(Math.PI);
    south.translate(cx, 0.34, rect.maxZ - 0.06);
    batch.add(material, south);

    const west = new THREE.PlaneGeometry(d - 0.7, 0.11);
    scaleUV(west, 4, 1);
    west.rotateY(Math.PI / 2);
    west.translate(rect.minX + 0.06, 0.34, cz);
    batch.add(material, west);

    const east = new THREE.PlaneGeometry(d - 0.7, 0.11);
    scaleUV(east, 4, 1);
    east.rotateY(-Math.PI / 2);
    east.translate(rect.maxX - 0.06, 0.34, cz);
    batch.add(material, east);
  };
  for (const rect of floorRects) skirting(rect, stripMaterial);

  // 机库两侧的高位暖色灯带：给这个最大的舱室一点层次
  {
    const hangarRect = roomRects.get('hangar');
    if (hangarRect) {
      for (const side of [-1, 1]) {
        const strip = new THREE.PlaneGeometry(rectDepth(hangarRect) - 2, 0.14);
        scaleUV(strip, 6, 1);
        strip.rotateY(side > 0 ? -Math.PI / 2 : Math.PI / 2);
        strip.translate(side > 0 ? hangarRect.maxX - 0.08 : hangarRect.minX + 0.08, 3.62, 25);
        batch.add(stripWarmMaterial, strip);
      }
    }
  }

  // ---- 甲板标识 -----------------------------------------------------------

  const stencils: Array<{ text: string; sub: string; x: number; z: number; size: number }> = [
    { text: '舰桥', sub: 'BRIDGE', x: -7.5, z: -26.5, size: 5 },
    { text: '机库', sub: 'HANGAR 01', x: -8.5, z: 29.5, size: 7 },
    { text: '货舱', sub: 'CARGO BAY', x: -29, z: -6.5, size: 6 },
    { text: '工程舱', sub: 'REACTOR', x: 24.5, z: 7.5, size: 5.5 },
    { text: '枢纽', sub: 'CENTRAL HUB', x: 0, z: 0, size: 5 },
  ];
  for (const stencil of stencils) {
    const material = new THREE.MeshBasicMaterial({
      map: deckStencilTexture(stencil.text, stencil.sub),
      transparent: true,
      opacity: 0.5,
      depthWrite: false,
      toneMapped: false,
      polygonOffset: true,
      polygonOffsetFactor: -1,
    });
    ownedMaterials.push(material);
    const geometry = planeGeometry(stencil.size, stencil.size, true);
    geometry.translate(stencil.x, DECK_Y + 0.016, stencil.z);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = `stencil:${stencil.sub}`;
    root.add(mesh);
  }

  // ---- 舱室铭牌（门边） ---------------------------------------------------

  /** 铭牌 = 自发光亚克力底板 + 白字透明贴图；`ry` 是牌面朝向 */
  const addLabel = (text: string, sub: string, x: number, y: number, z: number, ry: number): void => {
    const material = new THREE.MeshBasicMaterial({
      map: labelTexture(text, sub),
      transparent: true,
      depthWrite: false,
      toneMapped: false,
      color: 0xdff3ff,
    });
    ownedMaterials.push(material);
    const geometry = new THREE.PlaneGeometry(1.5, 0.375);
    geometry.rotateY(ry);
    geometry.translate(x, y, z);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = `label:${sub}`;
    root.add(mesh);

    // 底板往舱壁方向偏 5cm，保证从舱内先看到字、再看到底板
    const plate = new THREE.BoxGeometry(1.64, 0.46, 0.07);
    if (ry !== 0) plate.rotateY(ry);
    plate.translate(x - Math.sin(ry) * 0.05, y, z - Math.cos(ry) * 0.05);
    batch.add(darkMaterial, plate);
  };

  for (const room of ROOMS) {
    const rect = roomRects.get(room.id);
    const door = DOORS[room.id]?.[0];
    if (!rect || !door) continue;
    const offset = DOOR_WIDTH / 2 + 1.6;
    if (door.side === 'n') addLabel(room.label, room.code, door.at - offset, 2.75, rect.minZ + 0.09, 0);
    else if (door.side === 's') addLabel(room.label, room.code, door.at + offset, 2.75, rect.maxZ - 0.09, Math.PI);
    else if (door.side === 'w') addLabel(room.label, room.code, rect.minX + 0.09, 2.75, door.at - offset, Math.PI / 2);
    else addLabel(room.label, room.code, rect.maxX - 0.09, 2.75, door.at + offset, -Math.PI / 2);
  }
  // 枢纽铭牌挂在北墙的实墙上（正中是 9m 宽的走廊洞口，不能挂在那儿）
  addLabel('中央枢纽', 'CENTRAL HUB', 6.6, 2.9, hubRect.minZ + 0.1, 0);

  // ---- 扶手与猫道（装饰：都不在玩家会撞到的高度/位置上） ------------------

  const railing = (x0: number, z0: number, x1: number, z1: number, y: number): void => {
    const length = Math.hypot(x1 - x0, z1 - z0);
    const posts = Math.max(1, Math.round(length / 1.8));
    for (let i = 0; i <= posts; i += 1) {
      const t = i / posts;
      batch.box(steelMaterial, x0 + (x1 - x0) * t, y + 0.5, z0 + (z1 - z0) * t, 0.1, 1.0, 0.1, 1);
    }
    const alongX = Math.abs(x1 - x0) > Math.abs(z1 - z0);
    batch.box(
      steelMaterial,
      (x0 + x1) / 2,
      y + 1.0,
      (z0 + z1) / 2,
      alongX ? length : 0.09,
      0.09,
      alongX ? 0.09 : length,
      1,
    );
    batch.box(
      steelMaterial,
      (x0 + x1) / 2,
      y + 0.55,
      (z0 + z1) / 2,
      alongX ? length : 0.06,
      0.06,
      alongX ? 0.06 : length,
      1,
    );
  };

  // 舰桥艏部扶栏（窗前）：从指挥台两侧绕过，避免和指挥台穿模
  railing(-5.6, -29.2, -2.4, -29.2, 0.0);
  railing(2.4, -29.2, 5.6, -29.2, 0.0);

  // 机库两侧猫道 + 栏杆：y=3.0 高于玩家头部，因此不参与碰撞
  const catwalkY = 3.0;
  for (const side of [-1, 1]) {
    const catX = side * 13.0;
    const deck = new THREE.BoxGeometry(1.8, 0.12, 13);
    scaleUV(deck, 1.8 * GRATE_UV, 13 * GRATE_UV);
    deck.translate(catX, catwalkY, 25.5);
    batch.add(grateMaterial, deck);
    railing(catX - 0.85 * side, 19.4, catX - 0.85 * side, 31.6, catwalkY + 0.06);
  }
  // 工程舱沿外侧舱壁的检修猫道
  {
    const deck = new THREE.BoxGeometry(1.8, 0.12, 16);
    scaleUV(deck, 1.8 * GRATE_UV, 16 * GRATE_UV);
    deck.translate(36.9, catwalkY, -0.5);
    batch.add(grateMaterial, deck);
    railing(36.0, -8.4, 36.0, 7.4, catwalkY + 0.06);
  }

  // ---- 屏幕 / 指示灯注册表 ------------------------------------------------

  interface ScreenRecord {
    readonly material: THREE.MeshBasicMaterial;
    readonly phase: number;
  }
  const screens: ScreenRecord[] = [];

  interface LedRecord {
    readonly position: THREE.Vector3;
    readonly color: THREE.Color;
    readonly phase: number;
    readonly mode: 'blink' | 'pulse' | 'steady' | 'door';
    readonly door?: SlidingDoor;
  }
  const leds: LedRecord[] = [];

  const addLed = (
    x: number,
    y: number,
    z: number,
    color: number,
    mode: LedRecord['mode'],
    phase = 0,
    door?: SlidingDoor,
  ): void => {
    leds.push({ position: new THREE.Vector3(x, y, z), color: new THREE.Color(color), phase, mode, door });
  };

  /** 终端屏幕：贴图各不相同，因此每块屏幕一个材质（每块 1 个 draw call） */
  const addScreen = (
    title: string,
    lines: readonly string[],
    width: number,
    height: number,
    local: THREE.Vector3,
    frame: THREE.Matrix4,
    tilt: number,
    phase: number,
  ): void => {
    const geometry = new THREE.PlaneGeometry(width, height);
    geometry.rotateX(tilt);
    geometry.translate(local.x, local.y, local.z);
    geometry.applyMatrix4(frame);
    const material = new THREE.MeshBasicMaterial({
      map: screenTexture(title, lines),
      toneMapped: false,
      transparent: true,
      opacity: 0.98,
    });
    ownedMaterials.push(material);
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = `screen:${title}`;
    root.add(mesh);
    screens.push({ material, phase });

    // 屏幕四周的暗色边框（合批）
    const bezel = new THREE.BoxGeometry(width + 0.08, height + 0.08, 0.05);
    bezel.rotateX(tilt);
    bezel.translate(local.x, local.y, local.z - 0.035);
    bezel.applyMatrix4(frame);
    batch.add(darkMaterial, bezel);
  };

  // ---- 8 座控制终端 -------------------------------------------------------

  interface ConsoleSpec {
    /** 屏幕：本地坐标（+z 为屏幕朝向）与尺寸 */
    readonly screen: { x: number; y: number; z: number; w: number; h: number; tilt: number };
    /** 屏幕文字行（抬头由 STATIONS.terminal 提供） */
    readonly lines: readonly string[];
    /** 碰撞 footprint（宽 x, 深 z, 高） */
    readonly footprint: { w: number; d: number; h: number };
    readonly build: (parts: Parts) => void;
  }

  const consoleSpecs: Record<string, ConsoleSpec> = {
    // 指挥台：宽体舰长席 + 两侧翼台 + 背屏
    overview: {
      screen: { x: 0, y: 1.32, z: 0.14, w: 1.6, h: 0.62, tilt: -0.42 },
      lines: ['舰况总览 / ALL SYSTEMS', '子系统 指挥与控制系统', '链路 舰载总线在线', '待命 等待指挥员指令'],
      footprint: { w: 3.0, d: 1.05, h: 1.15 },
      build: (parts) => {
        parts.box(steelMaterial, 0, 0.55, 0, 2.6, 1.1, 0.9, [2, 1]);
        parts.box(darkMaterial, 0, 1.14, 0.06, 2.5, 0.14, 0.8, [2, 1]);
        parts.box(steelMaterial, -1.55, 0.8, 0, 0.5, 1.6, 0.85, [1, 1]);
        parts.box(steelMaterial, 1.55, 0.8, 0, 0.5, 1.6, 0.85, [1, 1]);
        parts.box(darkMaterial, 0, 1.6, -0.42, 2.2, 1.6, 0.16, [2, 1]);
        for (let i = 0; i < 3; i += 1) {
          parts.box(glowMaterial, -0.7 + i * 0.7, 1.95, -0.33, 0.5, 0.06, 0.03);
        }
        parts.cyl(steelMaterial, 0, 0.12, 0.2, 0.36, 0.42, 0.24, 16);
      },
    },
    // 通讯阵列：窄高机柜 + 顶部抛物面天线
    comms: {
      screen: { x: 0, y: 1.38, z: 0.3, w: 0.92, h: 0.5, tilt: -0.36 },
      lines: ['航行日志 / COMMS LOG', '子系统 通讯与日志阵列', '链路 量子中继已同步', '待命 等待日志检索'],
      footprint: { w: 1.7, d: 0.95, h: 2.6 },
      build: (parts) => {
        parts.box(hullMaterial, 0, 1.15, -0.2, 1.3, 2.3, 0.7, [1, 2]);
        parts.box(darkMaterial, 0, 0.5, 0.18, 1.1, 0.3, 0.5, [1, 1]);
        parts.cyl(steelMaterial, -0.85, 2.5, -0.2, 0.06, 0.08, 0.9, 10);
        parts.cyl(steelMaterial, -0.85, 3.05, -0.2, 0.62, 0.06, 0.3, 18, undefined, [Math.PI / 2.6, 0, 0]);
        parts.cyl(steelMaterial, 0.6, 2.62, -0.2, 0.035, 0.035, 1.1, 8);
        for (let i = 0; i < 4; i += 1) {
          parts.box(glowMaterial, 0.35, 0.9 + i * 0.28, 0.17, 0.34, 0.05, 0.04);
        }
      },
    },
    // 星图导航台：环形全息投影台（上方球体单独动画）
    nav: {
      screen: { x: 0, y: 1.22, z: 0.74, w: 0.8, h: 0.44, tilt: -0.5 },
      lines: ['星图与航迹 / NAV PLOT', '子系统 星图与航迹推算', '链路 陀螺阵列已校准', '待命 等待航线输入'],
      footprint: { w: 2.1, d: 2.1, h: 1.1 },
      build: (parts) => {
        parts.cyl(steelMaterial, 0, 0.45, 0, 0.5, 0.62, 0.9, 20);
        parts.cyl(hexMaterial, 0, 0.96, 0, 1.0, 1.0, 0.14, 24, [2, 2]);
        parts.torus(ringMaterial, 0, 1.05, 0, 1.0, 0.045);
        for (let i = 0; i < 4; i += 1) {
          const angle = (i / 4) * Math.PI * 2 + Math.PI / 4;
          parts.box(steelMaterial, Math.cos(angle) * 0.86, 0.55, Math.sin(angle) * 0.86, 0.12, 1.0, 0.12);
        }
        parts.box(darkMaterial, 0, 1.28, 0.76, 0.9, 0.5, 0.1, [1, 1], [-0.5, 0, 0]);
      },
    },
    // 反应堆控制台：高塔式状态柱 + 竖向能量条
    power: {
      screen: { x: 0, y: 1.55, z: 0.24, w: 1.0, h: 0.55, tilt: -0.34 },
      lines: ['能源分配 / POWER GRID', '子系统 反物质反应堆', '链路 主母线输出稳定', '待命 等待功率指令'],
      footprint: { w: 1.35, d: 1.05, h: 2.45 },
      build: (parts) => {
        parts.box(steelMaterial, 0, 0.28, 0, 1.3, 0.56, 0.9, [1, 1]);
        parts.box(hexMaterial, 0, 1.45, -0.16, 1.15, 2.1, 0.55, [1, 2]);
        parts.box(darkMaterial, 0, 0.56, 0.2, 1.2, 0.1, 0.55, [1, 1], [-0.34, 0, 0]);
        for (let i = 0; i < 9; i += 1) {
          parts.box(glowMaterial, 0.44, 0.75 + i * 0.16, 0.13, 0.16, 0.1, 0.05);
        }
        parts.box(glowWarmMaterial, -0.44, 1.1, 0.13, 0.1, 0.5, 0.05);
        parts.cyl(steelMaterial, 0, 2.6, -0.16, 0.28, 0.34, 0.2, 16);
      },
    },
    // 主机机柜：服务器排架
    mainframe: {
      screen: { x: 0, y: 1.62, z: 0.46, w: 0.86, h: 0.42, tilt: -0.12 },
      lines: ['模块管理 / MAINFRAME', '子系统 舰载主机机群', '链路 机群心跳正常', '待命 等待模块调度'],
      footprint: { w: 1.35, d: 0.95, h: 2.45 },
      build: (parts) => {
        parts.box(hullMaterial, 0, 1.2, 0, 1.2, 2.4, 0.8, [1, 2]);
        for (let i = 0; i < 6; i += 1) {
          parts.box(darkMaterial, 0, 0.42 + i * 0.34, 0.42, 1.04, 0.26, 0.06, [1, 1]);
          for (let j = 0; j < 4; j += 1) {
            parts.box(glowMaterial, -0.34 + j * 0.22, 0.36 + i * 0.34, 0.46, 0.05, 0.05, 0.02);
          }
        }
        parts.cyl(conduitMaterial, 0.34, 2.6, -0.1, 0.06, 0.06, 0.5, 8);
        parts.cyl(conduitMaterial, -0.34, 2.6, -0.1, 0.06, 0.06, 0.5, 8);
      },
    },
    // 飞行甲板终端：L 形双屏台 + 桌面上的僚机模型
    flight: {
      screen: { x: 0, y: 1.18, z: 0.22, w: 1.1, h: 0.56, tilt: -0.4 },
      lines: ['舰载单位 / FLIGHT DECK', '子系统 舰载机与僚机编队', '链路 机库数据链在线', '待命 等待放飞指令'],
      footprint: { w: 2.1, d: 1.05, h: 1.25 },
      build: (parts) => {
        parts.box(steelMaterial, 0, 0.5, 0, 1.9, 1.0, 0.9, [2, 1]);
        parts.box(darkMaterial, 0, 1.06, 0.05, 1.8, 0.12, 0.8, [2, 1], [-0.4, 0, 0]);
        parts.box(steelMaterial, -1.05, 0.75, -0.1, 0.4, 1.5, 0.8, [1, 1]);
        parts.box(steelMaterial, 0.62, 1.18, -0.16, 0.24, 0.06, 0.7);
        parts.box(steelMaterial, 0.62, 1.18, -0.16, 1.0, 0.04, 0.16);
        parts.box(glowMaterial, 0.62, 1.19, -0.5, 0.1, 0.03, 0.04);
        parts.cyl(steelMaterial, -0.6, 1.6, -0.3, 0.05, 0.05, 0.9, 8, undefined, [0, 0, -0.4]);
      },
    },
    // 船坞调配台：宽台 + 头顶吊车梁 + 操纵杆
    drydock: {
      screen: { x: 0, y: 1.3, z: 0.12, w: 1.2, h: 0.6, tilt: -0.38 },
      lines: ['补给与装载 / DRYDOCK', '子系统 船坞与补给调度', '链路 装载清单已同步', '待命 等待调度指令'],
      footprint: { w: 2.5, d: 1.05, h: 1.3 },
      build: (parts) => {
        parts.box(steelMaterial, 0, 0.55, 0, 2.3, 1.1, 0.9, [2, 1]);
        parts.box(darkMaterial, 0, 1.18, 0.06, 2.2, 0.14, 0.8, [2, 1]);
        parts.cyl(steelMaterial, -0.8, 1.36, 0.24, 0.05, 0.07, 0.36, 8);
        parts.sphere(glowWarmMaterial, -0.8, 1.58, 0.24, 0.07);
        parts.cyl(steelMaterial, -0.45, 1.36, 0.24, 0.05, 0.07, 0.36, 8);
        parts.sphere(glowMaterial, -0.45, 1.58, 0.24, 0.07);
        parts.box(steelMaterial, 0, 2.5, -0.2, 2.6, 0.16, 0.2);
        parts.box(darkMaterial, 0.5, 2.2, -0.2, 0.22, 0.6, 0.22);
        parts.box(hazardMaterial, 1.05, 2.62, -0.2, 0.5, 0.06, 0.22);
      },
    },
    // 火控台：低矮的炮手操纵架（玩家可越过它看机库，也不会堵住门洞）
    firecontrol: {
      screen: { x: 0, y: 1.16, z: -0.12, w: 1.0, h: 0.52, tilt: -0.5 },
      lines: ['舰炮管制 / FIRE CONTROL', '子系统 近防炮与护盾', '链路 火控雷达已锁定', '待命 等待交战授权'],
      footprint: { w: 1.5, d: 1.15, h: 1.35 },
      build: (parts) => {
        parts.cyl(steelMaterial, 0, 0.34, 0, 0.52, 0.66, 0.68, 18);
        parts.box(darkMaterial, 0, 0.74, -0.06, 1.2, 0.22, 0.9, [1, 1]);
        parts.box(steelMaterial, 0, 1.02, -0.36, 1.05, 0.4, 0.16, [1, 1], [-0.5, 0, 0]);
        parts.cyl(darkMaterial, -0.36, 0.98, 0.24, 0.045, 0.045, 0.34, 10);
        parts.cyl(darkMaterial, 0.36, 0.98, 0.24, 0.045, 0.045, 0.34, 10);
        parts.sphere(glowWarmMaterial, -0.36, 1.17, 0.24, 0.06);
        parts.sphere(glowWarmMaterial, 0.36, 1.17, 0.24, 0.06);
        parts.cyl(steelMaterial, -0.3, 0.5, 0.44, 0.07, 0.09, 0.9, 10, undefined, [Math.PI / 2, 0, 0]);
        parts.cyl(steelMaterial, 0.3, 0.5, 0.44, 0.07, 0.09, 0.9, 10, undefined, [Math.PI / 2, 0, 0]);
      },
    },
  };

  /**
   * 站位锚点直接取自 STATIONS：本文件不对 anchor 做任何偏移。
   *
   * 终端在本地坐标里「+z 朝向玩家」，这里按 facing 绕 Y 旋转后平移到 anchor；
   * 由于 facing 都是 π/2 的整数倍，旋转后的机身仍然是轴对齐的，
   * 碰撞盒只需按朝向交换宽深即可。
   */
  const consoleAnchors = new Map<string, THREE.Vector3>();
  for (const station of STATIONS) {
    consoleAnchors.set(station.id, new THREE.Vector3(station.anchor[0], DECK_Y, station.anchor[2]));
  }

  /** 道具的「聚焦锚点」：给 prop 类交互一个稳定的 Object3D，而不是把整舰 root 交出去 */
  const focusNode = (position: THREE.Vector3, name: string): THREE.Object3D => {
    const node = new THREE.Object3D();
    node.name = name;
    node.position.copy(position);
    root.add(node);
    return node;
  };

  for (const station of STATIONS) {
    const spec = consoleSpecs[station.id];
    const anchor = consoleAnchors.get(station.id);
    if (!spec || !anchor) continue;

    const frame = new THREE.Matrix4().makeRotationY(station.facing).setPosition(anchor.x, DECK_Y, anchor.z);
    spec.build(new Parts(batch, frame));

    addScreen(
      station.terminal,
      spec.lines,
      spec.screen.w,
      spec.screen.h,
      new THREE.Vector3(spec.screen.x, spec.screen.y, spec.screen.z),
      frame,
      spec.screen.tilt,
      station.anchor[0] * 0.7 + station.anchor[2] * 0.31,
    );

    // 全息光幕：屏幕上方一片缓慢呼吸的青色光
    const holo = new THREE.PlaneGeometry(spec.screen.w * 1.25, spec.screen.h * 1.4);
    holo.rotateX(spec.screen.tilt);
    holo.translate(spec.screen.x, spec.screen.y + 0.24, spec.screen.z + 0.06);
    holo.applyMatrix4(frame);
    batch.add(holoMaterial, holo);

    // 碰撞盒：朝向为 ±π/2 时 footprint 的宽深互换（朝向都是 90° 的整数倍）
    const swapped = Math.abs(Math.sin(station.facing)) > 0.5;
    const sizeX = swapped ? spec.footprint.d : spec.footprint.w;
    const sizeZ = swapped ? spec.footprint.w : spec.footprint.d;
    colliders.push(
      makeAABB('console', anchor.x, DECK_Y + spec.footprint.h / 2, anchor.z, sizeX, spec.footprint.h, sizeZ),
    );
    shadowSpots.push({ x: anchor.x, z: anchor.z, rx: sizeX * 0.7, rz: sizeZ * 0.7, strength: 1 });

    // 台面指示灯：每台 4 颗，颜色与频率都不同
    const ledLocal = new THREE.Vector3();
    const ledSpots: Array<readonly [number, number, number, number]> = [
      [-spec.footprint.w * 0.3, spec.footprint.h * 0.72, spec.footprint.d * 0.45, COLOR_CYAN],
      [spec.footprint.w * 0.3, spec.footprint.h * 0.72, spec.footprint.d * 0.45, 0x7ef0b0],
      [-spec.footprint.w * 0.38, 0.42, spec.footprint.d * 0.45, COLOR_ORANGE],
      [spec.footprint.w * 0.38, 0.42, spec.footprint.d * 0.45, COLOR_CYAN],
    ];
    ledSpots.forEach(([lx, ly, lz, color], index) => {
      ledLocal.set(lx, ly, lz).applyMatrix4(frame);
      addLed(ledLocal.x, ledLocal.y, ledLocal.z, color, index % 2 === 0 ? 'pulse' : 'blink', index * 1.7 + anchor.x * 0.3);
    });

    interactables.push({
      id: `prop:terminal:${station.id}`,
      kind: 'prop',
      position: anchor.clone(),
      hint: `${station.label} · ${station.subsystem}`,
      object: focusNode(anchor, `console:${station.id}`),
    });
  }

  // ---- 反应堆（工程舱） ---------------------------------------------------

  const reactorPos = new THREE.Vector3(31, DECK_Y, 4.8);
  {
    const frame = new THREE.Matrix4().makeRotationY(0).setPosition(reactorPos.x, DECK_Y, reactorPos.z);
    const parts = new Parts(batch, frame);
    parts.cyl(hexMaterial, 0, 0.28, 0, 2.5, 2.7, 0.56, 28, [4, 1]);
    parts.cyl(hazardMaterial, 0, 0.6, 0, 2.4, 2.4, 0.14, 28, [8, 1]);
    for (let i = 0; i < 6; i += 1) {
      const angle = (i / 6) * Math.PI * 2;
      parts.box(steelMaterial, Math.cos(angle) * 2.05, 1.8, Math.sin(angle) * 2.05, 0.3, 2.4, 0.3);
      parts.box(glowMaterial, Math.cos(angle) * 1.9, 0.95, Math.sin(angle) * 1.9, 0.08, 0.5, 0.08);
    }
    parts.torus(ringMaterial, 0, 3.2, 0, 2.15, 0.12, [Math.PI / 2, 0, 0]);
    parts.cyl(hexMaterial, 0, 3.45, 0, 1.1, 2.1, 0.5, 24, [3, 1]);
    parts.cyl(hazardMaterial, 0, 3.1, 0, 2.2, 2.2, 0.16, 28, [8, 1]);
    // 约束场玻璃罩 + 顶部管线接舱顶
    parts.cyl(glassMaterial, 0, 1.9, 0, 1.95, 1.95, 3.4, 26);
    parts.cyl(pipeMaterial, 0, 3.9, 0, 0.3, 0.3, 0.8, 12);
  }
  colliders.push(makeAABB('reactor', reactorPos.x, DECK_Y + 1.9, reactorPos.z, 5.4, 3.8, 5.4));
  shadowSpots.push({ x: reactorPos.x, z: reactorPos.z, rx: 3.6, rz: 3.6, strength: 1.2 });
  addLed(reactorPos.x + 2.5, 1.0, reactorPos.z, COLOR_CYAN, 'pulse', 0.4);
  addLed(reactorPos.x - 2.5, 1.0, reactorPos.z, COLOR_ORANGE, 'blink', 2.1);

  // 反应堆护栏：一圈警示围栏（真正挡住玩家的是上面的碰撞盒）
  for (let i = 0; i < 24; i += 1) {
    const a0 = (i / 24) * Math.PI * 2;
    const a1 = ((i + 1) / 24) * Math.PI * 2;
    const mid = (a0 + a1) / 2;
    batch.box(
      steelMaterial,
      reactorPos.x + Math.cos(mid) * 3.1,
      1.0,
      reactorPos.z + Math.sin(mid) * 3.1,
      0.09,
      0.09,
      0.86,
      1,
      [0, -mid, 0],
    );
  }

  // 等离子核心：球体 + 三层旋转约束环（各自独立动画）
  const plasmaCore = new THREE.Mesh(new THREE.SphereGeometry(1.05, 24, 18), plasmaMaterial);
  plasmaCore.position.set(reactorPos.x, 1.95, reactorPos.z);
  plasmaCore.name = 'plasma-core';
  root.add(plasmaCore);

  const coreRings: THREE.Mesh[] = [];
  const ringSpecs: Array<{ radius: number; tilt: number; speed: number }> = [
    { radius: 1.6, tilt: 0.4, speed: 0.55 },
    { radius: 1.85, tilt: -0.9, speed: -0.4 },
    { radius: 2.05, tilt: 1.4, speed: 0.28 },
  ];
  for (const spec of ringSpecs) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(spec.radius, 0.075, 8, 32), ringMaterial);
    ring.position.set(reactorPos.x, 1.95, reactorPos.z);
    ring.rotation.set(spec.tilt, 0, 0);
    ring.name = 'core-ring';
    root.add(ring);
    coreRings.push(ring);
  }

  interactables.push({
    id: 'prop:core',
    kind: 'prop',
    position: new THREE.Vector3(reactorPos.x - 3.6, DECK_Y, reactorPos.z),
    hint: '反应堆核心 · 约束场在线',
    object: focusNode(new THREE.Vector3(reactorPos.x, 1.95, reactorPos.z), 'prop:core'),
  });

  // ---- 陈设：货箱 / 工具架 / 座椅 / 舰载机 ---------------------------------

  const crateRnd = mulberry32(0xc4a7);
  interface CratePlacement {
    x: number;
    y: number;
    z: number;
    sx: number;
    sy: number;
    sz: number;
    ry: number;
  }
  const cratePlacements: CratePlacement[] = [];

  // 货箱禁区：控制台 / 反应堆 / 工具架 / 座椅 / 舰载机 / 炮台 / 配电盘 / 物资 / 舱门。
  // 半径取「道具外接半径 + 一点余量」，货箱撒点时必须整体落在所有禁区之外。
  const keepOut: Array<{ x: number; z: number; r: number }> = [];
  for (const anchor of consoleAnchors.values()) keepOut.push({ x: anchor.x, z: anchor.z, r: 2.3 });
  keepOut.push({ x: reactorPos.x, z: reactorPos.z, r: 4.4 });
  for (const [x, z] of RACK_POSITIONS) keepOut.push({ x, z, r: 2.0 });
  for (const [x, z] of CHAIR_POSITIONS) keepOut.push({ x, z, r: 1.3 });
  for (const spot of DRONE_POSITIONS) keepOut.push({ x: spot.x, z: spot.z, r: 2.6 });
  keepOut.push({ x: TURRET_POS.x, z: TURRET_POS.z, r: 2.6 });
  keepOut.push({ x: BREAKER_POS.x, z: BREAKER_POS.z, r: 1.6 });
  for (const [x, z] of HAZARD_CRATE_SPOTS) keepOut.push({ x, z, r: 1.4 });
  for (const spot of pickupSpots) keepOut.push({ x: spot.x, z: spot.z, r: 1.3 });
  for (const room of ROOMS) {
    const rect = roomRects.get(room.id);
    const door = DOORS[room.id]?.[0];
    if (!rect || !door) continue;
    // 门口 3m 内不堆货：门洞必须永远能通行
    const x = door.side === 'e' ? rect.maxX : door.side === 'w' ? rect.minX : door.at;
    const z = door.side === 'n' ? rect.minZ : door.side === 's' ? rect.maxZ : door.at;
    keepOut.push({ x, z, r: 3.0 });
  }

  const isFreeSpot = (x: number, z: number, radius: number): boolean =>
    keepOut.every((spot) => Math.hypot(x - spot.x, z - spot.z) > spot.r + radius);

  const pushCrates = (rect: Rect | undefined, count: number): void => {
    if (!rect) return;
    for (let i = 0; i < count; i += 1) {
      const size = 0.75 + crateRnd() * 0.55;
      let x = 0;
      let z = 0;
      let placed = false;
      for (let attempt = 0; attempt < 24 && !placed; attempt += 1) {
        x = rect.minX + 2.4 + crateRnd() * (rectWidth(rect) - 4.8);
        z = rect.minZ + 2.4 + crateRnd() * (rectDepth(rect) - 4.8);
        placed = isFreeSpot(x, z, size * 0.9);
      }
      // 24 次都撞禁区就少放一只，绝不硬塞
      if (!placed) continue;
      keepOut.push({ x, z, r: size * 0.8 }); // 箱底之间也留缝，避免互相穿插
      cratePlacements.push({
        x,
        y: size / 2,
        z,
        sx: size,
        sy: size,
        sz: size * (0.85 + crateRnd() * 0.4),
        ry: Math.round(crateRnd() * 4) * (Math.PI / 2),
      });
      if (crateRnd() > 0.62) {
        const top = size * (0.6 + crateRnd() * 0.3);
        cratePlacements.push({
          x: x + (crateRnd() - 0.5) * 0.2,
          y: size + top / 2,
          z: z + (crateRnd() - 0.5) * 0.2,
          sx: top,
          sy: top,
          sz: top,
          ry: Math.round(crateRnd() * 4) * (Math.PI / 2),
        });
      }
    }
  };
  pushCrates(roomRects.get('cargo'), low ? 6 : 11);
  pushCrates(roomRects.get('hangar'), low ? 2 : 4);

  const crateScratch = new THREE.Object3D();
  const crateGeometry = new THREE.BoxGeometry(1, 1, 1);
  scaleUV(crateGeometry, 1.6, 1.6);
  const crateMesh = new THREE.InstancedMesh(crateGeometry, crateMaterial, Math.max(1, cratePlacements.length));
  cratePlacements.forEach((crate, index) => {
    crateScratch.position.set(crate.x, DECK_Y + crate.y, crate.z);
    crateScratch.rotation.set(0, crate.ry, 0);
    crateScratch.scale.set(crate.sx, crate.sy, crate.sz);
    crateScratch.updateMatrix();
    crateMesh.setMatrixAt(index, crateScratch.matrix);
    // 碰撞按旋转后的最大外接尺寸给，玩家不会卡进货箱
    const half = Math.max(crate.sx, crate.sz) * 0.5;
    colliders.push(makeAABB('crate', crate.x, DECK_Y + crate.y, crate.z, half * 2, crate.sy, half * 2));
    shadowSpots.push({ x: crate.x, z: crate.z, rx: half * 1.5, rz: half * 1.5, strength: 0.8 });
  });
  crateMesh.count = cratePlacements.length;
  crateMesh.instanceMatrix.needsUpdate = true;
  crateMesh.frustumCulled = false;
  crateMesh.name = 'crates';
  root.add(crateMesh);

  // 危险品货箱：贴着舱壁的几只橙色标识箱
  const hazardCrateMesh = new THREE.InstancedMesh(
    new THREE.BoxGeometry(1.05, 1.05, 1.05),
    hazardMaterial,
    HAZARD_CRATE_SPOTS.length,
  );
  HAZARD_CRATE_SPOTS.forEach(([x, z], index) => {
    crateScratch.position.set(x, DECK_Y + 0.525, z);
    crateScratch.rotation.set(0, index * 0.7, 0);
    crateScratch.scale.set(1, 1, 1);
    crateScratch.updateMatrix();
    hazardCrateMesh.setMatrixAt(index, crateScratch.matrix);
    colliders.push(makeAABB('crate', x, DECK_Y + 0.525, z, 1.05, 1.05, 1.05));
    shadowSpots.push({ x, z, rx: 0.85, rz: 0.85, strength: 0.8 });
  });
  hazardCrateMesh.instanceMatrix.needsUpdate = true;
  hazardCrateMesh.frustumCulled = false;
  hazardCrateMesh.name = 'hazard-crates';
  root.add(hazardCrateMesh);

  // 工具架（工程舱，贴着 -z 舱壁）
  for (const [rackX, rackZ] of RACK_POSITIONS) {
    const frame = new THREE.Matrix4().makeRotationY(0).setPosition(rackX, DECK_Y, rackZ);
    const parts = new Parts(batch, frame);
    parts.box(steelMaterial, 0, 0.9, 0, 2.0, 1.8, 0.4, [2, 2]);
    parts.box(darkMaterial, 0, 1.82, 0.02, 2.1, 0.12, 0.5, [2, 1]);
    parts.box(hazardMaterial, 0, 1.66, 0.22, 2.0, 0.12, 0.06);
    for (let i = 0; i < 6; i += 1) {
      parts.box(glowMaterial, -0.75 + i * 0.3, 1.9, 0.16, 0.06, 0.06, 0.04);
      parts.cyl(darkMaterial, -0.75 + i * 0.3, 1.28, 0.22, 0.035, 0.035, 0.7, 8);
    }
    colliders.push(makeAABB('rack', rackX, DECK_Y + 0.9, rackZ, 2.1, 1.8, 0.6));
    shadowSpots.push({ x: rackX, z: rackZ, rx: 1.4, rz: 0.6, strength: 0.9 });
  }

  // 座椅：舰长席 + 两侧值班席
  const addChair = (x: number, z: number, ry: number): void => {
    const frame = new THREE.Matrix4().makeRotationY(ry).setPosition(x, DECK_Y, z);
    const parts = new Parts(batch, frame);
    parts.cyl(steelMaterial, 0, 0.22, 0, 0.22, 0.3, 0.44, 14);
    parts.box(steelMaterial, 0, 0.47, 0, 0.62, 0.12, 0.6, [1, 1]);
    parts.box(steelMaterial, 0, 0.83, -0.26, 0.6, 0.72, 0.12, [1, 1], [-0.12, 0, 0]);
    parts.box(steelMaterial, -0.34, 0.66, 0, 0.1, 0.1, 0.42);
    parts.box(steelMaterial, 0.34, 0.66, 0, 0.1, 0.1, 0.42);
    parts.box(glowMaterial, 0, 1.22, -0.3, 0.4, 0.05, 0.03);
    colliders.push(makeAABB('chair', x, DECK_Y + 0.45, z, 0.9, 0.9, 0.9));
    shadowSpots.push({ x, z, rx: 0.55, rz: 0.55, strength: 0.7 });
  };
  addChair(CHAIR_POSITIONS[0][0], CHAIR_POSITIONS[0][1], 0);
  addChair(CHAIR_POSITIONS[1][0], CHAIR_POSITIONS[1][1], Math.PI * 0.15);
  addChair(CHAIR_POSITIONS[2][0], CHAIR_POSITIONS[2][1], -Math.PI * 0.15);

  // 舰载机（机库）：两架，轻微悬浮摆动
  interface DroneRecord {
    readonly group: THREE.Group;
    readonly baseY: number;
    readonly phase: number;
  }
  const drones: DroneRecord[] = [];
  for (const spot of DRONE_POSITIONS) {
    const group = new THREE.Group();
    group.position.set(spot.x, 0.9, spot.z);
    group.rotation.y = spot.ry;
    group.name = 'drone';

    const bodyGeometry = mergeGeometries(
      [
        new THREE.BoxGeometry(0.7, 0.46, 2.8),
        new THREE.BoxGeometry(2.8, 0.12, 0.9).translate(0, -0.06, 0.15),
        new THREE.BoxGeometry(1.1, 0.1, 0.5).translate(0, 0.14, -1.25),
        new THREE.CylinderGeometry(0.16, 0.26, 1.0, 12).rotateX(Math.PI / 2).translate(0, 0, 1.7),
        new THREE.CylinderGeometry(0.05, 0.05, 0.5, 8).translate(-0.5, -0.4, 0.6),
        new THREE.CylinderGeometry(0.05, 0.05, 0.5, 8).translate(0.5, -0.4, 0.6),
        new THREE.CylinderGeometry(0.05, 0.05, 0.4, 8).translate(0, -0.35, -0.9),
      ],
      false,
    );
    if (bodyGeometry) group.add(new THREE.Mesh(bodyGeometry, hullMaterial));

    const canopy = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.3, 0.9), glassMaterial);
    canopy.position.set(0, 0.26, -0.5);
    group.add(canopy);

    const engine = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.12, 12), glowMaterial);
    engine.rotation.x = Math.PI / 2;
    engine.position.set(0, 0, 2.2);
    group.add(engine);

    root.add(group);
    drones.push({ group, baseY: 0.9, phase: spot.x * 0.3 });
    colliders.push(makeAABB('drone', spot.x, DECK_Y + 0.9, spot.z, 3.0, 1.4, 3.4));
    shadowSpots.push({ x: spot.x, z: spot.z, rx: 1.9, rz: 2.0, strength: 1 });
  }

  // ---- 小游戏道具：舰炮演习台 + 配电断路器盘 ------------------------------

  const turretPos = new THREE.Vector3(TURRET_POS.x, DECK_Y, TURRET_POS.z);
  const turretYoke = new THREE.Group();
  {
    const frame = new THREE.Matrix4().makeRotationY(Math.PI / 2).setPosition(turretPos.x, DECK_Y, turretPos.z);
    const parts = new Parts(batch, frame);
    parts.cyl(hexMaterial, 0, 0.22, 0, 1.15, 1.3, 0.44, 22, [3, 1]);
    parts.cyl(hazardMaterial, 0, 0.5, 0, 1.0, 1.0, 0.12, 22, [8, 1]);
    parts.box(steelMaterial, 0, 0.62, 0, 1.6, 0.24, 1.5, [1, 1]);
    parts.box(darkMaterial, 0, 0.9, -0.75, 0.7, 0.5, 0.3, [1, 1], [-0.3, 0, 0]);
    colliders.push(makeAABB('turret', turretPos.x, DECK_Y + 0.5, turretPos.z, 2.4, 1.2, 2.4));
    shadowSpots.push({ x: turretPos.x, z: turretPos.z, rx: 1.7, rz: 1.7, strength: 1 });
  }
  {
    // 旋转部分：炮塔本体 + 双联装炮管（独立 Group，缓慢扫掠）
    turretYoke.position.set(turretPos.x, DECK_Y + 0.74, turretPos.z);
    const bodyGeometry = mergeGeometries(
      [
        new THREE.BoxGeometry(1.2, 0.5, 1.0).translate(0, 0.25, 0),
        new THREE.BoxGeometry(0.9, 0.36, 0.7).translate(0, 0.6, -0.2),
        new THREE.CylinderGeometry(0.09, 0.11, 1.6, 12).rotateX(Math.PI / 2).translate(-0.22, 0.42, 0.9),
        new THREE.CylinderGeometry(0.09, 0.11, 1.6, 12).rotateX(Math.PI / 2).translate(0.22, 0.42, 0.9),
        new THREE.BoxGeometry(0.5, 0.1, 0.6).translate(0, 0.86, -0.35),
      ],
      false,
    );
    if (bodyGeometry) turretYoke.add(new THREE.Mesh(bodyGeometry, steelMaterial));
    const sight = new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.24, 0.06), glowMaterial);
    sight.position.set(0, 0.9, -0.68);
    turretYoke.add(sight);
    turretYoke.name = 'turret-yoke';
    root.add(turretYoke);
    addLed(turretPos.x + 0.9, 0.42, turretPos.z, COLOR_CYAN, 'pulse', 1.2);
    addLed(turretPos.x - 0.9, 0.42, turretPos.z, COLOR_ORANGE, 'blink', 0.2);
  }
  interactables.push({
    id: 'minigame:turret',
    kind: 'minigame',
    position: turretPos.clone(),
    hint: '进入舰炮演习',
    object: turretYoke,
    miniGame: 'turret',
  });

  const breakerPos = new THREE.Vector3(BREAKER_POS.x, DECK_Y, BREAKER_POS.z);
  {
    const frame = new THREE.Matrix4().makeRotationY(0).setPosition(breakerPos.x, DECK_Y, breakerPos.z);
    const parts = new Parts(batch, frame);
    parts.box(hullMaterial, 0, 1.5, 0, 1.5, 1.9, 0.22, [1, 2]);
    parts.box(hazardMaterial, 0, 2.42, 0.02, 1.5, 0.14, 0.26, [1, 1]);
    parts.box(darkMaterial, 0, 1.5, 0.13, 1.2, 1.6, 0.06, [1, 1]);
    for (let i = 0; i < 4; i += 1) {
      for (let j = 0; j < 2; j += 1) {
        parts.box(steelMaterial, -0.42 + i * 0.28, 0.95 + j * 0.36, 0.18, 0.16, 0.24, 0.08);
        parts.box(glowMaterial, -0.42 + i * 0.28, 1.1 + j * 0.36, 0.23, 0.08, 0.06, 0.02);
      }
    }
    parts.cyl(conduitMaterial, 0, 2.62, 0, 0.07, 0.07, 0.5, 8);
  }
  addScreen(
    'BREAKER',
    ['配电回路 / CIRCUIT', '子系统 检修配电回路', '状态 待检修', '待命 等待合闸'],
    0.6,
    0.32,
    new THREE.Vector3(0, 1.72, 0.16),
    new THREE.Matrix4().makeRotationY(0).setPosition(breakerPos.x, DECK_Y, breakerPos.z),
    0,
    3.3,
  );
  addLed(33.6, 2.3, -9.2, COLOR_ORANGE, 'blink', 0.9);
  interactables.push({
    id: 'minigame:circuit',
    kind: 'minigame',
    position: new THREE.Vector3(33, DECK_Y, -8.8),
    hint: '检修配电回路',
    object: focusNode(new THREE.Vector3(33, 1.5, -9.3), 'prop:breaker'),
    miniGame: 'circuit',
  });

  // ---- 12 件物资（3 电池 / 3 冷却剂 / 2 合金 / 2 数据核心 / 2 医疗包） -----

  interface PickupRecord {
    readonly group: THREE.Group;
    readonly baseY: number;
    readonly phase: number;
    readonly interactable: ShipInteractable;
  }
  const pickups: PickupRecord[] = [];

  // 注意：(±4.5, ±4.5) 附近是枢纽与走廊之间的接缝——两个矩形在这里只共享边界，
  // 站位点必须留在各自的矩形内，否则物资会落在不可达的角落里（bridge.test.tsx 有用例守住）。
  // 12 个落点见文件上方的 pickupSpots 常量表。
  const itemCounters: Partial<Record<ItemId, number>> = {};

  for (const spot of pickupSpots) {
    itemCounters[spot.item] = (itemCounters[spot.item] ?? 0) + 1;
    const group = new THREE.Group();
    group.name = `pickup:${spot.item}`;

    // 每件物资一个合并后的几何体（材质按种类共享），全舰约 15 个 draw call
    let material: THREE.Material = steelMaterial;
    let geometry: THREE.BufferGeometry | null = null;
    if (spot.item === 'power-cell') {
      material = darkMaterial;
      geometry = mergeGeometries(
        [
          new THREE.CylinderGeometry(0.11, 0.11, 0.34, 14),
          new THREE.CylinderGeometry(0.055, 0.055, 0.1, 10).translate(0, 0.21, 0),
        ],
        false,
      );
      const band = new THREE.Mesh(new THREE.CylinderGeometry(0.118, 0.118, 0.07, 14), pickupGlowMaterial);
      group.add(band);
    } else if (spot.item === 'coolant') {
      material = lightMaterial;
      geometry = mergeGeometries(
        [
          new THREE.CapsuleGeometry(0.13, 0.26, 6, 14),
          new THREE.CylinderGeometry(0.06, 0.06, 0.1, 10).translate(0, 0.26, 0),
        ],
        false,
      );
    } else if (spot.item === 'alloy') {
      material = hullMaterial;
      geometry = mergeGeometries(
        [new THREE.BoxGeometry(0.44, 0.05, 0.32), new THREE.BoxGeometry(0.42, 0.05, 0.3).translate(0.02, 0.06, 0.01)],
        false,
      );
    } else if (spot.item === 'data-core') {
      material = holoMaterial;
      geometry = new THREE.OctahedronGeometry(0.19, 0);
    } else {
      material = lightMaterial;
      geometry = mergeGeometries(
        [
          new THREE.BoxGeometry(0.34, 0.22, 0.24),
          new THREE.BoxGeometry(0.2, 0.06, 0.02).translate(0, 0.02, 0.13),
          new THREE.BoxGeometry(0.06, 0.16, 0.02).translate(0, 0.02, 0.13),
        ],
        false,
      );
    }
    if (geometry) {
      const mesh = new THREE.Mesh(geometry, material);
      mesh.name = `pickup-mesh:${spot.item}`;
      group.add(mesh);
    }

    const baseY = 0.72;
    group.position.set(spot.x, baseY, spot.z);
    root.add(group);

    const interactable: ShipInteractable = {
      id: `pickup:${spot.item}:${itemCounters[spot.item] ?? 1}`,
      kind: 'pickup',
      item: spot.item,
      position: new THREE.Vector3(spot.x, DECK_Y, spot.z),
      hint: `拾取 ${ITEMS[spot.item].name}`,
      object: group,
    };
    interactables.push(interactable);
    pickups.push({ group, baseY, phase: spot.x * 0.5 + spot.z * 0.3, interactable });
  }

  // ---- 舰门（DOORS 的四处开口） -------------------------------------------

  /** 门叶几何：主板 + 中肋 + 两侧包边 + 下部加强条，合并成一个 Mesh */
  const doorLeafGeometry = (width: number): THREE.BufferGeometry => {
    const merged = mergeGeometries(
      [
        new THREE.BoxGeometry(width, DOOR_H, 0.12),
        new THREE.BoxGeometry(width, 0.14, 0.16).translate(0, DOOR_H * 0.28, 0),
        new THREE.BoxGeometry(0.1, DOOR_H, 0.16).translate(width / 2 - 0.06, 0, 0),
        new THREE.BoxGeometry(0.1, DOOR_H, 0.16).translate(-width / 2 + 0.06, 0, 0),
        new THREE.BoxGeometry(width * 0.42, 0.1, 0.16).translate(0, -DOOR_H * 0.32, 0),
      ],
      false,
    );
    const geometry = merged ?? new THREE.BoxGeometry(width, DOOR_H, 0.12);
    scaleUV(geometry, 1.6, 2.4);
    return geometry;
  };

  for (const room of ROOMS) {
    const rect = roomRects.get(room.id);
    const doorDef = DOORS[room.id]?.[0];
    if (!rect || !doorDef) continue;

    const alongX = doorDef.side === 'n' || doorDef.side === 's';
    const wallCenter =
      doorDef.side === 'n'
        ? rect.minZ - WALL_THICKNESS / 2
        : doorDef.side === 's'
          ? rect.maxZ + WALL_THICKNESS / 2
          : doorDef.side === 'w'
            ? rect.minX - WALL_THICKNESS / 2
            : rect.maxX + WALL_THICKNESS / 2;
    const inward = doorDef.side === 'w' || doorDef.side === 'n' ? 1 : -1;

    const door = new SlidingDoor(`door:${room.id}`);
    const leafWidth = DOOR_WIDTH / 2 - 0.03;
    const leafGeometry = doorLeafGeometry(leafWidth);
    const travel = leafWidth + 0.12;

    for (const side of [-1, 1]) {
      const mesh = new THREE.Mesh(leafGeometry, doorLeafMaterial);
      mesh.name = `leaf:${room.id}:${side}`;
      const closedCenter = alongX
        ? new THREE.Vector3(doorDef.at + (side * DOOR_WIDTH) / 4, DOOR_H / 2, wallCenter)
        : new THREE.Vector3(wallCenter, DOOR_H / 2, doorDef.at + (side * DOOR_WIDTH) / 4);
      const axis = alongX ? new THREE.Vector3(side, 0, 0) : new THREE.Vector3(0, 0, side);
      // 门洞沿 x 时门叶法线朝 z；沿 z 时把门叶转 90°
      if (!alongX) mesh.rotation.y = Math.PI / 2;
      door.addLeaf(mesh, closedCenter, axis, travel);
    }
    root.add(door.object);
    doors.push(door);

    // 门框：两侧立柱 + 门楣压条 + 门洞灯带（合批；门框都在门洞之外，不挡通行）
    const jambOffset = DOOR_WIDTH / 2 + 0.11;
    if (alongX) {
      for (const side of [-1, 1]) {
        batch.box(
          steelMaterial,
          doorDef.at + side * jambOffset,
          DOOR_H / 2,
          wallCenter,
          0.22,
          DOOR_H,
          WALL_THICKNESS + 0.06,
          1,
        );
      }
      batch.box(hazardMaterial, doorDef.at, DOOR_H - 0.08, wallCenter, DOOR_WIDTH, 0.16, WALL_THICKNESS + 0.08, 1);
      const strip = new THREE.PlaneGeometry(DOOR_WIDTH * 0.7, 0.1);
      scaleUV(strip, 4, 1);
      strip.translate(doorDef.at, DOOR_H - 0.3, wallCenter + inward * 0.22);
      batch.add(stripMaterial, strip);
      addLed(doorDef.at, DOOR_H + 0.16, wallCenter + inward * 0.24, COLOR_ORANGE, 'door', 0, door);
    } else {
      for (const side of [-1, 1]) {
        batch.box(
          steelMaterial,
          wallCenter,
          DOOR_H / 2,
          doorDef.at + side * jambOffset,
          WALL_THICKNESS + 0.06,
          DOOR_H,
          0.22,
          1,
        );
      }
      batch.box(hazardMaterial, wallCenter, DOOR_H - 0.08, doorDef.at, WALL_THICKNESS + 0.08, 0.16, DOOR_WIDTH, 1);
      const strip = new THREE.PlaneGeometry(DOOR_WIDTH * 0.7, 0.1);
      scaleUV(strip, 4, 1);
      strip.rotateY(Math.PI / 2);
      strip.translate(wallCenter + inward * 0.22, DOOR_H - 0.3, doorDef.at);
      batch.add(stripMaterial, strip);
      addLed(wallCenter + inward * 0.24, DOOR_H + 0.16, doorDef.at, COLOR_ORANGE, 'door', 0, door);
    }
  }

  // ---- 机库气闸（舰艉外墙）：舱口凹龛 + 六瓣虹膜 + 力场 -------------------

  const airlockDoor = new SlidingDoor('door:airlock');
  {
    const hangarRect = roomRects.get('hangar');
    const airlockZ = hangarRect?.maxZ ?? 33;
    const inner = airlockZ + WALL_THICKNESS; // 舱壁外表面
    const recessDepth = 0.75;
    const halfW = 1.8;

    // 凹龛：侧壁 / 底板 / 顶板；出口敞开对星野
    batch.box(wallMaterial, -halfW - 0.2, WALL_H / 2, inner + recessDepth / 2, 0.4, WALL_H, recessDepth, WALL_UV);
    batch.box(wallMaterial, halfW + 0.2, WALL_H / 2, inner + recessDepth / 2, 0.4, WALL_H, recessDepth, WALL_UV);
    batch.box(floorMaterial, 0, DECK_Y - FLOOR_T / 2, inner + recessDepth / 2, halfW * 2, FLOOR_T, recessDepth, FLOOR_UV);
    batch.box(ceilingMaterial, 0, 3.6, inner + recessDepth / 2, halfW * 2 + 0.8, 0.4, recessDepth, 0.25);
    colliders.push(makeAABB('floor', 0, DECK_Y - FLOOR_T / 2, inner + recessDepth / 2, halfW * 2, FLOOR_T, recessDepth));

    // 力场：可见力场与碰撞盒在同一平面，玩家撞上去不会觉得「撞空气」
    const fieldGeometry = new THREE.PlaneGeometry(halfW * 2, 3.4);
    fieldGeometry.rotateY(Math.PI);
    fieldGeometry.translate(0, 1.7, inner + 0.02);
    const field = new THREE.Mesh(fieldGeometry, forceFieldMaterial);
    field.name = 'airlock-field';
    root.add(field);
    colliders.push(makeAABB('airlock-field', 0, 1.7, inner + 0.2, halfW * 2, 3.4, 0.4));

    // 舱口环 + 螺栓 + 危险边条
    batch.box(steelMaterial, 0, 3.5, inner + 0.1, halfW * 2 + 0.9, 0.4, 0.5, 1);
    batch.box(hazardMaterial, 0, 0.14, inner + 0.16, halfW * 2 + 0.6, 0.28, 0.24, 1.4);
    const ringGeometry = new THREE.TorusGeometry(1.72, 0.16, 10, 30);
    ringGeometry.translate(0, 1.7, inner - 0.02);
    batch.add(steelMaterial, ringGeometry);
    for (let i = 0; i < 12; i += 1) {
      const angle = (i / 12) * Math.PI * 2;
      batch.box(steelMaterial, Math.cos(angle) * 1.72, 1.7 + Math.sin(angle) * 1.72, inner - 0.12, 0.14, 0.14, 0.18, 1);
    }

    // 六瓣虹膜：每瓣绕自己的铰点旋转，开启时贴向舱口边缘
    const bladeGeometry = new THREE.BoxGeometry(1.16, 0.24, 0.12).translate(-0.58, 0, 0);
    const irisPivots: THREE.Group[] = [];
    for (let i = 0; i < 6; i += 1) {
      const angle = (i / 6) * Math.PI * 2;
      const pivot = new THREE.Group();
      pivot.position.set(Math.cos(angle) * 0.86, 1.7 + Math.sin(angle) * 0.86, inner - 0.06);
      pivot.rotation.z = angle + Math.PI;
      pivot.add(new THREE.Mesh(bladeGeometry, bladeMaterial));
      airlockDoor.object.add(pivot);
      irisPivots.push(pivot);
    }
    root.add(airlockDoor.object);
    doors.push(airlockDoor);

    // 虹膜开合（与 SlidingDoor.update 共用 openness）
    for (const pivot of irisPivots) {
      const base = pivot.rotation.z;
      anims.push(() => {
        pivot.rotation.z = base + airlockDoor.openness * 1.45;
      });
    }
    addLed(1.35, 3.5, inner + 0.32, COLOR_ORANGE, 'door', 0, airlockDoor);
    addLed(-1.35, 3.5, inner + 0.32, COLOR_CYAN, 'pulse', 1.4);

    interactables.push({
      id: 'prop:airlock',
      kind: 'prop',
      position: new THREE.Vector3(0, DECK_Y, airlockZ - 1.4),
      hint: '气闸舱口 · 仅停靠时可开启',
      object: airlockDoor.object,
    });
  }

  // 舰门的缓动**不在这里**推进：开门逻辑在游戏侧（engine.updateDoors 每帧根据
  // 玩家距离设置 door.open，然后调用一次 door.update(dt)）。若这里再挂一份，
  // 同一帧会被推进两次，门速翻倍。

  // ---- 垂吊线缆（摆动） ---------------------------------------------------

  interface CableRecord {
    readonly group: THREE.Group;
    readonly phase: number;
  }
  const cables: CableRecord[] = [];
  const cableSpots = low
    ? [
        { x: 1.4, z: -14, length: 1.6 },
        { x: -1.4, z: 12, length: 1.3 },
      ]
    : [
        { x: 1.4, z: -14, length: 1.6 },
        { x: -1.4, z: -10.5, length: 1.2 },
        { x: 1.4, z: 12, length: 1.3 },
        { x: -1.4, z: 15.5, length: 1.5 },
        { x: 16, z: 1.4, length: 1.25 },
        { x: -16, z: -1.4, length: 1.45 },
      ];
  for (const spot of cableSpots) {
    const group = new THREE.Group();
    group.position.set(spot.x, 3.95, spot.z);
    const geometry = new THREE.CylinderGeometry(0.035, 0.035, spot.length, 8);
    geometry.translate(0, -spot.length / 2, 0);
    group.add(new THREE.Mesh(geometry, conduitMaterial));
    const plug = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.16, 0.12), darkMaterial);
    plug.position.set(0, -spot.length, 0);
    group.add(plug);
    root.add(group);
    cables.push({ group, phase: spot.x * 0.4 + spot.z * 0.2 });
  }

  // ---- 星野 / 行星 / 尘埃 -------------------------------------------------

  const starCount = low ? 520 : 1500;
  const starPositions = new Float32Array(starCount * 3);
  const starColors = new Float32Array(starCount * 3);
  const starRnd = mulberry32(0x57a2);
  const scratchColor = new THREE.Color();
  for (let i = 0; i < starCount; i += 1) {
    // 球面均匀分布：cosθ 均匀采样，避免两极堆积
    const u = starRnd() * 2 - 1;
    const phi = starRnd() * Math.PI * 2;
    const s = Math.sqrt(1 - u * u);
    const radius = 820 + starRnd() * 120;
    starPositions[i * 3] = Math.cos(phi) * s * radius;
    starPositions[i * 3 + 1] = u * radius;
    starPositions[i * 3 + 2] = Math.sin(phi) * s * radius;
    const hue = starRnd();
    scratchColor.setHSL(hue > 0.82 ? 0.09 : hue > 0.45 ? 0.55 : 0.62, 0.35, 0.72 + starRnd() * 0.26);
    starColors[i * 3] = scratchColor.r;
    starColors[i * 3 + 1] = scratchColor.g;
    starColors[i * 3 + 2] = scratchColor.b;
  }
  const starGeometry = new THREE.BufferGeometry();
  starGeometry.setAttribute('position', new THREE.Float32BufferAttribute(starPositions, 3));
  starGeometry.setAttribute('color', new THREE.Float32BufferAttribute(starColors, 3));
  const starPoints = new THREE.Points(starGeometry, starMaterial);
  starPoints.name = 'starfield-points';
  starPoints.frustumCulled = false;
  root.add(starPoints);

  // 远处行星与卫星：给舷窗外的视野一个「目的地」，比纯星点更有纵深
  const planet = new THREE.Mesh(new THREE.SphereGeometry(70, 32, 24), planetMaterial);
  planet.position.set(-190, 70, -620);
  planet.name = 'planet';
  root.add(planet);
  const moon = new THREE.Mesh(new THREE.SphereGeometry(16, 20, 16), crateMaterial);
  moon.position.set(150, -40, -560);
  moon.name = 'moon';
  root.add(moon);

  // 尘埃：舱内漂浮的微粒，按各自速度漂移，越出所属舱室就从对面绕回
  const dustCount = low ? 0 : 260;
  const dustPositions = new Float32Array(dustCount * 3);
  const dustVelocity = new Float32Array(dustCount * 3);
  const dustZones: Rect[] = [];
  const dustRnd = mulberry32(0xd057);
  for (let i = 0; i < dustCount; i += 1) {
    const zone = floorRects[Math.floor(dustRnd() * floorRects.length)] ?? hubRect;
    dustZones.push(zone);
    dustPositions[i * 3] = zone.minX + dustRnd() * rectWidth(zone);
    dustPositions[i * 3 + 1] = 0.35 + dustRnd() * (DECK_HEIGHT - 0.7);
    dustPositions[i * 3 + 2] = zone.minZ + dustRnd() * rectDepth(zone);
    dustVelocity[i * 3] = (dustRnd() - 0.5) * 0.05;
    dustVelocity[i * 3 + 1] = (dustRnd() - 0.5) * 0.025;
    dustVelocity[i * 3 + 2] = (dustRnd() - 0.5) * 0.05;
  }
  const dustGeometry = new THREE.BufferGeometry();
  dustGeometry.setAttribute('position', new THREE.Float32BufferAttribute(dustPositions, 3));
  const dustPoints = new THREE.Points(dustGeometry, dustMaterial);
  dustPoints.name = 'dust';
  dustPoints.frustumCulled = false;
  if (dustCount > 0) root.add(dustPoints);

  // ---- 接触阴影（InstancedMesh，代替实时阴影） ----------------------------

  const shadowGeometry = new THREE.PlaneGeometry(1, 1);
  shadowGeometry.rotateX(-Math.PI / 2);
  const shadowMesh = new THREE.InstancedMesh(shadowGeometry, shadowMaterial, Math.max(1, shadowSpots.length));
  const shadowScratch = new THREE.Object3D();
  shadowSpots.forEach((spot, index) => {
    shadowScratch.position.set(spot.x, DECK_Y + 0.02, spot.z);
    shadowScratch.rotation.set(0, 0, 0);
    shadowScratch.scale.set(spot.rx * 2, 1, spot.rz * 2);
    shadowScratch.updateMatrix();
    shadowMesh.setMatrixAt(index, shadowScratch.matrix);
  });
  shadowMesh.count = shadowSpots.length;
  shadowMesh.instanceMatrix.needsUpdate = true;
  shadowMesh.frustumCulled = false;
  shadowMesh.name = 'contact-shadows';
  root.add(shadowMesh);

  // ---- 状态指示灯（InstancedMesh：逐帧改实例颜色实现闪烁） ----------------

  const ledGeometry = new THREE.SphereGeometry(0.045, 8, 6);
  const ledMesh = new THREE.InstancedMesh(ledGeometry, ledMaterial, Math.max(1, leds.length));
  const ledScratch = new THREE.Object3D();
  leds.forEach((led, index) => {
    ledScratch.position.copy(led.position);
    ledScratch.updateMatrix();
    ledMesh.setMatrixAt(index, ledScratch.matrix);
    ledMesh.setColorAt(index, led.color);
  });
  ledMesh.count = leds.length;
  ledMesh.instanceMatrix.needsUpdate = true;
  if (ledMesh.instanceColor) ledMesh.instanceColor.needsUpdate = true;
  ledMesh.frustumCulled = false;
  ledMesh.name = 'status-leds';
  root.add(ledMesh);

  // ---- 拾取物光晕（InstancedMesh，跟着物件上下浮动） ----------------------

  const haloGeometry = new THREE.SphereGeometry(0.3, 12, 10);
  const haloMesh = new THREE.InstancedMesh(haloGeometry, haloMaterial, Math.max(1, pickups.length));
  haloMesh.count = pickups.length;
  haloMesh.frustumCulled = false;
  haloMesh.name = 'pickup-halos';
  root.add(haloMesh);
  // 首帧就要有正确位置，否则光晕会先出现在原点
  pickups.forEach((pickup, index) => {
    ledScratch.position.copy(pickup.group.position);
    ledScratch.rotation.set(0, 0, 0);
    ledScratch.scale.setScalar(1);
    ledScratch.updateMatrix();
    haloMesh.setMatrixAt(index, ledScratch.matrix);
  });
  haloMesh.instanceMatrix.needsUpdate = true;

  // ---- 光照 ---------------------------------------------------------------

  // 半球光：舱顶冷、甲板暖，给全舰一个统一底光
  const hemi = new THREE.HemisphereLight(0x4d7fa3, 0x1b232c, 0.75);
  hemi.position.set(0, DECK_HEIGHT, 0);
  root.add(hemi);

  // 暖色主光：从舰艏右上方打下来，让舱壁有方向感（不投影）
  const keyLight = new THREE.DirectionalLight(COLOR_WARM, 1.15);
  keyLight.position.set(38, 46, -34);
  keyLight.target.position.set(0, 0, 0);
  root.add(keyLight);
  root.add(keyLight.target);

  // 只保留 5 盏实光：反应堆 / 舰桥 / 机库 / 枢纽 / 货舱（上限 6）
  const pointSpecs = [
    { x: reactorPos.x, y: 2.4, z: reactorPos.z, color: COLOR_CYAN, intensity: 48, distance: 26 },
    { x: 0, y: 3.9, z: -25, color: 0x9fe6ff, intensity: 34, distance: 24 },
    { x: 0, y: 3.9, z: 25, color: 0xdfefff, intensity: 44, distance: 32 },
    { x: 0, y: 3.9, z: 0, color: 0xbfe6ff, intensity: 30, distance: 22 },
    { x: -29, y: 3.9, z: 0, color: 0xffc98a, intensity: 26, distance: 22 },
  ];
  const pointLights: THREE.PointLight[] = [];
  for (const spec of pointSpecs) {
    const light = new THREE.PointLight(spec.color, spec.intensity, spec.distance, 2);
    light.position.set(spec.x, spec.y, spec.z);
    root.add(light);
    pointLights.push(light);
  }
  const reactorLight = pointLights[0];

  // ---- 环境与背景 ---------------------------------------------------------

  const environment = environmentTexture();
  const background = starfieldTexture();
  scene.environment = environment;
  scene.background = background;
  // 舱内偏暗：环境贴图只负责给金属一点反射层次，不参与主照明
  scene.environmentIntensity = 0.42;
  scene.backgroundIntensity = 0.85;

  // ---- 动画注册 -----------------------------------------------------------

  const clockColor = new THREE.Color();
  const doorClosedColor = new THREE.Color(COLOR_ORANGE);
  const doorOpenColor = new THREE.Color(COLOR_CYAN);

  // 屏幕闪烁 + 灯带呼吸
  anims.push((_dt, elapsed) => {
    for (const screen of screens) {
      const noise = Math.sin(elapsed * 2.1 + screen.phase) * 0.5 + Math.sin(elapsed * 7.3 + screen.phase * 1.7) * 0.2;
      let level = 0.86 + noise * 0.12;
      // 偶发跳帧：CRT 式的短促闪断
      if (Math.sin(elapsed * 11.7 + screen.phase * 3.1) > 0.985) level *= 0.55;
      screen.material.color.setScalar(level);
    }
    stripMaterial.opacity = 0.78 + Math.sin(elapsed * 1.6) * 0.12;
    stripWarmMaterial.opacity = 0.62 + Math.sin(elapsed * 1.1 + 1.7) * 0.1;
    holoMaterial.opacity = 0.24 + Math.sin(elapsed * 1.9) * 0.08;
  });

  // 指示灯（门灯随开合由橙转青）
  anims.push((_dt, elapsed) => {
    for (let i = 0; i < leds.length; i += 1) {
      const led = leds[i];
      if (!led) continue;
      if (led.mode === 'door' && led.door) {
        clockColor.copy(doorClosedColor).lerp(doorOpenColor, led.door.openness);
        clockColor.multiplyScalar(0.6 + 0.4 * Math.abs(Math.sin(elapsed * 2.4 + led.phase)));
      } else if (led.mode === 'blink') {
        clockColor.copy(led.color).multiplyScalar(Math.sin(elapsed * 3.4 + led.phase) > 0.15 ? 1 : 0.1);
      } else if (led.mode === 'pulse') {
        clockColor.copy(led.color).multiplyScalar(0.45 + 0.55 * (0.5 + 0.5 * Math.sin(elapsed * 2.3 + led.phase)));
      } else {
        clockColor.copy(led.color);
      }
      ledMesh.setColorAt(i, clockColor);
    }
    if (ledMesh.instanceColor) ledMesh.instanceColor.needsUpdate = true;
  });

  // 反应堆：核心脉动 + 约束环旋转 + 实光强度跟着脉动
  anims.push((_dt, elapsed) => {
    const pulse = 0.5 + 0.5 * Math.sin(elapsed * 1.35);
    plasmaCore.scale.setScalar(0.94 + pulse * 0.1);
    plasmaMaterial.opacity = 0.68 + pulse * 0.3;
    // 贴图缓慢平移，让等离子体「流动」起来
    texPlasma.offset.x = (elapsed * 0.035) % 1;
    texPlasma.offset.y = (elapsed * 0.018) % 1;
    for (let i = 0; i < coreRings.length; i += 1) {
      const ring = coreRings[i];
      const spec = ringSpecs[i];
      if (!ring || !spec) continue;
      ring.rotation.y = elapsed * spec.speed;
      ring.rotation.z = spec.tilt * 0.5 + Math.sin(elapsed * 0.6 + i) * 0.12;
    }
    if (reactorLight) reactorLight.intensity = 40 + pulse * 22;
    ringMaterial.emissiveIntensity = 0.35 + pulse * 0.45;
  });

  // 垂吊线缆摆动
  anims.push((_dt, elapsed) => {
    for (const cable of cables) {
      cable.group.rotation.z = Math.sin(elapsed * 0.85 + cable.phase) * 0.075;
      cable.group.rotation.x = Math.cos(elapsed * 0.67 + cable.phase * 1.3) * 0.06;
    }
  });

  // 拾取物：自转 + 上下浮动（光晕同步；已拾取的光晕缩到 0）
  anims.push((_dt, elapsed) => {
    for (let i = 0; i < pickups.length; i += 1) {
      const pickup = pickups[i];
      if (!pickup) continue;
      const collected = pickup.interactable.collected === true;
      const bob = Math.sin(elapsed * 1.6 + pickup.phase) * 0.08;
      pickup.group.position.y = pickup.baseY + (collected ? -0.5 : bob);
      pickup.group.rotation.y = elapsed * 0.9 + pickup.phase;
      ledScratch.position.copy(pickup.group.position);
      ledScratch.rotation.set(0, 0, 0);
      ledScratch.scale.setScalar(collected ? 0 : 1 + Math.sin(elapsed * 2.4 + pickup.phase) * 0.14);
      ledScratch.updateMatrix();
      haloMesh.setMatrixAt(i, ledScratch.matrix);
    }
    haloMesh.instanceMatrix.needsUpdate = true;
  });

  // 尘埃漂移
  const dustAttr = dustCount > 0 ? dustGeometry.getAttribute('position') : null;
  if (dustCount > 0 && dustAttr) {
    anims.push((dt) => {
      for (let i = 0; i < dustCount; i += 1) {
        const zone = dustZones[i];
        if (!zone) continue;
        let x = dustAttr.getX(i) + dustVelocity[i * 3] * dt;
        let y = dustAttr.getY(i) + dustVelocity[i * 3 + 1] * dt;
        let z = dustAttr.getZ(i) + dustVelocity[i * 3 + 2] * dt;
        if (x < zone.minX) x = zone.maxX;
        else if (x > zone.maxX) x = zone.minX;
        if (z < zone.minZ) z = zone.maxZ;
        else if (z > zone.maxZ) z = zone.minZ;
        if (y < 0.3) y = DECK_HEIGHT - 0.5;
        else if (y > DECK_HEIGHT - 0.4) y = 0.4;
        dustAttr.setXYZ(i, x, y, z);
      }
      dustAttr.needsUpdate = true;
    });
  }

  // 星野视差（星点整体极慢自转）+ 天体自转
  anims.push((_dt, elapsed) => {
    starPoints.rotation.y = elapsed * 0.004;
    starPoints.rotation.x = Math.sin(elapsed * 0.02) * 0.03;
    planet.rotation.y = elapsed * 0.006;
    moon.rotation.y = elapsed * 0.01;
  });

  // 舰载机悬浮 + 炮塔扫掠
  anims.push((_dt, elapsed) => {
    for (const drone of drones) {
      drone.group.position.y = drone.baseY + Math.sin(elapsed * 1.1 + drone.phase) * 0.06;
      drone.group.rotation.z = Math.sin(elapsed * 0.7 + drone.phase) * 0.03;
      drone.group.rotation.x = Math.cos(elapsed * 0.9 + drone.phase) * 0.02;
    }
    turretYoke.rotation.y = Math.sin(elapsed * 0.32) * 0.6;
  });

  // ---- flush：静态几何合并成少量 Mesh -------------------------------------

  batch.flush(root);

  // ---- update / dispose ---------------------------------------------------

  let disposed = false;

  const update = (dt: number, elapsed: number): void => {
    if (disposed) return;
    for (const anim of anims) anim(dt, elapsed);
  };

  const dispose = (): void => {
    if (disposed) return;
    disposed = true;
    anims.length = 0;

    root.traverse((object) => {
      const mesh = object as THREE.Mesh;
      if (mesh.geometry) mesh.geometry.dispose();
      const material = mesh.material;
      if (Array.isArray(material)) {
        for (const item of material) item.dispose();
      } else if (material) {
        material.dispose();
      }
    });

    // 构建期创建但可能未挂到 root 的材质，统一兜底释放
    for (const material of ownedMaterials) material.dispose();

    scene.remove(root);
    root.clear();

    if (scene.background === background) scene.background = null;
    if (scene.environment === environment) scene.environment = null;

    // 贴图走模块级缓存，卸载时一并归还显存
    disposeTextureCache();
  };

  return { root, colliders, interactables, doors, update, dispose };
}
