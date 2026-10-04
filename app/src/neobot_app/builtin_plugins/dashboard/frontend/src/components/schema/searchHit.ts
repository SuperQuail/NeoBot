// searchHit.ts —— 配置面板搜索命中判定（纯函数，供 Field 与 ConfigTreePanel 共用）
//
// 曾经这里只有一个 matchPath（只比路径），于是出现两类问题：
//   1. 搜「概率」这类只出现在字段**说明**里的词，命中数算出来了、右侧却一行都不渲染；
//   2. 搜群号这类只存在于**数组/字典值**里的内容，完全搜不到。
// 现在统一成「路径 / 说明 / 集合类字段的值」三选一命中，且只有这一处判定。
import type { FieldDescriptor } from '../../api/types';

/** 纯文本包含判定：大小写不敏感，两侧都做 trim。 */
export function matchesText(text: unknown, keyword: string): boolean {
  const needle = String(keyword || '').trim().toLowerCase();
  if (!needle) return true;
  return String(text ?? '').toLowerCase().includes(needle);
}

/**
 * 集合类字段（list/dict）的值要不要参与搜索？
 * 要——chip 里的群号、键值表里的系数都不在路径与说明里，
 * 不带上它们的话用户根本没法按内容找到这个字段。
 */
function collectionValueText(field: FieldDescriptor): string {
  if (field.kind !== 'list' && field.kind !== 'dict') return '';
  const value = field.value;
  if (value === null || value === undefined) return '';
  if (Array.isArray(value)) return value.map((item) => String(item ?? '')).join(' ');
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => key + ' ' + String(item ?? ''))
      .join(' ');
  }
  return '';
}

/** 字段是否命中关键词：路径 / 说明 / 集合值，任一命中即可。空关键词视为全命中。 */
export function fieldMatches(field: FieldDescriptor, keyword: string): boolean {
  if (!String(keyword || '').trim()) return true;
  return (
    matchesText(field.path.join('.'), keyword) ||
    matchesText(field.description, keyword) ||
    matchesText(collectionValueText(field), keyword)
  );
}

/**
 * 把分组按关键词收拢成「只含命中项」的副本（null = 整条不渲染）。
 *
 * 关键点：分组是因为某个孩子才被留下的，那个孩子的后代必须一起保留，
 * 否则用户会看到一个标题在、里面什么都没有的空壳。
 */
export function gatherField(field: FieldDescriptor, keyword: string): FieldDescriptor | null {
  if (!String(keyword || '').trim()) return field;
  if (field.kind === 'group') {
    const children = (field.fields || [])
      .map((child) => gatherField(child, keyword))
      .filter((child): child is FieldDescriptor => child !== null);
    if (children.length === 0) return fieldMatches(field, keyword) ? field : null;
    return { ...field, fields: children };
  }
  return fieldMatches(field, keyword) ? field : null;
}

/** 统计分组内命中的叶子字段数（空关键词 = 全部叶子数）。 */
export function countLeafHits(fields: FieldDescriptor[] | undefined, keyword: string): number {
  let hits = 0;
  for (const field of fields || []) {
    if (field.kind === 'group') hits += countLeafHits(field.fields, keyword);
    else if (fieldMatches(field, keyword)) hits += 1;
  }
  return hits;
}

/** 分组是否含有命中项（组名/说明自身命中时整组算命中）。 */
export function groupHasHits(field: FieldDescriptor, keyword: string): boolean {
  if (!String(keyword || '').trim()) return true;
  if (fieldMatches(field, keyword)) return true;
  return countLeafHits(field.fields, keyword) > 0;
}
