// 模型用量、调用明细与排行。

/** 最近调用明细 /api/stats/usage/records（来源列与分项） */
export interface UsageRecordItem {
  at?: string;
  module?: string;
  model_name?: string;
  provider_name?: string;
  input_tokens?: number;
  output_tokens?: number;
  cache_hit_tokens?: number;
  cache_miss_tokens?: number;
  cost_cny?: number;
  cost_source?: string;
  cost_source_kind?: 'builtin' | 'script' | 'fallback' | string;
  negative?: boolean;
  cost_detail?: { components?: Record<string, number>; note?: string; error?: string; raw?: string } | null;
}

export interface UsageRecordsPayload {
  available?: boolean;
  hours?: number;
  items?: UsageRecordItem[];
  error?: string;
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
