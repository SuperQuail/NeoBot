// endpoints.ts —— 后端 /api/* 端点集中封装（返回类型来自 ./types）
import { getJSON, getResult, postJSON } from './client';
import type {
  ActiveUser,
  BotSummary,
  ChatFlowDetailPayload,
  ChatFlowsPayload,
  ConfigChanges,
  ConfigDocument,
  EnvPayload,
  ExtensionEntry,
  LogPayload,
  ModelsPayload,
  Overview,
  PluginListPayload,
  PromptAnalysisPayload,
  PromptPreviewPayload,
  PromptsPayload,
  ProxyInfo,
  RankPayload,
  Result,
  ScheduledTaskActionBody,
  ScheduledTasksPayload,
  SeriesPayload,
  SeriesPoint,
  ServiceItem,
  SystemInfo,
  TasksPayload,
  UsagePayload,
} from './types';

export interface SimpleMessage {
  message?: string;
  /** 保存/重载类接口会带回「已生效 / 需重启」明细 */
  changes?: ConfigChanges;
  ok?: boolean;
  key?: string;
  saved_key?: string;
  provider?: string;
  model_name?: string;
  url?: string;
  proxy?: string;
  reachable?: boolean;
  authorized?: boolean;
  model_found?: boolean;
  latency_ms?: number;
  status?: number;
  detail?: string;
  models?: string[];
  [key: string]: unknown;
}

/** 运行状态（/api/admin/power，待机 / 软重启） */
export interface PowerState {
  ok?: boolean;
  /** 待机服务不可用时为 false，其余字段可能缺省 */
  available?: boolean;
  state?: 'running' | 'standby';
  standby?: boolean;
  reason?: string;
  operator?: string;
  /** 进入待机的时间戳与可读文本 */
  since?: number;
  since_text?: string;
  standby_seconds?: number;
  /** 待机期间是否保持 OneBot 连接 */
  connect_onebot?: boolean;
  /** 写操作（待机 / 恢复 / 软重启 / OneBot）返回的提示文案 */
  message?: string;
}

export interface PluginConfigSaveBody {
  revision?: number;
  mode: 'form' | 'toml';
  reload?: boolean;
  source?: string;
  config?: Record<string, unknown>;
}

export type ConfigSaveBody = PluginConfigSaveBody;

