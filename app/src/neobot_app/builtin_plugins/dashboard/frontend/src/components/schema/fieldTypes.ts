// components/schema/fieldTypes.ts —— 字段描述驱动的表单：类型契约与无副作用工具
// 由 SchemaForm 及其子组件共用；这里只放类型与纯函数，不放组件。
import type { FieldDescriptor } from '../../api/types';
import { setPath } from '../../utils/paths';

/** 字段值允许的类型（后端 schema 表达力所限，无法更精确） */
export type FieldValue = any;

/** 通用字段回调集合：各 Field* 组件共用 */
export interface FieldCallbacks {
  /** 字段当前值（后端快照；编辑草稿由父级 values 维护） */
  value?: FieldValue;
  onChange: (value: FieldValue) => void;
  disabled?: boolean;
  changed?: boolean;
  onRestore?: (path: FieldDescriptor['path'], value: FieldValue) => void;
  onShowHistory?: (descriptor: FieldDescriptor) => void;
  historyCount?: number;
  filter?: string;
}

export interface FieldProps extends FieldCallbacks {
  descriptor: FieldDescriptor;
  /** 外层工作区已呈现根分区头时，仅省略这一层标题与说明。 */
  hideGroupHeader?: boolean;
  /** 父级（ConfigTreePanel）已经按关键词筛过字段：这里不再二次过滤，只做高亮 */
  globallyFiltered?: boolean;
  changedPaths?: Set<string>;
  history?: Record<string, Array<{ value: unknown; at: string }>>;
  collapse?: Record<string, boolean>;
  onToggleCollapse?: (key: string) => void;
}

export interface SchemaFormProps {
  fields?: FieldDescriptor[];
  /** 插件配置使用插件自身的重载声明，不采用通用字段元数据汇总。 */
  showReloadSummary?: boolean;
  /** 分区导航已呈现根分区元信息；子组仍保留自己的标题。 */
  hideRootGroupHeader?: boolean;
  values?: Record<string, FieldValue>;
  onChange: (path: FieldDescriptor['path'], value: FieldValue) => void;
  disabled?: boolean;
  filter?: string;
  /** 字段已由父级筛好：只高亮命中，不再逐字段过滤 */
  globallyFiltered?: boolean;
  baseline?: Record<string, FieldValue>;
  history?: Record<string, Array<{ value: unknown; at: string }>>;
  onRestore?: (path: FieldDescriptor['path'], value: FieldValue) => void;
  onToggleCollapse?: (key: string) => void;
  collapse?: Record<string, boolean>;
}

/** 密钥类字段名：渲染成密码框并给「显示/隐藏」按钮 */
export const SECRET_RE = /token|password|secret|api[_-]?key|access[_-]?key|credential|authorization|cookie/i;

export function defaultsFromFields(
  fields: FieldDescriptor[] = [],
  parentPath: FieldDescriptor['path'] = [],
): Record<string, FieldValue> {
  let value: Record<string, FieldValue> = {};
  for (const field of fields) {
    let initial: FieldValue;
    if (field.kind === 'group') initial = defaultsFromFields(field.fields, field.path);
    else if (field.kind === 'model_list' || field.kind === 'list') initial = [];
    else if (field.kind === 'dict') initial = {};
    else {
      const fallback =
        field.type === 'bool' ? false : field.type === 'int' || field.type === 'float' ? 0 : '';
      // 后端掩码会把密钥残留成空串：数值/布尔字段回落到类型默认值
      initial = field.default === '' ? fallback : (field.default ?? fallback);
    }
    value = setPath(value, field.path.slice(parentPath.length), initial);
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
