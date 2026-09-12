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
  /** 是否处于待机状态（原 frozen 字段） */
  standby?: boolean;
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
  /** 配置校验告警：非空表示已存值非法、运行时已回落默认值 */
  config_error?: string | null;
  repo?: string;
  homepage?: string;
  tags?: string[];
  /** 依赖声明（可能带版本约束，如 dashboard>=1.0.0） */
  dependencies?: string[];
  /** 当前未满足的依赖说明（缺失 / 未就绪 / 版本不符） */
  dependency_issues?: string[];
  /** 依赖本插件的其他插件（停用 / 卸载时会联动处理） */
  dependents?: string[];
  /** 因前置插件未满足而自动禁用的原因 */
  disabled_reason?: string | null;
  /** 是否属于依赖自动禁用（区别于用户手动停用） */
  auto_disabled?: boolean;
}

/** 面板 HTTP 扩展 /api/extensions：依赖面板的插件挂在同一端口上的页面 */
export interface ExtensionEntry {
  name?: string;
  prefixes?: string[];
  auth_prefixes?: string[];
  panel?: {
    title?: string;
    path?: string;
    icon?: string;
    description?: string;
  } | null;
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

/** 提示词分析 /api/analysis/prompts —— 单个来源（系统提示词 / 工具定义 / 历史 …）的统计 */
export interface PromptPartReport {
  label: string;
  kind: string;
  chars?: number;
  tokens?: number;
  /** 文本过长被后端截断展示（统计仍按全文计算） */
  truncated?: boolean;
  /** 具体提示词文本，可能缺省 */
  text?: string;
}

/** 一个 Agent 装配出的完整提示词报告；装配失败时带 error、parts 为空、合计为 0 */
export interface AgentPromptReport {
  name: string;
  kind?: string;
  note?: string;
  model?: string;
  total_chars?: number;
  total_tokens?: number;
  parts?: PromptPartReport[];
  error?: string;
}

export interface PromptAnalysisPayload {
  ok?: boolean;
  /** 分析器未注入时为 false */
  available?: boolean;
  /** 估算口径说明（页面直接展示，不在前端硬编码） */
  rule?: string;
  generated_at?: number;
  agents?: AgentPromptReport[];
  error?: string;
}

/** 提示词模板 /api/prompts —— 一个可编辑键（template 可预览渲染，text 为纯文本） */
export interface PromptKeyView {
  /** 键路径：template 或 runtime.template */
  path: string;
  label: string;
  kind: 'template' | 'text';
  /** 当前生效值（自定义优先，其次默认） */
  value: string;
  /** 内置默认值（用于「恢复默认」差异展示） */
  default: string | null;
  /** 自定义文件里的值；为 null 表示未覆盖 */
  custom: string | null;
  overridden: boolean;
  /** 模板里出现的占位符名 */
  placeholders: string[];
}

export interface PromptSectionView {
  name: string;
  keys: PromptKeyView[];
  /** 分区内的 enabled 开关（未写时为 null） */
  enabled?: boolean | null;
  customized?: boolean;
}

export interface PromptsPayload {
  sections?: PromptSectionView[];
  default_file?: string;
  custom_file?: string;
  /** 当前会话是否有管理权限（决定能否保存） */
  editable?: boolean;
}

/** 提示词预览 /api/prompts/preview */
export interface PromptPreviewPayload {
  rendered?: string;
  placeholders?: string[];
  /** 渲染后仍未替换的占位符（说明取值缺失） */
  unresolved?: string[];
  /** 各占位符使用的模拟取值 */
  values?: Record<string, string>;
}

/** 聊天流 /api/chat-flows */
export interface ChatFlowItem {
  pipeline_key: string;
  /** 可读名称（群名 / 昵称）；后端解析失败时回落 pipeline_key，前端不要自己拼 */
  display_name?: string;
  conversation_kind?: string;
  conversation_id?: string;
  model?: string;
  active?: boolean;
  iterations?: number;
  /** 快照里保留的消息条数 */
  message_count?: number;
  /** 本次请求实际发出的消息总数 */
  total_messages?: number;
  prompt_chars?: number;
  updated_at?: number;
  age_seconds?: number | null;
  stale?: boolean;
}

export interface ChatFlowsPayload {
  ok?: boolean;
  items?: ChatFlowItem[];
  error?: string;
}

export interface ChatFlowMessage {
  role?: string;
  content?: string;
  truncated?: boolean;
  chars?: number;
  images?: number;
  tool_call_id?: string;
  tool_calls?: Array<{ id?: string; name?: string; arguments?: string }>;
}

/** 聊天流详情：比列表多出最近一次请求的完整内容 */
export interface ChatFlowDetailPayload extends ChatFlowItem {
  system_prompt?: string;
  /** 最近一次模型请求的消息（已截断，仅保留最近若干条） */
  messages?: ChatFlowMessage[];
  background_tasks?: Record<string, unknown>;
}

/** 定时任务 /api/scheduled-tasks */
export interface ScheduledTaskItem {
  task_id: string;
  title: string;
  detail?: string;
  recurrence: string;
  state: string;
  enabled: boolean;
  start_at?: string;
  end_at?: string;
  /** datetime-local 输入框需要的本地时间串 */
  start_at_local?: string;
  end_at_local?: string;
  next_run?: string;
  bindings?: Array<{ kind: string; id: string }>;
  metadata?: Record<string, unknown>;
  one_shot_notification?: boolean;
  completed_windows?: number;
  created_at?: string;
  updated_at?: string;
  version?: number;
}

export interface ScheduledTasksPayload {
  ok?: boolean;
  available?: boolean;
  tasks?: ScheduledTaskItem[];
  editable?: boolean;
  error?: string | null;
}

/** 定时任务写操作 /api/scheduled-tasks/action（action 必填，其余按动作透传） */
export interface ScheduledTaskActionBody {
  action: 'create' | 'update' | 'set_state' | 'set_notification_policy' | 'delete';
  task_uuid?: string;
  title?: string;
  detail?: string;
  recurrence?: string;
  start_at?: string;
  end_at?: string;
  bindings?: Array<{ kind: string; id: string }>;
  metadata?: Record<string, unknown>;
  one_shot_notification?: boolean;
  state?: 'active' | 'disabled';
}

/** ── 完整提示词历史 /api/chat-flows/prompts(|/prompt)（features/spec(3)） ── */

/** 一份落盘提示词的元数据（列表接口只给这个，不含正文） */
export interface ChatFlowPromptMeta {
  seq: number;
  /** 落盘文件的绝对路径（<DATA_DIR>/chat_flows/prompts/ctx_*.json） */
  path?: string;
  pipeline_key?: string;
  iteration?: number;
  model?: string;
  total_messages?: number;
  bytes?: number;
  recorded_at?: string;
}

export interface ChatFlowPromptsPayload {
  ok?: boolean;
  items?: ChatFlowPromptMeta[];
  /** 本次请求的过滤条件（空串 = 全部聊天流） */
  pipeline_key?: string;
  /** 全局保留份数（= ContextRecorder.max_files，默认 100） */
  limit?: number;
  error?: string;
}

/** 一份**完整的模型请求**：messages / response / usage 原样返回，前端不得截断 */
export interface ChatFlowPromptEntry {
  recorded_at?: string;
  stage?: string;
  event_id?: string;
  mode?: string;
  conversation_kind?: string;
  conversation_id?: string;
  pipeline_key?: string;
  /** 本次请求使用的模型名 */
  model?: string;
  iteration?: number;
  messages_count?: number;
  total_chars?: number;
  estimated_tokens?: number;
  output_chars?: number;
  usage?: Record<string, unknown> | null;
  messages?: Array<Record<string, unknown>>;
  response?: Record<string, unknown> | null;
  [key: string]: unknown;
}

export interface ChatFlowPromptPayload {
  ok?: boolean;
  seq?: number;
  entry?: ChatFlowPromptEntry | null;
  error?: string;
}

/** endpoints.chatFlowPromptLatest 的组合结果：元数据列表 + 最新一份全文 */
export interface ChatFlowLatestPrompt {
  items: ChatFlowPromptMeta[];
  /** 全局保留份数 */
  limit: number;
  /** 最新一份的 seq；没有任何历史时为 null */
  seq: number | null;
  entry: ChatFlowPromptEntry | null;
}

/** ── 档案管理 /api/archives*（features/spec(2)） ── */

/** 左栏表清单的一项 */
export interface ArchiveTable {
  table_name: string;
  count?: number;
  max_value_chars?: number;
  /** 超过存储上限（max_total_chars）的条目数 */
  over_limit_count?: number;
  /** 程序维护的内部表：禁止编辑，删除有额外风险 */
  internal?: boolean;
  /** 后端给该表的一句人话警告（内部表优先） */
  note?: string;
}

export interface ArchivesPayload {
  ok?: boolean;
  items?: ArchiveTable[];
  /** spec(1) 的单条档案存储上限（0 = 不限制） */
  max_total_chars?: number;
  /** 面板删除开关（dashboard 插件配置 allow_archive_delete） */
  delete_enabled?: boolean;
  readonly_reason?: string;
  /** 当前会话是否有管理权限（决定能否编辑 / 删除） */
  can_manage?: boolean;
  error?: string;
}

/** 列表条目摘要：**不含完整 value**（只有 preview 与 total_chars） */
export interface ArchiveItemSummary {
  table_name: string;
  key: string;
  preview?: string;
  preview_truncated?: boolean;
  total_chars?: number;
  tags?: string[];
  version?: number;
  created_at?: string;
  updated_at?: string;
  internal?: boolean;
}

export interface ArchiveItemsPayload {
  ok?: boolean;
  items?: ArchiveItemSummary[];
  table?: string;
  limit?: number;
  offset?: number;
  has_more?: boolean;
  max_total_chars?: number;
  delete_enabled?: boolean;
  can_manage?: boolean;
  error?: string;
}

/** 单条档案详情：返回全文（不截断）+ 可编辑性与警告 */
export interface ArchiveItemDetail extends ArchiveItemSummary {
  value?: string;
  /** 内部表为 false：面板禁止编辑（后端也会拒绝） */
  editable?: boolean;
  note?: string;
  message?: string;
  /** 409 冲突（PUT）时后端带回的**当前**内容，前端据此提示「已被他人修改」 */
  current?: ArchiveItemDetail | null;
  actual_version?: number;
  error?: string;
}

/** 档案列表查询参数（GET /api/archives/items） */
export interface ArchiveItemQuery {
  table: string;
  keyQuery?: string;
  valueQuery?: string;
  tags?: string;
  limit?: number;
  offset?: number;
  overLimitOnly?: boolean;
}

export interface ArchiveUpdateBody {
  table: string;
  key: string;
  value: string;
  tags?: string[];
  /** 乐观锁：必须带上读取时的版本号 */
  version: number;
}

export interface ArchiveDeleteBody {
  table: string;
  key: string;
  version?: number;
}