export const api = {
  // 鉴权
  login: (password: string) => postJSON<{ token?: string; csrf_token?: string }>('/api/auth/login', { password }),
  setup: (password: string, confirm: string) =>
    postJSON<{ token?: string; csrf_token?: string }>('/api/auth/setup', { password, confirm }),
  logout: () => postJSON<SimpleMessage>('/api/auth/logout'),
  me: () => getResult<{ authenticated?: boolean }>('/api/auth/me'),

  // 概览 / 统计
  overview: () => getJSON<Overview>('/api/overview'),
  bots: () => getJSON<BotSummary[]>('/api/bots'),
  system: () => getJSON<SystemInfo>('/api/system'),
  services: () => getJSON<{ items?: ServiceItem[] }>('/api/services'),
  tasks: () => getJSON<TasksPayload>('/api/tasks'),
  botDetail: () => getJSON<BotSummary>('/api/bot/detail'),
  logs: (limit = 80) => getJSON<LogPayload>('/api/logs?limit=' + limit),
  logsSince: (since: number, limit = 500) => getJSON<LogPayload>('/api/logs?since=' + since + '&limit=' + limit),
  seriesMessages: (days = 30) => getJSON<SeriesPayload>('/api/series/messages?days=' + days),
  seriesLatency: () => getJSON<SeriesPayload>('/api/series/latency'),
  statsApiCalls: (limit = 10) => getJSON<RankPayload>('/api/stats/api-calls?limit=' + limit),
  statsActiveUsers: (limit = 10) =>
    getJSON<RankPayload & { items?: ActiveUser[] }>('/api/stats/active-users?limit=' + limit),
  statsUsage: (hours = 24) => getJSON<UsagePayload>('/api/stats/usage?hours=' + hours),
  seriesUsage: (hours = 24, bucket = 'hour') =>
    getResult<UsagePayload>('/api/series/usage?hours=' + hours + '&bucket=' + bucket),

  // 提示词分析
  analysisPrompts: () => getJSON<PromptAnalysisPayload>('/api/analysis/prompts'),

  // 提示词模板（data/prompts）
  prompts: () => getResult<PromptsPayload>('/api/prompts'),
  promptsPreview: (body: { template?: string; section?: string; path?: string; values?: Record<string, string> }) =>
    postJSON<PromptPreviewPayload>('/api/prompts/preview', body),
  promptsSave: (body: { section: string; path: string; value: string }) =>
    postJSON<SimpleMessage>('/api/prompts/save', body),
  promptsReset: (body: { section: string; path: string }) =>
    postJSON<SimpleMessage>('/api/prompts/reset', body),

  // 聊天流（最近一次发给模型的内容 + 后台任务）
  chatFlows: () => getJSON<ChatFlowsPayload>('/api/chat-flows'),
  chatFlowDetail: (key: string) =>
    getJSON<ChatFlowDetailPayload>('/api/chat-flows/detail?key=' + encodeURIComponent(key)),

  // 定时任务管理
  scheduledTasks: (includeDisabled = true, limit = 200) =>
    getJSON<ScheduledTasksPayload>(
      '/api/scheduled-tasks?include_disabled=' + (includeDisabled ? '1' : '0') + '&limit=' + limit,
    ),
  scheduledTaskAction: (body: ScheduledTaskActionBody) =>
    postJSON<SimpleMessage>('/api/scheduled-tasks/action', body),

  // 面板 HTTP 扩展（依赖面板的插件挂载的页面入口）
  extensions: () => getJSON<{ items?: ExtensionEntry[] }>('/api/extensions'),

  // 插件
  plugins: () => getJSON<PluginListPayload>('/api/plugins'),
  pluginToggle: (name: string) => postJSON<SimpleMessage>('/api/plugins/' + encodeURIComponent(name) + '/toggle'),
  pluginReload: (name: string) => postJSON<SimpleMessage>('/api/plugins/' + encodeURIComponent(name) + '/reload'),
  pluginUpdate: (name: string) => postJSON<SimpleMessage>('/api/plugins/' + encodeURIComponent(name) + '/update'),
  pluginUninstall: (name: string) =>
    postJSON<SimpleMessage>('/api/plugins/' + encodeURIComponent(name) + '/uninstall'),
  pluginInstall: (repo: string, branch = 'main', replace = false) =>
    postJSON<SimpleMessage>('/api/plugins/install', { repo, branch, replace }),
  pluginsCheckUpdates: () => getResult<SimpleMessage>('/api/plugins/check-updates'),
  pluginsProxySave: (body: ProxyInfo) => postJSON<{ proxy?: ProxyInfo }>('/api/plugins/proxy', body),
  pluginConfig: (name: string) => getResult<ConfigDocument>('/api/plugins/' + encodeURIComponent(name) + '/config'),
  pluginConfigSave: (name: string, body: PluginConfigSaveBody) =>
    postJSON<ConfigDocument>('/api/plugins/' + encodeURIComponent(name) + '/config', body),

  // 本体配置 / 环境变量 / 模型
  config: () => getResult<ConfigDocument>('/api/config'),
  configSave: (body: ConfigSaveBody) => postJSON<ConfigDocument>('/api/config', body),
  configValidate: (body: ConfigSaveBody) =>
    postJSON<{ errors?: Array<{ path?: string; message?: string }> }>('/api/config/validate', body),
  configReload: () => postJSON<SimpleMessage>('/api/config/reload'),
  configModels: () => getResult<ModelsPayload>('/api/config/models'),
  modelsLibrarySave: (body: unknown) => postJSON<ModelsPayload>('/api/config/models/library', body),
  modelsAssignmentsSave: (body: unknown) => postJSON<ModelsPayload>('/api/config/models/assignments', body),
  modelsTest: (body: unknown) =>
    postJSON<{
      ok?: boolean;
      key?: string;
      provider?: string;
      model_name?: string;
      url?: string;
      proxy?: string;
      reachable?: boolean;
      authorized?: boolean;
      model_found?: boolean;
      latency_ms?: number;
      status?: number;
      detail?: string;
      message?: string;
      [k: string]: unknown;
    }>('/api/config/models/test', body),
  modelsProviderModels: (body: unknown) =>
    postJSON<{ ok?: boolean; models?: string[]; message?: string; provider?: string }>(
      '/api/config/models/provider-models',
      body,
    ),
  env: () => getResult<EnvPayload>('/api/config/env'),
  envSave: (body: unknown) => postJSON<EnvPayload>('/api/config/env', body),
  envAddPlatform: (body: unknown) => postJSON<EnvPayload>('/api/config/env/platform', body),

  // 运行状态（待机 / 软重启运行）
  powerStatus: () => getJSON<PowerState>('/api/admin/power'),
  standbyEnter: (reason = '') => postJSON<PowerState>('/api/admin/standby', { reason }),
  resume: (reason = '') => postJSON<PowerState>('/api/admin/resume', { reason }),
  reboot: (reason = '') => postJSON<PowerState>('/api/admin/reboot', { reason }),
  setStandbyOnebot: (enabled: boolean) => postJSON<PowerState>('/api/admin/standby/onebot', { enabled }),

  // 管理（重启进程以加载代码改动）
  restart: () => postJSON<SimpleMessage>('/api/admin/restart'),
};

export type Api = typeof api;
export type { Result, SeriesPoint };
