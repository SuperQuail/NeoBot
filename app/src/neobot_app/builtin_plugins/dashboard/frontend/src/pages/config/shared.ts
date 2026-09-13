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

/** 模型的 scope 上下文（provider / model_type）：随分组递归向下传递。 */
export interface FieldContext {
  provider?: unknown;
  model_type?: unknown;
}

/** kind=model_params 伪字段的可编辑载荷（spec(4) Part B）。 */
export interface ModelParamsDraft {
  enabled_params: string[];
  extra_body: Record<string, unknown>;
  values: Record<string, unknown>;
}

/** 由描述符 + 所在 settings 草稿对象拼出伪字段的 value（含各可选参数当前值）。 */
function modelParamsValue(field: FieldDescriptor, source: Record<string, any>): ModelParamsDraft {
  const catalog = Array.isArray(field.catalog) ? (field.catalog as Array<{ name?: unknown }>) : [];
  const enabled = Array.isArray(source.enabled_params)
    ? (source.enabled_params as unknown[]).map(String)
    : Array.isArray(field.enabled_params)
      ? (field.enabled_params as unknown[]).map(String)
      : [];
  const extra =
    source.extra_body && typeof source.extra_body === 'object'
      ? (source.extra_body as Record<string, unknown>)
      : field.extra_body && typeof field.extra_body === 'object'
        ? (field.extra_body as Record<string, unknown>)
        : {};
  const values: Record<string, unknown> = {};
  for (const entry of catalog) {
    const name = String(entry?.name ?? '');
    // 只带上草稿里真实存在的参数值；缺失的由组件回落到目录默认值
    if (name && source[name] !== undefined) values[name] = source[name];
  }
  return { enabled_params: enabled, extra_body: extra, values };
}

/** 把草稿值绑定到后端 schema 的描述符上（表单只认描述符上的 value）。 */
export function bindValues(
  fields: FieldDescriptor[],
  values?: Record<string, any>,
  context: FieldContext = {},
): FieldDescriptor[] {
  return (fields || []).map((field) => {
    const value = values ? values[field.name] : undefined;
    if (field.kind === 'group') {
      const nested = value && typeof value === 'object' ? value : {};
      const nextContext: FieldContext = {
        provider: (values && values.provider) ?? context.provider,
        model_type: (values && values.model_type) ?? context.model_type,
      };
      return { ...field, value: nested, fields: bindValues(field.fields || [], nested, nextContext) };
    }
    if (field.kind === 'model_params') {
      // 伪字段：值来自 settings 草稿（enabled_params / extra_body / 各可选参数值），
      // provider / model_type 来自同层条目（下拉候选按 scope 动态过滤）。
      const source = value && typeof value === 'object' ? (value as Record<string, any>) : {};
      return {
        ...field,
        value: modelParamsValue(field, source),
        provider: context.provider ?? field.provider,
        model_type: context.model_type ?? field.model_type,
      };
    }
    return { ...field, value: value === undefined ? field.value : value };
  });
}