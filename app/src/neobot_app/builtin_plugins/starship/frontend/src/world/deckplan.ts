// world/deckplan.ts —— 飞船布局数据（甲板网格 + 舱室定义 + 终端站位）。
// 网格化布局：每个字符代表一个 4m×4m 单元格，房间靠相邻关系自动开门，
// 因此布局改一个字符，几何、碰撞、导航提示会一起更新。

export const CELL = 4;
export const COLS = 30;
export const ROWS = 10;
/** 三层甲板的地板高度（米） */
export const DECK_Y = [0, 4.4, 8.8];
/** 舱室净高 */
export const ROOM_HEIGHT = 3.6;
/** 走廊/舱室墙厚的一半 */
export const WALL_THICKNESS = 0.18;

export interface DeckPlan {
  name: string;
  y: number;
  rows: string[];
}

/** 甲板字符 -> 舱室 id */
export const ROOM_LEGEND: Record<string, string> = {
  E: 'engineering',
  H: 'hangar',
  G: 'cargo',
  B: 'bridge',
  K: 'lounge',
  D: 'medbay',
  S: 'science',
  A: 'archive',
  M: 'command',
  O: 'observation',
  c: 'corridor',
};

export interface RoomInfo {
  /** 舱室 id（legend 里的值，同名字符会合并成同一个房间） */
  id: string;
  label: string;
  description: string;
  /** 该舱室是否是「有舷窗」的观景舱 */
  windows: boolean;
}

export const ROOMS: Record<string, RoomInfo> = {
  bridge: {
    id: 'bridge',
    label: '舰桥',
    description: '全舰指挥中枢，主控台与通讯台都在这里。',
    windows: true,
  },
  corridor: { id: 'corridor', label: '主走廊', description: '连接各舱室的通道。', windows: false },
  engineering: {
    id: 'engineering',
    label: '工程舱',
    description: '反应堆、能量分配与插件模块机架。',
    windows: false,
  },
  hangar: {
    id: 'hangar',
    label: '机库',
    description: '舰载机与损管设备停放区，兼作抢修训练场。',
    windows: true,
  },
  cargo: { id: 'cargo', label: '货舱', description: '补给与舰船战绩档案。', windows: false },
  lounge: { id: 'lounge', label: '休息厅', description: '船员休息区：咖啡机与点唱机。', windows: true },
  medbay: { id: 'medbay', label: '医务室', description: '生命体征与舰员健康监控。', windows: true },
  science: { id: 'science', label: '科学舱', description: '神经矩阵与提示词分析仪。', windows: false },
  archive: { id: 'archive', label: '档案舱', description: '航行日志与历史记录。', windows: true },
  command: { id: 'command', label: '指挥室', description: '舰载系统配置与权限管理。', windows: true },
  observation: {
    id: 'observation',
    label: '观景廊',
    description: '全舰视野最好的地方，也是舷侧炮塔的操炮位。',
    windows: true,
  },
};

const DECK_0 = [
  '##############################',
  '#............................#',
  '#EEEEEEEEE........HHHHHHHHHH.#',
  '#EEEEEEEEE........HHHHHHHHHH.#',
  '#EEEEEEEEEccccccccHHHHHHHHHH.#',
  '#EEEEEEEEE........HHHHHHHHHH.#',
  '#EEEEEEEEE........HHHHHHHHHH.#',
  '#....GGGGGGGGGGGGGGGGGGGG....#',
  '#............................#',
  '##############################',
];

const DECK_1 = [
  '##############################',
  '#............................#',
  '#BBBBBBBBBBB..........KKKKKKK#',
  '#BBBBBBBBBBB..........KKKKKKK#',
  '#BBBBBBBBBBBccccccccccccccccc#',
  '#BBBBBBBBBBB..........DDDDDDD#',
  '#BBBBBBBBBBB..........DDDDDDD#',
  '#............................#',
  '#............................#',
  '##############################',
];

const DECK_2 = [
  '##############################',
  '#............................#',
  '#SSSSSSSSSS.......AAAAAAAAAAA#',
  '#SSSSSSSSSS.......AAAAAAAAAAA#',
  '#cccccccccccccccccccccccccccc#',
  '#MMMMMMMMMMOOOOOOOOOOOOOOOOOO#',
  '#MMMMMMMMMMOOOOOOOOOOOOOOOOOO#',
  '#............................#',
  '#............................#',
  '##############################',
];

export const DECKS: DeckPlan[] = [
  { name: '工程甲板', y: DECK_Y[0], rows: DECK_0 },
  { name: '主甲板', y: DECK_Y[1], rows: DECK_1 },
  { name: '科学甲板', y: DECK_Y[2], rows: DECK_2 },
];

/** 竖向连接：同一 (col,row) 处两层甲板之间的爬梯 */
export interface LadderSpec {
  col: number;
  row: number;
  fromDeck: number;
  toDeck: number;
}

export const LADDERS: LadderSpec[] = [
  { col: 10, row: 4, fromDeck: 0, toDeck: 1 },
  { col: 25, row: 5, fromDeck: 0, toDeck: 1 },
  { col: 13, row: 4, fromDeck: 1, toDeck: 2 },
  { col: 24, row: 4, fromDeck: 1, toDeck: 2 },
];

/** 终端 / 互动点在舱室内的相对位置（相对舱室中心，单位米） */
export interface StationSpec {
  id: string;
  room: string;
  /** 相对舱室中心的偏移 */
  offset: [number, number];
  /** 朝向（弧度，0 = 面向 -Z，PI/2 = 面向 -X …） */
  yaw: number;
  label: string;
  hint: string;
  kind: 'terminal' | 'minigame' | 'prop';
  /** terminal: 菜单 id；minigame: 小游戏 id；prop: 互动内容 id */
  target: string;
}

