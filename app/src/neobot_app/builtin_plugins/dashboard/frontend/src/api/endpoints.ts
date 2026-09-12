// endpoints.ts —— 后端 /api/* 端点集中封装（返回类型来自 ./types）
import { deleteJSON, getJSON, getResult, postJSON, putJSON } from './client';
import type {
  ActiveUser,
  ArchiveDeleteBody,
  ArchiveItemDetail,
  ArchiveItemQuery,
  ArchiveItemsPayload,
  ArchiveUpdateBody,
  ArchivesPayload,
  BotSummary,
  ChatFlowDetailPayload,
  ChatFlowLatestPrompt,
  ChatFlowPromptEntry,
  ChatFlowPromptMeta,
  ChatFlowPromptPayload,
  ChatFlowPromptsPayload,
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

/** 完整提示词历史的过滤参数（空串 = 全部聊天流） */
const promptsPath = (key: string): string =>
  '/api/chat-flows/prompts' + (key ? '?key=' + encodeURIComponent(key) : '');

/** 档案列表查询串：只带上非空条件，避免把空筛选写进 URL */
export function archiveItemsQuery(query: ArchiveItemQuery): string {
  const params = new URLSearchParams();
  params.set('table', query.table);
  if (query.keyQuery) params.set('key_query', query.keyQuery);
  if (query.valueQuery) params.set('value_query', query.valueQuery);
  if (query.tags) params.set('tags', query.tags);
  params.set('limit', String(query.limit ?? 50));
  params.set('offset', String(query.offset ?? 0));
  if (query.overLimitOnly) params.set('over_limit', '1');
  return params.toString();
}

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

  // 完整提示词历史（spec(3)：列表只给元数据，正文按需读取、不截断）
  chatFlowPrompts: (key = '') => getJSON<ChatFlowPromptsPayload>(promptsPath(key)),
  chatFlowPrompt: (seq: number) =>
    getJSON<ChatFlowPromptPayload>('/api/chat-flows/prompt?seq=' + encodeURIComponent(String(seq))),
  chatFlowPromptClear: () => postJSON<SimpleMessage>('/api/chat-flows/prompts/clear'),
  /**
   * 默认视图：一次拿到元数据列表**和**最新一份全文（列表接口不返回正文）。
   * 这样进入页面 / 切换聊天流时只读一次盘；切换到历史里的其它份才走 chatFlowPrompt。
   */
  chatFlowPromptLatest: async (key = ''): Promise<ChatFlowLatestPrompt | null> => {
    const list = await getJSON<ChatFlowPromptsPayload>(promptsPath(key));
    if (!list) return null;
    const items = list.items || [];
    const latest = items.length > 0 ? items[items.length - 1] : null;
    const limit = Number(list.limit || 0);
    if (!latest || latest.seq === undefined || latest.seq === null) {
      return { items, limit, seq: null, entry: null };
    }
    const payload = await getJSON<ChatFlowPromptPayload>(
      '/api/chat-flows/prompt?seq=' + encodeURIComponent(String(latest.seq)),
    );
    return {
      items,
      limit,
      seq: latest.seq,
      entry: (payload && payload.ok !== false ? payload.entry : null) ?? null,
    };
  },

  // 档案管理（spec(2)：把模型侧的档案 CRUD 暴露到面板）
  archives: () => getJSON<ArchivesPayload>('/api/archives'),
  archiveItems: (query: ArchiveItemQuery) =>
    getJSON<ArchiveItemsPayload>('/api/archives/items?' + archiveItemsQuery(query)),
  archiveItem: (table: string, key: string) =>
    getResult<ArchiveItemDetail>(
      '/api/archives/item?table=' + encodeURIComponent(table) + '&key=' + encodeURIComponent(key),
    ),
  /** 编辑档案（乐观锁：版本不一致时后端返回 409 + current 内容） */
  archiveUpdate: (body: ArchiveUpdateBody) => putJSON<ArchiveItemDetail>('/api/archives/item', body),
  /** 删除档案（硬删除；需要 X-CSRF-Token 与面板开关 allow_archive_delete） */
  archiveDelete: (body: ArchiveDeleteBody) => deleteJSON<SimpleMessage>('/api/archives/item', body),

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
export type { ChatFlowPromptEntry, ChatFlowPromptMeta, Result, SeriesPoint };
