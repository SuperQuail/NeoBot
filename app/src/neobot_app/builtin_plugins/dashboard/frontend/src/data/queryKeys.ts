// data/queryKeys.ts —— 查询 key 与轮询周期的唯一来源
// 目的：所有页面用同一组 key，才能共享缓存与去重；
// 轮询周期集中在这里，避免每个页面各写一个魔法数字。
export const QK = {
  overview: 'overview',
  system: 'system',
  bots: 'bots',
  botDetail: 'bot-detail',
  services: 'services',
  tasks: 'tasks',
  logs: 'logs',
  latency: 'series:latency',
  messages: 'series:messages',
  apiCalls: 'stats:api-calls',
  activeUsers: 'stats:active-users',
  usage: 'stats:usage',
  usageSeries: 'series:usage',
  analysis: 'analysis:prompts',
  plugins: 'plugins',
  power: 'admin:power',
  pluginConfig: (id: string) => `plugin-config:${id}`,
  config: 'config',
  env: 'env',
  models: 'models',
} as const;

/** 轮询节奏（毫秒）：沿用改造前各页的既有节奏，只是收敛到一处 */
export const POLL = {
  /** 概览：10s */
  overview: 10_000,
  /** 系统资源：3s（Dashboard）/5s（System）→ 统一 5s，两页共享同一份数据 */
  system: 5_000,
  /** 机器人列表：10s */
  bots: 10_000,
  /** 机器人详情与延迟：10s */
  botDetail: 10_000,
  /** 服务与任务：30s / 15s */
  services: 30_000,
  tasks: 15_000,
  /** 最近日志：5s */
  logs: 5_000,
  /** 消息趋势：30s（Dashboard）/60s（Bots）→ 统一 60s */
  messages: 60_000,
  /** 排行：10s / 60s */
  apiCalls: 10_000,
  activeUsers: 60_000,
  /** 用量统计：60s */
  usage: 60_000,
  /** 提示词分析：30s */
  analysis: 30_000,
  /** 插件列表：20s */
  plugins: 20_000,
  /** 运行状态：5s（待机状态变化要能马上看到） */
  power: 5_000,
  /** 配置类：不轮询（由用户主动刷新） */
  none: 0,
} as const;
