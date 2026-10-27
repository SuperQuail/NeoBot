// 提示词模板、分析、聊天流与完整请求历史。

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

/** ── 提示词历史 /api/chat-flows/prompts(|/prompt)（spec(3) 建立，spec(10) 改纯内存） ── */

/** 一份提示词历史的元数据（列表接口只给这个，不含正文） */
export interface ChatFlowPromptMeta {
  seq: number;
  pipeline_key?: string;
  iteration?: number;
  model?: string;
  total_messages?: number;
  /** 重建后的完整篇幅（字节）；仅供面板展示「这一份有多大」 */
  bytes?: number;
  /** 实际驻留的补丁大小（字节）；逐份 diff 后通常只有完整篇幅的零头 */
  patch_bytes?: number;
  /** 该份里被脱敏成 sha256 的图片引用数 */
  images?: number;
  recorded_at?: string;
}

export interface ChatFlowPromptsPayload {
  ok?: boolean;
  items?: ChatFlowPromptMeta[];
  /** 本次请求的过滤条件（空串 = 全部聊天流） */
  pipeline_key?: string;
  /** 全局保留份数（= ContextRecorder.limit，默认 100） */
  limit?: number;
  /** 当前实际驻留内存（快照 + 全部补丁），与「每份都存全量」对比用 */
  storage_bytes?: number;
  /** 累计脱敏掉的图片引用处数 */
  image_refs?: number;
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
  /** 当前实际驻留内存（快照 + 全部补丁） */
  storage_bytes?: number;
  /** 累计脱敏掉的图片引用处数 */
  image_refs?: number;
  /** 最新一份的 seq；没有任何历史时为 null */
  seq: number | null;
  entry: ChatFlowPromptEntry | null;
}
