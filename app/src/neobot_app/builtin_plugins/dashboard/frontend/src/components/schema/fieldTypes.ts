// components/schema/fieldTypes.ts —— 字段描述驱动的表单：类型契约与无副作用工具
// 由 SchemaForm 及其子组件共用；这里只放类型与纯函数，不放组件。
import type { FieldDescriptor } from '../../api/types';

/** 字段值允许的类型（后端 schema 表达力所限，无法更精确） */
export type FieldValue = any;

/** 通用字段回调集合：各 Field* 组件共用 */
export interface FieldCallbacks {
  /** 字段当前值（后端快照；编辑草稿由父级 values 维护） */
  value?: FieldValue;
  onChange: (value: FieldValue) => void;
  disabled?: boolean;
  changed?: boolean;
  onRestore?: (path: string[], value: FieldValue) => void;
  onShowHistory?: (descriptor: FieldDescriptor) => void;
  historyCount?: number;
  filter?: string;
}

export interface FieldProps extends FieldCallbacks {
  descriptor: FieldDescriptor;
  changedPaths?: Set<string>;
  history?: Record<string, Array<{ value: unknown; at: string }>>;
  collapse?: Record<string, boolean>;
  onToggleCollapse?: (key: string) => void;
}

export interface SchemaFormProps {
  fields?: FieldDescriptor[];
  values?: Record<string, FieldValue>;
  onChange: (path: string[], value: FieldValue) => void;
  disabled?: boolean;
  filter?: string;
  baseline?: Record<string, FieldValue>;
  history?: Record<string, Array<{ value: unknown; at: string }>>;
  onRestore?: (path: string[], value: FieldValue) => void;
  onToggleCollapse?: (key: string) => void;
  collapse?: Record<string, boolean>;
}

/** 密钥类字段名：渲染成密码框并给「显示/隐藏」按钮 */
export const SECRET_RE = /token|password|secret|api[_-]?key|credential|access_key/i;

export function defaultsFromFields(fields: FieldDescriptor[] = []): Record<string, FieldValue> {
  const value: Record<string, FieldValue> = {};
  for (const field of fields) {
    if (field.kind === 'group') value[field.name] = defaultsFromFields(field.fields);
    else if (field.kind === 'model_list') value[field.name] = [];
    else if (field.kind === 'list') value[field.name] = [];
    else if (field.kind === 'dict') value[field.name] = {};
    else value[field.name] = field.default ?? (field.type === 'bool' ? false : field.type === 'int' || field.type === 'float' ? 0 : '');
  }
  return value;
}

export function pathKey(path?: Array<string | number>): string {
  return (path || []).join('.');
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') {
    const text = JSON.stringify(value);
    return text.length > 160 ? text.slice(0, 160) + '…' : text;
  }
  const text = String(value);
  return text.length > 160 ? text.slice(0, 160) + '…' : text;
}
