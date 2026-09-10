// 面板 API 契约类型 —— 与 dashboard/api.py 的响应结构一一对应。
// 约定：后端字段改动时先改这里，TS 会在编译期把所有受影响的前端调用点标出来。
// （后续可用 scripts/export_panel_types.py 从后端 schema 自动生成，见改造计划 P1-4）

/** getResult 的返回值：带 HTTP 状态码，编辑器需要区分校验失败与网络错误 */
export interface Result<T> {
  ok: boolean;
  data: T | null;
  error: string | null;
  status: number;
}

/** 系统信息快照 /api/system */
export interface SystemInfo {
  hostname?: string;
  os?: string;
  python_version?: string;
  pid?: number;
  cpu_percent?: number;
  cpu_count?: number;
  mem_percent?: number;
  mem_used_mb?: number;
  mem_total_mb?: number;
  process_memory_mb?: number;
  process_threads?: number;
  disk_percent?: number;
  disk_used_gb?: number;
  disk_total_gb?: number;
  load_average?: number[];
}

/** 概览 /api/overview */
export interface Overview {
  online?: boolean;
  app_name?: string;
  app_version?: string;
  uptime_seconds?: number;
  today_messages?: number;
  total_messages?: number;
  plugins_loaded?: number;
  plugins_total?: number;
  bot_nickname?: string;
  bot_user_id?: string | number;
}

/** 机器人 /api/bots 与 /api/bot/detail */
export interface BotSummary {
  user_id?: string | number;
  name?: string;
  nickname?: string;
  platform?: string;
  avatar_initial?: string;
  avatar_url?: string;
  status?: string;
  online?: boolean;
  latency_ms?: number;
  today_messages?: number;
  total_messages?: number;
  uptime_seconds?: number;
  app_name?: string;
  app_version?: string;
}

/** 采样点：趋势接口共用的最小结构 */
export interface SeriesPoint {
  at?: string;
  count?: number;
  ms?: number;
}

export interface SeriesPayload<T = SeriesPoint> {
  series?: T[];
  total?: number;
  last_id?: number;
  current_ms?: number;
  avg_ms?: number;
  success_rate?: number;
}

/** 日志 /api/logs */
export interface LogItem {
  id?: number;
  time?: string;
  datetime?: string;
  level?: string;
  module?: string;
  message?: string;
}

export interface LogPayload {
  items?: LogItem[];
  last_id?: number;
  total?: number;
}

/** 插件 /api/plugins */
export type PluginStatus = 'loaded' | 'disabled' | 'error' | 'unloaded' | 'stopped';

export interface Plugin {
  id?: string;
  path?: string;
  name: string;
  version?: string;
  official?: boolean;
  source?: string;
  status: PluginStatus | string;
  enabled?: boolean;
  manageable?: boolean;
  hot_reload?: boolean;
  config_hot_reload?: boolean;
  description?: string;
  author?: string;
  error?: string;
  repo?: string;
  homepage?: string;
  tags?: string[];
  config_section?: string;
}

export interface ProxyInfo {
  mode?: string;
  host?: string;
  port?: number;
  description?: string;
}

export interface PluginListPayload {
  items?: Plugin[];
  console_plugin?: string;
  manage_enabled?: boolean;
  hot_reload?: boolean;
  proxy?: ProxyInfo;
}

/** schema 字段描述（由后端 config_manager.describe_dataclass 生成） */
export type FieldKind = 'scalar' | 'group' | 'list' | 'dict' | 'model_list';

export interface FieldDescriptor {
  name: string;
  path: string[];
  kind: FieldKind;
  /** 读取时的当前值（后端快照，编辑草稿以 values 为准） */
  value?: unknown;
  type?: string;
  default?: unknown;
  description?: string;
  options?: string[];
  options_strict?: boolean;
  readonly?: boolean;
  multi?: boolean;
  min?: number;
  max?: number;
  hot_reload?: boolean;
  partial_hot_reload?: boolean;
  restart_reason?: string;
  /** 后端标记为不在表单里展示 */
  hidden?: boolean;
  fields?: FieldDescriptor[];
  items?: ModelItem[];
  item_fields?: FieldDescriptor[];
  [key: string]: unknown;
}

/** 保存/重载后返回的「已生效 / 需重启」明细 */
export interface ConfigChangeItem {
  path: string;
  reason?: string;
  before?: unknown;
  after?: unknown;
}

