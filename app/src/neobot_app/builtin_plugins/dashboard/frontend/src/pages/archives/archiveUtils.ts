/** 每页条目数（后端上限 200） */
export const PAGE_SIZE = 50;

/** 面板删除开关名（与模型侧的 agent.memory.archive.allow_delete 完全独立） */
export const DELETE_SWITCH = 'allow_archive_delete';

/** 批量条目状态 → 中文（与后端 ArchiveSummarizeBatchItem.status 对齐） */
export const BATCH_STATUS_TEXT: Record<string, string> = {
  pending: '等待中',
  running: '压缩中',
  done: '已完成',
  failed: '失败（已保留原文）',
  skipped: '已跳过',
};

export function formatTime(value?: string | null): string {
  if (!value) return '—';
  return value.replace('T', ' ').slice(0, 19);
}

export function formatListTime(value?: string | null): string {
  const full = formatTime(value);
  return /^\d{4}-\d{2}-\d{2}/.test(full) ? full.slice(5, 16) : full;
}

/** tags 输入框（逗号分隔）→ 数组 */
export function parseTags(value: string): string[] {
  return value
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}

export function tagText(tags?: string[]): string {
  return (tags || []).length > 0 ? (tags || []).join(', ') : '—';
}