export const STATIONS: StationSpec[] = [
  // 舰桥
  { id: 'bridge-main', room: 'bridge', offset: [-7, -4.5], yaw: -Math.PI / 2, label: '主控台', hint: '舰船总览与实时指标', kind: 'terminal', target: 'dashboard' },
  { id: 'bridge-comms', room: 'bridge', offset: [-7, 4.5], yaw: -Math.PI / 2, label: '通讯台', hint: '机器人与会话状态', kind: 'terminal', target: 'bots' },
  { id: 'bridge-nav', room: 'bridge', offset: [-13.5, 0], yaw: Math.PI / 2, label: '星图导航台', hint: '设定航线 / 触发跃迁', kind: 'prop', target: 'navigation' },
  { id: 'bridge-captain', room: 'bridge', offset: [10, 0], yaw: Math.PI / 2, label: '舰长席', hint: '坐下观察全舰', kind: 'prop', target: 'captain-chair' },
  // 休息厅
  { id: 'lounge-coffee', room: 'lounge', offset: [-4, -3], yaw: 0, label: '咖啡机', hint: '来一杯舰载合成咖啡', kind: 'prop', target: 'coffee' },
  { id: 'lounge-jukebox', room: 'lounge', offset: [4, 3], yaw: 0, label: '点唱机', hint: '播放一段合成音律', kind: 'prop', target: 'jukebox' },
  // 医务室
  { id: 'medbay-vitals', room: 'medbay', offset: [-6, 0], yaw: -Math.PI / 2, label: '生命体征仪', hint: '舰体资源与进程状态', kind: 'prop', target: 'vitals' },
  { id: 'medbay-kit', room: 'medbay', offset: [5, 0], yaw: Math.PI / 2, label: '医疗补给柜', hint: '补齐随身物资', kind: 'prop', target: 'supplies' },
  // 工程舱
  { id: 'eng-reactor', room: 'engineering', offset: [-13, 0], yaw: -Math.PI / 2, label: '反应堆监控', hint: '系统资源与进程', kind: 'terminal', target: 'system' },
  { id: 'eng-power', room: 'engineering', offset: [0, -6], yaw: 0, label: '能量分配', hint: '模型用量与开销', kind: 'terminal', target: 'usage' },
  { id: 'eng-racks', room: 'engineering', offset: [0, 6], yaw: Math.PI, label: '模块机架', hint: '插件装载与启停', kind: 'terminal', target: 'plugins' },
  { id: 'eng-repair', room: 'engineering', offset: [13, 0], yaw: Math.PI / 2, label: '损管终端', hint: '进入损管抢修演练', kind: 'minigame', target: 'repair' },
  // 机库
  { id: 'hangar-turret', room: 'hangar', offset: [0, -7], yaw: 0, label: '炮塔模拟器', hint: '进入舱外炮塔演练', kind: 'minigame', target: 'turret' },
  { id: 'hangar-crate', room: 'hangar', offset: [10, 6], yaw: 0, label: '补给箱', hint: '检查舰载补给', kind: 'prop', target: 'supplies' },
  // 货舱
  { id: 'cargo-scores', room: 'cargo', offset: [0, 0], yaw: 0, label: '战绩墙', hint: '小游戏排行榜与成就', kind: 'terminal', target: 'scores' },
  // 科学舱
  { id: 'sci-matrix', room: 'science', offset: [0, 0], yaw: 0, label: '神经矩阵', hint: '提示词与 Agent 分析', kind: 'terminal', target: 'analysis' },
  // 档案舱
  { id: 'archive-logs', room: 'archive', offset: [0, -3], yaw: 0, label: '航行日志', hint: '实时运行日志', kind: 'terminal', target: 'logs' },
  // 指挥室
  { id: 'command-config', room: 'command', offset: [0, -4], yaw: 0, label: '舰载系统配置', hint: '本体配置与环境变量', kind: 'terminal', target: 'config' },
  // 观景廊
  { id: 'obs-turret', room: 'observation', offset: [16, 2], yaw: Math.PI, label: '舷侧炮塔', hint: '进入舱外炮塔演练', kind: 'minigame', target: 'turret' },
  { id: 'obs-scope', room: 'observation', offset: [-6, 1], yaw: 0, label: '天文望远镜', hint: '观察舰外天体', kind: 'prop', target: 'telescope' },
];

/** 出生点（舰桥中央，面向舰艏） */
export const SPAWN = { deck: 1, room: 'bridge', offset: [4, 0], yaw: Math.PI / 2 };

export function cellX(col: number): number {
  return (col - COLS / 2) * CELL;
}

export function cellZ(row: number): number {
  return (row - ROWS / 2) * CELL;
}

export function cellCenter(col: number, row: number): [number, number] {
  return [cellX(col) + CELL / 2, cellZ(row) + CELL / 2];
}

/** 取某个字符串行的字符（越界返回 '#'） */
export function cellAt(deck: DeckPlan, col: number, row: number): string {
  if (row < 0 || row >= deck.rows.length) return '#';
  const line = deck.rows[row] ?? '';
  if (col < 0 || col >= line.length) return '#';
  return line[col];
}

export function isWalkable(ch: string): boolean {
  return ch !== '#' && ch !== '.' && ch !== ' ';
}
