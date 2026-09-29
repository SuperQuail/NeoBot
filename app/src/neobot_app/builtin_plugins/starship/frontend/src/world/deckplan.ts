/** Deliberately small inhabited enclave on a much larger ark. World units are metres.
 * New sectors must declare bounds, a walkable connection and station clearances here.
 * The surrounding 74.4 km hull is scenery, NOT an implicit walkable deck. */
export const ROOM_HEIGHT = 18;
export interface StationSpec {
  id: string; room: string; offset: [number, number]; yaw: number;
  label: string; hint: string; kind: 'terminal' | 'minigame' | 'prop'; target: string;
}
export interface SectorSpec {
  id: string; label: string; description: string;
  bounds: [number, number, number, number];
}
export const SECTORS: SectorSpec[] = [
  { id: 'bridge', label: '01 / 星穹舰桥', description: '灵能护盾穹顶 · 指挥与航行', bounds: [-24, 24, -42, 0] },
  { id: 'corridor', label: '中轴光廊', description: '前往机械铸造厂', bounds: [-5, 5, 0, 14] },
  { id: 'war-forge', label: '02 / 战争机械装配车间', description: '重型四足机体 · 铸造与武备', bounds: [-32, -5.5, 14, 58] },
  { id: 'robot-forge', label: '03 / 机器人装配车间', description: '灵能核心 · 机器人与神经矩阵', bounds: [5.5, 32, 14, 58] },
  { id: 'foundry-axis', label: '铸造厂中轴', description: '侧门通向独立车间 · 主路通向太阳核心', bounds: [-5.5, 5.5, 14, 58] },
  { id: 'rear-corridor', label: '恒星光廊', description: '连续米制通道 · 核心舱入口', bounds: [-6, 6, 58, 78] },
  { id: 'reactor', label: '04 / 太阳核心室', description: '太阳核心约束舱 · 星舰供能中枢', bounds: [-18, 18, 78, 118] },
  { id: 'archive-link', label: '记忆连廊', description: '太阳核心与资料室的实体连接', bounds: [18, 22, 82, 90] },
  { id: 'archive', label: '05 / 记忆资料室', description: '水晶档案 · 舰载配置与航行日志', bounds: [22, 54, 74, 106] },
];
export const EXPANSION_SECTORS = [
  // Only genuinely inaccessible future sectors belong here; reactor/archive are inhabited.
  { id: 'aft-vault', label: '后部封存舱', status: 'sealed', z: 118 },
  { id: 'hangar', label: '远征机库', status: 'sealed', z: 410 },
] as const;
export const STATIONS: StationSpec[] = [
  { id: 'bridge-main', room: 'bridge', offset: [0, 4], yaw: 0, label: '星图仪', hint: '选择航点 / 启动灵能跃迁', kind: 'prop', target: 'navigation' },
  { id: 'bridge-nav', room: 'bridge', offset: [0, -11], yaw: 0, label: '指挥核心', hint: '舰船总览与实时指标', kind: 'terminal', target: 'dashboard' },
  { id: 'bridge-config', room: 'archive', offset: [-8, 10], yaw: Math.PI, label: '舰载系统', hint: '配置与权限', kind: 'terminal', target: 'config' },
  { id: 'bridge-logs', room: 'archive', offset: [8, 10], yaw: Math.PI, label: '记忆水晶', hint: '航行日志', kind: 'terminal', target: 'logs' },
  { id: 'eng-reactor', room: 'reactor', offset: [-12, 0], yaw: Math.PI / 2, label: '太阳核心终端', hint: '系统状态与资源', kind: 'terminal', target: 'system' },
  { id: 'eng-power', room: 'reactor', offset: [12, 0], yaw: -Math.PI / 2, label: '能量调谐器', hint: '模型用量与开销', kind: 'terminal', target: 'usage' },
  { id: 'eng-repair', room: 'war-forge', offset: [9.75, 13], yaw: Math.PI / 2, label: '损管演练', hint: '机械回路抢修', kind: 'minigame', target: 'repair' },
  { id: 'robot-comms', room: 'robot-forge', offset: [-9.75, -14], yaw: -Math.PI / 2, label: '机器人中枢', hint: '机器人与会话状态', kind: 'terminal', target: 'bots' },
  { id: 'robot-modules', room: 'robot-forge', offset: [-9.75, 0], yaw: -Math.PI / 2, label: '装配矩阵', hint: '插件模块装载与启停', kind: 'terminal', target: 'plugins' },
  { id: 'robot-matrix', room: 'robot-forge', offset: [-9.75, 13], yaw: -Math.PI / 2, label: '神经水晶', hint: '提示词与 Agent 分析', kind: 'terminal', target: 'analysis' },
  { id: 'bridge-turret', room: 'bridge', offset: [17, 14], yaw: 0, label: '武备演练', hint: '舱外炮塔', kind: 'minigame', target: 'turret' },
  { id: 'bridge-scores', room: 'bridge', offset: [-17, 14], yaw: 0, label: '远征战绩', hint: '演练排行榜', kind: 'terminal', target: 'scores' },
];
