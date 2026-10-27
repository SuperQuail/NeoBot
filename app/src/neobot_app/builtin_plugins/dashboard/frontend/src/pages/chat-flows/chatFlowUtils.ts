import type { ChatFlowLatestPrompt } from '../../api/types';

export function formatAge(seconds?: number | null): string {
  if (seconds === undefined || seconds === null) return '—';
  if (seconds < 60) return Math.max(0, Math.round(seconds)) + ' 秒前';
  if (seconds < 3600) return Math.round(seconds / 60) + ' 分钟前';
  return Math.round(seconds / 3600) + ' 小时前';
}

export function formatTime(value?: string | null): string {
  if (!value) return '—';
  return value.replace('T', ' ').slice(0, 19);
}

export function formatBytes(value?: number): string {
  const bytes = Number(value || 0);
  if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
  if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return bytes + ' B';
}

export function roleLabel(role?: string): string {
  switch (role) {
    case 'system':
      return 'system';
    case 'user':
      return 'user';
    case 'assistant':
      return 'assistant';
    case 'tool':
      return 'tool';
    default:
      return role || '未知';
  }
}

/**
 * 轮询每次都返回新对象，但只要「最新那一份 + 列表规模」没变就沿用旧对象，
 * 让 PromptEntryView 的 memo 真正生效（否则每 5s 整份提示词重渲染一次）。
 */
export function samePromptPayload(a: ChatFlowLatestPrompt, b: ChatFlowLatestPrompt): boolean {
  return (
    // seq 全局唯一（清空后也继续递增），相同即同一份记录，正文必然一致
    a.seq === b.seq &&
    (a.items || []).length === (b.items || []).length &&
    a.limit === b.limit &&
    a.storage_bytes === b.storage_bytes &&
    a.image_refs === b.image_refs
  );
}