export interface ConfigChanges {
  hot_reload?: ConfigChangeItem[];
  needs_restart?: ConfigChangeItem[];
  hot_reload_count?: number;
  needs_restart_count?: number;
  [key: string]: unknown;
}

/** 配置文档（本体 config.toml / 插件配置共用） */
export interface ConfigDocument {
  section?: string;
  path?: string;
  revision?: number;
  form_supported?: boolean;
  source_available?: boolean;
  source?: string;
  config?: Record<string, unknown>;
  schema?: FieldDescriptor[];
  message?: string;
  applied?: boolean;
  /** 校验失败时后端返回的字段级错误 */
  errors?: Array<{ path?: string; message?: string }>;
  /** 重载后返回的生效明细 */
  changes?: ConfigChanges;
  [key: string]: unknown;
}

/** 模型库条目 */
export interface ModelItem {
  key?: string;
  name?: string;
  description?: string;
  provider?: string;
  model_name?: string;
  model_type?: string;
  type_label?: string;
  use_system_proxy?: boolean;
  /** 列表视图附带的状态标记 */
  key_configured?: boolean;
  url_configured?: boolean;
  registered?: boolean;
  assigned?: boolean;
  native_vision?: boolean;
  [key: string]: unknown;
}

export interface ModelProbeResult {
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
}

/** 模型库 /api/config/models */
export interface ModelsPayload {
  library?: ModelItem[];
  entry_schema?: FieldDescriptor[];
  provider_options?: string[];
  model_type_labels?: Record<string, string>;
  role_model_types?: Record<string, string>;
  roles_meta?: Array<{ role: string; label?: string; multi?: boolean; required?: boolean; model_type?: string; model_type_label?: string }>;
  assignments?: {
    roles?: Record<string, string>;
    creator_image_models?: string[];
    [key: string]: unknown;
  };
  revision?: number;
  providers?: string[];
  /** 写配置成功后后端带回的最新模型库视图 */
  models?: ModelItem[];
  /** 模型分配的「当前生效情况」表 */
  roles?: Array<{
    role: string;
    label?: string;
    key?: string;
    provider?: string;
    model_name?: string;
    status?: string;
    missing?: boolean;
    registered?: boolean;
    [k: string]: unknown;
  }>;
  saved_key?: string;
  message?: string;
  applied?: boolean;
  changes?: ConfigChanges;
  [key: string]: unknown;
}

/** 环境变量 /api/config/env */
export interface EnvItem {
  key: string;
  description?: string;
  value?: string;
  has_value?: boolean;
  builtin?: boolean;
  required?: boolean;
  removed?: boolean;
  /** 密钥类变量：只写不读 */
  sensitive?: boolean;
  [key: string]: unknown;
}

export interface EnvPayload {
  items?: EnvItem[];
  path?: string;
  platforms?: Array<{ name?: string; url?: string; has_key?: boolean; builtin?: boolean; [k: string]: unknown }>;
  revision?: number;
  message?: string;
  [key: string]: unknown;
}

/** 用量 /api/stats/usage 与 /api/series/usage */
export interface UsageTotals {
  calls?: number;
  input_tokens?: number;
  output_tokens?: number;
  cost_cny?: number;
}

export interface UsageRow extends UsageTotals {
  module?: string;
  module_name?: string;
  model_name?: string;
  provider_name?: string;
}

export interface UsagePayload {
  available?: boolean;
  error?: string;
  hours?: number;
  bucket?: string;
  totals?: UsageTotals;
  items?: UsageRow[];
  points?: Array<UsageRow & { at?: string }>;
  models?: UsageRow[];
  modules?: UsageRow[];
}

/** 服务 / 任务 */
export interface ServiceItem {
  name: string;
  description?: string;
  available?: boolean;
}

export interface TaskItem {
  task_id?: string;
  id?: string;
  name?: string;
  description?: string;
  kind?: string;
  status?: string;
  pipeline_key?: string;
  next_run?: string;
  trigger_time?: string;
  cron?: string;
}

export interface TasksPayload {
  scheduled?: TaskItem[];
  background?: TaskItem[];
}

/** 排行类 */
export interface RankItem {
  action?: string;
  module?: string;
  count?: number;
}

export interface RankPayload {
  items?: RankItem[];
  total_calls?: number;
  unique_actions?: number;
  tracked_users?: number;
}

export interface ActiveUser {
  user_id: string | number;
  nickname?: string;
  count?: number;
  last_seen?: number;
}
