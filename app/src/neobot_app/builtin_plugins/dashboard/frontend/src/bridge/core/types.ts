// types.ts —— 舰载控制台的功能契约
//
// 3D 场景（ship.ts）、交互层、全息面板（ui/panels）与存档（store.ts）共用。
// 所有面板都是真实数据面板：数据一律来自 src/api/endpoints.ts，不接假数据。

import type { Vec3 } from './layout';

/** 控制台编号 —— 与舰内实体终端一一对应 */
export type PanelId =
  | 'overview'
  | 'comms'
  | 'nav'
  | 'power'
  | 'mainframe'
  | 'flight'
  | 'drydock'
  | 'firecontrol';

/** 舰内可交互站位的定义 */
export interface Station {
  id: PanelId;
  /** 终端型号名，全息面板抬头显示 */
  terminal: string;
  /** 舰内编号牌 */
  code: string;
  /** 中文名 */
  label: string;
  /** 面板标题（抬头第二行） */
  title: string;
  /** 站位坐标（玩家走到附近可交互） */
  anchor: Vec3;
  /** 终端朝向：0=+z, π=-z, π/2=+x, -π/2=-x（面朝玩家的一侧） */
  facing: number;
  /** 该终端读取的舰载系统名，用于交互提示 */
  subsystem: string;
  /**
   * 终端**屏幕**平面的世界坐标（全息面板就贴在这里，不是贴在站位锚点上）。
   *
   * 这两个点的区别是「面板像不像场景里的一部分」的关键：
   * 站位锚点在终端机身中心，玩家为了交互本来就得站在它正前方，
   * 于是面板一出现就顶在脸正中间 —— 看起来就是个屏幕 UI。
   * 屏幕点偏在机身靠外一侧，面板因此会明显偏向一侧，需要转头去看，
   * 才像「悬浮在终端上方的一块投影」。
   *
   * 取值与 ship.ts 的 consoleSpecs 一致（同一批坐标），改动需同步。
   */
  screen: Vec3;
  /** 屏幕平面的朝向（与 facing 同义，独立列出便于单独微调） */
  screenYaw: number;
  /** 终端屏幕的物理尺寸（米），面板按它等比放大后贴上去 */
  screenSize: { width: number; height: number };
}

/**
 * 站位表。坐标按 layout.ts 的舱壁位置校对，规则是：
 *   · 舱壁内表面 = 舱室矩形边界；终端中心离最近的内表面 1.1~1.4m（既不穿墙也不悬在舱中央）；
 *   · `facing` 指终端屏幕的朝向，玩家必须站在它的正面才能接入；
 *   · 每个 anchor 都必须落在对应舱室/走廊的地板矩形内（bridge.test.tsx 有回归用例守住这条）。
 * 名称、编号与 facing 之间的对应关系改动时请一并更新测试。
 */
export const STATIONS: Station[] = [
  {
    id: 'overview',
    terminal: 'COMMAND CONSOLE',
    code: 'CMD-01',
    label: '指挥台',
    title: '舰况总览',
    // 舰桥北墙内表面 z=-30，指挥台朝 +z（玩家站在 z>-29.2 一侧）
    anchor: [0, 0, -29.2],
    facing: 0,
    subsystem: '指挥与控制系统',
    screen: [0, 1.32, -29.06],
    screenYaw: 0,
    screenSize: { width: 1.6, height: 0.62 },
  },
  {
    id: 'comms',
    terminal: 'COMMS ARRAY',
    code: 'COM-02',
    label: '通讯阵列终端',
    title: '航行日志',
    // 舰桥西墙内表面 x=-12
    anchor: [-11, 0, -23],
    facing: Math.PI / 2,
    subsystem: '通讯与日志阵列',
    screen: [-11, 1.38, -22.7],
    screenYaw: Math.PI / 2,
    screenSize: { width: 0.92, height: 0.5 },
  },
  {
    id: 'nav',
    terminal: 'NAV PLOTTER',
    code: 'NAV-03',
    label: '星图导航台',
    title: '星图与航迹',
    // 舰桥东墙内表面 x=+12
    anchor: [11, 0, -24],
    facing: -Math.PI / 2,
    subsystem: '星图与航迹推算',
    screen: [11, 1.22, -23.26],
    screenYaw: -Math.PI / 2,
    screenSize: { width: 0.8, height: 0.44 },
  },
  {
    id: 'power',
    terminal: 'POWER CORE',
    code: 'PWR-04',
    label: '反应堆控制台',
    title: '能源分配',
    // 工程舱东墙内表面 x=+38，反应堆控制台朝舱内（-x）
    anchor: [36.9, 0, 0],
    facing: -Math.PI / 2,
    subsystem: '反物质反应堆',
    screen: [36.9, 1.55, 0.24],
    screenYaw: -Math.PI / 2,
    screenSize: { width: 1.0, height: 0.55 },
  },
  {
    id: 'mainframe',
    terminal: 'MAINFRAME',
    code: 'CPU-05',
    label: '主机机柜',
    title: '模块管理',
    // 货舱西墙内表面 x=-38
    anchor: [-36.9, 0, -2],
    facing: Math.PI / 2,
    subsystem: '舰载主机机群',
    screen: [-36.9, 1.62, -1.54],
    screenYaw: Math.PI / 2,
    screenSize: { width: 0.86, height: 0.42 },
  },
  {
    id: 'flight',
    terminal: 'FLIGHT DECK',
    code: 'FLT-06',
    label: '飞行甲板终端',
    title: '舰载单位',
    // 机库南墙内表面 z=+33
    anchor: [-10, 0, 31.9],
    facing: 0,
    subsystem: '舰载机与僚机编队',
    screen: [-10, 1.18, 32.12],
    screenYaw: 0,
    screenSize: { width: 1.1, height: 0.56 },
  },
  {
    id: 'drydock',
    terminal: 'DRYDOCK',
    code: 'DCK-07',
    label: '船坞调配台',
    title: '补给与装载',
    anchor: [10, 0, 31.9],
    facing: 0,
    subsystem: '船坞与补给调度',
    screen: [10, 1.3, 32.02],
    screenYaw: 0,
    screenSize: { width: 1.2, height: 0.6 },
  },
  {
    id: 'firecontrol',
    terminal: 'FIRE CONTROL',
    code: 'WPN-08',
    label: '火控台',
    title: '舰炮管制',
    // 机库北墙内表面 z=+17（靠舱内一侧），火控台朝 +z
    anchor: [0, 0, 18.1],
    facing: Math.PI,
    subsystem: '近防炮与护盾',
    screen: [0, 1.16, 18.22],
    screenYaw: Math.PI,
    screenSize: { width: 1.0, height: 0.52 },
  },
];

