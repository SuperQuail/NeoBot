// 模型库、角色分配、连通性探测与计费。
import type { ConfigChanges, FieldDescriptor } from './config';

/** 模型库条目。model_ref 只是本机引用名，model_name 才是发给供应商的模型名 */
export interface ModelItem {
  model_ref?: string;
  name?: string;
  display_name?: string;
  provider?: string;
  model_name?: string;
  model_type?: string;
  type_label?: string;
  use_system_proxy?: boolean;
  /** 列表视图附带的状态标记（供应商 API Key 是否已配置，与引用名无关） */
  api_key_configured?: boolean;
  url_configured?: boolean;
  registered?: boolean;
  assigned?: boolean;
  native_vision?: boolean;
  /** 顶层推理强度原始值（claude: 前缀表示 Claude 系档位） */
  reasoning_effort?: string;
  /** 推理强度展示文案（后端生成；Claude 系带「Claude 系 ·」，空串 = 未设置） */
  reasoning_effort_label?: string;
  [key: string]: unknown;
}

export interface ModelProbeResult {
  ok?: boolean;
  model_ref?: string;
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

/** 模型视图：模型库 + 分配 + 角色 + 表单描述（后端 models_view() 的返回） */
export interface ModelsView {
  library?: ModelItem[];
  assignments?: {
    roles?: Record<string, string>;
    creator_image_models?: string[];
    [key: string]: unknown;
  };
  roles?: Array<{
    role: string;
    label?: string;
    model_ref?: string;
    display_name?: string;
    provider?: string;
    model_name?: string;
    status?: string;
    missing?: boolean;
    registered?: boolean;
    [k: string]: unknown;
  }>;
  roles_meta?: Array<{
    role: string;
    label?: string;
    multi?: boolean;
    required?: boolean;
    model_type?: string;
    model_type_label?: string;
  }>;
  entry_schema?: FieldDescriptor[];
  provider_options?: string[];
  model_name_options?: string[];
  model_type_labels?: Record<string, string>;
  role_model_types?: Record<string, string>;
  platforms?: Array<{
    name?: string;
    url?: string;
    has_key?: boolean;
    builtin?: boolean;
    [k: string]: unknown;
  }>;
  [key: string]: unknown;
}

/** 模型库 /api/config/models */
export interface ModelsPayload extends ModelsView {
  library?: ModelItem[];
  revision?: string;
  providers?: string[];
  /** 写配置成功后后端带回的最新**模型视图对象**（不是数组，取 .library 才是条目列表） */
  models?: ModelsView;
  saved_model_ref?: string;
  message?: string;
  applied?: boolean;
  changes?: ConfigChanges;
  /**
   * 模型/凭据变更后**仍需重启进程**才会用新模型的部分（issue #75）。
   * 分类表把 `models` 整体标成可热重载，所以 `changes.needs_restart_count` 常为 0；
   * 这份清单才是完整的「哪些没热更到」。
   */
  needs_restart_parts?: string[];
  [key: string]: unknown;
}

/** 计费（spec(4) Part A）：/api/config/billing */
export interface BillingScriptBinding {
  model_key: string;
  billing_script?: string;
  billing_config?: Record<string, unknown>;
  source?: string;
  available?: boolean;
  error?: string;
  loaded_at?: string;
  last_eval_ms?: number;
  eval_count?: number;
  [k: string]: unknown;
}

export interface BillingScriptStatus {
  name?: string;
  path?: string;
  ok?: boolean;
  error?: string;
  loaded_at?: string;
  elapsed_ms?: number;
  reload_count?: number;
  last_eval_ms?: number;
  last_source?: string;
  eval_count?: number;
  fallback_count?: number;
  [k: string]: unknown;
}

export interface BillingPayload {
  available?: boolean;
  enabled?: boolean;
  timeout_ms?: number;
  reload_on_change?: boolean;
  record_detail?: boolean;
  directory?: string;
  scripts?: string[];
  templates?: string[];
  policies?: Record<string, BillingScriptStatus>;
  bindings?: BillingScriptBinding[];
  errors?: Record<string, string>;
  reloaded?: string[];
  results?: Record<string, { ok?: boolean; error?: string; path?: string }>;
  [k: string]: unknown;
}

export interface BillingPreviewResult {
  ok?: boolean;
  cost_cny?: number;
  builtin_cost_cny?: number;
  source?: string;
  components?: Record<string, number>;
  note?: string;
  elapsed_ms?: number;
  error?: string;
  model_key?: string;
  billing_script?: string;
  billing_config?: Record<string, unknown>;
  enabled?: boolean;
  occurred_at?: string;
  local_time?: string;
  tzname?: string;
  message?: string;
  [k: string]: unknown;
}
