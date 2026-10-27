// 档案读写、AI 压缩与历史快照。

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
  /** 档案总结服务是否可用（false 时禁用「AI 压缩」入口） */
  summarize_available?: boolean;
  /** 手动压缩目标的下限 / 上限（上限 = max_total_chars，0 时取后端兜底值） */
  min_target_chars?: number;
  max_target_chars?: number;
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

/** 一次 AI 压缩任务 / 批量的状态（spec(4) Part C） */
export interface ArchiveSummarizeBatchItem {
  table: string;
  key: string;
  chars_before?: number;
  chars_after?: number | null;
  status?: 'pending' | 'running' | 'done' | 'failed' | 'skipped';
  error?: string;
  snapshot_id?: number | null;
}

export interface ArchiveSummarizeTask {
  ok?: boolean;
  task_id?: string | null;
  kind?: 'single' | 'batch';
  /** running / done / failed；noop = 目标不小于当前字数（零 token，不调用模型） */
  status?: 'running' | 'done' | 'failed' | 'noop';
  table?: string;
  key?: string;
  target_chars?: number;
  chars_before?: number;
  chars_after?: number | null;
  snapshot_id?: number | null;
  error?: string;
  operator_ip?: string;
  started_at?: number | null;
  finished_at?: number | null;
  message?: string;
  noop?: boolean;
  /** 批量：超出 MAX_BATCH_COMPRESS_ITEMS 而未处理的条数 */
  truncated?: number;
  /** 批量：逐条结果 */
  items?: ArchiveSummarizeBatchItem[];
  /** 批量：被跳过的条目（chars <= target 或正在被压缩） */
  skipped?: { table: string; key: string; reason?: string }[];
  succeeded?: number;
  failed?: number;
}

/** 压缩历史里的一份快照（列表不含全文） */
export interface ArchiveSnapshot {
  id: number;
  table_name: string;
  key: string;
  total_chars?: number;
  version?: number;
  /** manual（面板 / 批量）| auto（写超限自动压缩） */
  reason?: string;
  operator_ip?: string | null;
  created_at?: string;
  chars_before?: number | null;
  chars_after?: number | null;
  /** 压缩后字数的来源：该档案当前字数 / 后一份快照的压缩前字数 */
  chars_after_source?: 'current' | 'next_snapshot';
}

export interface ArchiveSnapshotsPayload {
  ok?: boolean;
  items?: ArchiveSnapshot[];
  table?: string;
  key?: string;
  current_chars?: number | null;
  keep_per_key?: number;
  /** 恒为 false：本期不提供「恢复到此快照」 */
  restore_supported?: boolean;
  error?: string;
}

export interface ArchiveSnapshotDetail {
  ok?: boolean;
  snapshot?: ArchiveSnapshot & { value?: string };
  error?: string;
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
