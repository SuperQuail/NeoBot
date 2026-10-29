// Weekly wall-clock intervals; weekdays identify the day the window starts.
export interface ScheduleWindow {
  weekdays: number[];
  start: string;
  end: string;
  next_day?: boolean;
  [key: string]: unknown;
}
export interface ScheduleOverride {
  kind: 'group' | 'private';
  id: string;
  windows?: ScheduleWindow[];
  [key: string]: unknown;
}
export const weekdays = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
export const newWindow = (): ScheduleWindow => ({
  weekdays: [1, 2, 3, 4, 5, 6, 7],
  start: '08:00',
  end: '22:00',
  next_day: false,
});
export function minutes(value: string): number {
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(value)) return NaN;
  const [hour, minute] = value.split(':').map(Number);
  return hour * 60 + minute;
}
export function time(value: number): string {
  const bounded = Math.max(0, Math.min(1439, value));
  return `${String(Math.floor(bounded / 60)).padStart(2, '0')}:${String(bounded % 60).padStart(2, '0')}`;
}
const object = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);
export function windowShape(value: unknown): value is ScheduleWindow {
  return (
    object(value) &&
    Array.isArray(value.weekdays) &&
    value.weekdays.every((day) => typeof day === 'number') &&
    typeof value.start === 'string' &&
    typeof value.end === 'string' &&
    (value.next_day === undefined || typeof value.next_day === 'boolean')
  );
}
export function overrideShape(value: unknown): value is ScheduleOverride {
  return (
    object(value) &&
    (value.kind === 'group' || value.kind === 'private') &&
    typeof value.id === 'string' &&
    (value.windows === undefined || (Array.isArray(value.windows) && value.windows.every(windowShape)))
  );
}
export function windowErrors(values: unknown, label: string): string[] {
  if (!Array.isArray(values)) return [`${label}：窗口必须是数组，请在 TOML 中修正。`];
  const errors: string[] = [];
  const intervals: { start: number; end: number; index: number }[] = [];
  values.forEach((value, index) => {
    const name = `${label}窗口 ${index + 1}`;
    if (!windowShape(value)) {
      errors.push(`${name}：窗口字段格式错误，请在 TOML 中修正。`);
      return;
    }
    const days = value.weekdays;
    if (
      !days.length ||
      days.some((day) => !Number.isInteger(day) || day < 1 || day > 7) ||
      new Set(days).size !== days.length
    )
      errors.push(`${name}：请选择不重复的星期（周一至周日）。`);
    const start = minutes(value.start),
      end = minutes(value.end);
    if (!Number.isFinite(start) || !Number.isFinite(end)) {
      errors.push(`${name}：时间必须为 HH:MM。`);
      return;
    }
    const duration = end + (value.next_day ? 1440 : 0) - start;
    if (duration <= 0 || duration >= 1440) {
      errors.push(`${name}：时长必须大于 0 且小于 24 小时，请检查次日选项。`);
      return;
    }
    days.forEach((day) => {
      const begin = (day - 1) * 1440 + start;
      // Duplicate a week to detect Sunday -> Monday intersections.
      [0, 10080].forEach((offset) =>
        intervals.push({ start: begin + offset, end: begin + duration + offset, index }),
      );
    });
  });
  intervals.sort((a, b) => a.start - b.start);
  if (intervals.some((item, i) => i > 0 && item.start < intervals[i - 1].end))
    errors.push(`${label}：窗口重叠（包括跨夜与周日到周一），请调整星期或时间。`);
  return errors;
}
export function scheduleErrors(value: Record<string, unknown>): string[] {
  const errors: string[] = [];
  try {
    if (typeof value.timezone !== 'string' || !value.timezone.trim()) throw new Error();
    new Intl.DateTimeFormat('en', { timeZone: value.timezone }).format();
  } catch {
    errors.push('时区无效，请填写 IANA 时区，例如 Asia/Shanghai。');
  }
  errors.push(...windowErrors(value.windows ?? [], '默认'));
  if (!Array.isArray(value.overrides ?? [])) return [...errors, '覆盖范围必须是数组，请在 TOML 中修正。'];
  const keys = new Set<string>();
  (value.overrides as unknown[] | undefined)?.forEach((scope, index) => {
    if (!overrideShape(scope)) {
      errors.push(`覆盖范围 ${index + 1}：字段格式错误，请在 TOML 中修正。`);
      return;
    }
    if (!scope.id.trim()) errors.push(`覆盖范围 ${index + 1}：会话 ID 不能为空。`);
    const key = JSON.stringify([scope.kind, scope.id]);
    if (keys.has(key)) errors.push(`覆盖范围 ${index + 1}：类型与会话 ID 重复。`);
    keys.add(key);
    errors.push(...windowErrors(scope.windows ?? [], `覆盖 ${index + 1}`));
  });
  return errors;
}
