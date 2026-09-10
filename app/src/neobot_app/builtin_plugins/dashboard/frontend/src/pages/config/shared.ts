// pages/config/shared.ts —— 配置管理各面板共用的小工具与类型
import type { FieldDescriptor } from '../../api/types';

export interface Leaf {
  path: string[];
  value: unknown;
}

export function collectLeaves(value: unknown, path: string[] = [], out: Leaf[] = []): Leaf[] {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const key of Object.keys(value as Record<string, unknown>)) {
      collectLeaves((value as Record<string, unknown>)[key], [...path, key], out);
    }
  } else {
    out.push({ path, value });
  }
  return out;
}

/** 一次字段修改记录（撤销/重做栈元素） */
export interface ChangeEntry {
  path: string[];
  before: unknown;
  after: unknown;
}

/** 字段历史：路径 -> 历史值列表 */
export type HistoryMap = Record<string, Array<{ value: unknown; at: string }>>;

export interface Notice {
  text: string;
  warning?: boolean;
}

/** 模型分配草稿：后端返回的是「角色 -> 模型 key」的映射，生图角色为多选数组 */
export interface AssignDraft extends Record<string, any> {
  creator_image_models?: string[];
}

/** 比较一次分组修改，找出真正变化的叶子配置项（用于逐项历史）。 */
export function changedLeaves(before: unknown, after: unknown, basePath: string[]): ChangeEntry[] {
  const beforeMap = new Map(collectLeaves(before).map((item) => [item.path.join('.'), item.value]));
  const changes: ChangeEntry[] = [];
  for (const item of collectLeaves(after)) {
    const key = item.path.join('.');
    if (JSON.stringify(beforeMap.get(key) ?? null) === JSON.stringify(item.value ?? null)) continue;
    changes.push({ path: [...basePath, ...item.path], before: beforeMap.get(key), after: item.value });
  }
  return changes;
}

/** 把草稿值绑定到后端 schema 的描述符上（表单只认描述符上的 value）。 */
export function bindValues(fields: FieldDescriptor[], values?: Record<string, any>): FieldDescriptor[] {
  return (fields || []).map((field) => {
    const value = values ? values[field.name] : undefined;
    if (field.kind === 'group') {
      const nested = value && typeof value === 'object' ? value : {};
      return { ...field, value: nested, fields: bindValues(field.fields || [], nested) };
    }
    return { ...field, value: value === undefined ? field.value : value };
  });
}