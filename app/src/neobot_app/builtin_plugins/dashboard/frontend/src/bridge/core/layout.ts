// layout.ts —— 战舰「NeoBot 号」的坐标契约
//
// 三维几何与碰撞体共用这一份布局常量：ship.ts 只负责「看起来像战舰」，
// 走廊/舱室的可行走范围由这里决定。任何一方单独改坐标都会导致穿墙或悬空，
// 因此新增舱室时先在这里登记，再改几何。
//
// 坐标约定（右手系，与 three.js 一致）：
//   +x 右舷 / -x 左舷      +z 舰艏 / -z 舰艉      +y 甲板向上
// 甲板面 y = 0，舱内净高 DECK_HEIGHT，舱壁厚 WALL_THICKNESS。
// 舰桥在 +z 端（视野朝向舷窗外的星野），机库在 -z 端。

/** 甲板面高度 */
export const DECK_Y = 0;
/** 舱内净高（门洞高度 = DECK_HEIGHT - DOOR_LINTEL） */
export const DECK_HEIGHT = 4.2;
/** 舱壁厚度 */
export const WALL_THICKNESS = 0.4;
/** 门洞宽度 */
export const DOOR_WIDTH = 4.4;
/** 门楣厚度（门洞上方保留的墙体） */
export const DOOR_LINTEL = 0.7;
/** 玩家碰撞体半径（水平截面按方形处理，与视觉胶囊体误差 < 5cm） */
export const PLAYER_RADIUS = 0.35;
/** 玩家碰撞体高度 */
export const PLAYER_HEIGHT = 1.8;
/** 眼睛相对脚底的高度 */
export const PLAYER_EYE = 1.62;

export type Vec3 = [number, number, number];
export type WallSide = 'n' | 's' | 'e' | 'w';

/** 轴对齐盒体：舱壁、舱门、道具碰撞都用它 */
export interface AABB {
  /** 可选标识，便于调试与交互高亮（如 'wall'、'console'、'crate'） */
  tag?: string;
  center: Vec3;
  size: Vec3;
}

export interface RoomDef {
  id: string;
  /** 舱室名牌（抬头显示器与舰内导航使用） */
  label: string;
  /** 英文代号，用于全息面板抬头，营造舰载系统观感 */
  code: string;
  /** 地板矩形中心 xz */
  center: [number, number];
  /** 地板矩形尺寸（x 宽度, z 深度） */
  size: [number, number];
  /** 一句话舱室用途，显示在交互提示里 */
  purpose: string;
}

export interface CorridorDef {
  id: string;
  /** 走廊中心线 xz */
  center: [number, number];
  /** 走廊尺寸（x 宽度, z 深度），其中偶数轴为通行方向 */
  size: [number, number];
}

export interface DoorDef {
  /** 所属舱壁：房间的哪一侧 */
  side: WallSide;
  /** 门洞中心沿墙方向的位置 */
  at: number;
}

/**
 * 舱室布局。大小与相对位置固定，改一处需同步改 ship.ts 的装饰件位置。
 *
 *        [舰桥 BRIDGE]  +z
 *              |
 *  [机库]==[十字走廊]==[工程舱]
 *              |
 *        [货舱 CARGO]   -z
 */
export const ROOMS: RoomDef[] = [
  {
    id: 'bridge',
    label: '舰桥',
    code: 'BRIDGE',
    center: [0, -25],
    size: [24, 10],
    purpose: '指挥中枢：舰况总览、航行日志与指挥台',
  },
  {
    id: 'hangar',
    label: '机库',
    code: 'HANGAR',
    center: [0, 25],
    size: [28, 16],
    purpose: '舰载机与货运舱：物资清点与补给调度',
  },
  {
    id: 'engineering',
    label: '工程舱',
    code: 'ENGINEERING',
    center: [29, 0],
    size: [18, 20],
    purpose: '动力核心：能源分配、反应堆维护',
  },
  {
    id: 'cargo',
    label: '货舱',
    code: 'CARGO',
    center: [-29, 0],
    size: [18, 20],
    purpose: '货柜与备件：装载清单与平台接入',
  },
];

/** 连通四个舱室的十字走廊（中央枢纽 + 四条支线） */
export const HUB: CorridorDef = { id: 'hub', center: [0, 0], size: [9, 9] };

export const CORRIDORS: CorridorDef[] = [
  { id: 'corridor-n', center: [0, -14.5], size: [9, 11] },
  { id: 'corridor-s', center: [0, 14.5], size: [9, 11] },
  { id: 'corridor-e', center: [14.5, 0], size: [11, 9] },
  { id: 'corridor-w', center: [-14.5, 0], size: [11, 9] },
];

/** 每个舱室的开门位置（十字走廊与舱室一一对应） */
export const DOORS: Record<string, DoorDef[]> = {
  bridge: [{ side: 's', at: 0 }],
  hangar: [{ side: 'n', at: 0 }],
  engineering: [{ side: 'w', at: 0 }],
  cargo: [{ side: 'e', at: 0 }],
};

export const ALL_ZONES: Array<RoomDef | CorridorDef> = [...ROOMS, HUB, ...CORRIDORS];

/** 玩家初始位置：舰桥指挥台前 2.2m，面朝舷窗（-z 方向，与指挥台同向） */
export const SPAWN_POSITION: Vec3 = [0, 0, -27];
export const SPAWN_YAW = Math.PI;

/** 判断某点是否位于任意舱室/走廊地板矩形内（用于「走出舰体」判定） */
export function isInsideHull(x: number, z: number): boolean {
  return ALL_ZONES.some((zone) => {
    const [cx, cz] = zone.center;
    const [sx, sz] = zone.size;
    // 留 1cm 容差，避免浮点误差把贴墙站位判成舱外
    return (
      Math.abs(x - cx) <= sx / 2 + 0.01 && Math.abs(z - cz) <= sz / 2 + 0.01
    );
  });
}

/** 根据坐标解析当前所在舱室，供抬头显示器显示位置 */
export function zoneAt(x: number, z: number): RoomDef | CorridorDef | null {
  for (const zone of ALL_ZONES) {
    const [cx, cz] = zone.center;
    const [sx, sz] = zone.size;
    if (Math.abs(x - cx) <= sx / 2 + 0.01 && Math.abs(z - cz) <= sz / 2 + 0.01) {
      return zone;
    }
  }
  return null;
}

/** 舱室/走廊的显示名（走廊按方位命名） */
export function zoneLabel(zone: RoomDef | CorridorDef | null): string {
  if (!zone) return '舰外';
  if ('label' in zone) return zone.label;
  if ('code' in zone) return (zone as RoomDef).code;
  const names: Record<string, string> = {
    hub: '中央枢纽',
    'corridor-n': '前部走廊',
    'corridor-s': '后部走廊',
    'corridor-e': '右舷走廊',
    'corridor-w': '左舷走廊',
  };
  return names[zone.id] ?? '通道';
}
