import { deserialize, serialize } from 'node:v8';

export const SCENARIOS = new Set(['default', 'long', 'empty', 'readonly']);
export const clone = (value) => deserialize(serialize(value));
export const now = () => new Date().toISOString();
export const longText = '这是完全虚构的长中文演示内容，用于检查窄屏换行、字段宽度、滚动与信息层级。'.repeat(
  12,
);
export const longUrl = 'https://example.invalid/preview/' + 'very-long-path-segment/'.repeat(12);
export const created = '2026-10-25T09:30:00';

/** Scenario switches preserve the current in-memory edits. */
export function createScenario(initial = 'default') {
  if (!SCENARIOS.has(initial)) throw new Error('未知演示场景');
  let name = initial;
  return {
    get name() {
      return name;
    },
    empty: () => name === 'empty',
    canManage: () => name !== 'readonly',
    label: (normal) => (name === 'long' ? normal + ' · ' + longText.slice(0, 96) : normal),
    set(next) {
      if (!SCENARIOS.has(next)) return false;
      name = next;
      return true;
    },
  };
}