export const STATION_BY_ID: Record<PanelId, Station> = Object.fromEntries(
  STATIONS.map((station) => [station.id, station]),
) as Record<PanelId, Station>;

/** 舰况四项指标 —— 直接绑定真实运行数据，让舰体状态会随系统负载变化 */
export type VitalKey = 'energy' | 'atmosphere' | 'hull' | 'heat';

export interface Vital {
  key: VitalKey;
  label: string;
  /** 0~100 */
  value: number;
  /** 单位后缀，如 % */
  unit: string;
  /** 数据来源说明，显示在提示里 */
  source: string;
}

/** 舰载物资清单（探索收集） */
export type ItemId = 'power-cell' | 'coolant' | 'alloy' | 'data-core' | 'medkit';

export interface ItemDef {
  id: ItemId;
  name: string;
  hint: string;
  /** 每份物资为舰体恢复的数值 */
  restore: Partial<Record<VitalKey, number>>;
}

export const ITEMS: Record<ItemId, ItemDef> = {
  'power-cell': {
    id: 'power-cell',
    name: '能量电池',
    hint: '为反应堆补充一次脉冲，提升能源储备',
    restore: { energy: 18 },
  },
  coolant: {
    id: 'coolant',
    name: '冷却剂罐',
    hint: '给主机回路降温',
    restore: { heat: -22, energy: 4 },
  },
  alloy: {
    id: 'alloy',
    name: '装甲合金板',
    hint: '修补舰体外壳',
    restore: { hull: 20 },
  },
  'data-core': {
    id: 'data-core',
    name: '数据核心',
    hint: '恢复生命保障系统的运行参数',
    restore: { atmosphere: 16 },
  },
  medkit: {
    id: 'medkit',
    name: '医疗包',
    hint: '恢复生命值',
    restore: {},
  },
};

export const ITEM_IDS = Object.keys(ITEMS) as ItemId[];

/** 小游戏记录：用于舰内排行榜与成就 */
export interface MiniGameRecord {
  best: number;
  plays: number;
  lastAt: number;
}

export interface ShipLog {
  version: number;
  /** 已访问过的终端（首次访问播放解锁提示） */
  visited: PanelId[];
  /** 已收集物资 */
  inventory: Partial<Record<ItemId, number>>;
  /** 已解锁成就 id */
  achievements: string[];
  miniGames: Record<string, MiniGameRecord>;
  /** 累计在舰内行走的米数，用于「航程」统计 */
  distance: number;
  lastPos: Vec3 | null;
}

/** 成就定义：交互过程中逐步点亮，提供正反馈 */
export interface AchievementDef {
  id: string;
  name: string;
  hint: string;
}

export const ACHIEVEMENTS: AchievementDef[] = [
  { id: 'boarded', name: '登舰', hint: '进入 NeoBot 号并完成舰载引导' },
  { id: 'all-terminals', name: '全系统在线', hint: '访问全部 8 座控制终端' },
  { id: 'first-repair', name: '损管员', hint: '完成一次断路器修复' },
  { id: 'turret-ace', name: '近防王牌', hint: '在舰炮演习中击毁 15 个以上目标' },
  { id: 'cargo-master', name: '装载长', hint: '在货舱调度中拿到 300 分以上' },
  { id: 'collector', name: '拾荒者', hint: '收集 10 件舰载物资' },
  { id: 'systems-nominal', name: '全舰正常', hint: '让四项舰况全部回到 80% 以上' },
];
