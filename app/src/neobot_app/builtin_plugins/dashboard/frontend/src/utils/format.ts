// format.ts —— 展示用格式化工具

export function fmtUptime(sec?: number | null): string {
  const total = Math.floor(sec || 0);
  const d = Math.floor(total / 86400);
  const h = Math.floor((total % 86400) / 3600);
  const m = Math.floor((total % 3600) / 60);
  if (d > 0) return `${d} 天 ${h} 小时`;
  if (h > 0) return `${h} 时 ${m} 分`;
  return m > 0 ? `${m} 分` : '< 1 分';
}

export function fmtNum(n?: number | null): string {
  if (n == null) return '—';
  return Number(n).toLocaleString('en-US');
}

export function fmt1(n?: number | null, suf = ''): string {
  if (n == null || !isFinite(n)) return '—';
  return n.toFixed(1) + suf;
}

/** 日志级别 → tag 样式 */
export function mapTag(level?: string | null): 'ok' | 'warn' | 'err' | 'info' {
  const normalized = String(level || '').toLowerCase();
  if (normalized === 'success') return 'ok';
  if (normalized === 'warning') return 'warn';
  if (normalized === 'error' || normalized === 'critical') return 'err';
  return 'info';
}

/** 相对时间（秒级时间戳） */
export function fmtRelTime(ts?: number | null): string {
  if (!ts) return '—';
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}
