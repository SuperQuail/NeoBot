// terminals/shared.ts —— 终端共用的格式化与类型（对应面板 /api/* 的响应结构）。

import type { ApiResult } from '../net/api';

export interface OverviewPayload {
  online?: boolean;
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

export interface SystemPayload {
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
  uptime_seconds?: number;
  load_average?: number[];
}

export interface SeriesPoint {
  at?: string;
  count?: number;
  ms?: number;
}

export interface LatencyPayload {
  series?: SeriesPoint[];
  current_ms?: number;
  avg_ms?: number;
  success_rate?: number;
}

export interface MessageSeriesPayload {
  series?: SeriesPoint[];
  days?: number;
}

export interface RankItem {
  name?: string;
  label?: string;
  count?: number;
  value?: number;
  user_id?: string | number;
  nickname?: string;
}

export interface RankPayload {
  items?: RankItem[];
  total?: number;
}

export interface UsageTotals {
  calls?: number;
  input_tokens?: number;
  output_tokens?: number;
  cost_cny?: number;
}

export interface UsagePoint {
  bucket?: string;
  calls?: number;
  input_tokens?: number;
  output_tokens?: number;
  cost_cny?: number;
}

export interface UsagePayload {
  available?: boolean;
  bucket?: string;
  hours?: number;
  currency?: string;
  points?: UsagePoint[];
  models?: Array<Record<string, number | string>>;
  modules?: Array<Record<string, number | string>>;
  items?: Array<{ module?: string; calls?: number; input_tokens?: number; output_tokens?: number; cost_cny?: number }>;
  totals?: UsageTotals;
  error?: string;
}

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

export interface PluginItem {
  id?: string;
  name: string;
  version?: string;
  official?: boolean;
  status?: string;
  enabled?: boolean;
  description?: string;
  author?: string;
  error?: string;
  hot_reload?: boolean;
  config_hot_reload?: boolean;
  dependencies?: string[];
  dependents?: string[];
  dependency_issues?: string[];
  disabled_reason?: string | null;
  auto_disabled?: boolean;
  manageable?: boolean;
}

export interface PluginListPayload {
  items?: PluginItem[];
  manage_enabled?: boolean;
  installer?: boolean;
  console_plugin?: string;
  error?: string;
}

export interface PromptAnalysisItem {
  key?: string;
  name?: string;
  label?: string;
  agent?: string;
  chars?: number;
  tokens?: number;
  estimated_tokens?: number;
  sections?: Array<{ name?: string; chars?: number; tokens?: number }>;
  error?: string;
}

export interface PromptAnalysisPayload {
  items?: PromptAnalysisItem[];
  sources?: PromptAnalysisItem[];
  total_chars?: number;
  total_tokens?: number;
  generated_at?: string;
  [key: string]: unknown;
}

export interface FieldDescriptor {
  name?: string;
  path?: string[];
  kind?: string;
  value?: unknown;
  type?: string;
  default?: unknown;
  description?: string;
  options?: string[];
  readonly?: boolean;
  min?: number;
  max?: number;
  hot_reload?: boolean;
  hidden?: boolean;
  fields?: FieldDescriptor[];
  [key: string]: unknown;
}

export interface ConfigDocument {
  section?: string;
  path?: string;
  revision?: number;
  form_supported?: boolean;
  source_available?: boolean;
  source?: string;
  config?: Record<string, unknown>;
  schema?: FieldDescriptor[];
  can_manage?: boolean;
  secrets_hidden?: boolean;
  message?: string;
  errors?: Array<{ path?: string; message?: string }>;
  [key: string]: unknown;
}

export interface ScoreItem {
  id?: number;
  game?: string;
  score?: number;
  duration_ms?: number;
  player?: string;
  detail?: string;
  created_at?: string;
}

export interface ScorePayload {
  items?: ScoreItem[];
  totals?: Record<string, number>;
  best?: number;
  rank?: number;
  saved?: boolean;
  player?: string;
}

export interface AchievementItem {
  key?: string;
  count?: number;
  detail?: string;
  first_at?: string;
  last_at?: string;
}

export interface PowerPayload {
  ok?: boolean;
  available?: boolean;
  state?: string;
  standby?: boolean;
  reason?: string;
  operator?: string;
  since_text?: string;
  standby_seconds?: number;
  connect_onebot?: boolean;
  message?: string;
}

export interface SimpleMessage {
  ok?: boolean;
  message?: string;
  error?: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// 格式化
// ---------------------------------------------------------------------------

export function pad(value: number, size = 2): string {
  return String(value).padStart(size, '0');
}

export function formatDuration(seconds?: number | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return '—';
  const total = Math.floor(seconds);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (days > 0) return days + ' 天 ' + hours + ' 小时';
  if (hours > 0) return hours + ' 小时 ' + pad(minutes) + ' 分';
  if (minutes > 0) return minutes + ' 分 ' + pad(secs) + ' 秒';
  return secs + ' 秒';
}

export function formatNumber(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return Math.round(value).toLocaleString('zh-CN');
}

export function formatTokens(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—';
  if (value >= 1_000_000) return (value / 1_000_000).toFixed(2) + 'M';
  if (value >= 1000) return (value / 1000).toFixed(1) + 'K';
  return String(Math.round(value));
}

export function formatCost(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—';
  if (value === 0) return '¥0';
  if (value < 0.01) return '¥' + value.toFixed(4);
  if (value < 1) return '¥' + value.toFixed(3);
  return '¥' + value.toFixed(2);
}

export function formatClock(iso?: string | null): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso).slice(11, 19) || '—';
  return pad(date.getHours()) + ':' + pad(date.getMinutes()) + ':' + pad(date.getSeconds());
}

export function failMessage(result: ApiResult<unknown>): string {
  if (result.status === 401) return '面板会话已失效，请回到控制台重新登录';
  return result.error || '请求失败';
}

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
