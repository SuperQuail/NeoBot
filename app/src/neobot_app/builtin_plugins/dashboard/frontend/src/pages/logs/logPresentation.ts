import type { LogItem } from '../../api/types';

export function logLocation(item: LogItem): string {
  const location = [item.file, item.line]
    .filter((value) => value !== undefined && value !== null && value !== '')
    .join(':');
  return [location, item.function].filter(Boolean).join(' · ');
}

export function logFields(item: LogItem): string {
  return item.fields && Object.keys(item.fields).length ? JSON.stringify(item.fields, null, 2) : '';
}

export function logException(item: LogItem): string {
  if (!item.exception) return '';
  const title = [item.exception.type, item.exception.message].filter(Boolean).join(': ');
  return [title, item.exception.traceback].filter(Boolean).join('\n');
}

export function logSearchText(item: LogItem): string {
  return [item.message, item.module, logLocation(item), logFields(item), logException(item)].join('\n');
}

export function formatLogExport(item: LogItem): string {
  const header = `[${item.datetime || item.time || ''}] [${(item.level || '').toUpperCase()}] [${item.module || '-'}] ${item.message || ''}`;
  const location = logLocation(item);
  const fields = logFields(item);
  const exception = logException(item);
  return [
    header,
    location && `调用位置: ${location}`,
    fields && `结构化字段: ${fields}`,
    exception && `异常详情: ${exception}`,
  ]
    .filter(Boolean)
    .join('\n');
}
