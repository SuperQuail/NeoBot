// format.js —— 展示用格式化工具(移植自旧 utils.js)

export function fmtUptime(sec) {
  sec = Math.floor(sec || 0);
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return `${d} 天 ${h} 小时`;
  if (h > 0) return `${h} 时 ${m} 分`;
  return m > 0 ? `${m} 分` : '< 1 分';
}

export function fmtNum(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString('en-US');
}

export function fmt1(n, suf = '') {
  if (n == null || !isFinite(n)) return '—';
  return n.toFixed(1) + suf;
}

// 日志级别 → tag 样式
export function mapTag(level) {
  level = String(level || '').toLowerCase();
  if (level === 'success') return 'ok';
  if (level === 'warning') return 'warn';
  if (level === 'error' || level === 'critical') return 'err';
  return 'info';
}

export function fmtRelTime(ts) {
  if (!ts) return '—';
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return '刚刚';
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}
